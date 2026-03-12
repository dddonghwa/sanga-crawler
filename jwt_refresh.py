"""
jwt_refresh_playwright.py ─ NID 쿠키를 이용한 Naver JWT 자동 갱신 (개선 버전)

[기존 코드 문제점]
  1. headless=False 하드코딩 → CI/CD 환경에서 실패
  2. wait_until="networkidle" → 타임아웃 빈번
  3. 봇 탐지 우회 없음 → navigator.webdriver 노출
  4. JWT 유발 트리거 부족 → captured 리스트가 빈 채로 종료
  5. captured[0] 접근 시 빈 리스트면 IndexError 발생

[개선 사항 - anti_bot_scraper 참고]
  - navigator.webdriver 숨기기 (add_init_script)
  - 이미지/폰트/미디어 차단으로 속도 향상
  - 사람처럼 줌 아웃 → 이동 → 줌 인 (human_like_recenter)
  - wait_for_selector("canvas") + wait_for_response() 조합
  - headless 모드 환경변수로 제어 (CI: True, 로컬: False)
  - 명확한 예외 메시지 포함

[필요 환경변수]
  NAVER_NID_SES  : 브라우저 개발자도구 → Application → Cookies → NID_SES 값
  NAVER_NID_AUT  : NID_AUT 값
  HEADLESS       : "true" (CI 기본값), "false" (로컬 디버깅)
"""

import asyncio
import math
import os
import random
from urllib.parse import parse_qs, urlparse

from playwright.async_api import async_playwright

_TARGET_URL = (
    "https://new.land.naver.com/complexes"
    "?ms=37.5608,126.9888,15&a=APT&b=A1"
)
_NAVER_DOMAIN = ".naver.com"

# ──────────────────────────────────────────────
# 맵 이동 헬퍼 (anti_bot_scraper 참고)
# ──────────────────────────────────────────────

def _ll_to_pixel(lat: float, lon: float, z: float):
    """위도/경도 → 픽셀 좌표 (메르카토르 투영)"""
    scale = 256 * (2 ** z)
    x = (lon + 180.0) / 360.0 * scale
    siny = math.sin(math.radians(lat))
    y = (0.5 - math.log((1 + siny) / (1 - siny)) / (4 * math.pi)) * scale
    return x, y


async def _get_ms(page):
    """현재 페이지 URL에서 위도/경도/줌 파싱"""
    u = urlparse(page.url)
    ms = parse_qs(u.query).get("ms", [None])[0]
    if not ms:
        return None
    try:
        la, lo, zz = ms.split(",")
        return float(la), float(lo), float(zz)
    except Exception:
        return None


async def _wheel_to_zoom(page, target_zoom: int, step_delay: float = 0.3):
    """마우스 휠로 특정 줌 레벨까지 단계적으로 이동"""
    for _ in range(20):
        cur = await _get_ms(page)
        if not cur:
            await asyncio.sleep(0.3)
            continue
        _, _, z = cur
        if round(z) == target_zoom:
            return
        await page.mouse.move(960, 540)
        await page.mouse.wheel(0, -300 if target_zoom > z else 300)
        await asyncio.sleep(step_delay)


async def _drag_to_latlon(page, lat: float, lon: float, tolerance_px: float = 3.5):
    """맵을 드래그하여 특정 위도/경도로 점진적 이동"""
    for _ in range(18):
        cur = await _get_ms(page)
        if not cur:
            await asyncio.sleep(0.3)
            continue
        cur_lat, cur_lon, z = cur
        x1, y1 = _ll_to_pixel(cur_lat, cur_lon, z)
        x2, y2 = _ll_to_pixel(lat, lon, z)
        dx, dy = x2 - x1, y2 - y1
        dist = math.hypot(dx, dy)
        if dist <= tolerance_px:
            return
        step = min(800.0, dist)
        r = step / (dist + 1e-9)
        mx, my = dx * r, dy * r
        await page.mouse.move(960, 540)
        await page.mouse.down()
        await page.mouse.move(960 - mx, 540 - my, steps=20)
        await page.mouse.up()
        await asyncio.sleep(0.35)


async def _human_like_recenter(page, lat: float, lon: float, zoom: int):
    """
    봇 탐지 우회용 자연스러운 맵 이동.
    랜덤 줌 아웃 → 대략 이동 → 원하는 줌으로 확대 → 정확한 위치 조정
    """
    rand_out = random.randint(9, 12)
    await _wheel_to_zoom(page, rand_out)
    await _drag_to_latlon(page, lat, lon)
    await _wheel_to_zoom(page, zoom)
    await _drag_to_latlon(page, lat, lon)


# ──────────────────────────────────────────────
# 메인 함수
# ──────────────────────────────────────────────

