-- ════════════════════════════════════════════════════════════════
-- 001_create_tables.sql
-- Supabase SQL Editor 또는 Supabase CLI로 실행하세요.
-- ════════════════════════════════════════════════════════════════

-- ── listings: 상가 매물 정보 ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS listings (
    id              BIGSERIAL       PRIMARY KEY,
    article_no      VARCHAR(20)     UNIQUE NOT NULL,
    crawled_at      TIMESTAMPTZ     DEFAULT NOW(),

    -- 지역 (크롤러가 추가)
    cortar_no       VARCHAR(20)     DEFAULT '',
    sido            VARCHAR(50)     DEFAULT '',
    sigungu         VARCHAR(50)     DEFAULT '',
    dong            VARCHAR(50)     DEFAULT '',

    -- 매물 정보
    location        TEXT,
    features        TEXT,
    contract_area   NUMERIC(8, 2),    -- 계약면적 ㎡
    exclusive_area  NUMERIC(8, 2),    -- 전용면적 ㎡
    floor           SMALLINT,
    total_floors    SMALLINT,
    direction       VARCHAR(20),
    realtor         VARCHAR(100),

    -- 가격 (단위: 만원)
    sale_price      INTEGER,          -- 매매대금
    deposit         INTEGER,          -- 기보증금
    monthly_rent    INTEGER,          -- 월세
    yield_rate      NUMERIC(5, 2),    -- 수익률 % = 월세*12/(매매가-보증금)*100

    -- 링크
    detail_url      TEXT,

    -- 지도 좌표 (Phase 3 카카오맵 Geocoding 후 채움)
    latitude        NUMERIC(10, 7),
    longitude       NUMERIC(10, 7)
);

-- ── crawl_log: 크롤링 이력 ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS crawl_log (
    id           BIGSERIAL    PRIMARY KEY,
    started_at   TIMESTAMPTZ,
    finished_at  TIMESTAMPTZ,
    total_count  INTEGER,              -- 전체 수집 건수
    yield_count  INTEGER,              -- 수익률 산출 가능 건수
    status       VARCHAR(20)  DEFAULT 'success'  -- 'success' | 'partial' | 'failed'
);

-- ════════════════════════════════════════════════════════════════
-- 인덱스 (조회 성능)
-- ════════════════════════════════════════════════════════════════

CREATE INDEX IF NOT EXISTS idx_listings_region
    ON listings (sido, sigungu, dong);

CREATE INDEX IF NOT EXISTS idx_listings_yield
    ON listings (yield_rate DESC NULLS LAST);

CREATE INDEX IF NOT EXISTS idx_listings_crawled
    ON listings (crawled_at DESC);

-- 기보증금·월세 보유 매물만 빠르게 필터링
CREATE INDEX IF NOT EXISTS idx_listings_has_rent
    ON listings (deposit, monthly_rent)
    WHERE deposit > 0 AND monthly_rent > 0;

-- ════════════════════════════════════════════════════════════════
-- Row Level Security (RLS)
-- ════════════════════════════════════════════════════════════════

ALTER TABLE listings  ENABLE ROW LEVEL SECURITY;
ALTER TABLE crawl_log ENABLE ROW LEVEL SECURITY;

-- 프론트엔드(anon 키)에서 읽기만 허용
CREATE POLICY "anon_read_listings"
    ON listings
    FOR SELECT
    TO anon
    USING (true);

CREATE POLICY "anon_read_crawl_log"
    ON crawl_log
    FOR SELECT
    TO anon
    USING (true);

-- service_role 키는 RLS를 자동 우회 → 크롤러의 UPSERT/INSERT는 추가 정책 불필요

-- ════════════════════════════════════════════════════════════════
-- 편의 뷰: 수익률 있는 매물만 (프론트엔드에서 바로 사용 가능)
-- ════════════════════════════════════════════════════════════════

CREATE OR REPLACE VIEW listings_with_yield AS
SELECT
    article_no,
    crawled_at,
    sido,
    sigungu,
    dong,
    location,
    features,
    ROUND(contract_area / 3.305785, 1)  AS contract_pyeong,  -- ㎡ → 평 변환
    ROUND(exclusive_area / 3.305785, 1) AS exclusive_pyeong,
    contract_area,
    exclusive_area,
    floor,
    total_floors,
    direction,
    realtor,
    sale_price,
    deposit,
    monthly_rent,
    yield_rate,
    detail_url,
    latitude,
    longitude
FROM listings
WHERE
    deposit      > 0
    AND monthly_rent > 0
    AND yield_rate   IS NOT NULL
ORDER BY yield_rate DESC;
