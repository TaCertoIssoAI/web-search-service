import asyncio
import socket
import threading
from contextlib import asynccontextmanager
from typing import Callable

import httpx
import pytest
import uvicorn

from web_search_service.browser_pool import PoolStats
from web_search_service.models import SearchResult
from web_search_service import server as server_module


def _get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class _FakePool:
    def stats(self) -> PoolStats:
        return PoolStats(
            total=1,
            available=1,
            in_use=0,
            total_acquisitions=0,
            total_releases=0,
        )

    @asynccontextmanager
    async def context(self):
        yield object()


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
    calls: list[tuple[str, list[str], int]] = []
    trusted = ["trusted.one", "trusted.two"]

    async def fake_execute_search(
        ctx,
        query: str,
        domains: list[str] | None = None,
        n_results: int = 10,
        settings=None,
    ):
        calls.append((query, domains or [], n_results))
        active_domains = domains or []
        url_domain = active_domains[0] if active_domains else "example.com"
        results = [
            SearchResult(
                position=1,
                title="Test Result",
                url=f"https://{url_domain}/path",
                snippet="A test snippet",
                displayed_url=url_domain,
            )
        ]
        return results, query

    @asynccontextmanager
    async def fake_lifespan(app):
        app.state.pool = _FakePool()
        yield

    monkeypatch.setattr(server_module, "execute_search", fake_execute_search)
    monkeypatch.setattr(server_module, "_load_trusted_domains", lambda: trusted)
    server_module.app.router.lifespan_context = fake_lifespan

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
        yield base_url, calls, trusted
    finally:
        server.should_exit = True
        thread.join(timeout=5)


class TestServerIntegration:
    async def test_normal_query(self, running_server):
        base_url, calls, trusted = running_server
        async with httpx.AsyncClient(base_url=base_url) as client:
            resp = await client.get("/search", params={"query": "test"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["query"] == "test"
        assert data["results"][0]["title"] == "Test Result"
        assert calls[-1] == ("test", trusted, 10)

    async def test_domain_filtering(self, running_server):
        base_url, calls, _trusted = running_server
        async with httpx.AsyncClient(base_url=base_url) as client:
            resp = await client.get(
                "/search",
                params=[("query", "test"), ("domains", "example.com"), ("domains", "foo.com")],
            )
        assert resp.status_code == 200
        assert calls[-1] == ("test", ["example.com", "foo.com"], 10)

    async def test_n_results(self, running_server):
        base_url, calls, trusted = running_server
        async with httpx.AsyncClient(base_url=base_url) as client:
            resp = await client.get("/search", params={"query": "test", "n_results": 3})
        assert resp.status_code == 200
        assert calls[-1] == ("test", trusted, 3)

    async def test_five_consecutive_requests(self, running_server):
        base_url, calls, _trusted = running_server
        async with httpx.AsyncClient(base_url=base_url) as client:
            for i in range(5):
                resp = await client.get("/search", params={"query": f"test {i}"})
                assert resp.status_code == 200
        assert len(calls) >= 5

    async def test_domain_filtering_three_domains_urls_within_set(self, running_server):
        base_url, _calls, _trusted = running_server
        allowed = {"a.com", "b.com", "c.com"}
        async with httpx.AsyncClient(base_url=base_url) as client:
            resp = await client.get(
                "/search",
                params=[("query", "test"), ("domains", "a.com"), ("domains", "b.com"), ("domains", "c.com")],
            )
        assert resp.status_code == 200
        data = resp.json()
        for result in data["results"]:
            assert any(result["url"].startswith(f"https://{d}/") for d in allowed)

    async def test_domain_filtering_single_domain_urls_within_set(self, running_server):
        base_url, _calls, _trusted = running_server
        allowed = {"only.com"}
        async with httpx.AsyncClient(base_url=base_url) as client:
            resp = await client.get(
                "/search",
                params=[("query", "test"), ("domains", "only.com")],
            )
        assert resp.status_code == 200
        data = resp.json()
        for result in data["results"]:
            assert any(result["url"].startswith(f"https://{d}/") for d in allowed)
