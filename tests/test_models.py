import pytest
from pydantic import ValidationError

from web_search_service.models import (
    ErrorResponse,
    HealthResponse,
    SearchResponse,
    SearchResult,
)


class TestSearchResult:
    def test_valid_result(self):
        r = SearchResult(
            position=1,
            title="Test",
            url="https://example.com",
            snippet="A snippet",
            displayed_url="example.com",
            date="2 hours ago",
        )
        assert r.position == 1
        assert r.date == "2 hours ago"

    def test_date_defaults_to_none(self):
        r = SearchResult(
            position=1, title="T", url="https://x.com", snippet="", displayed_url=""
        )
        assert r.date is None


class TestSearchResponse:
    def test_valid_response(self):
        result = SearchResult(
            position=1, title="T", url="https://x.com", snippet="s", displayed_url="x.com"
        )
        resp = SearchResponse(
            query="test", effective_query="test", results=[result], total_results=1
        )
        assert resp.total_results == 1
        assert len(resp.results) == 1

    def test_serialization_round_trip(self):
        result = SearchResult(
            position=1,
            title="Title",
            url="https://example.com",
            snippet="snippet",
            displayed_url="example.com",
            date="1h ago",
        )
        resp = SearchResponse(
            query="q", effective_query="q", results=[result], total_results=1
        )
        data = resp.model_dump()
        restored = SearchResponse.model_validate(data)
        assert restored == resp

    def test_empty_results(self):
        resp = SearchResponse(
            query="nothing", effective_query="nothing", results=[], total_results=0
        )
        assert resp.results == []


class TestHealthResponse:
    def test_valid(self):
        h = HealthResponse(status="ok", pool_size=5, pool_available=3, pool_in_use=2)
        assert h.status == "ok"


class TestErrorResponse:
    def test_valid(self):
        e = ErrorResponse(detail="something went wrong")
        assert e.detail == "something went wrong"

    def test_missing_detail_raises(self):
        with pytest.raises(ValidationError):
            ErrorResponse()  # type: ignore[call-arg]
