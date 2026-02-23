import asyncio
import socket
import threading

import httpx
import pytest
import uvicorn

from web_search_service.models import SearchResult
from web_search_service import server as server_module


def _get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def _wait_until_ready(base_url: str, timeout_s: float = 5.0) -> None:
    deadline = asyncio.get_event_loop().time() + timeout_s
    async with httpx.AsyncClient(base_url=base_url) as client:
        while True:
            try:
                resp = await client.get("/health", timeout=0.5)
                if resp.status_code == 200:
                    return
            except Exception:
                pass
            if asyncio.get_event_loop().time() >= deadline:
                raise RuntimeError("Server did not become ready in time")
            await asyncio.sleep(0.1)


@pytest.fixture
async def running_server(monkeypatch):
    trusted = ["trusted.one", "trusted.two"]
    ddgs_calls: list[tuple[str, list[str], int]] = []

    async def fake_execute_ddgs_search(
        query: str,
        domains: list[str] | None = None,
        n_results: int = 10,
        settings=None,
        semaphore=None,
    ):
        active_domains = domains or []
        ddgs_calls.append((query, active_domains, n_results))
        url_domain = active_domains[0] if active_domains else "example.com"
        results = [
            SearchResult(
                position=1,
                title="DDGS Result",
                url=f"https://{url_domain}/path",
                snippet="A ddgs snippet",
                displayed_url=url_domain,
            )
        ]
        return results, query

    monkeypatch.setattr(server_module, "execute_ddgs_search", fake_execute_ddgs_search)
    monkeypatch.setattr(server_module, "_load_trusted_domains", lambda: trusted)

    port = _get_free_port()
    config = uvicorn.Config(
        server_module.app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"
    await _wait_until_ready(base_url)
    try:
        yield base_url, trusted, ddgs_calls
    finally:
        server.should_exit = True
        thread.join(timeout=5)


class TestDdgsServerIntegration:
    async def test_ddgs_normal_query(self, running_server):
        base_url, trusted, ddgs_calls = running_server
        async with httpx.AsyncClient(base_url=base_url) as client:
            resp = await client.get("/ddgs/search", params={"query": "test"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["query"] == "test"
        assert data["results"][0]["title"] == "DDGS Result"
        assert ddgs_calls[-1] == ("test", trusted, 10)

    @pytest.mark.parametrize(
        "query",
        [
            "https://example.com",
            "check http://evil.com/payload",
            "search https://foo.bar/baz?x=1 now",
        ],
    )
    async def test_ddgs_query_with_url_returns_422(self, running_server, query):
        base_url, _trusted, ddgs_calls = running_server
        calls_before = len(ddgs_calls)
        async with httpx.AsyncClient(base_url=base_url) as client:
            resp = await client.get("/ddgs/search", params={"query": query})
        assert resp.status_code == 422
        assert resp.json()["detail"] == "Query must not contain URLs"
        assert len(ddgs_calls) == calls_before
