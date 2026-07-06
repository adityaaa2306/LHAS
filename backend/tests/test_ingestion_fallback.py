"""Tests for ingestion source fallback and deduplication."""

import pytest

from app.services.paper_ingestion import PaperObject, PaperSource


def _paper(**kwargs) -> PaperObject:
    defaults = dict(
        authors=[], abstract="", year=2024,
    )
    defaults.update(kwargs)
    return PaperObject(**defaults)


def test_deduplication_by_doi():
    from app.services.paper_ingestion import PaperIngestionService

    svc = PaperIngestionService.__new__(PaperIngestionService)
    papers = [
        _paper(paper_id="a", title="Same Paper", doi="10.1/x", source=PaperSource.PUBMED),
        _paper(paper_id="b", title="Same Paper", doi="10.1/x", source=PaperSource.SEMANTIC_SCHOLAR),
        _paper(paper_id="c", title="Different", doi="10.1/y", source=PaperSource.ARXIV),
    ]
    deduped = svc._stage3_deduplication(papers)
    dois = [p.doi for p in deduped]
    assert dois.count("10.1/x") == 1
    assert len(deduped) == 2


def test_deduplication_by_title():
    from app.services.paper_ingestion import PaperIngestionService

    svc = PaperIngestionService.__new__(PaperIngestionService)
    papers = [
        _paper(paper_id="a", title="Ozempic Review", source=PaperSource.PUBMED),
        _paper(paper_id="b", title="ozempic review", source=PaperSource.SEMANTIC_SCHOLAR),
    ]
    deduped = svc._stage3_deduplication(papers)
    assert len(deduped) == 1
