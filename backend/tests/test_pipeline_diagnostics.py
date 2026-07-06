"""Tests for pipeline diagnostics and heuristic graph linking."""

import pytest
from unittest.mock import MagicMock
from uuid import uuid4

from app.models.claims import DirectionEnum
from app.services.memory_system import MemorySystemService


def _claim(intervention, outcome, direction):
    claim = MagicMock()
    claim.id = uuid4()
    claim.intervention_canonical = intervention
    claim.outcome_canonical = outcome
    claim.direction = direction
    claim.population = None
    return claim


def test_heuristic_edge_supports_same_direction():
    service = MemorySystemService(db=MagicMock())
    new = _claim("semaglutide", "weight loss", DirectionEnum.POSITIVE)
    existing = _claim("semaglutide", "weight loss", DirectionEnum.POSITIVE)
    result = service._heuristic_edge_resolution(new, existing)
    assert result is not None
    assert result["edge_type"] == "SUPPORTS"


def test_heuristic_edge_skips_opposing_for_contradiction_module():
    service = MemorySystemService(db=MagicMock())
    new = _claim("semaglutide", "weight loss", DirectionEnum.POSITIVE)
    existing = _claim("semaglutide", "weight loss", DirectionEnum.NEGATIVE)
    result = service._heuristic_edge_resolution(new, existing)
    assert result is None


def test_enrich_graph_adds_structural_nodes():
    service = MemorySystemService(db=MagicMock())
    claim_id = str(uuid4())
    paper_id = str(uuid4())
    claim = MagicMock()
    claim.paper_id = paper_id
    claim.intervention_canonical = "semaglutide"
    claim.outcome_canonical = "weight loss"

    claim_nodes = [{
        "id": claim_id,
        "node_type": "claim",
        "label": "semaglutide -> weight loss",
        "statement": "test",
        "intervention_canonical": "semaglutide",
        "outcome_canonical": "weight loss",
        "direction": "positive",
        "claim_type": "causal",
        "composite_confidence": 0.8,
        "study_design_score": 0.7,
        "publication_year": 2023,
        "edge_count": 0,
        "contradiction_count": 0,
        "topic_key": "x",
    }]

    nodes, edges = service._enrich_graph_with_structural_nodes(
        claim_nodes,
        [],
        {claim_id: claim},
        {paper_id: "Semaglutide safety trial"},
        {claim_id},
    )

    node_types = {n["node_type"] for n in nodes}
    edge_types = {e["edge_type"] for e in edges}
    assert "claim" in node_types
    assert "paper" in node_types
    assert "drug" in node_types
    assert "outcome" in node_types
    assert "MENTIONS" in edge_types
    assert "DERIVED_FROM" in edge_types
    assert len(edges) >= 3
