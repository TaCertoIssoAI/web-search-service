FROM python:3.11-slim

WORKDIR /app

# System dependencies (build + runtime)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libxml2-dev \
    libxslt-dev \
    libssl-dev \
    libffi-dev \
    libgtk-3-0 \
    libdbus-glib-1-2 \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

# Camoufox browser (patched Firefox) + system deps
RUN python -m playwright install --with-deps firefox && \
    python -m camoufox fetch

# App code
COPY . .

# Non-root user
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PORT=8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

CMD ["uvicorn", "web_search_service.server:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "2"]
