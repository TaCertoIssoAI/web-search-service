from __future__ import annotations

import argparse
import asyncio
import shlex
import sys

from web_search_service.browser_pool import BrowserContextPool
from web_search_service.config import Settings
from web_search_service.models import SearchResult
from web_search_service.search import execute_search


def _parse_input(raw: str) -> tuple[str, list[str], int]:
    tokens = shlex.split(raw)
    query_parts: list[str] = []
    domains: list[str] = []
    n_results = 10
    i = 0
    while i < len(tokens):
        if tokens[i] == "--domains" and i + 1 < len(tokens):
            domains = [d.strip() for d in tokens[i + 1].split(",") if d.strip()]
            i += 2
        elif tokens[i] == "--n" and i + 1 < len(tokens):
            n_results = int(tokens[i + 1])
            i += 2
        else:
            query_parts.append(tokens[i])
            i += 1
    return " ".join(query_parts), domains, n_results


def _print_results(results: list[SearchResult], effective_query: str) -> None:
    print(f"\nEffective query: {effective_query}")
    print(f"Results: {len(results)}\n")
    for r in results:
        date_str = f" [{r.date}]" if r.date else ""
        print(f"  {r.position}.{date_str} {r.title}")
        print(f"     {r.url}")
        if r.snippet:
            print(f"     {r.snippet}")
        print()


async def _run(headless: bool) -> None:
    pool_settings = Settings(browser_pool_size=1, browser_headless=headless)
    pool = BrowserContextPool(settings=pool_settings)
    await pool.start()

    mode = "headless" if headless else "visible browser"
    print(f"Web Search CLI ({mode}) — type 'help' for usage, 'quit' to exit")
    try:
        while True:
            try:
                raw = input("search> ").strip()
            except EOFError:
                break

            if not raw:
                continue
            if raw in ("exit", "quit", "q"):
                break
            if raw == "help":
                print("Usage: <query> [--domains d1,d2] [--n 5]")
                print("Commands: help, exit/quit/q")
                continue

            try:
                query, domains, n_results = _parse_input(raw)
            except ValueError as exc:
                print(f"Parse error: {exc}")
                continue

            if not query:
                print("Please provide a search query.")
                continue

            try:
                async with pool.context() as ctx:
                    results, effective_query = await execute_search(
                        ctx, query, domains=domains, n_results=n_results, settings=pool_settings
                    )
                _print_results(results, effective_query)
            except Exception as exc:
                print(f"Error: {exc}")
    finally:
        await pool.shutdown()


def main() -> None:
    parser = argparse.ArgumentParser(description="Web Search CLI")
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="Run browser in visible mode (for debugging)",
    )
    args = parser.parse_args()

    try:
        asyncio.run(_run(headless=not args.no_headless))
    except KeyboardInterrupt:
        print("\nBye!")
        sys.exit(0)
