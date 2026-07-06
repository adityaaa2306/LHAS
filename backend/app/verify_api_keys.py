"""
End-to-end API key verification.

Run: docker compose exec backend python -m app.verify_api_keys
"""

from __future__ import annotations

import asyncio
import sys

from app.services.external_health import (
    DEFAULT_S2_PROBE_QUERIES,
    probe_all_external_services,
)


def _check(label: str, ok: bool, detail: str = "") -> bool:
    mark = "✓" if ok else "✗"
    line = f"  {mark} {label}"
    if detail:
        line += f" — {detail}"
    print(line)
    return ok


def _section(title: str) -> None:
    print(f"\n{title}")
    print("-" * len(title))


def _print_s2_field_validation(payload: dict) -> bool:
    """Print per-field validation results; return True if all fields OK."""
    failures = payload.get("field_validation_failures") or []
    papers_checked = payload.get("papers_checked", 0)

    if papers_checked == 0:
        return _check("Field validation", False, "no papers checked")

    if not failures:
        return _check(
            "Field validation",
            True,
            f"all checks passed on {papers_checked} papers "
            "(title/authors/year/citations per paper; abstract >=60% & doi >=80%; open_access_pdf when flagged)",
        )

    all_ok = True
    _check("Field validation", False, f"{len(failures)} issue(s)")
    for fail in failures[:10]:
        query = fail.get("query", "?")
        issue = fail.get("issue") or fail.get("missing_fields", fail)
        all_ok = False
        print(f"    [{query}] {issue}")
    if len(failures) > 10:
        print(f"    ... and {len(failures) - 10} more")
    return False


async def main() -> int:
    print("LHAS API Integration Verification")
    print("=" * 40)

    payload = await probe_all_external_services(
        full_s2_validation=True,
        s2_queries=DEFAULT_S2_PROBE_QUERIES,
    )

    all_ok = True

    _section("Semantic Scholar")
    s2 = payload["semanticScholar"]
    _check("API key configured", s2.get("status") != "missing")
    _check("Authenticated", s2.get("authenticated") is True)
    _check(
        "Search probes",
        s2.get("searches_succeeded") == s2.get("searches_expected"),
        f"{s2.get('searches_succeeded')}/{s2.get('searches_expected')} queries",
    )
    for q in DEFAULT_S2_PROBE_QUERIES:
        qr = (s2.get("queries") or {}).get(q, {})
        q_status = qr.get("status", "failed")
        q_ok = q_status == "ok"
        detail = ""
        if q_ok:
            detail = f"{qr.get('papers', 0)} papers, total_in_index={qr.get('total_in_index')}"
        elif qr.get("error"):
            detail = qr["error"]
        elif qr.get("issues"):
            detail = "; ".join(qr["issues"][:2])
        _check(f"Search '{q}'", q_ok, detail)
    fields_ok = _print_s2_field_validation(s2)
    if s2.get("remaining_requests") is not None:
        print(f"  remaining_requests={s2['remaining_requests']}")
    print(f"  Average latency: {s2.get('latency_ms', 0):.0f} ms")
    all_ok = all_ok and s2.get("status") == "healthy" and fields_ok

    _section("PubMed")
    pub = payload["pubmed"]
    _check("API key configured", pub.get("status") != "missing")
    _check("Search successful", pub.get("status") == "healthy", f"{pub.get('papers_retrieved', 0)} papers")
    print(f"  Latency: {pub.get('latency_ms', 0):.0f} ms")
    all_ok = all_ok and pub.get("status") == "healthy"

    _section("Embedding Provider")
    emb = payload["embedding"]
    _check("API key configured", emb.get("status") != "missing")
    _check("Embedding generated", emb.get("status") == "healthy", f"dimension={emb.get('dimension')}")
    print(f"  Latency: {emb.get('latency_ms', 0):.0f} ms")
    all_ok = all_ok and emb.get("status") == "healthy"

    print("\n" + "=" * 40)
    if all_ok:
        print("All integrations PASSED")
        return 0
    print("Some integrations FAILED — see details above")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
