from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from web_search_service.browser_pool import BrowserContextPool, PoolStats
from web_search_service.models import SearchResult
from web_search_service.search import SearchError
from web_search_service.server import app


@pytest.fixture
def mock_pool():
    pool = MagicMock(spec=BrowserContextPool)
    pool.stats.return_value = PoolStats(
        total=5, available=4, in_use=1, total_acquisitions=10, total_releases=9
    )
    return pool


@pytest.fixture
async def client(mock_pool):
    app.state.pool = mock_pool
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestHealth:
    async def test_health_returns_200(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["pool_size"] == 5
        assert data["pool_available"] == 4
        assert data["pool_in_use"] == 1


class TestSearch:
    async def test_search_returns_results(self, client: AsyncClient, mock_pool):
        mock_results = [
            SearchResult(
                position=1,
                title="Test Result",
                url="https://example.com",
                snippet="A test snippet",
                displayed_url="example.com",
            )
        ]
        mock_ctx = AsyncMock()

        async def fake_context():
            class _CM:
                async def __aenter__(self):
                    return mock_ctx
                async def __aexit__(self, *args):
                    pass
            return _CM()

        ctx_manager = AsyncMock()
        ctx_manager.__aenter__ = AsyncMock(return_value=mock_ctx)
        ctx_manager.__aexit__ = AsyncMock(return_value=False)
        mock_pool.context.return_value = ctx_manager

        with patch("web_search_service.server.execute_search", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = (mock_results, "test query")
            resp = await client.get("/search", params={"query": "test"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["query"] == "test"
        assert len(data["results"]) == 1
        assert data["results"][0]["title"] == "Test Result"

    async def test_search_missing_query_returns_422(self, client: AsyncClient):
        resp = await client.get("/search")
        assert resp.status_code == 422

    async def test_search_captcha_returns_429(self, client: AsyncClient, mock_pool):
        ctx_manager = AsyncMock()
        ctx_manager.__aenter__ = AsyncMock(return_value=AsyncMock())
        ctx_manager.__aexit__ = AsyncMock(return_value=False)
        mock_pool.context.return_value = ctx_manager

        with patch("web_search_service.server.execute_search", new_callable=AsyncMock) as mock_exec:
            mock_exec.side_effect = SearchError("CAPTCHA detected")
            resp = await client.get("/search", params={"query": "test"})

        assert resp.status_code == 429

    async def test_search_timeout_returns_504(self, client: AsyncClient, mock_pool):
        ctx_manager = AsyncMock()
        ctx_manager.__aenter__ = AsyncMock(return_value=AsyncMock())
        ctx_manager.__aexit__ = AsyncMock(return_value=False)
        mock_pool.context.return_value = ctx_manager

        with patch("web_search_service.server.execute_search", new_callable=AsyncMock) as mock_exec:
            mock_exec.side_effect = TimeoutError("pool exhausted")
            resp = await client.get("/search", params={"query": "test"})

        assert resp.status_code == 504
