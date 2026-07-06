"""Tests for retrieval query building."""

from app.services.paper_ingestion import (
    build_retrieval_queries,
    sanitize_pubmed_query,
    _extract_keyword_terms,
)


def test_sanitize_pubmed_conversational_query():
    q = "what are the long term effects of ozempic on our bodies?"
    sanitized = sanitize_pubmed_query(q)
    assert "ozempic" in sanitized
    assert "?" not in sanitized


def test_extract_keyword_terms_includes_ozempic_and_semaglutide():
    terms = _extract_keyword_terms(
        "what are the long term effects of ozempic on our bodies?",
        ["ozempic", "long-term effects", "human body"],
    )
    assert any("ozempic" in t.lower() for t in terms)
    assert any("semaglutide" in t.lower() for t in terms)


def test_build_retrieval_queries_keyword_first():
    base = "what are the long term effects of ozempic on our bodies?"
    concepts = ["ozempic", "long-term effects", "human body"]
    queries = build_retrieval_queries(base, [base], concepts)
    assert queries[0] == "ozempic"
    assert queries[-1] == base
