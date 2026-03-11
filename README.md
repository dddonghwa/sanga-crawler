# 네이버 상가 수익률 분석기

네이버 부동산에서 상가 매매 매물을 크롤링하고,
**기보증금·월세 보유 매물만 필터링**하여 수익률을 계산·정렬해주는 도구입니다.

> **수익률 계산식**: `월세 × 12 ÷ (매매대금 − 기보증금) × 100`

---

## 전체 파일 구조

```
crawler/
 ├── jwt_refresh.py               # NID 쿠키 → JWT 자동 추출 (Playwright)
 ├── db.py                        # Supabase UPSERT / 조회
 ├── crawl_scheduled.py           # 전국 비동기 크롤러 (매일 자동 실행용)
 ├── crawler_core.py              # 동기 크롤링 핵심 로직 (웹앱·CLI 공용)
 ├── crawl.py                     # CLI 크롤러 (수동 실행용)
 ├── app.py                       # Streamlit 웹앱 (개발·테스트용)
 ├── requirements.txt
 ├── enhancement.md               # 향후 개선 방안 메모
 ├── .github/
 │   └── workflows/
 │       └── daily_crawl.yml      # GitHub Actions 스케줄러 (매일 KST 02:00)
 └── supabase/
     └── migrations/
         └── 001_create_tables.sql  # DB 테이블 + RLS + 뷰 정의
```

---

## Phase 1 — 자동화 기반 구축

### 동작 흐름

```
[GitHub Actions: 매일 KST 02:00]
         │
         ▼
[jwt_refresh.py]
  NID_SES + NID_AUT 쿠키(3~6개월 유효)로
  Playwright 헤드리스 브라우저를 약 10초간 실행
  → JWT Bearer 토큰 자동 추출
         │
         ▼
[crawl_scheduled.py]
  전국 시/도 → 시/군/구 순회
  상세 API를 10건씩 asyncio.gather()로 병렬 호출
  200건마다 Supabase에 스트리밍 UPSERT
         │
         ▼
[Supabase PostgreSQL]
  listings 테이블에 UPSERT (article_no 기준 중복 방지)
  crawl_log 테이블에 이력 저장
         │
         ▼
[Vercel Frontend] (Phase 2)
  listings_with_yield 뷰에서 바로 읽기
  지역 필터 + 수익률 정렬 + 평수 변환 표시
```

---

## 초기 세팅 순서

### 1. Supabase 테이블 생성

