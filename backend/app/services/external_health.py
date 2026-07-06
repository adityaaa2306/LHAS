"""
External service health probes — shared by /health/external and verify_api_keys.

Performs live integration checks with strict Semantic Scholar field validation
to detect silent API schema regressions.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.config import settings

logger = logging.getLogger(__name__)

DEFAULT_S2_PROBE_QUERIES = ("ozempic", "diabetes", "covid")
STARTUP_S2_PROBE_QUERY = "machine learning"


@dataclass
class PaperFieldValidation:
    """Result of validating one paper's required fields."""

    paper_id: str
    query: str
    missing_fields: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.missing_fields) == 0


# Per-paper fields that must always be present (API schema contract).
_PER_PAPER_REQUIRED = ("title", "authors", "publication_year", "citation_count")

# Fields that may be absent on individual papers but must appear on most results.
_BATCH_THRESHOLD_FIELDS = {
    "abstract": 0.6,
    "doi": 0.8,
}


def _per_paper_missing(parsed: dict) -> List[str]:
    """Return missing structural fields for a single paper."""
    missing: List[str] = []
    if not (parsed.get("title") or "").strip():
        missing.append("title")
    if not parsed.get("authors"):
        missing.append("authors")
    if parsed.get("year") is None:
        missing.append("publication_year")
    if parsed.get("citations_count") is None:
        missing.append("citation_count")
    if parsed.get("is_open_access") is True and not (parsed.get("pdf_url") or "").strip():
        missing.append("open_access_pdf")
    return missing


def validate_s2_paper_fields(parsed: dict) -> List[str]:
    """
    Strict per-paper validation (all fields including abstract and doi).

    Used in unit tests; probes use validate_s2_query_batch for realistic thresholds.
    """
    missing = _per_paper_missing(parsed)
    if not (parsed.get("abstract") or "").strip():
        missing.append("abstract")
    if not (parsed.get("doi") or "").strip():
        missing.append("doi")
    return missing


def validate_s2_query_batch(parsed_papers: List[dict]) -> List[str]:
    """
    Validate a batch of papers from one search query.

    - title, authors, year, citation_count: required on every paper
    - abstract, doi: required on >= 80% of papers (catches API regressions, allows sparse records)
    - open_access_pdf: required when is_open_access is True
    """
    if not parsed_papers:
        return ["no_papers"]

    issues: List[str] = []
    n = len(parsed_papers)

    for i, parsed in enumerate(parsed_papers):
        for field in _per_paper_missing(parsed):
            pid = parsed.get("paper_id") or f"index_{i}"
            issues.append(f"paper {pid}: missing {field}")

    for field, min_ratio in _BATCH_THRESHOLD_FIELDS.items():
        if field == "abstract":
            present = sum(1 for p in parsed_papers if (p.get("abstract") or "").strip())
        else:
            present = sum(1 for p in parsed_papers if (p.get("doi") or "").strip())
        ratio = present / n
        if ratio < min_ratio:
            issues.append(
                f"{field} present on only {present}/{n} papers "
                f"({ratio:.0%} < required {min_ratio:.0%})"
            )

    return issues


