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
_TARGET_URL = "https://new.land.naver.com/complexes?ms=37.38282,127.118926,15&a=APT:PRE:ABYG:JGC&e=RETAIL"
_NAVER_DOMAIN = ".naver.com"

async def get_fresh_jwt(nid_ses: str, nid_aut: str) -> str:
    async with async_playwright() as pw:
        # headless=False로 두고 실제로 토큰이 찍히는지 눈으로 확인해보는 것도 좋습니다.
        browser = await pw.chromium.launch(headless=False) 
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )

        # 쿠키 주입 (작성하신 코드 유지)
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

        captured = []

        async def _on_request(request):
            # 대문자 Authorization도 확인 (가끔 라이브러리마다 다름)
            auth = request.headers.get("authorization") or request.headers.get("Authorization", "")
            if "Bearer " in auth and "land.naver.com" in request.url:
                token = auth.replace("Bearer ", "").strip()
                if len(token) > 100: # JWT는 보통 꽤 깁니다.
                    captured.append(token)

        page = await context.new_page()
        page.on("request", _on_request)

        # 페이지 로드 시 'networkidle'을 기다려 모든 API 호출이 끝날 때까지 대기
        try:
            await page.goto(_TARGET_URL, wait_until="networkidle", timeout=30000)
        except:
            pass

        # 만약 그래도 없다면, 화면의 특정 요소를 클릭하는 동작 추가
        if not captured:
            try:
                # 상가 매물 탭 클릭 유도
                await page.click("button.filter_btn", timeout=5000) 
                await asyncio.sleep(2)
            except:
                pass
            
    return captured[0]


# ── 단독 실행: 토큰 추출 테스트 ──────────────────────────────────────────────
if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    load_dotenv(override=False)
    nid_ses = os.environ.get("NAVER_NID_SES", "")
    nid_aut = os.environ.get("NAVER_NID_AUT", "")

    if not nid_ses or not nid_aut:
        print("ERROR: NAVER_NID_SES / NAVER_NID_AUT 환경변수를 설정하세요.")
        raise SystemExit(1)

    print("JWT 자동 추출 중...")

    jwt = asyncio.run(get_fresh_jwt(nid_ses, nid_aut))
    print(f"성공!\nJWT (앞 80자): {jwt[:80]}...")
