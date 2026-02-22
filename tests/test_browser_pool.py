import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from web_search_service.browser_pool import BrowserContextPool
from web_search_service.config import Settings


@pytest.mark.asyncio
async def test_per_request_browser_created_and_closed():
    pool = BrowserContextPool(settings=Settings(browser_pool_size=1))
    pool._semaphore = asyncio.Semaphore(1)

    fake_pw = AsyncMock()
    fake_browser = AsyncMock()
    fake_ctx = AsyncMock()

    async def fake_start():
        return fake_pw

    async def fake_new_browser(pw, headless):
        return fake_browser

    async def fake_new_context(**kwargs):
        return fake_ctx

    with patch("web_search_service.browser_pool.async_playwright") as mock_pw:
        mock_pw.return_value.start = fake_start
        with patch("web_search_service.browser_pool.AsyncNewBrowser", side_effect=fake_new_browser):
            fake_browser.new_context = AsyncMock(side_effect=fake_new_context)

            async with pool.context() as ctx:
                assert ctx is fake_ctx

    fake_ctx.close.assert_awaited_once()
    fake_browser.close.assert_awaited_once()
    fake_pw.stop.assert_awaited_once()
    assert pool.stats().in_use == 0


@pytest.mark.asyncio
async def test_semaphore_released_when_browser_creation_fails():
    pool = BrowserContextPool(settings=Settings(browser_pool_size=1))
    pool._semaphore = asyncio.Semaphore(1)

    with patch(
        "web_search_service.browser_pool.async_playwright"
    ) as mock_pw:
        mock_pw.return_value.start = AsyncMock(side_effect=RuntimeError("spawn failed"))

        with pytest.raises(RuntimeError, match="spawn failed"):
            await pool.acquire()

    assert pool._semaphore._value == 1, "semaphore slot should be released after failure"
    assert pool.stats().in_use == 0
