import asyncio
from unittest.mock import MagicMock, patch

import pytest

from web_search_service.ddgs_search import (
    DdgsSearchError,
    _build_effective_query,
    _map_result,
    execute_ddgs_search,
)


class TestBuildEffectiveQuery:
    def test_no_domains(self):
        assert _build_effective_query("python asyncio") == "python asyncio"

    def test_empty_domains(self):
        assert _build_effective_query("python asyncio", []) == "python asyncio"

    def test_single_domain(self):
        result = _build_effective_query("python", ["docs.python.org"])
        assert result == "python site:docs.python.org"

    def test_multiple_domains(self):
        result = _build_effective_query("python", ["a.com", "b.com", "c.com"])
        assert result == "python site:a.com OR site:b.com OR site:c.com"


class TestMapResult:
    def test_maps_fields_correctly(self):
        raw = {
            "title": "Example Title",
            "href": "https://example.com/page?q=1",
            "body": "Some snippet text",
        }
        result = _map_result(1, raw)
        assert result.position == 1
        assert result.title == "Example Title"
        assert result.url == "https://example.com/page?q=1"
        assert result.snippet == "Some snippet text"
        assert result.displayed_url == "example.com"
        assert result.date is None

    def test_missing_fields_default_to_empty(self):
        result = _map_result(3, {})
        assert result.position == 3
        assert result.title == ""
        assert result.url == ""
        assert result.snippet == ""
        assert result.displayed_url == ""
        assert result.date is None

    def test_displayed_url_extracts_hostname(self):
        raw = {"title": "T", "href": "https://sub.domain.org/path", "body": "B"}
        result = _map_result(1, raw)
        assert result.displayed_url == "sub.domain.org"


class TestExecuteDdgsSearch:
    async def test_returns_mapped_results(self):
        fake_raw = [
            {"title": "R1", "href": "https://a.com/1", "body": "Snippet 1"},
            {"title": "R2", "href": "https://b.com/2", "body": "Snippet 2"},
        ]
        with patch(
            "web_search_service.ddgs_search._run_ddgs_search", return_value=fake_raw
        ):
            results, effective_query = await execute_ddgs_search("test query")

        assert len(results) == 2
        assert effective_query == "test query"
        assert results[0].position == 1
        assert results[0].title == "R1"
        assert results[0].url == "https://a.com/1"
        assert results[1].position == 2
        assert results[1].snippet == "Snippet 2"

    async def test_domain_filtering_in_effective_query(self):
        with patch(
            "web_search_service.ddgs_search._run_ddgs_search", return_value=[]
        ) as mock_run:
            _, effective_query = await execute_ddgs_search(
                "test", domains=["x.com", "y.com"]
            )

        assert effective_query == "test site:x.com OR site:y.com"
        assert mock_run.call_args[0][0] == "test site:x.com OR site:y.com"

    async def test_empty_results(self):
        with patch(
            "web_search_service.ddgs_search._run_ddgs_search", return_value=[]
        ):
            results, _ = await execute_ddgs_search("nothing")

        assert results == []

    async def test_exception_raises_ddgs_search_error(self):
        with patch(
            "web_search_service.ddgs_search._run_ddgs_search",
            side_effect=RuntimeError("network error"),
        ):
            with pytest.raises(DdgsSearchError, match="network error"):
                await execute_ddgs_search("fail")

    async def test_semaphore_limits_concurrency(self):
        semaphore = asyncio.Semaphore(1)
        with patch(
            "web_search_service.ddgs_search._run_ddgs_search", return_value=[]
        ):
            results, _ = await execute_ddgs_search(
                "test", semaphore=semaphore
            )
        assert results == []
