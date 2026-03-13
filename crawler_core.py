"""
crawler_core.py ─ 네이버 부동산 상가 크롤러 핵심 로직 (동기 버전)

웹 앱(app.py)에서 import해서 사용합니다.
CLI 버전은 crawl.py(비동기) 를 그대로 유지합니다.

JWT와 쿠키를 환경변수가 아닌 함수 인자로 받아 독립적으로 동작합니다.
"""

import time

import httpx

# ── 엔드포인트 ───────────────────────────────────────────────────────────────
BASE            = "https://new.land.naver.com"
LIST_ENDPOINT   = BASE + "/api/articles"
DTL_ENDPOINT    = BASE + "/api/articles/{no}?complexNo="
REGION_ENDPOINT = BASE + "/api/regions/list"
BASE_REFERER    = "https://new.land.naver.com/offices?ms=37.5,127.0,14&a=SG&b=A1&e=RETAIL"

# ── 딜레이 (초) ───────────────────────────────────────────────────────────────
DELAY_LIST   = 0.5   # 목록 페이지 간
DELAY_DETAIL = 0.3   # 상세 요청 간


# ════════════════════════════════════════════════════════════════
# 예외
# ════════════════════════════════════════════════════════════════

class TokenExpiredError(Exception):
    """JWT 401 만료 시 발생"""


# ════════════════════════════════════════════════════════════════
# 헤더
# ════════════════════════════════════════════════════════════════