1. [Supabase](https://supabase.com) 프로젝트 생성
2. Dashboard → **SQL Editor**
3. `supabase/migrations/001_create_tables.sql` 전체 내용 붙여넣기 후 실행

생성되는 항목:
- `listings` 테이블 (매물 데이터)
- `crawl_log` 테이블 (크롤링 이력)
- 인덱스 (지역별·수익률·날짜 검색 최적화)
- RLS 정책 (anon 키로 읽기만 허용, service_role 키로 쓰기)
- `listings_with_yield` 뷰 (수익률 있는 매물만, 평수 변환 포함)

### 2. GitHub Secrets 등록

GitHub 저장소 → **Settings → Secrets and variables → Actions → New repository secret**

| Secret 이름 | 값 | 어디서 가져오나 |
|---|---|---|
| `NAVER_NID_SES` | `...` | 브라우저 F12 → Application → Cookies → `.naver.com` → `NID_SES` 값 |
| `NAVER_NID_AUT` | `...` | 동일, `NID_AUT` 값 |
| `SUPABASE_URL` | `https://xxx.supabase.co` | Supabase → Settings → API → Project URL |
| `SUPABASE_KEY` | `service_role key` | Supabase → Settings → API → `service_role` (**절대 공개 금지**) |

> **NID 쿠키 갱신 주기**: 약 3~6개월마다 만료됩니다.
> 만료 시 브라우저에서 새 값을 복사해 GitHub Secrets를 업데이트하세요.

### 3. 패키지 설치 (로컬 테스트 시)

```bash
pip install -r requirements.txt
playwright install chromium
```

### 4. 로컬에서 먼저 테스트 (특정 시/도만)

전국 크롤링 전에 특정 시/도로 먼저 검증하세요.

```bash
# Windows CMD
set NAVER_NID_SES=여기에_NID_SES_값
set NAVER_NID_AUT=여기에_NID_AUT_값
set SUPABASE_URL=https://xxx.supabase.co
set SUPABASE_KEY=service_role_키

python crawl_scheduled.py --sido 서울특별시

# PowerShell
$env:NAVER_NID_SES="..."
$env:NAVER_NID_AUT="..."
$env:SUPABASE_URL="https://xxx.supabase.co"
$env:SUPABASE_KEY="..."

python crawl_scheduled.py --sido 서울특별시
```

### 5. GitHub Actions 수동 실행으로 전국 크롤링 검증

1. GitHub 저장소 → **Actions** 탭
2. **전국 상가 일일 크롤링** 클릭
3. **Run workflow** 버튼
4. `sido` 입력란: 비워두면 전국, 특정 시/도 입력 가능
5. 실행 후 로그 확인

이후부터는 **매일 새벽 2시(KST)에 자동 실행**됩니다.

### 6. JWT 자동 추출 단독 테스트

```bash
python jwt_refresh.py
# 출력 예시:
# JWT 자동 추출 중...
# 성공!
# JWT (앞 80자): eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

---

## 핵심 포인트

| 항목 | 설명 |
|---|---|
| **JWT 자동화** | NID 쿠키(3~6개월)만 관리하면 JWT는 매일 자동 갱신. 사람이 개입할 필요 없음 |
| **크롤링 속도** | `asyncio.gather()`로 상세 API 10건 병렬 호출 → 순차 대비 **약 6배** 빠름 |
| **안전한 중단** | 200건마다 Supabase UPSERT → 크롤 도중 중단돼도 그 전까지 데이터 보존 |
| **JWT 만료 대응** | `TokenExpiredError` 발생 시 JWT 자동 재갱신 후 해당 지역 재시도 |
| **중복 방지** | `article_no` 기준 UPSERT → 매일 실행해도 중복 없이 최신 데이터로 업데이트 |
| **프론트 연동** | `listings_with_yield` 뷰에서 바로 읽기 (평수 변환, 수익률 필터 내장) |
| **Supabase 보안** | anon 키는 읽기 전용(프론트용), service_role 키는 쓰기 가능(크롤러 서버 전용) |

---

## 인증 키 관리 요약

```
장기 보관 (GitHub Secrets)       단기 자동 갱신
──────────────────────────       ─────────────────────────────
NAVER_NID_SES  (3~6개월)   →    JWT Bearer Token (3시간)
NAVER_NID_AUT  (3~6개월)   →    Playwright가 매일 자동 추출
SUPABASE_URL   (영구)
SUPABASE_KEY   (영구)
```

---

## 수동 CLI 크롤링 (기존 방식 유지)

자동화 없이 수동으로 크롤링하고 싶을 때는 기존 `crawl.py`를 그대로 사용합니다.

```bash
# 환경변수에 JWT 직접 입력
set NAVER_JWT=eyJhbGci...
set NAVER_COOKIE=NID_SES=...

python crawl.py           # 대화형 지역 선택 → CSV/JSON 저장
python crawl.py --resume  # JWT 만료 후 이어서 실행
```

---

## 향후 개발 계획 (enhancement.md 참고)

- **Phase 2**: Vercel + Next.js 프론트엔드 (Supabase에서 데이터 읽기, 지역 필터 UI)
- **Phase 3**: 카카오맵 API 연동 (매물 지도 시각화), Claude API로 LLM 자동 추천
  - 수익률 5% 이상 + 입지 좋은 곳 + 주변 시세 대비 저평가 매물 자동 추천
- **기타**: 평수 변환 UI, 관리비 포함 수익률 계산, 알림 기능
