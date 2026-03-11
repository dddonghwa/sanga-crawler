"""
네이버 부동산 상가 크롤러

사용 전 환경변수 설정:
  Windows CMD:   set NAVER_COOKIE=... && set NAVER_JWT=...
  PowerShell:    $env:NAVER_COOKIE="..."; $env:NAVER_JWT="..."

실행:
  python crawl.py           # 대화형 지역 선택 → 크롤링
  python crawl.py --resume  # JWT 만료 후 이어서 실행

JWT 만료(3시간) 시:
  1. 브라우저 개발자도구 → Network → 아무 요청 헤더 → authorization 값 복사
  2. set NAVER_JWT=새토큰값
  3. python crawl.py --resume
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime

import httpx

# ── 인증 정보 (환경변수) ─────────────────────────────────────────────────────
NAVER_COOKIE = os.environ.get("NAVER_COOKIE", "")
NAVER_JWT    = os.environ.get("NAVER_JWT", "")

# ── 엔드포인트 ───────────────────────────────────────────────────────────────
BASE            = "https://new.land.naver.com"
LIST_ENDPOINT   = BASE + "/api/articles"
DTL_ENDPOINT    = BASE + "/api/articles/{no}?complexNo="
REGION_ENDPOINT = BASE + "/api/regions/list"
BASE_REFERER    = "https://new.land.naver.com/offices?ms=37.5,127.0,14&a=SG&b=A1&e=RETAIL"

# ── 딜레이 ───────────────────────────────────────────────────────────────────
DELAY_LIST   = 0.5
DELAY_DETAIL = 0.3
DELAY_REGION = 0.2

# ── 기타 ─────────────────────────────────────────────────────────────────────
PROGRESS_FILE = "progress.json"

CSV_FIELDS = [
    "매물번호",
    "소재지",
    "매물특징",
    "계약면적(㎡)",
    "전용면적(㎡)",
    "해당층",
    "총층",
    "매매대금(만원)",
    "기보증금(만원)",
    "월세(만원)",
    "방향",
    "중개사",
    "상세정보",
]


# ════════════════════════════════════════════════════════════════
# 헤더
# ════════════════════════════════════════════════════════════════

def make_headers(article_no: str = "") -> dict:
    referer = BASE_REFERER + (f"&articleNo={article_no}" if article_no else "")
    return {
        "Accept":             "*/*",
        "Accept-Language":    "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Connection":         "keep-alive",
        "Cookie":             NAVER_COOKIE,
        "User-Agent":         "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
        "authorization":      f"Bearer {NAVER_JWT}",
        "Referer":            referer,
        "Sec-Fetch-Dest":     "empty",
        "Sec-Fetch-Mode":     "cors",
        "Sec-Fetch-Site":     "same-origin",
        "sec-ch-ua":          '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
        "sec-ch-ua-mobile":   "?0",
        "sec-ch-ua-platform": '"Windows"',
    }


# ════════════════════════════════════════════════════════════════
# 지역 API
# ════════════════════════════════════════════════════════════════

async def fetch_regions(client: httpx.AsyncClient, parent_cortar_no: str) -> list[dict]:
    """Naver 지역 계층 API: 하위 지역 목록 반환"""
    resp = await client.get(
        REGION_ENDPOINT,
        params={"cortarNo": parent_cortar_no},
        headers=make_headers(),
    )
    resp.raise_for_status()
    return resp.json().get("regionList", [])


# ════════════════════════════════════════════════════════════════
# 대화형 지역 선택 UI
# ════════════════════════════════════════════════════════════════

def _print_choices(items: list[dict], key: str = "cortarName", allow_all: bool = False):
    """번호 목록 출력. allow_all=True이면 0번(전체) 포함."""
    if allow_all:
        print("   0. 전체")
    for i, item in enumerate(items, 1):
        # 4열 출력 (항목이 많을 때 보기 편하도록)
        end = "\n" if i % 4 == 0 or i == len(items) else "   "
        print(f"  {i:>2}. {item[key]:<12}", end=end)
    if len(items) % 4 != 0:
        print()  # 마지막 줄 개행


def _ask(prompt: str, max_val: int, allow_all: bool = False) -> int | None:
    """
    숫자 입력 받기.
    - allow_all=True: 0 입력 시 None 반환 (전체 선택)
    - 그 외: 1~max_val 사이 정수 반환
    """
    while True:
        try:
            val = int(input(f"{prompt}: ").strip())
            if allow_all and val == 0:
                return None          # 전체
            if 1 <= val <= max_val:
                return val
            print(f"  → 0~{max_val} 사이 번호를 입력하세요.")
        except ValueError:
            print("  → 숫자를 입력하세요.")
        except (EOFError, KeyboardInterrupt):
            print("\n취소되었습니다.")
            sys.exit(0)


async def select_regions(client: httpx.AsyncClient) -> tuple[list[dict], str]:
    """
    3단계 대화형 지역 선택.

    1단계: 시/도 선택 (단일 선택)
    2단계: 시/군/구 선택 (단일 선택 또는 0=전체)
    3단계: 동 선택 (단일 선택 또는 0=전체)  ← 시/군/구 전체 선택 시 생략

    Returns:
        regions : [{"cortarNo": ..., "label": ...}]  ← crawl_all에 전달
        label   : 출력 파일명에 쓸 짧은 지역명
    """
    SEP = "─" * 50

    # ── 1단계: 시/도 ─────────────────────────────────────────────────────────
    print(f"\n{SEP}")
    print("[1단계] 시/도를 선택하세요")
    print(SEP)
    sido_list = await fetch_regions(client, "0000000000")
    _print_choices(sido_list)

    idx = _ask("번호 입력", len(sido_list), allow_all=False)
    sido = sido_list[idx - 1]
    print(f"  ✔ {sido['cortarName']}")

    # ── 2단계: 시/군/구 ───────────────────────────────────────────────────────
    print(f"\n{SEP}")
    print(f"[2단계] 시/군/구를 선택하세요  ({sido['cortarName']})")
    print(SEP)
    sigungu_list = await fetch_regions(client, sido["cortarNo"])
    _print_choices(sigungu_list, allow_all=True)

    idx = _ask("번호 입력 (0=전체)", len(sigungu_list), allow_all=True)

    if idx is None:
        # 시/도 전체 → 시/군/구별로 각각 크롤링
        label   = sido["cortarName"]
        regions = [
            {
                "cortarNo": r["cortarNo"],
                "label":    f"{sido['cortarName']} {r['cortarName']}",
            }
            for r in sigungu_list
        ]
        print(f"  ✔ {sido['cortarName']} 전체 ({len(regions)}개 시/군/구)")
        return regions, label

    sigungu = sigungu_list[idx - 1]
    print(f"  ✔ {sigungu['cortarName']}")

    # ── 3단계: 동 ─────────────────────────────────────────────────────────────
    print(f"\n{SEP}")
    print(f"[3단계] 동을 선택하세요  ({sido['cortarName']} {sigungu['cortarName']})")
    print(SEP)
    dong_list = await fetch_regions(client, sigungu["cortarNo"])

    if not dong_list:
        # 동 목록이 없는 지역(시 전체 단위) → 시/군/구 cortarNo로 바로 크롤링
        label   = f"{sido['cortarName']} {sigungu['cortarName']}"
        regions = [{"cortarNo": sigungu["cortarNo"], "label": label}]
        print(f"  (동 단위 없음 — 시/군/구 전체로 크롤링합니다)")
        return regions, label

    _print_choices(dong_list, allow_all=True)
    idx = _ask("번호 입력 (0=전체)", len(dong_list), allow_all=True)

    if idx is None:
        # 시/군/구 전체 → 시/군/구 cortarNo 하나로 크롤링
        label   = f"{sido['cortarName']} {sigungu['cortarName']}"
        regions = [{"cortarNo": sigungu["cortarNo"], "label": label}]
        print(f"  ✔ {sigungu['cortarName']} 전체")
    else:
        dong    = dong_list[idx - 1]
        label   = f"{sido['cortarName']} {sigungu['cortarName']} {dong['cortarName']}"
        regions = [{"cortarNo": dong["cortarNo"], "label": label}]
        print(f"  ✔ {dong['cortarName']}")

    return regions, label


# ════════════════════════════════════════════════════════════════
# 진행 상황 저장 / 불러오기
# ════════════════════════════════════════════════════════════════

def load_progress() -> dict:
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_progress(progress: dict):
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


# ════════════════════════════════════════════════════════════════
# 필드 추출
# ════════════════════════════════════════════════════════════════

def extract_record(article_no: str, detail: dict) -> dict:
    d = detail.get("articleDetail",  {})
    p = detail.get("articlePrice",   {})
    s = detail.get("articleSpace",   {})
    f = detail.get("articleFloor",   {})
    a = detail.get("articleAddition",{})
    r = detail.get("articleRealtor", {})

    return {
        "매물번호":       article_no,
        "소재지":         d.get("exposureAddress", ""),
        "매물특징":       d.get("articleFeatureDescription", ""),
        "계약면적(㎡)":   s.get("supplySpace", ""),
        "전용면적(㎡)":   s.get("exclusiveSpace", ""),
        "해당층":         f.get("correspondingFloorCount", ""),
        "총층":           f.get("totalFloorCount", ""),
        "매매대금(만원)": p.get("dealPrice", 0),
        "기보증금(만원)": p.get("allWarrantPrice", 0),
        "월세(만원)":     p.get("allRentPrice", 0),
        "방향":           a.get("direction", ""),
        "중개사":         r.get("realtorName", ""),
        "상세정보":       f"https://fin.land.naver.com/articles/{article_no}",
    }


# ════════════════════════════════════════════════════════════════
# URL 빌더
# ════════════════════════════════════════════════════════════════

def build_list_url(cortar_no: str, page: int) -> str:
    return (
        f"{LIST_ENDPOINT}"
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


# ════════════════════════════════════════════════════════════════
# API 요청
# ════════════════════════════════════════════════════════════════

async def fetch_list_page(client: httpx.AsyncClient, cortar_no: str, page: int) -> dict:
    resp = await client.get(build_list_url(cortar_no, page), headers=make_headers())
    resp.raise_for_status()
    return resp.json()


async def fetch_detail(client: httpx.AsyncClient, article_no: str) -> dict:
    url = DTL_ENDPOINT.format(no=article_no)
    resp = await client.get(url, headers=make_headers(article_no))
    resp.raise_for_status()
    return resp.json()


# ════════════════════════════════════════════════════════════════
# CSV 유틸
# ════════════════════════════════════════════════════════════════

def _csv_escape(v) -> str:
    s = str(v) if v is not None else ""
    if any(c in s for c in (',', '\n', '\r', '"')):
        s = '"' + s.replace('"', '""') + '"'
    return s


def append_to_csv(csv_path: str, records: list[dict]):
    """기존 CSV에 행 추가. 파일이 없으면 헤더 포함해 새로 생성."""
    write_header = not os.path.exists(csv_path)
    with open(csv_path, "a", encoding="utf-8-sig") as f:
        if write_header:
            f.write(",".join(CSV_FIELDS) + "\n")
        for rec in records:
            row = [_csv_escape(rec.get(col, "")) for col in CSV_FIELDS]
            f.write(",".join(row) + "\n")


# ════════════════════════════════════════════════════════════════
# 단일 지역 크롤링
# ════════════════════════════════════════════════════════════════

class TokenExpiredError(Exception):
    pass


async def crawl_region(
    client: httpx.AsyncClient,
    cortar_no: str,
    label: str,
) -> list[dict]:
    """단일 cortarNo 크롤링. JWT 만료 시 TokenExpiredError 발생."""
    article_nos: list[str] = []

    # 1단계: articleNo 수집
    page = 1
    while True:
        try:
            data     = await fetch_list_page(client, cortar_no, page)
            articles = data.get("articleList", [])
            is_more  = data.get("isMoreData", False)
            article_nos.extend(str(a["articleNo"]) for a in articles)
            if not articles or not is_more:
                break
            page += 1
            await asyncio.sleep(DELAY_LIST)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise TokenExpiredError()
            print(f"    [목록 오류] HTTP {e.response.status_code} — 건너뜀")
            break
        except Exception as e:
            print(f"    [목록 오류] {e} — 건너뜀")
            break

    if not article_nos:
        return []

    print(f"  {label}: 매물 {len(article_nos)}건 → 상세 수집 중...")

    # 2단계: 상세 수집
    records: list[dict] = []
    for article_no in article_nos:
        try:
            detail = await fetch_detail(client, article_no)
            if "error" not in detail:
                records.append(extract_record(article_no, detail))
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise TokenExpiredError()
        except Exception:
            pass
        await asyncio.sleep(DELAY_DETAIL)

    return records


# ════════════════════════════════════════════════════════════════
# 전체 크롤링 루프
# ════════════════════════════════════════════════════════════════

async def crawl_all(
    regions: list[dict],
    label: str,
    resume: bool = False,
):
    """
    regions: [{"cortarNo": ..., "label": ...}]
    label  : 출력 파일명에 쓸 지역명
    """
    # ── 진행 파일 처리 ───────────────────────────────────────────────────────
    progress = load_progress()

    if resume and progress:
        out_base      = progress["out_base"]
        completed     = set(progress.get("completed", []))
        total_records = progress.get("total_records", 0)
        # resume 시 저장된 regions 복원
        regions       = progress.get("regions", regions)
        label         = progress.get("label", label)
        print(f"\n이전 진행 이어서: {len(completed)}개 지역 완료, {total_records}건 수집됨")
    else:
        ts            = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_base      = f"output_{label.replace(' ', '_')}_{ts}"
        completed     = set()
        total_records = 0
        progress      = {
            "out_base":      out_base,
            "label":         label,
            "regions":       regions,
            "started_at":    datetime.now().isoformat(),
            "completed":     [],
            "total_records": 0,
        }
        save_progress(progress)

    csv_path  = out_base + ".csv"
    json_path = out_base + ".json"

    print(f"출력 파일: {csv_path}\n")

    # ── 기존 JSON 로드 (resume 시) ────────────────────────────────────────────
    all_records: list[dict] = []
    if resume and os.path.exists(json_path):
        with open(json_path, encoding="utf-8") as f:
            all_records = json.load(f)

    # ── 크롤링 루프 ──────────────────────────────────────────────────────────
    total = len(regions)
    print("=" * 60)
    print(f"크롤링 시작: {label} ({total}개 지역)")
    print("=" * 60)

    async with httpx.AsyncClient(verify=False, timeout=30) as client:
        for idx, region in enumerate(regions, 1):
            cortar_no    = region["cortarNo"]
            region_label = region["label"]

            if cortar_no in completed:
                print(f"  [{idx:>3}/{total}] {region_label} — 이미 완료")
                continue

            print(f"\n[{idx:>3}/{total}] {region_label}")

            try:
                records = await crawl_region(client, cortar_no, region_label)

                if records:
                    append_to_csv(csv_path, records)
                    all_records.extend(records)
                    total_records += len(records)

                completed.add(cortar_no)
                progress["completed"]     = list(completed)
                progress["total_records"] = total_records
                save_progress(progress)

                print(f"    → {len(records)}건 수집 (누적 {total_records}건)")

            except TokenExpiredError:
                print("\n" + "!" * 60)
                print("JWT 토큰이 만료되었습니다.")
                print(f"\n  완료: {len(completed)}/{total}개 지역")
                print(f"  수집: {total_records}건")
                print(f"\n토큰 갱신 후 아래 명령으로 이어서 실행하세요:")
                print("  python crawl.py --resume")
                print("!" * 60)
                break

        else:
            print("\n" + "=" * 60)
            print("크롤링 완료!")
            print(f"  지역: {len(completed)}/{total}개")
            print(f"  매물: {total_records}건")

    # JSON 저장 (전체 또는 중간 중단 시 현재까지)
    if all_records:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(all_records, f, ensure_ascii=False, indent=2)

    print(f"\n  CSV  → {csv_path}")
    print(f"  JSON → {json_path}")
    print("=" * 60)


# ════════════════════════════════════════════════════════════════
# 메인
# ════════════════════════════════════════════════════════════════

async def main():
    parser = argparse.ArgumentParser(
        description="네이버 부동산 상가 매매 크롤러"
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help=f"이전 진행 이어서 실행 ({PROGRESS_FILE} 기반)",
    )
    args = parser.parse_args()

    # 환경변수 확인
    if not NAVER_JWT:
        print("ERROR: NAVER_JWT 환경변수가 없습니다.\n")
        print("설정 방법:")
        print("  CMD:        set NAVER_JWT=eyJhbGci...")
        print("  PowerShell: $env:NAVER_JWT=\"eyJhbGci...\"")
        sys.exit(1)

    print(f"JWT  : {NAVER_JWT[:50]}...")
    print(f"쿠키 : {'설정됨 (' + str(len(NAVER_COOKIE)) + '자)' if NAVER_COOKIE else '없음'}")

    if args.resume:
        # --resume: 지역 선택 없이 바로 이어서 실행
        progress = load_progress()
        if not progress:
            print(f"\nERROR: {PROGRESS_FILE} 파일이 없습니다. 먼저 일반 실행을 해주세요.")
            sys.exit(1)
        await crawl_all(regions=[], label="", resume=True)
    else:
        # 대화형 지역 선택
        async with httpx.AsyncClient(verify=False, timeout=30) as client:
            regions, label = await select_regions(client)

        print(f"\n선택 완료: {label} ({len(regions)}개 지역 크롤링 예정)")
        print("─" * 50)

        await crawl_all(regions=regions, label=label)


if __name__ == "__main__":
    asyncio.run(main())
