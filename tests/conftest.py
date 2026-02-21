import pytest

from web_search_service.config import Settings

SAMPLE_SERP_HTML = """\
<html><body>
<article data-testid="result">
    <a data-testid="result-title-a" href="https://example.com/result1">First Result Title</a>
    <a data-testid="result-extras-url-link" href="https://example.com/result1"><span>example.com</span></a>
    <div data-testid="result-snippet">This is the first snippet with some text.</div>
    <time datetime="2025-01-01T00:00:00Z">2 hours ago</time>
</article>
<article data-testid="result">
    <a data-testid="result-title-a" href="https://example.com/result2">Second Result Title</a>
    <a data-testid="result-extras-url-link" href="https://example.com/result2"><span>example.com/page2</span></a>
    <div data-testid="result-snippet">This is the second snippet.</div>
</article>
<article data-testid="result">
    <a data-testid="result-title-a" href="https://example.com/result3">Third Result Title</a>
    <a data-testid="result-extras-url-link" href="https://example.com/result3"><span>example.com/page3</span></a>
    <div data-testid="result-snippet">Third snippet using result-snippet testid.</div>
    <time datetime="2025-01-01T00:00:00Z">1 day ago</time>
</article>
<article data-testid="result">
    <span>No title or link here</span>
</article>
</body></html>
"""


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        browser_pool_size=2,
        browser_headless=True,
        context_acquire_timeout=5.0,
        min_action_delay=0.0,
        max_action_delay=0.0,
    )


@pytest.fixture
def sample_serp_html() -> str:
    return SAMPLE_SERP_HTML
