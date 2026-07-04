"""뉴스 수집·본문 추출 서비스.

기존 구현과 달리 Playwright 브라우저를 기사마다 새로 띄우지 않고
하나를 계속 재사용한다. 추출마다 격리된 브라우저 컨텍스트만 만들었다
닫으므로 프로세스 생성 비용과 좀비 프로세스 누적이 사라진다.
"""

import asyncio
import logging

import aiohttp
from playwright.async_api import async_playwright, Browser, Page, Playwright

from ..config import Settings

logger = logging.getLogger("news_bot")

NAVER_NEWS_API_URL = "https://openapi.naver.com/v1/search/news.json"

# 본문 추출 선택자 목록 (구체적인 것 우선)
CONTENT_SELECTORS: tuple[str, ...] = (
    "article",
    ".article_body",
    ".article-body",
    "#articleBodyContents",
    "#articeBody",
    ".news_end",
    ".article_view",
    "#newsContent",
    ".article-content",
    'div[itemprop="articleBody"]',
    "#content",
    ".content",
)

MIN_CONTENT_LENGTH = 100


class CrawlingService:
    """네이버 뉴스 API 조회와 기사 본문 추출을 담당한다."""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._nltk_ready = False

        # 공유 자원 — start()/close()로 수명 관리
        self._http: aiohttp.ClientSession | None = None
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._browser_lock = asyncio.Lock()

    # ── 수명 주기 ──────────────────────────────────────────────

    async def start(self):
        """공유 HTTP 세션을 준비하고 newspaper3k용 NLTK 데이터를 내려받는다."""
        if self._http is None or self._http.closed:
            self._http = aiohttp.ClientSession()
        if not self._nltk_ready:
            await asyncio.to_thread(self._download_nltk_data)
            self._nltk_ready = True

    async def close(self):
        """브라우저·HTTP 세션 등 공유 자원을 정리한다."""
        if self._browser is not None:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
        if self._http is not None and not self._http.closed:
            await self._http.close()
        self._http = None

    @staticmethod
    def _download_nltk_data():
        import nltk

        nltk.download("punkt_tab", quiet=True)
        nltk.download("punkt", quiet=True)

    # ── 네이버 뉴스 API ────────────────────────────────────────

    async def fetch_naver_news(self, query: str | None = None, display: int | None = None) -> list[dict]:
        """네이버 뉴스 API에서 IT 기술 뉴스를 검색한다."""
        s = self._settings
        if not s.naver_client_id or not s.naver_client_secret:
            logger.warning("네이버 API 클라이언트 ID 또는 시크릿이 설정되지 않았습니다. 뉴스 검색을 건너뜁니다.")
            return []

        if self._http is None or self._http.closed:
            await self.start()

        headers = {
            "X-Naver-Client-Id": s.naver_client_id,
            "X-Naver-Client-Secret": s.naver_client_secret,
        }
        params = {
            "query": query or s.news_query,
            "display": display or s.fetch_display,
            "sort": "date",
        }

        try:
            async with self._http.get(
                NAVER_NEWS_API_URL, headers=headers, params=params,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("items", [])
                error_text = await response.text()
                logger.error(f"네이버 API 오류 발생: Status {response.status}, Error: {error_text}")
                return []
        except Exception as e:
            logger.error(f"네이버 API 요청 중 오류 발생: {e}")
            return []

    # ── 본문 추출 (3단계 폴백) ─────────────────────────────────

    async def extract_article_content(self, url: str) -> tuple[str | None, str]:
        """뉴스 기사 본문을 추출한다.

        1. Cloudflare Browser Rendering (환경변수 설정 시)
        2. newspaper3k
        3. 로컬 Playwright (재사용 브라우저)
        모두 실패하면 (None, "failed")를 반환한다.
        """
        if self._settings.cloudflare_api_token:
            try:
                logger.info("  -> [0단계] Cloudflare Browser Rendering 시도...")
                content = await self._extract_with_cloudflare(url)
                if content:
                    logger.info(f"     ✓ Cloudflare 성공 (길이: {len(content)})")
                    return content, "cloudflare"
            except Exception as e:
                logger.warning(f"     ✗ Cloudflare 오류: {e}")

        try:
            logger.info("  -> [1단계] newspaper3k로 본문 추출 시도...")
            content = await self._extract_with_newspaper(url)
            if content:
                logger.info(f"     ✓ newspaper3k 성공 (길이: {len(content)})")
                return content, "newspaper3k"
        except Exception:
            logger.warning("     ✗ newspaper3k 오류 또는 데이터 부족")

        try:
            logger.info("  -> [2단계] 로컬 playwright로 본문 추출 시도...")
            content = await self._extract_with_local_browser(url)
            if content:
                logger.info(f"     ✓ 로컬 playwright 성공 (길이: {len(content)})")
                return content, "playwright"
        except Exception as e:
            logger.error(f"     ✗ 로컬 playwright 오류: {e}")

        return None, "failed"

    async def _extract_with_newspaper(self, url: str) -> str | None:
        from newspaper import Article as Article3k

        article = Article3k(url, language="ko")
        await asyncio.wait_for(asyncio.to_thread(article.download), timeout=10.0)
        await asyncio.wait_for(asyncio.to_thread(article.parse), timeout=5.0)

        content = article.text.strip()
        if content and len(content) > MIN_CONTENT_LENGTH:
            return content
        return None

    async def _extract_with_local_browser(self, url: str) -> str | None:
        """재사용 브라우저에서 격리된 컨텍스트를 열어 본문을 추출한다."""
        browser = await self._get_browser()
        context = await browser.new_context()
        try:
            page = await context.new_page()
            await page.goto(url, timeout=15000, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)
            return await self._find_content_with_selectors(page)
        finally:
            await context.close()

    async def _extract_with_cloudflare(self, url: str) -> str | None:
        """Cloudflare의 Browser Rendering API를 사용하여 페이지를 추출한다."""
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(
                f"wss://browser.cloudflare.com/v1?token={self._settings.cloudflare_api_token}"
            )
            try:
                page = await browser.new_page()
                await page.goto(url, timeout=30000, wait_until="domcontentloaded")
                await page.wait_for_timeout(3000)  # JS 로딩 대기
                return await self._find_content_with_selectors(page)
            finally:
                await browser.close()

    async def _get_browser(self) -> Browser:
        """공유 Chromium 인스턴스를 반환한다. 죽어 있으면 재기동한다."""
        async with self._browser_lock:
            if self._browser is not None and self._browser.is_connected():
                return self._browser

            if self._browser is not None:
                logger.warning("공유 브라우저 연결이 끊어져 재시작합니다.")
                try:
                    await self._browser.close()
                except Exception:
                    pass
                self._browser = None

            if self._playwright is None:
                self._playwright = await async_playwright().start()

            self._browser = await self._playwright.chromium.launch(headless=True)
            logger.info("✓ 공유 Chromium 브라우저 기동 완료.")
            return self._browser

    @staticmethod
    async def _find_content_with_selectors(page: Page) -> str | None:
        """페이지에서 선택자를 순서대로 시도하여 본문 텍스트를 추출한다."""
        for selector in CONTENT_SELECTORS:
            try:
                element = await page.query_selector(selector)
                if element is None:
                    continue
                text = await element.inner_text()
                if text and len(text.strip()) > MIN_CONTENT_LENGTH:
                    return text.strip()
            except Exception:
                continue
        return None
