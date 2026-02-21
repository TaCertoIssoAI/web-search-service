from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator

from camoufox.async_api import AsyncNewBrowser
from playwright.async_api import Browser, BrowserContext, Playwright, async_playwright

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
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._queue: asyncio.Queue[BrowserContext] = asyncio.Queue()
        self._semaphore = asyncio.Semaphore(self._settings.browser_pool_size)
        self._total = 0
        self._total_acquisitions = 0
        self._total_releases = 0

    async def _create_context(self) -> BrowserContext:
        assert self._browser is not None
        ctx = await self._browser.new_context(
            locale="en-US",
            timezone_id="America/New_York",
            extra_http_headers={"Accept-Encoding": "gzip, deflate"},
        )
        return ctx

    async def start(self) -> None:
        self._playwright = await async_playwright().start()
        self._browser = await AsyncNewBrowser(
            self._playwright,
            headless=self._settings.browser_headless,
        )

        for _ in range(self._settings.browser_pool_size):
            ctx = await self._create_context()
            await self._queue.put(ctx)
            self._total += 1

        logger.info("Browser pool started with %d contexts", self._total)

    async def acquire(self) -> BrowserContext:
        try:
            await asyncio.wait_for(
                self._semaphore.acquire(),
                timeout=self._settings.context_acquire_timeout,
            )
        except asyncio.TimeoutError:
            raise TimeoutError("Timed out waiting to acquire browser context") from None

        ctx = self._queue.get_nowait()
        self._total_acquisitions += 1
        return ctx

    async def release(self, ctx: BrowserContext, *, healthy: bool = True) -> None:
        if not healthy:
            try:
                await ctx.close()
            except Exception:
                logger.warning("Failed to close unhealthy context", exc_info=True)
            ctx = await self._create_context()
        else:
            try:
                await ctx.clear_cookies()
            except Exception:
                logger.warning("Failed to clear cookies, replacing context", exc_info=True)
                try:
                    await ctx.close()
                except Exception:
                    pass
                ctx = await self._create_context()

        await self._queue.put(ctx)
        self._semaphore.release()
        self._total_releases += 1

    @asynccontextmanager
    async def context(self) -> AsyncIterator[BrowserContext]:
        ctx = await self.acquire()
        healthy = True
        try:
            yield ctx
        except Exception:
            healthy = False
            raise
        finally:
            await self.release(ctx, healthy=healthy)

    def stats(self) -> PoolStats:
        available = self._queue.qsize()
        return PoolStats(
            total=self._total,
            available=available,
            in_use=self._total - available,
            total_acquisitions=self._total_acquisitions,
            total_releases=self._total_releases,
        )

    async def shutdown(self) -> None:
        while not self._queue.empty():
            ctx = self._queue.get_nowait()
            try:
                await ctx.close()
            except Exception:
                logger.warning("Failed to close context during shutdown", exc_info=True)

        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

        logger.info("Browser pool shut down")
