from __future__ import annotations

import socket
import sys
import threading
import time

import httpx
import uvicorn

from web_search_service.config import settings


def _get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_until_ready(base_url: str, timeout_s: float = 10.0) -> None:
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            resp = httpx.get(f"{base_url}/health", timeout=0.5)
            if resp.status_code == 200:
                return
        except Exception:
            pass
        if time.monotonic() >= deadline:
            raise RuntimeError("Server did not become ready in time")
        time.sleep(0.1)


def _print_results(data: dict) -> None:
    print(f"\nEffective query: {data['effective_query']}")
    print(f"Results: {data['total_results']}\n")
    for r in data["results"]:
        date_str = f" [{r['date']}]" if r.get("date") else ""
        print(f"  {r['position']}.{date_str} {r['title']}")
        print(f"     {r['url']}")
        if r.get("snippet"):
            print(f"     {r['snippet']}")
        print()


def main() -> None:
    port = _get_free_port()
    base_url = f"http://127.0.0.1:{port}"

    from web_search_service.server import app

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    try:
        _wait_until_ready(base_url)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"DDGS Search CLI (server on port {port}) — type 'quit' to exit")

    try:
        while True:
            try:
                raw = input("ddgs> ").strip()
            except EOFError:
                break

            if not raw:
                continue
            if raw in ("exit", "quit", "q"):
                break

            try:
                resp = httpx.get(
                    f"{base_url}/ddgs/search",
                    params={"query": raw},
                    timeout=settings.ddgs_timeout + 5,
                )
                if resp.status_code == 200:
                    _print_results(resp.json())
                else:
                    detail = resp.json().get("detail", resp.text)
                    print(f"Error ({resp.status_code}): {detail}")
            except Exception as exc:
                print(f"Error: {exc}")
    except KeyboardInterrupt:
        pass

    print("\nBye!")
    server.should_exit = True
