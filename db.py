"""
db.py ─ Supabase 연동 모듈 (서버 사이드 크롤러 전용)

[필요 환경변수]
  SUPABASE_URL  : https://<project-ref>.supabase.co
  SUPABASE_KEY  : service_role 키 (Settings → API → service_role)
                  ※ service_role 키는 RLS를 우회해 쓰기가 가능합니다.
                    절대 프론트엔드/클라이언트에 노출하지 마세요.
"""

import os
from datetime import datetime, timezone

from supabase import Client, create_client

# ── 클라이언트 싱글턴 ────────────────────────────────────────────────────────
_client: Client | None = None


def _get_client() -> Client:
    global _client
    if _client is None:
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_KEY"]
        _client = create_client(url, key)
    return _client


# ════════════════════════════════════════════════════════════════
# 내부 변환
# ════════════════════════════════════════════════════════════════

def _to_db_row(record: dict) -> dict:
    """
    crawler_core.extract_record() 결과(한글 키)를
    Supabase listings 컬럼(영문)으로 변환합니다.
    """
    def _num(val):
        """숫자 변환. 빈값이면 None 반환."""
        if val in (None, "", "없음"):
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    def _int(val):
        n = _num(val)
        return int(n) if n is not None else None

    return {
        "article_no":     record.get("매물번호"),
        "crawled_at":     datetime.now(timezone.utc).isoformat(),

        # 지역 (crawl_scheduled.py에서 추가)
        "sido":           record.get("sido",      ""),
        "sigungu":        record.get("sigungu",   ""),
        "dong":           record.get("dong",      ""),
        "cortar_no":      record.get("cortar_no", ""),

        # 매물 정보
        "location":       record.get("소재지"),
        "features":       record.get("매물특징"),
        "contract_area":  _num(record.get("계약면적(㎡)")),
        "exclusive_area": _num(record.get("전용면적(㎡)")),
        "floor":          _int(record.get("해당층")),
        "total_floors":   _int(record.get("총층")),
        "direction":      record.get("방향"),
        "realtor":        record.get("중개사"),

        # 가격 (만원)
        "sale_price":     _int(record.get("매매대금(만원)")),
        "deposit":        _int(record.get("기보증금(만원)")),
        "monthly_rent":   _int(record.get("월세(만원)")),
        "yield_rate":     _num(record.get("수익률(%)")),

        # 링크
        "detail_url":     record.get("상세정보"),

        # 지도 (Phase 3, 현재는 null)
        "latitude":       None,
        "longitude":      None,
    }


# ════════════════════════════════════════════════════════════════
# 공개 함수
# ════════════════════════════════════════════════════════════════

def upsert_listings(records: list[dict], batch_size: int = 300) -> int:
    """
    listings 테이블에 UPSERT.
    article_no 중복 시 모든 컬럼을 최신 값으로 덮어씁니다.

    Parameters
    ----------
    records    : extract_record() + 지역 필드가 포함된 dict 리스트
    batch_size : 1회 upsert 건수 (Supabase 1MB 제한 고려)

    Returns
    -------
    int : 실제 upsert된 건수
    """
    if not records:
        return 0

    client = _get_client()
    rows   = [_to_db_row(r) for r in records]
    count  = 0

    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        client.table("listings").upsert(batch, on_conflict="article_no").execute()
        count += len(batch)

    return count


def insert_crawl_log(log: dict) -> None:
    """crawl_log 테이블에 크롤링 이력 1건 저장."""
    _get_client().table("crawl_log").insert(log).execute()


def get_last_crawl() -> dict | None:
    """
    가장 최근에 성공한 크롤링 정보를 반환합니다.
    프론트엔드에서 '마지막 업데이트 시각' 표시에 사용합니다.
    """
    res = (
        _get_client()
        .table("crawl_log")
        .select("finished_at, total_count, yield_count")
        .eq("status", "success")
        .order("finished_at", desc=True)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None
