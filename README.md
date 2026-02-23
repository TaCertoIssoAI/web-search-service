# TaCertoIssoAI

**TaCertoIssoAI** is a non-profit project dedicated to combating misinformation and educating Brazilians against fake news. Its use of search libraries (Playwright/Camoufox for browser-based search and `ddgs` for lightweight HTTP-based search) is grounded in this mission — enabling automated verification of claims and retrieval of trustworthy sources to help users distinguish reliable information from disinformation.

## Requirements

- Python 3.11+
- Playwright browsers installed

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m playwright install
```

## Run The Server

```bash
web-search-server
```

Or, directly with Python:

```bash
python -m web_search_service.server
```

## Run the Interactive CLI

```bash
ddgs-cli
```

Starts the server in the background and opens a REPL that sends queries to `/ddgs/search`.

## Run With Docker

Build the image:

```bash
docker build -t web-search-service .
```

Run the container:

```bash
docker run --rm -p 6050:6050 web-search-service
```

Verify:

```bash
curl http://127.0.0.1:6050/health
```

## Verify It's Running

```bash
curl http://127.0.0.1:6050/health
```

Expected response (shape):

```json
{"status":"ok","pool_size":5,"pool_available":4,"pool_in_use":1}
```

## Example Search

Browser-based search:

```bash
curl "http://127.0.0.1:6050/search?query=python"
```

Lightweight ddgs search (no browser):

```bash
curl "http://127.0.0.1:6050/ddgs/search?query=python"
```

Optional parameters:

- `domains` (repeatable): `?domains=example.com&domains=foo.com`
- `n_results`: `?n_results=5`

## Server Interface

Base URL: `http://127.0.0.1:6050`

Endpoints:

- `GET /health`
  - Response: JSON with pool stats.
  - Example:
    ```json
    {"status":"ok","pool_size":5,"pool_available":4,"pool_in_use":1}
    ```
- `GET /search`
  - Browser-based DuckDuckGo search via Playwright + Camoufox.
  - Query params:
    - `query` (string, required)
    - `domains` (string, repeatable)
    - `n_results` (int, 1..50)
  - Response (shape):
    ```json
    {
      "query": "python",
      "effective_query": "python",
      "results": [
        {
          "position": 1,
          "title": "Example Title",
          "url": "https://example.com",
          "snippet": "Example snippet",
          "displayed_url": "example.com",
          "date": "2 hours ago"
        }
      ],
      "total_results": 1
    }
    ```
- `GET /ddgs/search`
  - Lightweight DuckDuckGo search via the `ddgs` library (no browser required). Same query params and response shape as `/search`.

## Notes

- The `/search` endpoint opens a browser via Playwright/Camoufox. If DuckDuckGo presents a CAPTCHA, the request will return `429`.
- The `/ddgs/search` endpoint uses pure HTTP requests — no browser overhead, no CAPTCHA issues.
- This project is intended for non-commercial, educational, and public-interest use only.
