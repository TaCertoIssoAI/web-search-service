from io import StringIO
from unittest.mock import patch

from web_search_service.cli import _parse_input, _print_results
from web_search_service.models import SearchResult


class TestParseInput:
    def test_basic_query(self):
        query, domains, n = _parse_input("python asyncio tutorial")
        assert query == "python asyncio tutorial"
        assert domains == []
        assert n == 10

    def test_with_domains(self):
        query, domains, n = _parse_input("test --domains reddit.com,stackoverflow.com")
        assert query == "test"
        assert domains == ["reddit.com", "stackoverflow.com"]

    def test_with_n_results(self):
        query, domains, n = _parse_input("test --n 5")
        assert query == "test"
        assert n == 5

    def test_combined_options(self):
        query, domains, n = _parse_input("web scraping --domains github.com --n 3")
        assert query == "web scraping"
        assert domains == ["github.com"]
        assert n == 3

    def test_quoted_strings(self):
        query, domains, n = _parse_input('"exact phrase search"')
        assert query == "exact phrase search"


class TestPrintResults:
    def test_output_format(self):
        results = [
            SearchResult(
                position=1,
                title="Test Title",
                url="https://example.com",
                snippet="A test snippet",
                displayed_url="example.com",
                date="2 hours ago",
            ),
            SearchResult(
                position=2,
                title="No Date Title",
                url="https://example.com/2",
                snippet="",
                displayed_url="example.com/2",
            ),
        ]
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            _print_results(results, "test query")
            output = mock_stdout.getvalue()

        assert "Effective query: test query" in output
        assert "Results: 2" in output
        assert "1. [2 hours ago] Test Title" in output
        assert "https://example.com" in output
        assert "A test snippet" in output
        assert "2. No Date Title" in output

    def test_empty_results(self):
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            _print_results([], "empty query")
            output = mock_stdout.getvalue()

        assert "Results: 0" in output
