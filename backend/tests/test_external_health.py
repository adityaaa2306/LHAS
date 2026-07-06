"""Unit tests for external health probes and field validation."""

import pytest

from app.services.external_health import (
    validate_s2_paper_fields,
    validate_s2_query_batch,
)


def _full_paper(**overrides):
    base = {
        "paper_id": "abc123",
        "title": "Ozempic and Weight Loss",
        "abstract": "A study of GLP-1 agonists.",
        "year": 2023,
        "authors": ["Alice Smith"],
        "doi": "10.1000/test",
        "citations_count": 42,
        "is_open_access": False,
        "pdf_url": None,
    }
    base.update(overrides)
    return base


def test_validate_s2_paper_fields_all_present():
    assert validate_s2_paper_fields(_full_paper()) == []


def test_validate_s2_paper_fields_missing_title():
    assert "title" in validate_s2_paper_fields(_full_paper(title=""))


def test_validate_s2_paper_fields_missing_abstract():
    assert "abstract" in validate_s2_paper_fields(_full_paper(abstract="  "))


def test_validate_s2_paper_fields_missing_authors():
    assert "authors" in validate_s2_paper_fields(_full_paper(authors=[]))


def test_validate_s2_paper_fields_missing_year():
    assert "publication_year" in validate_s2_paper_fields(_full_paper(year=None))


def test_validate_s2_paper_fields_missing_citation_count():
    assert "citation_count" in validate_s2_paper_fields(_full_paper(citations_count=None))


def test_validate_s2_paper_fields_missing_doi():
    assert "doi" in validate_s2_paper_fields(_full_paper(doi=None))


def test_validate_s2_paper_fields_citation_count_zero_is_valid():
    assert validate_s2_paper_fields(_full_paper(citations_count=0)) == []


def test_validate_s2_paper_fields_open_access_pdf_required_when_flagged():
    missing = validate_s2_paper_fields(
        _full_paper(is_open_access=True, pdf_url=None),
    )
    assert "open_access_pdf" in missing


def test_validate_s2_paper_fields_open_access_pdf_ok_when_present():
    assert validate_s2_paper_fields(
        _full_paper(is_open_access=True, pdf_url="https://example.com/paper.pdf"),
    ) == []


def test_validate_s2_query_batch_all_good():
    papers = [_full_paper() for _ in range(5)]
    assert validate_s2_query_batch(papers) == []


def test_validate_s2_query_batch_abstract_threshold():
    papers = [_full_paper() for _ in range(4)] + [_full_paper(abstract="")]
    # 4/5 = 80% exactly — should pass
    assert validate_s2_query_batch(papers) == []


def test_validate_s2_query_batch_abstract_below_threshold():
    papers = [_full_paper() for _ in range(3)] + [_full_paper(abstract="") for _ in range(2)]
    issues = validate_s2_query_batch(papers)
    assert any("abstract" in i for i in issues)


def test_validate_s2_query_batch_per_paper_title_required():
    papers = [_full_paper(), _full_paper(title="")]
    issues = validate_s2_query_batch(papers)
    assert any("title" in i for i in issues)
