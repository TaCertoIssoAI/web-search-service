import asyncio

import pytest

from web_search_service.browser_pool import BrowserContextPool
from web_search_service.config import Settings


@pytest.fixture
def pool_settings() -> Settings:
    return Settings(
        browser_pool_size=2,
        browser_headless=True,
        context_acquire_timeout=2.0,
        min_action_delay=0.0,
        max_action_delay=0.0,
    )


@pytest.fixture
async def pool(pool_settings: Settings):
    p = BrowserContextPool(settings=pool_settings)
    await p.start()
    yield p
    await p.shutdown()


class TestPoolStart:
    async def test_creates_correct_number_of_contexts(self, pool: BrowserContextPool):
        stats = pool.stats()
        assert stats.total == 2
        assert stats.available == 2
        assert stats.in_use == 0


class TestAcquireRelease:
    async def test_acquire_reduces_available(self, pool: BrowserContextPool):
        ctx = await pool.acquire()
        stats = pool.stats()
        assert stats.available == 1
        assert stats.in_use == 1
        await pool.release(ctx)

    async def test_release_restores_available(self, pool: BrowserContextPool):
        ctx = await pool.acquire()
        await pool.release(ctx)
        stats = pool.stats()
        assert stats.available == 2
        assert stats.in_use == 0

    async def test_stats_track_acquisitions_and_releases(self, pool: BrowserContextPool):
        ctx = await pool.acquire()
        await pool.release(ctx)
        stats = pool.stats()
        assert stats.total_acquisitions == 1
        assert stats.total_releases == 1


class TestContextManager:
    async def test_context_manager_acquire_release(self, pool: BrowserContextPool):
        async with pool.context() as ctx:
            assert ctx is not None
            stats = pool.stats()
            assert stats.in_use == 1
        stats = pool.stats()
        assert stats.in_use == 0


class TestPoolExhaustion:
    async def test_timeout_when_pool_exhausted(self, pool_settings: Settings):
        pool_settings.browser_pool_size = 1
        pool_settings.context_acquire_timeout = 0.5
        pool = BrowserContextPool(settings=pool_settings)
        await pool.start()
        try:
            ctx = await pool.acquire()
            with pytest.raises(TimeoutError):
                await pool.acquire()
            await pool.release(ctx)
        finally:
            await pool.shutdown()


class TestUnhealthyRelease:
    async def test_unhealthy_release_replaces_context(self, pool: BrowserContextPool):
        ctx = await pool.acquire()
        await pool.release(ctx, healthy=False)
        stats = pool.stats()
        assert stats.total == 2
        assert stats.available == 2


class TestShutdown:
    async def test_shutdown_clears_pool(self, pool_settings: Settings):
        pool = BrowserContextPool(settings=pool_settings)
        await pool.start()
        await pool.shutdown()
        stats = pool.stats()
        assert stats.available == 0
