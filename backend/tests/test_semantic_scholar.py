"""Integration tests for Semantic Scholar client."""

import re

import pytest
import httpx

from app.services.semantic_scholar import (
    SemanticScholarClient,
    SemanticScholarAuthError,
    AuthMode,
    normalize_api_key,
    parse_paper_item,
    reset_semantic_scholar_client,
)

SEARCH_PATTERN = re.compile(r".*paper/search.*")


@pytest.fixture(autouse=True)
async def _reset_client():
    await reset_semantic_scholar_client()
    yield
    await reset_semantic_scholar_client()


@pytest.fixture(autouse=True)
def _fast_rate_limit(monkeypatch):
    async def instant_sleep(_):
        return None

    monkeypatch.setattr("app.services.semantic_scholar.asyncio.sleep", instant_sleep)


def test_normalize_api_key_strips_whitespace():
    assert normalize_api_key("  abc123  ") == "abc123"
    assert normalize_api_key("api_key_here") is None
    assert normalize_api_key("") is None
    assert normalize_api_key(None) is None


def test_parse_paper_item_nested_fields():
    item = {
        "paperId": "abc",
        "title": "Test Paper",
        "abstract": "An abstract.",
        "year": 2024,
        "authors": [{"name": "Alice"}, {"name": "Bob"}],
        "externalIds": {"DOI": "10.1/test", "PubMed": "123"},
        "openAccessPdf": {"url": "https://example.com/paper.pdf"},
        "citationCount": 10,
        "influentialCitationCount": 2,
        "isOpenAccess": True,
        "fieldsOfStudy": ["Medicine"],
        "url": "https://semanticscholar.org/paper/abc",
    }
    parsed = parse_paper_item(item)
    assert parsed["paper_id"] == "abc"
    assert parsed["authors"] == ["Alice", "Bob"]
    assert parsed["pdf_url"] == "https://example.com/paper.pdf"
    assert parsed["doi"] == "10.1/test"


@pytest.mark.asyncio
async def test_successful_search(httpx_mock):
    httpx_mock.add_response(
        url=SEARCH_PATTERN,
        json={
            "total": 100,
            "offset": 0,
            "data": [{"paperId": "p1", "title": "Ozempic Study", "abstract": "GLP-1"}],
        },
        headers={"x-ratelimit-remaining": "99"},
    )
    client = SemanticScholarClient("s2k-testkey123456789012345678901234")
    result = await client.search("ozempic", max_results=5)
    await client.close()

    assert result.success
    assert len(result.raw_items) == 1
    assert result.metrics.paper_count == 1


@pytest.mark.asyncio
async def test_invalid_api_key_no_retry(httpx_mock):
    httpx_mock.add_response(url=SEARCH_PATTERN, status_code=403, json={"message": "Forbidden"})
    client = SemanticScholarClient("invalid-key-1234567890123456789012")
    result = await client.search("ozempic", max_results=5)
    await client.close()

    assert not result.success
    assert isinstance(result.error, SemanticScholarAuthError)
    assert client.auth_mode == AuthMode.DISABLED
    assert len(httpx_mock.get_requests()) == 1


@pytest.mark.asyncio
async def test_empty_search_result(httpx_mock):
    httpx_mock.add_response(url=SEARCH_PATTERN, json={"total": 0, "offset": 0, "data": []})
    client = SemanticScholarClient("s2k-testkey123456789012345678901234")
    result = await client.search("totalGarbageNonsenseXYZ", max_results=5)
    await client.close()

    assert not result.success
    assert result.metrics.total_available == 0


@pytest.mark.asyncio
async def test_rate_limit_is_retryable(httpx_mock):
    httpx_mock.add_response(url=SEARCH_PATTERN, status_code=429, json={"message": "Too Many Requests"})
    httpx_mock.add_response(
        url=SEARCH_PATTERN,
        json={"total": 1, "offset": 0, "data": [{"paperId": "p1", "title": "OK"}]},
    )
    client = SemanticScholarClient("s2k-testkey123456789012345678901234")
    result = await client.search("ozempic", max_results=1)
    await client.close()

    assert result.success
    assert result.metrics.retry_count >= 1


@pytest.mark.asyncio
async def test_connect_timeout(httpx_mock):
    httpx_mock.add_exception(httpx.ConnectTimeout("connect timeout"), url=SEARCH_PATTERN)
    client = SemanticScholarClient("s2k-testkey123456789012345678901234")
    result = await client.search("ozempic", max_results=1)
    await client.close()

    assert not result.success
    assert result.error is not None