def _parse_rate_limit_remaining(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _status_from_ok(ok: bool, *, configured: bool = True, degraded: bool = False) -> str:
    if not configured:
        return "missing"
    if ok and not degraded:
        return "healthy"
    if degraded:
        return "degraded"
    return "unhealthy"


async def probe_semantic_scholar(
    *,
    queries: tuple[str, ...] = DEFAULT_S2_PROBE_QUERIES,
    max_results_per_query: int = 5,
    strict_field_validation: bool = True,
) -> Dict[str, Any]:
    from app.services.semantic_scholar import (
        AuthMode,
        SemanticScholarClient,
        normalize_api_key,
        parse_paper_item,
    )

    key = normalize_api_key(settings.SEMANTIC_SCHOLAR_API_KEY)
    if not key:
        return {
            "status": "missing",
            "authenticated": False,
            "latency_ms": 0,
            "remaining_requests": None,
            "papers_checked": 0,
            "field_validation_failures": [],
            "error": "SEMANTIC_SCHOLAR_API_KEY not configured",
        }

    client = SemanticScholarClient(key)
    latencies: List[float] = []
    remaining: Optional[int] = None
    field_failures: List[Dict[str, Any]] = []
    papers_checked = 0
    searches_ok = 0
    last_error: Optional[str] = None
    query_results: Dict[str, Dict[str, Any]] = {}

    try:
        for query in queries:
            result = await client.search(query, max_results=max_results_per_query)
            latencies.append(result.metrics.latency_ms)
            parsed_remaining = _parse_rate_limit_remaining(result.metrics.rate_limit_remaining)
            if parsed_remaining is not None:
                remaining = parsed_remaining

            if not result.success:
                last_error = str(result.error)
                query_results[query] = {"status": "failed", "papers": 0, "error": last_error}
                continue

            if not result.raw_items:
                last_error = f"No papers returned for query '{query}'"
                query_results[query] = {"status": "failed", "papers": 0, "error": last_error}
                continue

            searches_ok += 1

            if not strict_field_validation:
                papers_checked += len(result.raw_items)
                query_results[query] = {
                    "status": "ok",
                    "papers": len(result.raw_items),
                    "total_in_index": result.metrics.total_available,
                }
                continue

            parsed_batch = [parse_paper_item(item) for item in result.raw_items]
            papers_checked += len(parsed_batch)
            batch_issues = validate_s2_query_batch(parsed_batch)

            if batch_issues:
                for issue in batch_issues:
                    field_failures.append({"query": query, "issue": issue})
                query_results[query] = {
                    "status": "field_validation_failed",
                    "papers": len(parsed_batch),
                    "total_in_index": result.metrics.total_available,
                    "issues": batch_issues,
                }
            else:
                query_results[query] = {
                    "status": "ok",
                    "papers": len(parsed_batch),
                    "total_in_index": result.metrics.total_available,
                    "fields_validated": [
                        "title", "authors", "publication_year", "citation_count",
                        "abstract (>=60%)", "doi (>=80%)", "open_access_pdf (when applicable)",
                    ],
                }
    finally:
        await client.close()

    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
    authenticated = client.auth_mode == AuthMode.AUTHENTICATED

    fields_ok = strict_field_validation and not field_failures
    searches_ok_enough = searches_ok == len(queries)
    ok = searches_ok_enough and fields_ok and authenticated

    degraded = (
        searches_ok > 0
        and (not searches_ok_enough or not fields_ok)
        and client.auth_mode != AuthMode.DISABLED
    )

    payload: Dict[str, Any] = {
        "status": _status_from_ok(ok, degraded=degraded),
        "latency_ms": round(avg_latency, 1),
        "authenticated": authenticated,
        "remaining_requests": remaining,
        "papers_checked": papers_checked,
        "searches_succeeded": searches_ok,
        "searches_expected": len(queries),
        "queries": query_results,
    }

    if field_failures:
        payload["field_validation_failures"] = field_failures
    if last_error and not ok:
        payload["error"] = last_error

    return payload


async def probe_pubmed(*, query: str = "ozempic", max_results: int = 5) -> Dict[str, Any]:
    if not settings.PUBMED_API_KEY:
        return {
            "status": "missing",
            "latency_ms": 0,
            "papers_retrieved": 0,
            "error": "PUBMED_API_KEY not configured",
        }

    from app.services.paper_ingestion import PubMedConnector

    t0 = time.perf_counter()
    try:
        pub = PubMedConnector(settings.PUBMED_API_KEY)
        papers = await pub.search(query, max_results)
        ms = (time.perf_counter() - t0) * 1000
        count = len(papers)
        ok = count > 0
        return {
            "status": _status_from_ok(ok, degraded=not ok),
            "latency_ms": round(ms, 1),
            "papers_retrieved": count,
        }
    except Exception as e:
        ms = (time.perf_counter() - t0) * 1000
        logger.warning("PubMed health probe failed: %s", e)
        return {
            "status": "unhealthy",
            "latency_ms": round(ms, 1),
            "papers_retrieved": 0,
            "error": str(e),
        }


async def probe_embedding() -> Dict[str, Any]:
    if not settings.EMBEDDING_MODEL_API_KEY:
        return {
            "status": "missing",
            "latency_ms": 0,
            "dimension": None,
            "model": settings.EMBEDDING_MODEL_NAME,
            "error": "EMBEDDING_MODEL_API_KEY not configured",
        }

    from openai import AsyncOpenAI

    t0 = time.perf_counter()
    try:
        client = AsyncOpenAI(
            api_key=settings.EMBEDDING_MODEL_API_KEY,
            base_url=settings.EMBEDDING_BASE_URL,
        )
        response = await client.embeddings.create(
            input=["health probe"],
            model=settings.EMBEDDING_MODEL_NAME,
            encoding_format="float",
            extra_body={
                "modality": ["text"],
                "input_type": "query",
                "truncate": "NONE",
            },
        )
        ms = (time.perf_counter() - t0) * 1000
        dim = len(response.data[0].embedding)
        return {
            "status": _status_from_ok(dim > 0),
            "latency_ms": round(ms, 1),
            "dimension": dim,
            "model": settings.EMBEDDING_MODEL_NAME,
        }
    except Exception as e:
        ms = (time.perf_counter() - t0) * 1000
        logger.warning("Embedding health probe failed: %s", e)
        return {
            "status": "unhealthy",
            "latency_ms": round(ms, 1),
            "dimension": None,
            "model": settings.EMBEDDING_MODEL_NAME,
            "error": str(e),
        }


async def probe_all_external_services(
    *,
    full_s2_validation: bool = True,
    s2_queries: tuple[str, ...] = DEFAULT_S2_PROBE_QUERIES,
) -> Dict[str, Any]:
    """Run all external probes and return aggregated health payload."""
    s2 = await probe_semantic_scholar(
        queries=s2_queries,
        strict_field_validation=full_s2_validation,
    )
    pubmed = await probe_pubmed()
    embedding = await probe_embedding()

    statuses = [s2["status"], pubmed["status"], embedding["status"]]
    if any(s == "unhealthy" for s in statuses):
        overall = "unhealthy"
    elif any(s in ("degraded", "missing") for s in statuses):
        overall = "degraded"
    else:
        overall = "healthy"

    return {
        "status": overall,
        "semanticScholar": s2,
        "pubmed": pubmed,
        "embedding": embedding,
    }


def external_health_http_status(payload: Dict[str, Any]) -> int:
    """Map probe result to HTTP status code."""
    overall = payload.get("status", "unhealthy")
    if overall == "healthy":
        return 200
    if overall == "degraded":
        return 200  # deps partially available — still report in body
    return 503