async def get_fresh_jwt(nid_ses: str, nid_aut: str, headless: bool = True) -> str:
    """
    NID 쿠키로 Naver Land JWT 토큰 추출.

    Args:
        nid_ses:  네이버 NID_SES 쿠키 값 (3~6개월 유효)
        nid_aut:  네이버 NID_AUT 쿠키 값 (3~6개월 유효)
        headless: CI 환경 True, 로컬 디버깅 False

    Returns:
        JWT Bearer 토큰 문자열 (헤더용: "Bearer <token>")

    Raises:
        RuntimeError: JWT 토큰을 캡처하지 못한 경우
    """
    captured: list[str] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=headless,
            args=["--no-sandbox", "--disable-setuid-sandbox"] if headless else [],
        )

        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            locale="ko-KR",
        )

        # 이미지/폰트/미디어 차단 → 로딩 속도 2~3배 향상
        async def _block_heavy(route):
            if route.request.resource_type in ("image", "media", "font"):
                return await route.abort()
            return await route.continue_()

        await context.route("**/*", _block_heavy)

        # NID 쿠키 주입
        await context.add_cookies([
            {
                "name": "NID_SES",
                "value": nid_ses,
                "domain": _NAVER_DOMAIN,
                "path": "/",
                "secure": True,
                "sameSite": "None",
            },
            {
                "name": "NID_AUT",
                "value": nid_aut,
                "domain": _NAVER_DOMAIN,
                "path": "/",
                "secure": True,
                "sameSite": "None",
            },
        ])

        page = await context.new_page()

        # webdriver 속성 숨기기 (네이버 봇 탐지 우회 핵심)
        await page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )

        # 요청 헤더에서 JWT Bearer 토큰 캡처
        async def _on_request(request):
            auth = (
                request.headers.get("authorization")
                or request.headers.get("Authorization", "")
            )
            if "Bearer " in auth and "land.naver.com" in request.url:
                token = auth.replace("Bearer ", "").strip()
                if len(token) > 100:  # JWT는 100자 이상
                    captured.append(token)

        page.on("request", _on_request)

        # ── 1단계: 페이지 로드 ──────────────────────────────
        print("  [1/4] 페이지 로딩 중...")
        try:
            await page.goto(
                _TARGET_URL,
                wait_until="domcontentloaded",  # networkidle 대신 → 타임아웃 방지
                timeout=30_000,
            )
        except Exception as e:
            print(f"  페이지 로드 경고: {e}")

        # ── 2단계: 맵 캔버스 로딩 대기 ─────────────────────
        print("  [2/4] 맵 캔버스 대기 중...")
        try:
            await page.wait_for_selector("canvas", timeout=20_000)
            print("  맵 로딩 완료")
        except Exception:
            print("  캔버스 로딩 타임아웃 (계속 진행)")

        # ── 3단계: JWT 유발 (사람처럼 맵 이동) ─────────────
        if not captured:
            print("  [3/4] JWT 유발을 위해 사람처럼 맵 이동 중...")
            try:
                # 첫 API 응답 대기 (단지 마커 또는 매물 목록)
                await page.wait_for_response(
                    lambda r: (
                        "complexes/single-markers" in r.url
                        or "/api/articles/complex/" in r.url
                        or "/api/map/" in r.url
                    ),
                    timeout=15_000,
                )
            except Exception:
                print("  API 응답 대기 타임아웃 (계속 진행)")

            # 사람처럼 줌 아웃 → 이동 → 줌 인
            await _human_like_recenter(page, 37.5608, 126.9888, 15)
            await asyncio.sleep(1.0)

        # ── 4단계: 그래도 없으면 줌 변경으로 추가 트리거 ───
        if not captured:
            print("  [4/4] 줌 변경으로 추가 API 호출 트리거 중...")
            for delta in [-300, -300, 300, -300]:
                await page.mouse.move(960, 540)
                await page.mouse.wheel(0, delta)
                await asyncio.sleep(0.8)
            await asyncio.sleep(2.0)

        await browser.close()

    # ── 결과 반환 ────────────────────────────────────────────
    if not captured:
        raise RuntimeError(
            "JWT 토큰을 가져오지 못했습니다.\n"
            "  1) NID_SES / NID_AUT 쿠키가 유효한지 확인하세요 (3~6개월 만료).\n"
            "  2) 로컬에서 HEADLESS=false 로 실행해 브라우저 화면을 확인하세요.\n"
            "  3) 네이버 로그인이 정상인지 브라우저에서 직접 확인하세요."
        )

    token = captured[0]
    print(f"  JWT 캡처 성공 (앞 50자: {token[:50]}...)")
    return token


# ── 단독 실행: 토큰 추출 테스트 ──────────────────────────────
if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv(override=False)

    nid_ses = os.environ.get("NAVER_NID_SES", "")
    nid_aut = os.environ.get("NAVER_NID_AUT", "")

    if not nid_ses or not nid_aut:
        print("ERROR: NAVER_NID_SES / NAVER_NID_AUT 환경변수를 설정하세요.")
        raise SystemExit(1)

    # HEADLESS=false 로 설정하면 브라우저 화면 표시 (디버깅 용도)
    headless = os.environ.get("HEADLESS", "true").lower() == "true"
    print(f"JWT 자동 추출 중... (headless={headless})")

    jwt_token = asyncio.run(get_fresh_jwt(nid_ses, nid_aut, headless=headless))
    print(f"성공!\nJWT (앞 80자): {jwt_token[:80]}...")
