"""Tests for the research retrieval planner."""

import pytest

from app.services.research_retrieval.planner import RetrievalPlanner
from app.services.research_retrieval.ontology import expand_entity_from_text


def test_ozempic_ontology_expansion():
    found = expand_entity_from_text("what are the long term effects of ozempic on our bodies?")
    assert any(term == "ozempic" for term, _ in found)
    entry = found[0][1]
    assert entry["canonical"] == "semaglutide"


@pytest.mark.asyncio
async def test_planner_never_only_raw_question():
    planner = RetrievalPlanner(llm_provider=None)
    structured = {
        "normalized_query": "what are the long term effects of ozempic on our bodies?",
        "key_concepts": ["ozempic", "long-term effects", "human body"],
    }
    plan = await planner.plan(structured)

    assert len(plan.searches) >= 10
    assert plan.intent.is_medical
    assert any(e.name.lower() == "ozempic" or "semaglutide" in e.synonyms for e in plan.entities)

    raw = structured["normalized_query"].lower()
    search_queries = [s.query.lower() for s in plan.searches]
    assert not all(q == raw for q in search_queries)
    assert any("semaglutide" in q for q in search_queries)


@pytest.mark.asyncio
async def test_planner_includes_multiple_sources():
    planner = RetrievalPlanner(llm_provider=None)
    plan = await planner.plan({
        "normalized_query": "ozempic long term safety adverse effects",
        "key_concepts": ["ozempic"],
    })
    sources = {s.source for s in plan.searches}
    assert "pubmed" in sources
    assert "semantic_scholar" in sources
    assert "europe_pmc" in sources


@pytest.mark.asyncio
async def test_gap_fill_generates_targeted_searches():
    planner = RetrievalPlanner(llm_provider=None)
    plan = await planner.plan({
        "normalized_query": "semaglutide safety",
        "key_concepts": ["semaglutide"],
    })
    gaps = planner.plan_gap_fill(plan, ["pancreatitis", "cardiovascular outcomes"])
    assert len(gaps) >= 2
    assert any("pancreatitis" in g.query for g in gaps)