def make_headers(jwt: str, cookie: str, article_no: str = "") -> dict:
    referer = BASE_REFERER + (f"&articleNo={article_no}" if article_no else "")
    return {
        "Accept":             "*/*",
        "Accept-Language":    "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Connection":         "keep-alive",
        "Cookie":             cookie,
        "User-Agent":         (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/145.0.0.0 Safari/537.36"
        ),
        "authorization":      f"Bearer {jwt}",
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

def fetch_regions(
    client: httpx.Client,
    parent_cortar_no: str,
    jwt: str,
    cookie: str,
) -> list[dict]:
    """cortarNo 하위 지역 목록 반환."""
    resp = client.get(
        REGION_ENDPOINT,
        params={"cortarNo": parent_cortar_no},
        headers=make_headers(jwt, cookie),
    )
    resp.raise_for_status()
    return resp.json().get("regionList", [])


# ════════════════════════════════════════════════════════════════
# 수익률 계산
# ════════════════════════════════════════════════════════════════

def calculate_yield(매매가: float, 보증금: float, 월세: float) -> float | None:
    """
    투자 수익률(연) = 월세 × 12 / (매매가 − 보증금) × 100
    분모가 0 이하거나 월세가 없으면 None 반환.
    """
    분모 = 매매가 - 보증금
    if not 월세 or 분모 <= 0:
        return None
    return round(월세 * 12 / 분모 * 100, 2)


# ════════════════════════════════════════════════════════════════
# 필드 추출
# ════════════════════════════════════════════════════════════════

def extract_record(article_no: str, detail: dict) -> dict:
    d   = detail.get("articleDetail",          {})
    p   = detail.get("articlePrice",           {})
    s   = detail.get("articleSpace",           {})
    f   = detail.get("articleFloor",           {})
    a   = detail.get("articleAddition",        {})
    r   = detail.get("articleRealtor",         {})
    fac = detail.get("articleFacility",        {})
    b   = detail.get("articleBuildingRegister",{})

    매매가 = p.get("dealPrice",       0) or 0
    보증금 = p.get("allWarrantPrice", 0) or 0
    월세   = p.get("allRentPrice",    0) or 0

    return {
        "매물번호":       article_no,
        "소재지":         d.get("exposureAddress", ""),
        "매물특징":       d.get("articleFeatureDescription", ""),
        "계약면적(㎡)":   s.get("supplySpace", ""),
        "전용면적(㎡)":   s.get("exclusiveSpace", ""),
        "해당층":         f.get("correspondingFloorCount", ""),
        "총층":           f.get("totalFloorCount", ""),
        "매매대금(만원)": 매매가,
        "기보증금(만원)": 보증금,
        "월세(만원)":     월세,
        "수익률(%)":      calculate_yield(매매가, 보증금, 월세),
        "방향":           a.get("direction", ""),
        "중개사":         r.get("realtorName", ""),
        "상세정보":       f"https://fin.land.naver.com/articles/{article_no}",

        # 002_add_columns.sql 추가 필드
        "매물노출시작일":  d.get("exposeStartYMD", ""),
        "현재용도":        b.get("mainPurpsCdNm", ""),
        "법정용도":        d.get("lawUsage", ""),
        "건축승인일":      fac.get("buildingUseAprvYmd", ""),
        "건물구조":        b.get("strctCdNm", ""),
        "지하층수":        b.get("ugrndFlrCnt"),
        "연면적(㎡)":      b.get("totArea"),
        "전용률(%)":       s.get("exclusiveRate"),
        "월관리비(원)":    d.get("monthlyManagementCost"),
        "융자금(만원)":    p.get("financePrice"),
        "지하철도보(분)":  d.get("walkingTimeToNearSubway"),
        "주차대수":        d.get("parkingCount"),
        "태그목록":        d.get("tagList", []),
        "상세설명":        d.get("detailDescription", ""),
        "중개사대표전화":  r.get("representativeTelNo", ""),
        "중개사휴대폰":    r.get("cellPhoneNo", ""),

        # 좌표 (Phase 3 대기 없이 API에서 직접 수집)
        "위도":            d.get("latitude"),
        "경도":            d.get("longitude"),
    }


# ════════════════════════════════════════════════════════════════
# URL / 내부 API 요청
# ════════════════════════════════════════════════════════════════

def _build_list_url(cortar_no: str, page: int) -> str:
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


def _get_list_page(
    client: httpx.Client, cortar_no: str, page: int, jwt: str, cookie: str
) -> dict:
    resp = client.get(_build_list_url(cortar_no, page), headers=make_headers(jwt, cookie))
    resp.raise_for_status()
    return resp.json()


def _get_detail(
    client: httpx.Client, article_no: str, jwt: str, cookie: str
) -> dict:
    url  = DTL_ENDPOINT.format(no=article_no)
    resp = client.get(url, headers=make_headers(jwt, cookie, article_no))
    resp.raise_for_status()
    return resp.json()


# ════════════════════════════════════════════════════════════════
# 단일 지역 크롤링
# ════════════════════════════════════════════════════════════════

def crawl_region(
    client: httpx.Client,
    cortar_no: str,
    label: str,
    jwt: str,
    cookie: str,
    progress_cb=None,
) -> list[dict]:
    """
    단일 cortarNo의 상가 매매 매물을 모두 수집합니다.

    Parameters
    ----------
    client      : 재사용할 httpx.Client
    cortar_no   : 지역 코드
    label       : 로그/콜백용 지역명
    jwt         : Bearer 토큰 값 (Bearer 이후 값만)
    cookie      : 쿠키 문자열
    progress_cb : callable(done: int, total: int, msg: str) | None
                  상세 수집 진행 상황 콜백

    Returns
    -------
    list[dict]  : extract_record() 결과 목록

    Raises
    ------
    TokenExpiredError : 401 응답 시
    """
    article_nos: list[str] = []

    # ── 1단계: 목록 수집 ─────────────────────────────────────────────────────
    page = 1
    while True:
        try:
            data     = _get_list_page(client, cortar_no, page, jwt, cookie)
            articles = data.get("articleList", [])
            is_more  = data.get("isMoreData", False)
            article_nos.extend(str(a["articleNo"]) for a in articles)
            if not articles or not is_more:
                break
            page += 1
            time.sleep(DELAY_LIST)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise TokenExpiredError()
            break
        except Exception:
            break

    if not article_nos:
        return []

    total = len(article_nos)

    # ── 2단계: 상세 수집 ─────────────────────────────────────────────────────
    records: list[dict] = []
    for i, article_no in enumerate(article_nos, 1):
        try:
            detail = _get_detail(client, article_no, jwt, cookie)
            if "error" not in detail:
                records.append(extract_record(article_no, detail))
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise TokenExpiredError()
        except Exception:
            pass

        if progress_cb:
            progress_cb(i, total, f"{label}: {i}/{total}건 수집 중")
        time.sleep(DELAY_DETAIL)

    return records
