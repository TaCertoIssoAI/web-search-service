from __future__ import annotations

import asyncio
import json
import logging
import re
from contextlib import asynccontextmanager
from typing import AsyncIterator

import uvicorn
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from importlib import resources

from web_search_service.browser_pool import BrowserContextPool
from web_search_service.config import settings
from web_search_service.ddgs_search import DdgsSearchError, execute_ddgs_search
from web_search_service.models import ErrorResponse, HealthResponse, SearchResponse
from web_search_service.search import SearchError, execute_search

logger = logging.getLogger(__name__)

_URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    pool = BrowserContextPool()
    await pool.start()
    app.state.pool = pool
    app.state.ddgs_semaphore = asyncio.Semaphore(settings.ddgs_max_workers)
    yield
    await pool.shutdown()


app = FastAPI(title="Web Search Service", lifespan=lifespan)

_TRUSTED_DOMAINS_CACHE: list[str] | None = None


def _load_trusted_domains() -> list[str]:
    global _TRUSTED_DOMAINS_CACHE
    if _TRUSTED_DOMAINS_CACHE is not None:
        return _TRUSTED_DOMAINS_CACHE
    try:
        data_path = resources.files("web_search_service").joinpath("trusted_domains.json")
        raw = data_path.read_text(encoding="utf-8")
        payload = json.loads(raw)
        domains = payload.get("domains", [])
        if not isinstance(domains, list):
            domains = []
    except Exception:
        domains = []
    _TRUSTED_DOMAINS_CACHE = [d for d in domains if isinstance(d, str) and d.strip()]
    return _TRUSTED_DOMAINS_CACHE


def _effective_domains(user_domains: list[str]) -> list[str]:
    if user_domains:
        return user_domains
    return _load_trusted_domains()


@app.get("/search", response_model=SearchResponse, responses={422: {"model": ErrorResponse}, 429: {"model": ErrorResponse}, 504: {"model": ErrorResponse}})
async def search(
    query: str = Query(..., min_length=1),
    domains: list[str] = Query(default=[]),
    n_results: int = Query(default=settings.default_n_results, ge=1, le=settings.max_n_results),
) -> SearchResponse | JSONResponse:
    if _URL_PATTERN.search(query):
        return JSONResponse(
            status_code=422,
            content={"detail": "Query must not contain URLs"},
        )

    pool: BrowserContextPool = app.state.pool
    try:
        async with pool.context() as ctx:
            results, effective_query = await execute_search(
                ctx, query, domains=_effective_domains(domains), n_results=n_results
            )
        return SearchResponse(
            query=query,
            effective_query=effective_query,
            results=results,
            total_results=len(results),
        )
    except SearchError as exc:
        if "CAPTCHA" in str(exc):
            return JSONResponse(status_code=429, content={"detail": str(exc)})
        return JSONResponse(status_code=500, content={"detail": str(exc)})
    except TimeoutError as exc:
        return JSONResponse(status_code=504, content={"detail": str(exc)})
    except Exception as exc:
        logger.exception("Unexpected error during search")
        return JSONResponse(status_code=500, content={"detail": str(exc)})


@app.get(
    "/ddgs/search",
    response_model=SearchResponse,
    responses={422: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def ddgs_search(
    query: str = Query(..., min_length=1),
    domains: list[str] = Query(default=[]),
    n_results: int = Query(default=settings.default_n_results, ge=1, le=settings.max_n_results),
) -> SearchResponse | JSONResponse:
    if _URL_PATTERN.search(query):
        return JSONResponse(
            status_code=422,
            content={"detail": "Query must not contain URLs"},
        )

    try:
        results, effective_query = await execute_ddgs_search(
            query,
            domains=_effective_domains(domains),
            n_results=n_results,
            semaphore=app.state.ddgs_semaphore,
        )
        return SearchResponse(
            query=query,
            effective_query=effective_query,
            results=results,
            total_results=len(results),
        )
    except DdgsSearchError as exc:
        return JSONResponse(status_code=500, content={"detail": str(exc)})
    except Exception as exc:
        logger.exception("Unexpected error during ddgs search")
        return JSONResponse(status_code=500, content={"detail": str(exc)})


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    pool: BrowserContextPool = app.state.pool
    stats = pool.stats()
    return HealthResponse(
        status="ok",
        pool_size=stats.total,
        pool_available=stats.available,
        pool_in_use=stats.in_use,
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    uvicorn.run(app, host=settings.host, port=settings.port)
