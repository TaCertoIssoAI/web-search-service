# Web Search Service

FastAPI service that performs DuckDuckGo searches using Playwright/Camoufox and returns structured results.

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

## Verify It’s Running

```bash
curl http://127.0.0.1:6050/health
```

Expected response (shape):

```json
{"status":"ok","pool_size":5,"pool_available":4,"pool_in_use":1}
```

## Example Search

```bash
curl "http://127.0.0.1:6050/search?query=python"
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

## Notes

- The server will open a browser via Playwright/Camoufox.
- If DuckDuckGo presents a CAPTCHA, the request will return `429`.
