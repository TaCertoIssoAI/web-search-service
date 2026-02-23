from __future__ import annotations

import asyncio
import logging
from urllib.parse import urlparse

from ddgs import DDGS

from web_search_service.config import Settings, settings as default_settings
from web_search_service.models import SearchResult

logger = logging.getLogger(__name__)


class DdgsSearchError(Exception):
    pass


def _build_effective_query(query: str, domains: list[str] | None = None) -> str:
    if not domains:
        return query
    domain_filter = " OR ".join(f"site:{d}" for d in domains)
    return f"{query} {domain_filter}"


def _map_result(position: int, raw: dict) -> SearchResult:
    href = raw.get("href", "")
    parsed = urlparse(href)
    displayed_url = parsed.hostname or ""
    return SearchResult(
        position=position,
        title=raw.get("title", ""),
        url=href,
        snippet=raw.get("body", ""),
        displayed_url=displayed_url,
        date=None,
    )


def _run_ddgs_search(
    effective_query: str,
    n_results: int,
    timeout: int,
) -> list[dict]:
    return DDGS(timeout=timeout).text(
        effective_query,
        region="us-en",
        timelimit="y",
        max_results=n_results,
    )


async def execute_ddgs_search(
    query: str,
    domains: list[str] | None = None,
    n_results: int = 10,
    settings: Settings | None = None,
    semaphore: asyncio.Semaphore | None = None,
) -> tuple[list[SearchResult], str]:
    s = settings or default_settings
    effective_query = _build_effective_query(query, domains)

    async def _do_search() -> list[dict]:
        return await asyncio.to_thread(
            _run_ddgs_search, effective_query, n_results, s.ddgs_timeout
        )

    try:
        if semaphore is not None:
            async with semaphore:
                raw_results = await _do_search()
        else:
            raw_results = await _do_search()
    except Exception as exc:
        raise DdgsSearchError(str(exc)) from exc

    results = [_map_result(i + 1, r) for i, r in enumerate(raw_results)]
    logger.info("DDGS found %d results for query: %s", len(results), query)
    return results, effective_query
