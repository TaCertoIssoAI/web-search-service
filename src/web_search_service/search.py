from __future__ import annotations

import calendar
import logging
import random
import re
from datetime import date
from urllib.parse import urlencode

from playwright.async_api import BrowserContext, Page

from web_search_service.config import Settings, settings as default_settings
from web_search_service.models import SearchResult

logger = logging.getLogger(__name__)

_SNIPPET_PREFIX_RE = re.compile(
    r"^(Today|Yesterday|\d+\s+(?:min|mins|minute|minutes|hour|hours|day|days|week|weeks|month|months|year|years)\s+ago)\s*[:\-–—]?\s*",
    re.IGNORECASE,
)

SELECTORS = {
    "result_container": "[data-testid='result']",
    "title": "a[data-testid='result-title-a']",
    "snippet": [
        "[data-testid='result-snippet']",
        ".result__snippet",
        ".result__snippet.js-result-snippet",
        "a.result__snippet",
        "div.result__snippet",
        "span.result__snippet",
    ],
    "displayed_url": "a[data-testid='result-extras-url-link'] span",
    "date": "time",
}


class SearchError(Exception):
    pass


def _sanitize_snippet(snippet: str) -> str:
    if not snippet:
        return ""
    cleaned = _SNIPPET_PREFIX_RE.sub("", snippet).strip()
    return cleaned


def _subtract_months(base: date, months: int) -> date:
    if months <= 0:
        return base
    year = base.year
    month = base.month - months
    while month <= 0:
        month += 12
        year -= 1
    last_day = calendar.monthrange(year, month)[1]
    day = min(base.day, last_day)
    return date(year, month, day)


def _date_filter_last_n_months(months: int) -> str:
    end = date.today()
    start = _subtract_months(end, months)
    return f"{start.isoformat()}..{end.isoformat()}"


def build_search_url(
    query: str,
    domains: list[str] | None = None,
    n_results: int = 10,
) -> tuple[str, str]:
    effective_query = query
    if domains:
        domain_filter = " OR ".join(f"site:{d}" for d in domains)
        effective_query = f"{query} {domain_filter}"

    params = {
        "q": effective_query,
        "kl": "us-en",
        "df": _date_filter_last_n_months(6),
    }
    url = f"https://duckduckgo.com/?{urlencode(params)}"
    return url, effective_query


def _is_captcha(content: str) -> bool:
    lower = content.lower()
    return "bots use duckduckgo" in lower or "captcha" in lower


async def _wait_for_captcha_resolution(page: Page, timeout: int = 120000) -> bool:
    """Wait for the user to solve the CAPTCHA manually. Returns True if resolved."""
    logger.warning("CAPTCHA detected — solve it in the browser window, waiting up to %ds...", timeout // 1000)
    try:
        await page.wait_for_function(
            """() => {
                const body = document.body.innerText.toLowerCase();
                return !body.includes('bots use duckduckgo') && !body.includes('captcha');
            }""",
            timeout=timeout,
        )
        logger.info("CAPTCHA resolved, continuing search")
        return True
    except Exception:
        return False


async def _extract_results(page: Page, n_results: int) -> list[SearchResult]:
    results: list[SearchResult] = []
    containers = page.locator(SELECTORS["result_container"])
    count = await containers.count()

    for i in range(count):
        if len(results) >= n_results:
            break

        container = containers.nth(i)

        title_el = container.locator(SELECTORS["title"])
        if await title_el.count() == 0:
            continue
        title = (await title_el.first.text_content() or "").strip()
        if not title:
            continue

        url = await title_el.first.get_attribute("href") or ""
        if not url:
            continue

        cite_el = container.locator(SELECTORS["displayed_url"])
        displayed_url = ""
        if await cite_el.count() > 0:
            displayed_url = (await cite_el.first.text_content() or "").strip()

        date_el = container.locator(SELECTORS["date"])
        date = None
        if await date_el.count() > 0:
            date = (await date_el.first.text_content() or "").strip() or None

        snippet = ""
        for selector in SELECTORS["snippet"]:
            snippet_el = container.locator(selector)
            if await snippet_el.count() == 0:
                continue
            snippet = (await snippet_el.first.text_content() or "").strip()
            if not snippet:
                snippet = (await snippet_el.first.inner_text() or "").strip()
            if snippet:
                break
        if not snippet:
            # Fallback: pick the longest meaningful text inside the result container.
            candidate_texts = await container.locator("div, span, p").all_inner_texts()
            cleaned: list[str] = []
            for text in candidate_texts:
                normalized = " ".join(text.split()).strip()
                if not normalized:
                    continue
                if normalized in {title, displayed_url, date or ""}:
                    continue
                if normalized.startswith("http"):
                    continue
                cleaned.append(normalized)
            if cleaned:
                snippet = max(cleaned, key=len)
        snippet = _sanitize_snippet(snippet)

        results.append(
            SearchResult(
                position=len(results) + 1,
                title=title,
                url=url,
                snippet=snippet,
                displayed_url=displayed_url,
                date=date,
            )
        )

    return results


async def execute_search(
    ctx: BrowserContext,
    query: str,
    domains: list[str] | None = None,
    n_results: int = 10,
    settings: Settings | None = None,
) -> tuple[list[SearchResult], str]:
    s = settings or default_settings
    url, effective_query = build_search_url(query, domains, n_results)

    page = await ctx.new_page()
    try:
        delay = random.uniform(s.min_action_delay, s.max_action_delay)
        await page.wait_for_timeout(delay * 1000)

        await page.goto(url, timeout=s.search_navigation_timeout, wait_until="domcontentloaded")

        content = await page.content()
        if _is_captcha(content):
            resolved = await _wait_for_captcha_resolution(page)
            if not resolved:
                raise SearchError("CAPTCHA was not solved in time")

        try:
            await page.locator(SELECTORS["result_container"]).first.wait_for(
                timeout=s.search_result_wait_timeout,
            )
        except Exception:
            content = await page.content()
            if _is_captcha(content):
                resolved = await _wait_for_captcha_resolution(page)
                if not resolved:
                    raise SearchError("CAPTCHA was not solved in time")
                # After solving, wait for results again
                try:
                    await page.locator(SELECTORS["result_container"]).first.wait_for(
                        timeout=s.search_result_wait_timeout,
                    )
                except Exception:
                    return [], effective_query
            else:
                return [], effective_query

        results = await _extract_results(page, n_results)
        logger.info("Found %d results for query: %s", len(results), query)
        return results, effective_query
    finally:
        await page.close()
