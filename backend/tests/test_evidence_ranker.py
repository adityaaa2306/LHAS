"""Tests for evidence ranking and QC."""

from app.services.paper_ingestion import PaperObject, PaperSource
from app.services.research_retrieval.models import ResearchEntity, ResearchIntent, RetrievalPlan
from app.services.research_retrieval.ranker import is_obviously_irrelevant, rank_papers


def _plan() -> RetrievalPlan:
    return RetrievalPlan(
        entities=[
            ResearchEntity(
                name="Ozempic",
                entity_type="drug",
                canonical_names=["semaglutide"],
                synonyms=["ozempic", "semaglutide"],
                drug_class="GLP-1 receptor agonist",
            )
        ],
        intent=ResearchIntent(
            domain="medical",
            primary_question="ozempic long term effects",
            is_medical=True,
            coverage_dimensions=["pancreatitis", "cardiovascular"],
        ),
        searches=[],
    )


def test_rejects_ibd_paper_for_ozempic_query():
    plan = _plan()
    paper = PaperObject(
        paper_id="x1",
        title="IBD management in inflammatory bowel disease",
        authors=[],
        abstract="Crohn disease and ulcerative colitis treatment pathways.",
        year=2020,
        source=PaperSource.SEMANTIC_SCHOLAR,
    )
    reason = is_obviously_irrelevant(paper, plan)
    assert reason is not None


def test_keeps_relevant_semaglutide_paper():
    plan = _plan()
    paper = PaperObject(
        paper_id="x2",
        title="Long-term safety of semaglutide: systematic review",
        authors=[],
        abstract="Semaglutide adverse effects including gastrointestinal and cardiovascular outcomes.",
        year=2023,
        source=PaperSource.PUBMED,
        citations_count=120,
    )
    assert is_obviously_irrelevant(paper, plan) is None
    ranked = rank_papers([paper], plan, {paper.paper_id: 0.7})
    assert ranked[0].evidence_rank_score > 0.5
