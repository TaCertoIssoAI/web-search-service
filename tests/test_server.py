import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from web_search_service.ddgs_search import DdgsSearchError
from web_search_service.models import SearchResult
from web_search_service.server import app


@pytest.fixture
async def client():
    app.state.ddgs_semaphore = asyncio.Semaphore(5)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestHealth:
    async def test_health_returns_200(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"


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
