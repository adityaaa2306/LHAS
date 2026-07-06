"""Validate external API keys at startup using real integration probes."""

import logging
from typing import Dict

from app.services.external_health import STARTUP_S2_PROBE_QUERY, probe_semantic_scholar, probe_pubmed, probe_embedding

logger = logging.getLogger(__name__)


async def validate_api_keys() -> Dict[str, str]:
    """
    Run integration checks against configured external APIs.
    Returns status map: service -> 'ok' | 'missing' | 'invalid' | 'error' | 'degraded'.
    """
    results: Dict[str, str] = {}

    s2 = await probe_semantic_scholar(
        queries=(STARTUP_S2_PROBE_QUERY,),
        max_results_per_query=1,
        strict_field_validation=True,
    )
    s2_status = s2.get("status", "unhealthy")
    if s2_status == "healthy":
        results["semantic_scholar"] = "ok"
        logger.info(
            "Semantic Scholar OK auth=%s latency_ms=%s",
            s2.get("authenticated"),
            s2.get("latency_ms"),
        )
    elif s2_status == "missing":
        results["semantic_scholar"] = "missing"
        logger.warning("SEMANTIC_SCHOLAR_API_KEY not configured — S2 retrieval disabled")
    elif s2_status == "degraded":
        results["semantic_scholar"] = "degraded"
        if s2.get("field_validation_failures"):
            logger.warning(
                "Semantic Scholar field validation failed at startup: %s",
                s2["field_validation_failures"],
            )
        else:
            logger.warning("Semantic Scholar degraded at startup: %s", s2.get("error"))
    else:
        err = s2.get("error", "")
        if "403" in err or "401" in err or not s2.get("authenticated"):
            results["semantic_scholar"] = "invalid"
            logger.error(
                "SEMANTIC_SCHOLAR_API_KEY rejected. Ensure root .env has the correct key "
                "and remove stale SEMANTIC_SCHOLAR_API_KEY from Windows user environment variables."
            )
        else:
            results["semantic_scholar"] = "error"
            logger.warning("Semantic Scholar probe failed: %s", err or s2)

    pub = await probe_pubmed(query="test", max_results=1)
    pub_status = pub.get("status", "unhealthy")
    if pub_status == "healthy":
        results["pubmed"] = "ok"
    elif pub_status == "missing":
        results["pubmed"] = "missing"
    elif pub_status == "degraded":
        results["pubmed"] = "degraded"
    else:
        results["pubmed"] = "error"
        logger.warning("PubMed key check failed: %s", pub.get("error"))

    emb = await probe_embedding()
    emb_status = emb.get("status", "unhealthy")
    if emb_status == "healthy":
        results["embedding"] = "ok"
        logger.info("Embedding model %s OK (dim=%s)", emb.get("model"), emb.get("dimension"))
    elif emb_status == "missing":
        results["embedding"] = "missing"
    else:
        results["embedding"] = "error"
        logger.warning("Embedding key check failed: %s", emb.get("error"))

    logger.info("API key validation: %s", results)
    return results
