"""
crawl_scheduled.py ─ 전국 상가 일일 자동 크롤링 (비동기 병렬 버전)

[특징]
  - JWT는 jwt_refresh.py가 자동 갱신 (NID 쿠키 기반, 약 10초)
  - 상세 API를 DETAIL_BATCH건씩 asyncio.gather()로 병렬 호출 (enhancement.md 반영)
  - TokenExpiredError 발생 시 JWT 재갱신 후 해당 지역 재시도
  - DB_UPSERT_EVERY건마다 Supabase에 스트리밍 UPSERT → 중단 시 데이터 보존

[실행]
  python crawl_scheduled.py                # 전국
  python crawl_scheduled.py --sido 경기도  # 특정 시/도만 (테스트용)

[필요 환경변수]
  NAVER_NID_SES, NAVER_NID_AUT  : Naver NID 쿠키 (3~6개월 유효)
  SUPABASE_URL, SUPABASE_KEY    : Supabase 프로젝트 정보
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone

import httpx
from dotenv import load_dotenv

# .env 파일이 있으면 로드 (로컬 개발용).
# 이미 설정된 환경변수(GitHub Actions secrets 등)는 덮어쓰지 않음.
load_dotenv(override=False)

from crawler_core import (
    BASE,
    DTL_ENDPOINT,
    DELAY_LIST,
    REGION_ENDPOINT,
    TokenExpiredError,
    extract_record,
    make_headers,
)
from db import get_last_crawl, insert_crawl_log, upsert_listings
from jwt_refresh import get_fresh_jwt

# ── 병렬 처리 파라미터 ────────────────────────────────────────────────────────
DETAIL_BATCH    = 1     # 동시 상세 요청 수 (429 위험 시 줄이세요)
DELAY_BATCH     = 1.0   # 배치 완료 후 대기 (초)
DB_UPSERT_EVERY = 200   # N건마다 Supabase UPSERT (메모리 관리)

# ── 재시도 파라미터 ──────────────────────────────────────────────────────────
RETRY_MAX       = 5     # 429 발생 시 최대 재시도 횟수
RETRY_BASE_WAIT = 5.0   # 재시도 초기 대기 시간 (초, 지수 백오프)

# ── URL 상수 ─────────────────────────────────────────────────────────────────
_LIST_ENDPOINT = BASE + "/api/articles"


# ════════════════════════════════════════════════════════════════
# 인증 정보 컨테이너 (JWT 갱신 시 전역 업데이트)
# ════════════════════════════════════════════════════════════════

class _Creds:
    jwt:    str = ""
    cookie: str = ""

_creds = _Creds()


async def _refresh_jwt() -> None:
    """
    JWT를 갱신하고 _creds를 업데이트합니다.

    NAVER_JWT 환경변수가 있으면 해당 값을 직접 사용합니다 (CI/CD 권장).
    없으면 NID 쿠키로 Playwright를 통해 자동 추출합니다.
    """
    nid_ses = os.environ["NAVER_NID_SES"]
    nid_aut = os.environ["NAVER_NID_AUT"]
    _creds.cookie = f"NID_SES={nid_ses}; NID_AUT={nid_aut}"

    static_jwt = os.environ.get("NAVER_JWT", "").strip()
    if static_jwt:
        _creds.jwt = static_jwt
        print(f"  → JWT 환경변수에서 로드 ({_creds.jwt[:40]}...)")
    else:
        print("  → JWT 자동 갱신 중 (약 10초)...")
        _creds.jwt = await get_fresh_jwt(nid_ses, nid_aut)
        print(f"  → JWT 갱신 완료 ({_creds.jwt[:40]}...)")


# ════════════════════════════════════════════════════════════════
# 429 재시도 헬퍼
# ════════════════════════════════════════════════════════════════

async def _get_with_retry(client: httpx.AsyncClient, url: str, **kwargs) -> httpx.Response:
    """
    429 Too Many Requests 또는 ReadTimeout 발생 시 지수 백오프로 재시도합니다.
    Retry-After 헤더가 있으면 해당 값을 우선 사용합니다.
    """
    last_exc: Exception | None = None
    for attempt in range(RETRY_MAX + 1):
        try:
            resp = await client.get(url, **kwargs)
        except httpx.ReadTimeout as e:
            last_exc = e
            wait = RETRY_BASE_WAIT * (2 ** attempt)
            print(f"  [Timeout] 응답 없음. {wait:.0f}초 후 재시도 ({attempt + 1}/{RETRY_MAX})...")
            await asyncio.sleep(wait)
            continue

        if resp.status_code != 429:
            return resp

        retry_after = resp.headers.get("Retry-After")
        wait = float(retry_after) if retry_after else RETRY_BASE_WAIT * (2 ** attempt)
        print(f"  [429] 요청 제한. {wait:.0f}초 후 재시도 ({attempt + 1}/{RETRY_MAX})...")
        await asyncio.sleep(wait)

    if last_exc:
        raise last_exc
    # 마지막 시도 결과 반환 (raise_for_status는 호출부에서)
    return resp


# ════════════════════════════════════════════════════════════════
# 비동기 API 요청
# ════════════════════════════════════════════════════════════════

def _build_list_url(cortar_no: str, page: int) -> str:
    return (
        f"{_LIST_ENDPOINT}"
        f"?cortarNo={cortar_no}"
        f"&order=rank&realEstateType=SG&tradeType=A1"
        f"&tag=%3A%3A%3A%3A%3A%3A%3A%3A"
        f"&rentPriceMin=0&rentPriceMax=900000000"
        f"&priceMin=0&priceMax=900000000"
        f"&areaMin=0&areaMax=900000000"
        f"&oldBuildYears&recentlyBuildYears"
        f"&minHouseHoldCount&maxHouseHoldCount"
        f"&showArticle=false&sameAddressGroup=false"
        f"&minMaintenanceCost&maxMaintenanceCost"
        f"&priceType=RETAIL&directions="
        f"&page={page}&articleState"
    )


async def _fetch_regions(
    client: httpx.AsyncClient, cortar_no: str
) -> list[dict]:
    resp = await _get_with_retry(
        client,
        REGION_ENDPOINT,
        params={"cortarNo": cortar_no},
        headers=make_headers(_creds.jwt, _creds.cookie),
    )
    if resp.status_code == 401:
        raise TokenExpiredError()
    resp.raise_for_status()
    return resp.json().get("regionList", [])


async def _fetch_list_page(
    client: httpx.AsyncClient, cortar_no: str, page: int
) -> dict:
    resp = await _get_with_retry(
        client,
        _build_list_url(cortar_no, page),
        headers=make_headers(_creds.jwt, _creds.cookie),
    )
    if resp.status_code == 401:
        raise TokenExpiredError()
    resp.raise_for_status()
    return resp.json()


async def _fetch_detail_safe(
    client: httpx.AsyncClient, article_no: str
) -> dict | None:
    """에러 처리 포함 단일 상세 조회. 401 → TokenExpiredError."""
    try:
        url  = DTL_ENDPOINT.format(no=article_no)
        resp = await _get_with_retry(
            client, url, headers=make_headers(_creds.jwt, _creds.cookie, article_no)
        )
        if resp.status_code == 401:
            raise TokenExpiredError()
        resp.raise_for_status()
        detail = resp.json()
        return detail if "error" not in detail else None
    except TokenExpiredError:
        raise
    except Exception:
        return None


# ════════════════════════════════════════════════════════════════
# 시/군/구 단위 비동기 크롤링
# ════════════════════════════════════════════════════════════════

async def _crawl_sigungu(
    client:       httpx.AsyncClient,
    sido_name:    str,
    sigungu_name: str,
    cortar_no:    str,
) -> list[dict]:
    """
    시/군/구 단위 비동기 크롤링.

    1단계: 목록 API → articleNo 수집 (순차)
    2단계: 상세 API → DETAIL_BATCH건씩 asyncio.gather() 병렬 호출

    수집된 레코드에 sido / sigungu / cortar_no 필드를 추가합니다.
    """
    label = f"{sido_name} {sigungu_name}"

    # ── 1단계: 목록 수집 ────────────────────────────────────────────────────
    article_nos: list[str] = []
    page = 1
    while True:
        try:
            data     = await _fetch_list_page(client, cortar_no, page)
            articles = data.get("articleList", [])
            article_nos.extend(str(a["articleNo"]) for a in articles)
            if not articles or not data.get("isMoreData", False):
                break
            page += 1
            await asyncio.sleep(DELAY_LIST)
        except TokenExpiredError:
            raise
        except Exception as e:
            print(f"    [목록 오류] {label} p{page}: {e}")
            break

    if not article_nos:
        return []

    total = len(article_nos)
    print(f"  {label}: 매물 {total}건 → 상세 수집 중...")

    # ── 2단계: 배치 병렬 상세 수집 ──────────────────────────────────────────
    records: list[dict] = []

    for i in range(0, total, DETAIL_BATCH):
        batch = article_nos[i : i + DETAIL_BATCH]

        # 401이 asyncio.gather 안에서 발생하면 위로 전파됨
        results = await asyncio.gather(
            *[_fetch_detail_safe(client, no) for no in batch],
            return_exceptions=False,
        )

        for article_no, detail in zip(batch, results):
            if detail:
                rec = extract_record(article_no, detail)
                # 지역 메타데이터 추가 (DB 저장용)
                rec["sido"]      = sido_name
                rec["sigungu"]   = sigungu_name
                rec["dong"]      = ""
                rec["cortar_no"] = cortar_no
                records.append(rec)

        await asyncio.sleep(DELAY_BATCH)

    yield_cnt = sum(1 for r in records if r.get("수익률(%)") is not None)
    print(f"  {label}: {len(records)}건 수집 (수익률 산출 {yield_cnt}건)")
    return records


# ════════════════════════════════════════════════════════════════
# 메인 크롤링 루프
# ════════════════════════════════════════════════════════════════

async def main() -> None:
    parser = argparse.ArgumentParser(description="전국 상가 일일 크롤러")
    parser.add_argument(
        "--sido",
        metavar="시/도명",
        help="특정 시/도만 크롤링합니다 (예: --sido 경기도). 미입력 시 전국.",
    )
    parser.add_argument(
        "--sigungu",
        metavar="시/군/구명",
        help="특정 시/군/구만 크롤링합니다 (예: --sigungu '수원시 장안구'). --sido 와 함께 사용.",
    )
    parser.add_argument(
        "--dong",
        metavar="읍/면/동명",
        help="특정 읍/면/동만 크롤링합니다 (예: --dong 율전동). --sido, --sigungu 와 함께 사용.",
    )
    args = parser.parse_args()

    # ── 인수 조합 검증 ────────────────────────────────────────────────────────
    if args.sigungu and not args.sido:
        print("ERROR: --sigungu 사용 시 --sido 도 함께 지정해야 합니다.")
        sys.exit(1)
    if args.dong and not args.sigungu:
        print("ERROR: --dong 사용 시 --sigungu 도 함께 지정해야 합니다.")
        sys.exit(1)

    # ── 환경변수 검증 ────────────────────────────────────────────────────────
    for var in ("NAVER_NID_SES", "NAVER_NID_AUT", "SUPABASE_URL", "SUPABASE_KEY"):
        if not os.environ.get(var):
            print(f"ERROR: 환경변수 {var} 가 설정되지 않았습니다.")
            sys.exit(1)
    if not os.environ.get("NAVER_JWT"):
        print("INFO: NAVER_JWT 미설정 → Playwright로 JWT 자동 추출합니다.")

    print("=" * 60)
    print(f"크롤링 시작: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    target_parts = [p for p in [args.sido, args.sigungu, args.dong] if p]
    if target_parts:
        print(f"대상: {' '.join(target_parts)}")
    else:
        last = get_last_crawl()
        if last:
            print(f"직전 크롤링: {last['finished_at']} ({last['total_count']:,}건)")
    print("=" * 60)

    # ── 1. JWT 자동 갱신 ────────────────────────────────────────────────────
    await _refresh_jwt()

    started_at    = datetime.now(timezone.utc)
    total_records = 0
    yield_records = 0
    status        = "success"

    async with httpx.AsyncClient(verify=False, timeout=60) as client:

        # ── 2. 시/도 목록 조회 ────────────────────────────────────────────────
        sido_list = await _fetch_regions(client, "0000000000")

        if args.sido:
            sido_list_filtered = [s for s in sido_list if s["cortarName"] == args.sido]
            if not sido_list_filtered:
                valid = ", ".join(s["cortarName"] for s in sido_list)
                print(f"ERROR: '{args.sido}'를 찾을 수 없습니다.\n유효한 값: {valid}")
                sys.exit(1)
            sido_list = sido_list_filtered

        print(f"대상 시/도: {len(sido_list)}개\n")

        # ── 3. 시/도 순회 ─────────────────────────────────────────────────────
        pending_records: list[dict] = []   # DB_UPSERT_EVERY건마다 flush

        for sido in sido_list:
            sido_name = sido["cortarName"]
            print(f"\n{'─' * 50}")
            print(f"[시/도] {sido_name}")
            print(f"{'─' * 50}")

            try:
                sigungu_list = await _fetch_regions(client, sido["cortarNo"])
            except Exception as e:
                print(f"  시/군/구 목록 조회 실패: {e}")
                status = "partial"
                continue

            # --sigungu 필터
            if args.sigungu:
                sigungu_list = [s for s in sigungu_list if s["cortarName"] == args.sigungu]
                if not sigungu_list:
                    print(f"ERROR: '{args.sigungu}'를 찾을 수 없습니다.")
                    sys.exit(1)

            # ── 4. 시/군/구 순회 ───────────────────────────────────────────────
            for sigungu in sigungu_list:
                sigungu_name = sigungu["cortarName"]

                # --dong 지정 시 동 단위로 한 단계 더 내려가서 크롤링
                if args.dong:
                    try:
                        dong_list = await _fetch_regions(client, sigungu["cortarNo"])
                    except Exception as e:
                        print(f"  읍/면/동 목록 조회 실패: {e}")
                        status = "partial"
                        continue

                    dong_list = [d for d in dong_list if d["cortarName"] == args.dong]
                    if not dong_list:
                        print(f"ERROR: '{args.dong}'를 찾을 수 없습니다.")
                        sys.exit(1)

                    crawl_targets = [
                        (f"{sigungu_name} {d['cortarName']}", d["cortarNo"])
                        for d in dong_list
                    ]
                else:
                    crawl_targets = [(sigungu_name, sigungu["cortarNo"])]

                for crawl_label, crawl_cortar in crawl_targets:
                    jwt_retried = False

                    while True:
                        try:
                            records = await _crawl_sigungu(
                                client,
                                sido_name,
                                crawl_label,
                                crawl_cortar,
                            )
                            pending_records.extend(records)

                            # 일정 건수마다 DB UPSERT (메모리 관리 + 중단 시 데이터 보존)
                            if len(pending_records) >= DB_UPSERT_EVERY:
                                upserted = upsert_listings(pending_records)
                                total_records += upserted
                                yield_records += sum(
                                    1 for r in pending_records if r.get("수익률(%)")
                                )
                                print(f"  [DB] {upserted}건 저장 (누적 {total_records:,}건)")
                                pending_records = []

                            break  # 성공 → while 탈출

                        except TokenExpiredError:
                            if not jwt_retried:
                                print(f"  [JWT 만료] {crawl_label} — 자동 갱신 후 재시도...")
                                await _refresh_jwt()
                                jwt_retried = True
                                # while 루프 계속 → 재시도
                            else:
                                print(f"  [JWT 만료] {crawl_label} — 재갱신 실패, 건너뜀")
                                status = "partial"
                                break

                        except Exception as e:
                            print(f"  [{crawl_label} 오류] {e}")
                            break

            # 시/도 완료 로그
            print(f"\n[{sido_name}] 완료 — 누적 {total_records + len(pending_records):,}건")

        # ── 남은 레코드 최종 UPSERT ────────────────────────────────────────────
        if pending_records:
            upserted = upsert_listings(pending_records)
            total_records += upserted
            yield_records += sum(1 for r in pending_records if r.get("수익률(%)"))
            print(f"  [DB] 최종 {upserted}건 저장")

    # ── 5. 크롤링 로그 저장 ──────────────────────────────────────────────────
    finished_at = datetime.now(timezone.utc)
    elapsed_min = int((finished_at - started_at).total_seconds() // 60)

    insert_crawl_log({
        "started_at":  started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "total_count": total_records,
        "yield_count": yield_records,
        "status":      status,
    })

    print("\n" + "=" * 60)
    print("크롤링 완료!")
    print(f"  전체 매물   : {total_records:,}건")
    print(f"  수익률 산출 : {yield_records:,}건")
    print(f"  소요 시간   : {elapsed_min}분")
    print(f"  상태        : {status}")
    print("=" * 60)

    if status != "success":
        sys.exit(1)  # GitHub Actions에서 실패로 표시


if __name__ == "__main__":
    asyncio.run(main())
