"""
Production-grade Semantic Scholar Academic Graph API client.

Spec: https://api.semanticscholar.org/api-docs/graph
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://api.semanticscholar.org/graph/v1"
SEARCH_PATH = "/paper/search"
USER_AGENT = "LHAS/1.0 (research-mission-dashboard; +https://github.com/lhas)"

# Fields valid for GET /paper/search (no openAccessPdf.url — returns 400 on search).
DEFAULT_SEARCH_FIELDS = (
    "paperId,corpusId,externalIds,title,abstract,year,venue,"
    "publicationDate,authors,citationCount,influentialCitationCount,"
    "isOpenAccess,openAccessPdf,fieldsOfStudy,url"
)

# Transient HTTP status codes eligible for retry.
_RETRYABLE_STATUS = frozenset({408, 429, 500, 502, 503, 504})
# Never retry these — auth/permission/client errors.
_NON_RETRYABLE_STATUS = frozenset({400, 401, 403, 404, 405, 410, 422})


class SemanticScholarError(Exception):
    """Base error for Semantic Scholar integration."""

    def __init__(self, message: str, *, status_code: Optional[int] = None, body: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class SemanticScholarAuthError(SemanticScholarError):
    """API key missing, invalid, or forbidden."""


class SemanticScholarRateLimitError(SemanticScholarError):
    """Rate limit exceeded after retries."""


class SemanticScholarNetworkError(SemanticScholarError):
    """DNS, connect, read, or SSL failure."""


class SemanticScholarResponseError(SemanticScholarError):
    """Unexpected response shape or server error."""


class AuthMode(str, Enum):
    AUTHENTICATED = "authenticated"
    UNAUTHENTICATED = "unauthenticated"
    DISABLED = "disabled"  # key configured but rejected — do not retry unauth with bad key state


@dataclass
class RequestMetrics:
    url: str = ""
    status_code: Optional[int] = None
    latency_ms: float = 0.0
    retry_count: int = 0
    response_bytes: int = 0
    paper_count: int = 0
    total_available: Optional[int] = None
    rate_limit_remaining: Optional[str] = None
    rate_limit_limit: Optional[str] = None
    retry_after: Optional[str] = None
    auth_mode: AuthMode = AuthMode.UNAUTHENTICATED
    error: Optional[str] = None


@dataclass
class SearchResult:
    """Outcome of a search — never silently empty without metadata."""

    papers: List[Any] = field(default_factory=list)  # PaperObject instances filled by caller
    raw_items: List[dict] = field(default_factory=list)
    metrics: RequestMetrics = field(default_factory=RequestMetrics)
    success: bool = False
    error: Optional[SemanticScholarError] = None
    query: str = ""


def normalize_api_key(raw: Optional[str]) -> Optional[str]:
    """Strip whitespace/newlines and reject placeholders."""
    if raw is None:
        return None
    key = raw.strip()
    if not key:
        return None
    placeholders = frozenset({
        "api_key_here", "your_key", "your_api_key_here",
    })
    if key.lower() in placeholders:
        return None
    return key


def _redact_headers(headers: Dict[str, str]) -> Dict[str, str]:
    out = {}
    for k, v in headers.items():
        if k.lower() == "x-api-key":
            out[k] = f"***{v[-4:]}" if len(v) >= 4 else "***"
        else:
            out[k] = v
    return out


def _backoff_seconds(attempt: int, retry_after: Optional[str] = None) -> float:
    if retry_after:
        try:
            return float(retry_after) + random.uniform(0.1, 0.5)
        except ValueError:
            pass
    base = min(60.0, 1.0 * (2 ** attempt))
    return base + random.uniform(0.0, 0.5)


class SemanticScholarClient:
    """
    Async Semantic Scholar Graph API client.

    - Shared httpx connection pool (one client per instance)
    - Explicit timeouts (connect/read/write/pool — not inflated)
    - Retries only transient failures (429, 5xx, timeouts)
    - Never retries 401/403/404
    - Structured logging with redacted secrets
    """

    MAX_RETRIES = 3
    PAGE_LIMIT = 100

    def __init__(self, api_key: Optional[str] = None):
        self._api_key = normalize_api_key(api_key)
        self._auth_mode = AuthMode.AUTHENTICATED if self._api_key else AuthMode.UNAUTHENTICATED
        self._key_validated = False
        self._key_invalid = False

        self._timeout = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)
        self._client: Optional[httpx.AsyncClient] = None
        self._request_lock = asyncio.Lock()  # enforce 1 RPS for authenticated keys

    @property
    def auth_mode(self) -> AuthMode:
        return self._auth_mode

    @property
    def api_key_configured(self) -> bool:
        return self._api_key is not None

    @property
    def api_key_invalid(self) -> bool:
        return self._key_invalid

    def _build_headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }
        if self._api_key and self._auth_mode == AuthMode.AUTHENTICATED:
            headers["x-api-key"] = self._api_key
        return headers

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=BASE_URL,
                timeout=self._timeout,
                follow_redirects=True,
                http2=False,
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
                headers={"User-Agent": USER_AGENT},
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def validate_key(self) -> RequestMetrics:
        """Smoke-test authentication with a minimal search."""
        result = await self._execute_search("machine learning", limit=1, offset=0)
        return result.metrics

    async def search(
        self,
        query: str,
        max_results: int = 100,
        *,
        fields: Optional[str] = None,
        year_filter: Optional[str] = None,
        open_access_only: bool = False,
    ) -> SearchResult:
        """
        Search papers with pagination until max_results or API exhausted.

        Raises nothing — returns SearchResult with error populated on failure.
        """
        query = (query or "").strip()
        if not query:
            metrics = RequestMetrics(auth_mode=self._auth_mode, error="empty_query")
            return SearchResult(
                success=False,
                query=query,
                metrics=metrics,
                error=SemanticScholarResponseError("Empty search query"),
            )

        if self._auth_mode == AuthMode.DISABLED:
            metrics = RequestMetrics(auth_mode=self._auth_mode, error="auth_disabled")
            return SearchResult(
                success=False,
                query=query,
                metrics=metrics,
                error=SemanticScholarAuthError(
                    "Semantic Scholar API key is invalid — source disabled for this session. "
                    "Update SEMANTIC_SCHOLAR_API_KEY in root .env and recreate the backend container."
                ),
            )

        fields = fields or DEFAULT_SEARCH_FIELDS
        collected: List[dict] = []
        offset = 0
        total_available: Optional[int] = None
        aggregate_metrics = RequestMetrics(auth_mode=self._auth_mode)
        last_error: Optional[SemanticScholarError] = None

        while len(collected) < max_results:
            page_limit = min(self.PAGE_LIMIT, max_results - len(collected))
            page = await self._execute_search(
                query,
                limit=page_limit,
                offset=offset,
                fields=fields,
                year_filter=year_filter,
                open_access_only=open_access_only,
            )
            aggregate_metrics.retry_count += page.metrics.retry_count
            if page.metrics.latency_ms:
                aggregate_metrics.latency_ms += page.metrics.latency_ms
            aggregate_metrics.rate_limit_remaining = page.metrics.rate_limit_remaining
            aggregate_metrics.rate_limit_limit = page.metrics.rate_limit_limit

            if not page.success:
                last_error = page.error
                aggregate_metrics.error = page.metrics.error
                break

            total_available = page.metrics.total_available
            batch = page.raw_items
            if not batch:
                break

            collected.extend(batch)
            offset += len(batch)

            if total_available is not None and offset >= total_available:
                break
            if len(batch) < page_limit:
                break

        aggregate_metrics.paper_count = len(collected)
        aggregate_metrics.total_available = total_available
        aggregate_metrics.response_bytes = sum(len(str(p)) for p in collected[:5])

        if collected:
            logger.info(
                "semantic_scholar.search ok query=%r papers=%d total=%s auth=%s latency_ms=%.0f retries=%d",
                query[:60],
                len(collected),
                total_available,
                self._auth_mode.value,
                aggregate_metrics.latency_ms,
                aggregate_metrics.retry_count,
            )
            return SearchResult(
                success=True,
                query=query,
                raw_items=collected,
                metrics=aggregate_metrics,
            )

        return SearchResult(
            success=False,
            query=query,
            raw_items=[],
            metrics=aggregate_metrics,
            error=last_error or SemanticScholarResponseError(f"No papers returned for query '{query}'"),
        )

    async def _execute_search(
        self,
        query: str,
        *,
        limit: int,
        offset: int = 0,
        fields: str = DEFAULT_SEARCH_FIELDS,
        year_filter: Optional[str] = None,
        open_access_only: bool = False,
    ) -> SearchResult:
        params: Dict[str, Any] = {
            "query": query,
            "limit": min(limit, self.PAGE_LIMIT),
            "offset": offset,
            "fields": fields,
        }
        if year_filter:
            params["year"] = year_filter
        if open_access_only:
            params["openAccessPdf"] = ""

        headers = self._build_headers()
        metrics = RequestMetrics(
            url=f"{BASE_URL}{SEARCH_PATH}",
            auth_mode=self._auth_mode,
        )

        last_exc: Optional[SemanticScholarError] = None

        for attempt in range(self.MAX_RETRIES + 1):
            try:
                if self._auth_mode == AuthMode.AUTHENTICATED:
                    async with self._request_lock:
                        await asyncio.sleep(1.05)
                        return await self._send_request(SEARCH_PATH, params, headers, metrics)
                async with self._request_lock:
                    await asyncio.sleep(5.0)
                    return await self._send_request(SEARCH_PATH, params, headers, metrics)
            except SemanticScholarRateLimitError as e:
                last_exc = e
                metrics.retry_after = metrics.retry_after or getattr(e, "retry_after", None)
                if attempt < self.MAX_RETRIES:
                    wait = _backoff_seconds(attempt, metrics.retry_after)
                    logger.warning(
                        "semantic_scholar retry query=%r attempt=%d wait=%.1fs reason=%s",
                        query[:40], attempt + 1, wait, e,
                    )
                    metrics.retry_count += 1
                    await asyncio.sleep(wait)
                    continue
                break
            except SemanticScholarError as e:
                last_exc = e
                break
            except Exception as e:
                last_exc = SemanticScholarNetworkError(str(e))
                break

        err = last_exc or SemanticScholarNetworkError("Request failed after retries")
        metrics.error = str(err)
        return SearchResult(
            success=False,
            query=query,
            metrics=metrics,
            error=err,
        )

    async def _send_request(
        self,
        path: str,
        params: Dict[str, Any],
        headers: Dict[str, str],
        metrics: RequestMetrics,
    ) -> SearchResult:
        client = await self._get_client()
        t0 = time.perf_counter()

        logger.debug(
            "semantic_scholar.request path=%s auth=%s headers=%s params=%s",
            path,
            self._auth_mode.value,
            _redact_headers(headers),
            {k: (v[:60] + "..." if k == "query" and isinstance(v, str) and len(v) > 60 else v) for k, v in params.items()},
        )

        try:
            response = await client.get(path, params=params, headers=headers)
            metrics.latency_ms = (time.perf_counter() - t0) * 1000
            metrics.status_code = response.status_code
            metrics.response_bytes = len(response.content)
            metrics.rate_limit_remaining = response.headers.get("x-ratelimit-remaining")
            metrics.rate_limit_limit = response.headers.get("x-ratelimit-limit")
            metrics.retry_after = response.headers.get("retry-after")

            logger.info(
                "semantic_scholar.response status=%d latency_ms=%.0f bytes=%d auth=%s "
                "rate_remaining=%s retry_after=%s",
                response.status_code,
                metrics.latency_ms,
                metrics.response_bytes,
                self._auth_mode.value,
                metrics.rate_limit_remaining,
                metrics.retry_after,
            )

            if response.status_code == 200:
                data = response.json()
                items = data.get("data") or []
                metrics.total_available = data.get("total")
                metrics.paper_count = len(items)
                self._key_validated = True
                return SearchResult(success=True, raw_items=items, metrics=metrics)

            body = response.text[:500]
            metrics.error = f"HTTP {response.status_code}: {body}"

            if response.status_code in _NON_RETRYABLE_STATUS:
                if response.status_code in (401, 403):
                    self._handle_auth_failure(response.status_code, body)
                    raise SemanticScholarAuthError(
                        f"Semantic Scholar authentication failed ({response.status_code}): {body}",
                        status_code=response.status_code,
                        body=body,
                    )
                if response.status_code == 404:
                    raise SemanticScholarResponseError(
                        f"Semantic Scholar resource not found: {body}",
                        status_code=404,
                        body=body,
                    )
                raise SemanticScholarResponseError(
                    f"Semantic Scholar client error ({response.status_code}): {body}",
                    status_code=response.status_code,
                    body=body,
                )

            if response.status_code in _RETRYABLE_STATUS:
                raise SemanticScholarRateLimitError(
                    f"Semantic Scholar transient error ({response.status_code}): {body}",
                    status_code=response.status_code,
                    body=body,
                )

            raise SemanticScholarResponseError(
                f"Semantic Scholar unexpected status ({response.status_code}): {body}",
                status_code=response.status_code,
                body=body,
            )

        except httpx.ConnectTimeout as e:
            metrics.latency_ms = (time.perf_counter() - t0) * 1000
            metrics.error = f"ConnectTimeout: {e}"
            logger.error("semantic_scholar ConnectTimeout query=%r", params.get("query", "")[:40])
            raise SemanticScholarNetworkError(f"Connect timeout: {e}") from e
        except httpx.ReadTimeout as e:
            metrics.latency_ms = (time.perf_counter() - t0) * 1000
            metrics.error = f"ReadTimeout: {e}"
            logger.error("semantic_scholar ReadTimeout query=%r", params.get("query", "")[:40])
            raise SemanticScholarNetworkError(f"Read timeout: {e}") from e
        except httpx.NetworkError as e:
            metrics.latency_ms = (time.perf_counter() - t0) * 1000
            metrics.error = f"NetworkError: {e}"
            logger.error("semantic_scholar NetworkError: %s", e)
            raise SemanticScholarNetworkError(str(e)) from e
        except SemanticScholarError:
            raise
        except Exception as e:
            metrics.latency_ms = (time.perf_counter() - t0) * 1000
            metrics.error = f"{type(e).__name__}: {e}"
            raise SemanticScholarNetworkError(str(e)) from e

    def _handle_auth_failure(self, status_code: int, body: str) -> None:
        if not self._api_key:
            return
        self._key_invalid = True
        self._auth_mode = AuthMode.DISABLED
        logger.error(
            "semantic_scholar.auth_failed status=%d body=%s "
            "Check SEMANTIC_SCHOLAR_API_KEY in root .env — "
            "host environment variables override .env when docker-compose uses ${VAR} interpolation.",
            status_code,
            body[:200],
        )


def parse_paper_item(item: dict) -> dict:
    """Normalize a raw S2 paper JSON object into connector fields."""
    external_ids = item.get("externalIds") or {}
    authors_raw = item.get("authors") or []
    authors = []
    for a in authors_raw:
        if isinstance(a, dict):
            name = a.get("name")
            if name:
                authors.append(name)
        elif isinstance(a, str):
            authors.append(a)

    oa_pdf = item.get("openAccessPdf") or {}
    pdf_url = oa_pdf.get("url") if isinstance(oa_pdf, dict) else None

    return {
        "paper_id": item.get("paperId"),
        "title": item.get("title") or "",
        "abstract": item.get("abstract") or "",
        "year": item.get("year"),
        "authors": authors,
        "doi": external_ids.get("DOI"),
        "pubmed_id": external_ids.get("PubMed"),
        "arxiv_id": external_ids.get("ArXiv"),
        "url": item.get("url"),
        "pdf_url": pdf_url,
        "is_open_access": item.get("isOpenAccess"),
        "venue": item.get("venue"),
        "citations_count": item.get("citationCount"),
        "influential_citation_count": item.get("influentialCitationCount"),
        "fields_of_study": item.get("fieldsOfStudy") or [],
    }


# Module-level singleton for connection reuse across ingestion
_client_singleton: Optional[SemanticScholarClient] = None
_client_lock = asyncio.Lock()


async def get_semantic_scholar_client(api_key: Optional[str] = None) -> SemanticScholarClient:
    global _client_singleton
    async with _client_lock:
        if _client_singleton is None:
            _client_singleton = SemanticScholarClient(api_key)
        return _client_singleton


async def reset_semantic_scholar_client() -> None:
    """Close and clear singleton (for tests)."""
    global _client_singleton
    async with _client_lock:
        if _client_singleton:
            await _client_singleton.close()
        _client_singleton = None
