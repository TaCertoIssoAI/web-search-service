from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

import uvicorn
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

from web_search_service.browser_pool import BrowserContextPool
from web_search_service.config import settings
from web_search_service.models import ErrorResponse, HealthResponse, SearchResponse
from web_search_service.search import SearchError, execute_search

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    pool = BrowserContextPool()
    await pool.start()
    app.state.pool = pool
    yield
    await pool.shutdown()


app = FastAPI(title="Web Search Service", lifespan=lifespan)


@app.get("/search", response_model=SearchResponse, responses={429: {"model": ErrorResponse}, 504: {"model": ErrorResponse}})
async def search(
    query: str = Query(..., min_length=1),
    domains: list[str] = Query(default=[]),
    n_results: int = Query(default=settings.default_n_results, ge=1, le=settings.max_n_results),
) -> SearchResponse | JSONResponse:
    pool: BrowserContextPool = app.state.pool
    try:
        async with pool.context() as ctx:
            results, effective_query = await execute_search(
                ctx, query, domains=domains, n_results=n_results
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
