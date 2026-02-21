from pydantic import BaseModel


class SearchResult(BaseModel):
    position: int
    title: str
    url: str
    snippet: str
    displayed_url: str
    date: str | None = None


class SearchResponse(BaseModel):
    query: str
    effective_query: str
    results: list[SearchResult]
    total_results: int


class HealthResponse(BaseModel):
    status: str
    pool_size: int
    pool_available: int
    pool_in_use: int


class ErrorResponse(BaseModel):
    detail: str
