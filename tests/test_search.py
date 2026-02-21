from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from playwright.async_api import TimeoutError as PlaywrightTimeoutError, async_playwright

from web_search_service.search import (
    SearchError,
    _extract_results,
    build_search_url,
    execute_search,
)


class TestBuildSearchUrl:
    def test_basic_url(self):
        url, eq = build_search_url("python asyncio")
        assert "q=python+asyncio" in url
        assert "duckduckgo.com" in url
        assert eq == "python asyncio"

    def test_domain_filters(self):
        url, eq = build_search_url("test", domains=["reddit.com", "stackoverflow.com"])
        assert "site%3Areddit.com" in url or "site:reddit.com" in eq
        assert "site%3Astackoverflow.com" in url or "site:stackoverflow.com" in eq
        assert "test" in eq

    def test_special_characters(self):
        url, eq = build_search_url("c++ templates & tricks")
        assert "c%2B%2B" in url
        assert eq == "c++ templates & tricks"

    def test_sort_newest_first(self):
        url, _ = build_search_url("news")
        assert "df=" in url
        assert "%2E%2E" in url or ".." in url


class TestExtractResults:
    @pytest.fixture
    async def browser(self):
        pw = await async_playwright().start()
        browser = await pw.chromium.launch(headless=True)
        yield browser
        await browser.close()
        await pw.stop()

    async def test_extracts_results_from_html(self, browser, sample_serp_html: str):
        page = await browser.new_page()
        await page.set_content(sample_serp_html)
        results = await _extract_results(page, n_results=10)
        await page.close()

        assert len(results) == 3
        assert results[0].title == "First Result Title"
        assert results[0].url == "https://example.com/result1"
        assert results[0].snippet == "This is the first snippet with some text."
        assert results[0].displayed_url == "example.com"
        assert results[0].date == "2 hours ago"
        assert results[0].position == 1

    async def test_skips_containers_without_title(self, browser, sample_serp_html: str):
        page = await browser.new_page()
        await page.set_content(sample_serp_html)
        results = await _extract_results(page, n_results=10)
        await page.close()
        # 4th div.g has no h3/link, should be skipped
        assert len(results) == 3

    async def test_respects_n_results_limit(self, browser, sample_serp_html: str):
        page = await browser.new_page()
        await page.set_content(sample_serp_html)
        results = await _extract_results(page, n_results=2)
        await page.close()
        assert len(results) == 2

    async def test_second_result_has_no_date(self, browser, sample_serp_html: str):
        page = await browser.new_page()
        await page.set_content(sample_serp_html)
        results = await _extract_results(page, n_results=10)
        await page.close()
        assert results[1].date is None

    async def test_third_result_snippet(self, browser, sample_serp_html: str):
        page = await browser.new_page()
        await page.set_content(sample_serp_html)
        results = await _extract_results(page, n_results=10)
        await page.close()
        assert "Third snippet" in results[2].snippet
        assert "result__snippet" in results[2].snippet


class TestExecuteSearchCaptcha:
    async def test_captcha_not_solved_raises(self):
        mock_page = AsyncMock()
        mock_page.content = AsyncMock(return_value="<html>bots use DuckDuckGo too</html>")
        mock_page.goto = AsyncMock()
        mock_page.wait_for_timeout = AsyncMock()
        mock_page.close = AsyncMock()
        # wait_for_function times out → CAPTCHA not solved
        mock_page.wait_for_function = AsyncMock(side_effect=TimeoutError("timed out"))

        mock_locator = MagicMock()
        mock_locator.count = AsyncMock(return_value=0)
        mock_locator.first = MagicMock()
        mock_locator.first.wait_for = AsyncMock()
        mock_page.locator = MagicMock(return_value=mock_locator)

        mock_ctx = AsyncMock()
        mock_ctx.new_page = AsyncMock(return_value=mock_page)

        with pytest.raises(SearchError, match="CAPTCHA was not solved"):
            await execute_search(mock_ctx, "test query")


class TestExecuteSearchRetries:
    async def test_retry_on_goto_timeout_then_success(self):
        mock_page = AsyncMock()
        mock_page.goto = AsyncMock(side_effect=[PlaywrightTimeoutError("timed out"), None])
        mock_page.content = AsyncMock(return_value="<html></html>")
        mock_page.wait_for_timeout = AsyncMock()
        mock_page.close = AsyncMock()

        mock_locator = MagicMock()
        mock_locator.count = AsyncMock(return_value=1)
        mock_locator.first = MagicMock()
        mock_locator.first.wait_for = AsyncMock()
        mock_page.locator = MagicMock(return_value=mock_locator)

        mock_ctx = AsyncMock()
        mock_ctx.new_page = AsyncMock(return_value=mock_page)

        with patch("web_search_service.search._extract_results", new_callable=AsyncMock) as mock_extract:
            mock_extract.return_value = []
            results, _ = await execute_search(mock_ctx, "test query")

        assert results == []
        assert mock_page.goto.call_count == 2

    async def test_exhausts_retries_on_goto_timeout(self):
        mock_page = AsyncMock()
        mock_page.goto = AsyncMock(side_effect=PlaywrightTimeoutError("timed out"))
        mock_page.content = AsyncMock(return_value="<html></html>")
        mock_page.wait_for_timeout = AsyncMock()
        mock_page.close = AsyncMock()

        mock_ctx = AsyncMock()
        mock_ctx.new_page = AsyncMock(return_value=mock_page)

        with pytest.raises(PlaywrightTimeoutError):
            await execute_search(mock_ctx, "test query")
        assert mock_page.goto.call_count == 3
