from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator

from camoufox.async_api import AsyncNewBrowser
from playwright.async_api import BrowserContext, async_playwright

from web_search_service.config import Settings, settings as default_settings

logger = logging.getLogger(__name__)


@dataclass
class PoolStats:
    total: int
    available: int
    in_use: int
    total_acquisitions: int
    total_releases: int


class BrowserContextPool:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or default_settings
        self._semaphore = asyncio.Semaphore(self._settings.browser_pool_size)
        self._total_acquisitions = 0
        self._total_releases = 0

    async def start(self) -> None:
        logger.info("Browser pool (per-request browser) initialized with size %d", self._settings.browser_pool_size)

    async def _new_browser_and_context(self) -> tuple:
        pw = await async_playwright().start()
        browser = await AsyncNewBrowser(
            pw,
            headless=self._settings.browser_headless,
        )
        ctx = await browser.new_context(
            locale="en-US",
            timezone_id="America/New_York",
            extra_http_headers={"Accept-Encoding": "gzip, deflate"},
        )
        return pw, browser, ctx

    async def acquire(self) -> tuple:
        try:
            await asyncio.wait_for(
                self._semaphore.acquire(),
                timeout=self._settings.context_acquire_timeout,
            )
        except asyncio.TimeoutError:
            raise TimeoutError("Timed out waiting to acquire browser context") from None
        self._total_acquisitions += 1
        return await self._new_browser_and_context()

    async def release(self, resources: tuple, *, healthy: bool = True) -> None:
        pw, browser, ctx = resources
        try:
            await ctx.close()
        except Exception:
            logger.warning("Failed to close context", exc_info=True)
        try:
            await browser.close()
        except Exception:
            logger.warning("Failed to close browser", exc_info=True)
        try:
            await pw.stop()
        except Exception:
            logger.warning("Failed to stop Playwright", exc_info=True)
        self._semaphore.release()
        self._total_releases += 1

    @asynccontextmanager
    async def context(self) -> AsyncIterator[BrowserContext]:
        resources = await self.acquire()
        pw, browser, ctx = resources
        healthy = True
        try:
            yield ctx
        except Exception:
            healthy = False
            raise
        finally:
            await self.release(resources, healthy=healthy)

    def stats(self) -> PoolStats:
        in_use = self._settings.browser_pool_size - self._semaphore._value  # type: ignore[attr-defined]
        available = self._settings.browser_pool_size - in_use
        return PoolStats(
            total=self._settings.browser_pool_size,
            available=available,
            in_use=in_use,
            total_acquisitions=self._total_acquisitions,
            total_releases=self._total_releases,
        )

    async def shutdown(self) -> None:
        logger.info("Browser pool shutdown (per-request browser mode)")
