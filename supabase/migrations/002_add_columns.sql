-- ════════════════════════════════════════════════════════════════
-- 002_add_columns.sql
-- 001_create_tables.sql 실행 후 적용하세요.
-- ════════════════════════════════════════════════════════════════

-- ── listings 테이블에 컬럼 추가 ──────────────────────────────────────────────
ALTER TABLE listings
    ADD COLUMN IF NOT EXISTS expose_start_ymd    CHAR(8),           -- 매물 노출 시작일 (YYYYMMDD)
    ADD COLUMN IF NOT EXISTS current_usage       VARCHAR(100),      -- 현재 용도 (예: 병원, 음식점)
    ADD COLUMN IF NOT EXISTS law_usage           VARCHAR(200),      -- 법정 용도 (예: 제1종 근린생활시설)
    ADD COLUMN IF NOT EXISTS building_approve_ymd CHAR(8),          -- 건축물 사용 승인일 (YYYYMMDD)
    ADD COLUMN IF NOT EXISTS structure_name      VARCHAR(100),      -- 건물 구조 (예: 철근콘크리트구조)
    ADD COLUMN IF NOT EXISTS underground_floors  SMALLINT,          -- 지하 층수
    ADD COLUMN IF NOT EXISTS total_area          NUMERIC(10, 2),    -- 건물 전체 연면적 ㎡
    ADD COLUMN IF NOT EXISTS exclusive_rate      NUMERIC(5, 2),     -- 전용률 %
    ADD COLUMN IF NOT EXISTS monthly_mgmt_cost   INTEGER,           -- 월 관리비 (원 단위)
    ADD COLUMN IF NOT EXISTS finance_price       INTEGER,           -- 융자금 (만원)
    ADD COLUMN IF NOT EXISTS walking_to_subway   SMALLINT,          -- 지하철까지 도보 시간 (분)
    ADD COLUMN IF NOT EXISTS parking_count       SMALLINT,          -- 주차 가능 대수
    ADD COLUMN IF NOT EXISTS tag_list            TEXT[],            -- 태그 목록 (예: ['10년이내', '주차가능'])
    ADD COLUMN IF NOT EXISTS detail_description  TEXT,              -- 매물 상세 설명
    ADD COLUMN IF NOT EXISTS realtor_tel         VARCHAR(30),       -- 중개사 대표 전화
    ADD COLUMN IF NOT EXISTS realtor_cell        VARCHAR(30);       -- 중개사 휴대폰

-- ── 인덱스 추가 ──────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_listings_current_usage
    ON listings (current_usage);

CREATE INDEX IF NOT EXISTS idx_listings_walking_subway
    ON listings (walking_to_subway);

-- ── listings_with_yield 뷰 업데이트 ─────────────────────────────────────────
CREATE OR REPLACE VIEW listings_with_yield AS
SELECT
    article_no,
    crawled_at,
    sido,
    sigungu,
    dong,
    location,
    features,
    ROUND(contract_area  / 3.305785, 1) AS contract_pyeong,
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
    longitude,
    expose_start_ymd,
    current_usage,
    law_usage,
    building_approve_ymd,
    structure_name,
    underground_floors,
    total_area,
    exclusive_rate,
    monthly_mgmt_cost,
    finance_price,
    walking_to_subway,
    parking_count,
    tag_list,
    detail_description,
    realtor_tel,
    realtor_cell
FROM listings
WHERE
    deposit      > 0
    AND monthly_rent > 0
    AND yield_rate   IS NOT NULL
ORDER BY yield_rate DESC;

-- ── region_hierarchy 뷰 (지역 드롭다운용) ──────────────────────────────────
CREATE OR REPLACE VIEW region_hierarchy AS
SELECT DISTINCT
    sido,
    sigungu,
    dong
FROM listings
WHERE sido IS NOT NULL AND sido <> ''
ORDER BY sido, sigungu, dong;
