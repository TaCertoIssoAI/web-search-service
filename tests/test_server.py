import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from web_search_service.browser_pool import BrowserContextPool, PoolStats
from web_search_service.ddgs_search import DdgsSearchError
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
    app.state.ddgs_semaphore = asyncio.Semaphore(4)
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

        with patch("web_search_service.server._load_trusted_domains", return_value=[]):
            with patch("web_search_service.server.execute_search", new_callable=AsyncMock) as mock_exec:
                mock_exec.return_value = (mock_results, "test query")
                resp = await client.get("/search", params={"query": "test"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["query"] == "test"
        assert len(data["results"]) == 1
        assert data["results"][0]["title"] == "Test Result"
        assert mock_exec.call_args.kwargs["domains"] == []

    async def test_search_missing_query_returns_422(self, client: AsyncClient):
        resp = await client.get("/search")
        assert resp.status_code == 422

    @pytest.mark.parametrize(
        "query",
        [
            "http://example.com",
            "https://example.com",
            "check this https://example.com/page",
            "HTTP://EXAMPLE.COM",
            "look at http://foo.bar/baz?q=1",
        ],
    )
    async def test_search_query_with_url_returns_422(self, client: AsyncClient, query: str):
        resp = await client.get("/search", params={"query": query})
        assert resp.status_code == 422
        assert resp.json()["detail"] == "Query must not contain URLs"

    @pytest.mark.parametrize(
        "query",
        [
            "python asyncio tutorial",
            "example.com best practices",
            "what is ftp://something",
            "how to configure host:port",
        ],
    )
    async def test_search_query_without_url_is_allowed(self, client: AsyncClient, mock_pool, query: str):
        ctx_manager = AsyncMock()
        ctx_manager.__aenter__ = AsyncMock(return_value=AsyncMock())
        ctx_manager.__aexit__ = AsyncMock(return_value=False)
        mock_pool.context.return_value = ctx_manager

        with patch("web_search_service.server._load_trusted_domains", return_value=[]):
            with patch("web_search_service.server.execute_search", new_callable=AsyncMock) as mock_exec:
                mock_exec.return_value = ([], query)
                resp = await client.get("/search", params={"query": query})

        assert resp.status_code == 200

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

    async def test_search_uses_trusted_domains_when_none_provided(self, client: AsyncClient, mock_pool):
        ctx_manager = AsyncMock()
        ctx_manager.__aenter__ = AsyncMock(return_value=AsyncMock())
        ctx_manager.__aexit__ = AsyncMock(return_value=False)
        mock_pool.context.return_value = ctx_manager

        with patch("web_search_service.server._load_trusted_domains", return_value=["a.com", "b.com"]):
            with patch("web_search_service.server.execute_search", new_callable=AsyncMock) as mock_exec:
                mock_exec.return_value = ([], "test query")
                resp = await client.get("/search", params={"query": "test"})

        assert resp.status_code == 200
        assert mock_exec.call_args.kwargs["domains"] == ["a.com", "b.com"]


class TestDdgsSearch:
    async def test_ddgs_search_returns_results(self, client: AsyncClient):
        mock_results = [
            SearchResult(
                position=1,
                title="DDGS Result",
                url="https://example.com",
                snippet="A ddgs snippet",
                displayed_url="example.com",
            )
        ]

        with patch("web_search_service.server._load_trusted_domains", return_value=[]):
            with patch(
                "web_search_service.server.execute_ddgs_search", new_callable=AsyncMock
            ) as mock_exec:
                mock_exec.return_value = (mock_results, "test query")
                resp = await client.get("/ddgs/search", params={"query": "test"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["query"] == "test"
        assert len(data["results"]) == 1
        assert data["results"][0]["title"] == "DDGS Result"

    @pytest.mark.parametrize(
        "query",
        [
            "http://example.com",
            "https://example.com",
            "check this https://example.com/page",
        ],
    )
    async def test_ddgs_search_query_with_url_returns_422(
        self, client: AsyncClient, query: str
    ):
        resp = await client.get("/ddgs/search", params={"query": query})
        assert resp.status_code == 422
        assert resp.json()["detail"] == "Query must not contain URLs"

    async def test_ddgs_search_missing_query_returns_422(self, client: AsyncClient):
        resp = await client.get("/ddgs/search")
        assert resp.status_code == 422

    async def test_ddgs_search_uses_trusted_domains_when_none_provided(
        self, client: AsyncClient
    ):
        with patch(
            "web_search_service.server._load_trusted_domains",
            return_value=["a.com", "b.com"],
        ):
            with patch(
                "web_search_service.server.execute_ddgs_search",
                new_callable=AsyncMock,
            ) as mock_exec:
                mock_exec.return_value = ([], "test query")
                resp = await client.get("/ddgs/search", params={"query": "test"})

        assert resp.status_code == 200
        assert mock_exec.call_args.kwargs["domains"] == ["a.com", "b.com"]

    async def test_ddgs_search_error_returns_500(self, client: AsyncClient):
        with patch("web_search_service.server._load_trusted_domains", return_value=[]):
            with patch(
                "web_search_service.server.execute_ddgs_search",
                new_callable=AsyncMock,
            ) as mock_exec:
                mock_exec.side_effect = DdgsSearchError("ddgs failed")
                resp = await client.get("/ddgs/search", params={"query": "test"})

        assert resp.status_code == 500
        assert resp.json()["detail"] == "ddgs failed"
