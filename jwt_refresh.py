"""
jwt_refresh.py ─ NID 쿠키를 이용한 Naver JWT 자동 갱신

[동작 원리]
  NID_SES / NID_AUT 쿠키(3~6개월 유효)를 헤드리스 브라우저에 주입하면
  Naver Land React 앱이 자동으로 JWT를 발급합니다.
  첫 API 요청에서 Authorization 헤더를 가로채 토큰을 추출합니다.
  Playwright 실행 시간: 약 5~15초

[필요 환경변수]
  NAVER_NID_SES  : 브라우저 개발자도구 → Application → Cookies → NID_SES 값
  NAVER_NID_AUT  : NID_AUT 값

[NID 쿠키 갱신 주기]
  만료 시 브라우저에서 새 값을 복사해 GitHub Secrets를 업데이트하세요.
  (NAVER_NID_SES, NAVER_NID_AUT)
"""

import asyncio

from playwright.async_api import async_playwright

# JWT를 유발할 Naver Land 상가 목록 페이지
_TARGET_URL = "https://new.land.naver.com/offices?a=SG&b=A1"
_NAVER_DOMAIN = ".naver.com"


async def get_fresh_jwt(nid_ses: str, nid_aut: str) -> str:
    """
    NID 쿠키로 Naver Land에 접속하여 JWT Bearer 토큰을 자동 추출합니다.

    Parameters
    ----------
    nid_ses : NID_SES 쿠키 값
    nid_aut : NID_AUT 쿠키 값

    Returns
    -------
    str : JWT 토큰 문자열 (Bearer 이후 값만)

    Raises
    ------
    RuntimeError : 토큰 추출 실패 (쿠키 만료 등)
    """
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/145.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )

        # ── NID 쿠키 주입 ──────────────────────────────────────────────────
        await context.add_cookies([
            {
                "name":   "NID_SES",
                "value":  nid_ses,
                "domain": _NAVER_DOMAIN,
                "path":   "/",
                "secure": True,
            },
            {
                "name":   "NID_AUT",
                "value":  nid_aut,
                "domain": _NAVER_DOMAIN,
                "path":   "/",
                "secure": True,
            },
        ])

        # ── API 요청 가로채기 ───────────────────────────────────────────────
        captured: list[str] = []

        async def _on_request(request):
            if captured:
                return
            auth = request.headers.get("authorization", "")
            if (
                auth.startswith("Bearer ")
                and "land.naver.com" in request.url
                and "/api/" in request.url
            ):
                token = auth.removeprefix("Bearer ").strip()
                if len(token) > 50:   # 짧은 오탐 방지
                    captured.append(token)

        page = await context.new_page()
        page.on("request", _on_request)

        # ── 페이지 로드 ────────────────────────────────────────────────────
        try:
            await page.goto(_TARGET_URL, wait_until="domcontentloaded", timeout=25_000)
        except Exception:
            pass  # timeout 무시 — 토큰만 캡처되면 충분

        # domcontentloaded 후에도 토큰이 없으면 추가 대기
        for _ in range(10):
            if captured:
                break
            await asyncio.sleep(1)

        await browser.close()

    if not captured:
        raise RuntimeError(
            "JWT 자동 추출 실패.\n"
            "NID_SES / NID_AUT 쿠키가 만료되었을 수 있습니다.\n"
            "브라우저 개발자도구에서 새 쿠키 값을 복사한 후\n"
            "GitHub Secrets(NAVER_NID_SES, NAVER_NID_AUT)를 갱신하세요."
        )

    return captured[0]


# ── 단독 실행: 토큰 추출 테스트 ──────────────────────────────────────────────
if __name__ == "__main__":
    import os

    nid_ses = os.environ.get("NAVER_NID_SES", "")
    nid_aut = os.environ.get("NAVER_NID_AUT", "")

    if not nid_ses or not nid_aut:
        print("ERROR: NAVER_NID_SES / NAVER_NID_AUT 환경변수를 설정하세요.")
        raise SystemExit(1)

    print("JWT 자동 추출 중...")
    jwt = asyncio.run(get_fresh_jwt(nid_ses, nid_aut))
    print(f"성공!\nJWT (앞 80자): {jwt[:80]}...")
