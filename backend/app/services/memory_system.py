from __future__ import annotations

import json
import logging
import math
from collections import Counter
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Mission, ResearchClaim, ResearchPaper, SynthesisAnswer
from app.models.contradiction import ContradictionRecord
from app.models.belief_revision import BeliefEscalation, BeliefRevisionRecord, BeliefState, EscalationStatusEnum
from app.models.memory import (
    CanonicalEntityIndexRecord,
    ClaimGraphEdge,
    ClaimGraphNode,
    ClaimVersionLedger,
    DominantDirection,
    DriftMetric,
    EntityType,
    GraphEdgeType,
    MemoryEventType,
    MissionCheckpoint,
    MissionSnapshot,
    ProvenanceLogEntry,
    RawClaimRecord,
    RawPaperRecord,
    RawPaperStatus,
    SynthesisHistory,
    SynthesisTrigger,
)
from app.services.llm import get_llm_provider

logger = logging.getLogger(__name__)

VALID_EDGE_TYPES = {
    GraphEdgeType.SUPPORTS.value,
    GraphEdgeType.CONTRADICTS.value,
    GraphEdgeType.REPLICATES.value,
    GraphEdgeType.REFINES.value,
    GraphEdgeType.IS_SUBGROUP_OF.value,
}


def _uuid(value: Any) -> Optional[UUID]:
    if value in (None, ""):
        return None
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


def _enum_value(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(getattr(value, "value", value) or default)


def _claim_statement(claim: ResearchClaim) -> str:
    return (claim.statement_normalized or claim.statement_raw or "").strip()


def _jsonable(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    return value


def _current_year() -> int:
    return datetime.utcnow().year


def _claim_publication_year(claim: ResearchClaim) -> Optional[int]:
    provenance = claim.provenance or {}
    document_frame = provenance.get("document_frame") or {}
    for candidate in (
        document_frame.get("publication_year"),
        provenance.get("publication_year"),
    ):
        try:
            if candidate is not None:
                return int(candidate)
        except (TypeError, ValueError):
            continue
    return None


def _recency_component(year: Optional[int]) -> float:
    if not year:
        return 0.75
    age = max(0, _current_year() - year)
    if age <= 5:
        return 1.0
    if age >= 10:
        return 0.5
    return round(1.0 - ((age - 5) * 0.1), 4)


def _study_design_delta(left: ResearchClaim, right: ResearchClaim) -> float:
    try:
        left_score = float(left.study_design_score or 0.5)
        right_score = float(right.study_design_score or 0.5)
    except (TypeError, ValueError):
        return 0.0
    return round(abs(left_score - right_score), 4)


def _confidence_product(left: ResearchClaim, right: ResearchClaim) -> float:
    try:
        return round(float(left.composite_confidence or 0.0) * float(right.composite_confidence or 0.0), 6)
    except (TypeError, ValueError):
        return 0.0


def _edge_weight(left: ResearchClaim, right: ResearchClaim) -> Dict[str, float]:
    study_delta = _study_design_delta(left, right)
    confidence_product = _confidence_product(left, right)
    recency_weight = min(
        _recency_component(_claim_publication_year(left)),
        _recency_component(_claim_publication_year(right)),
    )
    weight = confidence_product * recency_weight * (1 - (0.3 * study_delta))
    return {
        "study_design_delta": round(study_delta, 4),
        "confidence_product": round(confidence_product, 6),
        "recency_weight": round(recency_weight, 4),
        "edge_weight": round(max(0.0, weight), 6),
    }


def _is_directional_contradiction(left: str, right: str) -> bool:
    left_norm = left.lower().strip()
    right_norm = right.lower().strip()
    if not left_norm or not right_norm or left_norm == "unclear" or right_norm == "unclear":
        return False
    opposites = {
        ("positive", "negative"),
        ("negative", "positive"),
        ("positive", "null"),
        ("null", "positive"),
    }
    return (left_norm, right_norm) in opposites


def _same_entity_pair(left: ResearchClaim, right: ResearchClaim) -> bool:
    return (
        (left.intervention_canonical or "").strip().lower()
        and (left.outcome_canonical or "").strip().lower()
        and (left.intervention_canonical or "").strip().lower() == (right.intervention_canonical or "").strip().lower()
        and (left.outcome_canonical or "").strip().lower() == (right.outcome_canonical or "").strip().lower()
    )


class MemorySystemService:
    def __init__(
        self,
        db: AsyncSession,
        llm_provider: Any = None,
        embedding_service: Any = None,
    ):
        self.db = db
        self.llm_provider = llm_provider or get_llm_provider()
        self.embedding_service = embedding_service

    async def record_paper_record(
        self,
        paper: ResearchPaper,
        actor: str = "paper_ingestion",
        status: RawPaperStatus = RawPaperStatus.INGESTED,
    ) -> None:
        payload = {
            "paper_id": str(paper.id),
            "external_paper_id": paper.paper_id,
            "title": paper.title,
            "authors": paper.authors or [],
            "doi_or_url": paper.doi or paper.arxiv_url or paper.semantic_scholar_url or paper.pubmed_url,
            "publication_year": paper.year,
            "journal": None,
            "study_type": (paper.score_breakdown or {}).get("study_type"),
            "ingestion_timestamp": (paper.retrieved_at or datetime.utcnow()).isoformat(),
            "mission_id": str(paper.mission_id),
            "full_text_available": bool((paper.full_text_content or "").strip()),
            "abstract_text": paper.abstract,
            "status": status.value,
            "source": _enum_value(paper.source, "unknown"),
            "final_score": paper.final_score,
        }
        self.db.add(
            RawPaperRecord(
                mission_id=str(paper.mission_id),
                research_paper_id=paper.id,
                paper_external_id=paper.paper_id,
                title=paper.title,
                authors=paper.authors or [],
                doi_or_url=payload["doi_or_url"],
                publication_year=paper.year,
                journal=None,
                study_type=payload["study_type"],
                ingestion_timestamp=paper.retrieved_at or datetime.utcnow(),
                full_text_available=bool((paper.full_text_content or "").strip()),
                abstract_text=paper.abstract,
                status=status,
                actor=actor,
                payload=_jsonable(payload),
            )
        )

    async def snapshot_existing_claim_versions(
        self,
        paper_id: UUID,
        mission_id: str,
        actor: str = "claim_extraction",
    ) -> None:
        existing = (
            await self.db.execute(
                select(ResearchClaim).where(
                    ResearchClaim.paper_id == paper_id,
                    ResearchClaim.mission_id == mission_id,
                )
            )
        ).scalars().all()

        for claim in existing:
            next_version = await self._next_version_number(claim.id)
            old_payload = self._claim_state_payload(claim)
            self.db.add(
                ClaimVersionLedger(
                    claim_id=claim.id,
                    mission_id=mission_id,
                    version_number=next_version,
                    changed_field="claim_replaced",
                    old_value=_jsonable(old_payload),
                    new_value=None,
                    changed_by_module=actor,
                )
            )
            await self.log_event(
                event_type=MemoryEventType.CLAIM_CONFIDENCE_REVISED,
                mission_id=mission_id,
                actor=actor,
                claim_id=claim.id,
                previous_value=_jsonable(old_payload),
                new_value=None,
            )

    async def register_claim_creation(
        self,
        claim: ResearchClaim,
        raw_payload: Dict[str, Any],
        actor: str = "claim_extraction",
    ) -> None:
        self.db.add(
            RawClaimRecord(
                mission_id=claim.mission_id,
                research_claim_id=claim.id,
                paper_id=claim.paper_id,
                actor=actor,
                extraction_timestamp=claim.extraction_timestamp or datetime.utcnow(),
                payload=_jsonable(raw_payload),
            )
        )
        await self.log_event(
            event_type=MemoryEventType.CLAIM_CREATED,
            mission_id=claim.mission_id,
            actor=actor,
            claim_id=claim.id,
            paper_id=claim.paper_id,
            previous_value=None,
            new_value=_jsonable(self._claim_state_payload(claim)),
        )
        await self._update_entity_index(claim)
        await self._upsert_graph_node(claim)
        await self._resolve_links_for_claim(claim)

    async def log_event(
        self,
        event_type: MemoryEventType,
        mission_id: str,
        actor: str,
        claim_id: Optional[UUID] = None,
        paper_id: Optional[UUID] = None,
        previous_value: Any = None,
        new_value: Any = None,
    ) -> None:
        self.db.add(
            ProvenanceLogEntry(
                event_type=event_type,
                mission_id=mission_id,
                actor=actor,
                claim_id=claim_id,
                paper_id=paper_id,
                previous_value=_jsonable(previous_value),
                new_value=_jsonable(new_value),
            )
        )

    async def finalize_cycle(
        self,
        mission_id: str,
        trigger: SynthesisTrigger = SynthesisTrigger.NEW_PAPER,
        actor: str = "memory_system",
    ) -> Dict[str, Any]:
        mission = await self.db.get(Mission, mission_id)
        if not mission:
            raise ValueError(f"Mission not found: {mission_id}")

        cycle_number = int((mission.session_count or 0) + 1)
        latest_synthesis = await self._sync_synthesis_history(mission_id, trigger)
        snapshot = await self._create_snapshot(mission_id, cycle_number, latest_synthesis)
        await self.db.flush()
        drift = await self._create_drift_metric(mission_id, cycle_number, snapshot)
        await self.db.flush()
        checkpoint = await self._write_checkpoint(mission_id, cycle_number, snapshot, latest_synthesis)

        mission.session_count = cycle_number
        mission.last_run = datetime.utcnow()
        mission.confidence_score = float(snapshot.current_confidence_score or mission.confidence_score or 0.0)
        await self.log_event(
            event_type=MemoryEventType.BELIEF_STATE_UPDATED,
            mission_id=mission_id,
            actor=actor,
            previous_value=None,
            new_value={
                "cycle_number": cycle_number,
                "snapshot_id": str(snapshot.id),
                "drift_metric_id": str(drift.id) if drift else None,
                "checkpoint_id": str(checkpoint.id) if checkpoint else None,
            },
        )
        return {
            "cycle_number": cycle_number,
            "snapshot_id": str(snapshot.id),
            "drift_metric_id": str(drift.id) if drift else None,
            "checkpoint_id": str(checkpoint.id) if checkpoint else None,
        }

    async def run_cluster_pass(self, mission_id: str, actor: str = "memory_cluster_engine") -> Dict[str, Any]:
        if not self.embedding_service:
            await self.log_event(
                event_type=MemoryEventType.CLUSTER_PASS_FAILED,
                mission_id=mission_id,
                actor=actor,
                previous_value=None,
                new_value={"reason": "embedding_service_unavailable"},
            )
            return {"success": False, "reason": "embedding_service_unavailable"}

        claims = (
            await self.db.execute(
                select(ResearchClaim).where(ResearchClaim.mission_id == mission_id)
            )
        ).scalars().all()
        if len(claims) < 2:
            return {"success": True, "flagged_pairs": 0}

        statements = [_claim_statement(claim) for claim in claims]
        embeddings = await self.embedding_service.embed_batch(statements, input_type="passage")
        flagged_pairs = 0

        for idx, left in enumerate(claims):
            left_embedding = embeddings[idx] if idx < len(embeddings) else None
            if left_embedding is None:
                continue
            for jdx in range(idx + 1, len(claims)):
                right_embedding = embeddings[jdx] if jdx < len(embeddings) else None
                if right_embedding is None:
                    continue
                if await self._edge_exists(left.id, claims[jdx].id):
                    continue
                similarity = self._cosine_similarity(left_embedding, right_embedding)
                if similarity >= 0.85:
                    flagged_pairs += 1
                    await self.log_event(
                        event_type=MemoryEventType.CLUSTER_REVIEW_FLAGGED,
                        mission_id=mission_id,
                        actor=actor,
                        claim_id=left.id,
                        previous_value=None,
                        new_value={
                            "other_claim_id": str(claims[jdx].id),
                            "similarity": round(similarity, 4),
                        },
                    )
        return {"success": True, "flagged_pairs": flagged_pairs}

    async def get_memory_overview(self, mission_id: str) -> Dict[str, Any]:
        latest_snapshot = (
            await self.db.execute(
                select(MissionSnapshot)
                .where(MissionSnapshot.mission_id == mission_id)
                .order_by(MissionSnapshot.cycle_number.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        latest_drift = (
            await self.db.execute(
                select(DriftMetric)
                .where(DriftMetric.mission_id == mission_id)
                .order_by(DriftMetric.cycle_number.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        contradictions = (
            await self.db.execute(
                select(func.count(ContradictionRecord.id)).where(ContradictionRecord.mission_id == mission_id)
            )
        ).scalar_one()
        provenance_count = (
            await self.db.execute(
                select(func.count(ProvenanceLogEntry.id)).where(ProvenanceLogEntry.mission_id == mission_id)
            )
        ).scalar_one()
        node_count = (
            await self.db.execute(
                select(func.count(ClaimGraphNode.claim_id)).where(ClaimGraphNode.mission_id == mission_id)
            )
        ).scalar_one()
        edge_count = (
            await self.db.execute(
                select(func.count(ClaimGraphEdge.id)).where(ClaimGraphEdge.mission_id == mission_id)
            )
        ).scalar_one()
        checkpoint_count = (
            await self.db.execute(
                select(func.count(MissionCheckpoint.id)).where(MissionCheckpoint.mission_id == mission_id)
            )
        ).scalar_one()

        return {
            "mission_id": mission_id,
            "latest_snapshot": self._snapshot_response(latest_snapshot) if latest_snapshot else None,
            "latest_drift": self._drift_response(latest_drift) if latest_drift else None,
            "belief_state": await self._belief_state_overview(mission_id),
            "graph": {
                "node_count": int(node_count or 0),
                "edge_count": int(edge_count or 0),
                "contradictions": int(contradictions or 0),
            },
            "audit": {
                "provenance_events": int(provenance_count or 0),
                "checkpoints": int(checkpoint_count or 0),
            },
        }

    async def get_snapshot_history(self, mission_id: str) -> List[Dict[str, Any]]:
        snapshots = (
            await self.db.execute(
                select(MissionSnapshot)
                .where(MissionSnapshot.mission_id == mission_id)
                .order_by(MissionSnapshot.cycle_number.desc())
            )
        ).scalars().all()
        return [self._snapshot_response(snapshot) for snapshot in snapshots]

    async def get_drift_history(self, mission_id: str) -> List[Dict[str, Any]]:
        rows = (
            await self.db.execute(
                select(DriftMetric)
                .where(DriftMetric.mission_id == mission_id)
                .order_by(DriftMetric.cycle_number.desc())
            )
        ).scalars().all()
        return [self._drift_response(row) for row in rows]

    async def get_provenance_log(
        self,
        mission_id: str,
        claim_id: Optional[str] = None,
        paper_id: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        query = select(ProvenanceLogEntry).where(ProvenanceLogEntry.mission_id == mission_id)
        if claim_id:
            query = query.where(ProvenanceLogEntry.claim_id == _uuid(claim_id))
        if paper_id:
            query = query.where(ProvenanceLogEntry.paper_id == _uuid(paper_id))
        rows = (
            await self.db.execute(query.order_by(ProvenanceLogEntry.timestamp.desc()).limit(limit))
        ).scalars().all()
        return [
            {
                "id": str(row.id),
                "event_type": row.event_type.value,
                "claim_id": str(row.claim_id) if row.claim_id else None,
                "paper_id": str(row.paper_id) if row.paper_id else None,
                "mission_id": row.mission_id,
                "timestamp": row.timestamp.isoformat() if row.timestamp else None,
                "actor": row.actor,
                "previous_value": row.previous_value,
                "new_value": row.new_value,
            }
            for row in rows
        ]

    async def get_claim_memory_detail(self, claim_id: str) -> Dict[str, Any]:
        claim_uuid = _uuid(claim_id)
        claim = await self.db.get(ResearchClaim, claim_uuid)
        if not claim:
            raise ValueError(f"Claim not found: {claim_id}")

        versions = (
            await self.db.execute(
                select(ClaimVersionLedger)
                .where(ClaimVersionLedger.claim_id == claim_uuid)
                .order_by(ClaimVersionLedger.version_number.desc())
            )
        ).scalars().all()
        provenance = await self.get_provenance_log(claim.mission_id, claim_id=claim_id, limit=200)
        edges = (
            await self.db.execute(
                select(ClaimGraphEdge).where(
                    ClaimGraphEdge.mission_id == claim.mission_id,
                    or_(
                        ClaimGraphEdge.claim_a_id == claim_uuid,
                        ClaimGraphEdge.claim_b_id == claim_uuid,
                    ),
                )
            )
        ).scalars().all()

        return {
            "claim_id": claim_id,
            "statement": _claim_statement(claim),
            "mission_id": claim.mission_id,
            "paper_id": str(claim.paper_id),
            "versions": [
                {
                    "id": str(row.id),
                    "version_number": row.version_number,
                    "changed_field": row.changed_field,
                    "old_value": row.old_value,
                    "new_value": row.new_value,
                    "changed_at": row.changed_at.isoformat() if row.changed_at else None,
                    "changed_by_module": row.changed_by_module,
                }
                for row in versions
            ],
            "provenance": provenance,
            "graph_edges": [
                {
                    "id": str(edge.id),
                    "edge_type": edge.edge_type.value,
                    "other_claim_id": str(edge.claim_b_id if edge.claim_a_id == claim_uuid else edge.claim_a_id),
                    "edge_weight": edge.edge_weight,
                    "study_design_delta": edge.study_design_delta,
                    "confidence_product": edge.confidence_product,
                    "recency_weight": edge.recency_weight,
                    "justification": edge.justification,
                    "resolution_status": edge.resolution_status,
                    "created_at": edge.created_at.isoformat() if edge.created_at else None,
                }
                for edge in edges
            ],
        }

    async def get_active_contradictions(self, mission_id: str) -> List[Dict[str, Any]]:
        rows = (
            await self.db.execute(
                select(ContradictionRecord)
                .where(ContradictionRecord.mission_id == mission_id)
                .order_by(ContradictionRecord.timestamp.desc())
            )
        ).scalars().all()
        claim_ids = {
            claim_id
            for row in rows
            for claim_id in (_uuid(row.claim_a_id), _uuid(row.claim_b_id))
            if claim_id is not None
        }
        claims = (
            (
                await self.db.execute(
                    select(ResearchClaim).where(ResearchClaim.id.in_(claim_ids))
                )
            ).scalars().all()
            if claim_ids
            else []
        )
        claim_map = {claim.id: claim for claim in claims}
        paper_ids = {claim.paper_id for claim in claims if claim.paper_id is not None}
        papers = (
            (
                await self.db.execute(
                    select(ResearchPaper).where(ResearchPaper.id.in_(paper_ids))
                )
            ).scalars().all()
            if paper_ids
            else []
        )
        paper_map = {paper.id: paper for paper in papers}
        items: List[Dict[str, Any]] = []
        for row in rows:
            edge = await self.db.get(ClaimGraphEdge, row.graph_edge_id) if row.graph_edge_id else None
            claim_a_uuid = _uuid(row.claim_a_id)
            claim_b_uuid = _uuid(row.claim_b_id)
            claim_a = claim_map.get(claim_a_uuid) if claim_a_uuid else None
            claim_b = claim_map.get(claim_b_uuid) if claim_b_uuid else None
            paper_a = paper_map.get(claim_a.paper_id) if claim_a and claim_a.paper_id else None
            paper_b = paper_map.get(claim_b.paper_id) if claim_b and claim_b.paper_id else None
            items.append(
                {
                    "id": str(row.id),
                    "graph_edge_id": str(row.graph_edge_id) if row.graph_edge_id else None,
                    "claim_a_id": str(row.claim_a_id),
                    "claim_b_id": str(row.claim_b_id),
                    "edge_type": GraphEdgeType.CONTRADICTS.value,
                    "severity": _enum_value(row.severity),
                    "edge_weight": edge.edge_weight if edge else 0.0,
                    "study_design_delta": edge.study_design_delta if edge else row.quality_parity_delta,
                    "confidence_product": edge.confidence_product if edge else row.confidence_product,
                    "recency_weight": edge.recency_weight if edge else None,
                    "resolution_status": row.resolution_status,
                    "justification": edge.justification if edge else None,
                    "created_at": row.timestamp.isoformat() if row.timestamp else None,
                    "intervention_canonical": row.intervention_canonical,
                    "outcome_canonical": row.outcome_canonical,
                    "population_overlap": _enum_value(row.population_overlap),
                    "direction_a": _enum_value(row.direction_a),
                    "direction_b": _enum_value(row.direction_b),
                    "claim_a_statement": _claim_statement(claim_a) if claim_a else None,
                    "claim_b_statement": _claim_statement(claim_b) if claim_b else None,
                    "claim_a_paper_title": getattr(paper_a, "title", None),
                    "claim_b_paper_title": getattr(paper_b, "title", None),
                }
            )
        return items

    async def get_graph_visualization(
        self,
        mission_id: str,
        max_nodes: int = 48,
        max_edges: int = 120,
    ) -> Dict[str, Any]:
        node_rows = (
            await self.db.execute(
                select(ClaimGraphNode)
                .where(ClaimGraphNode.mission_id == mission_id)
            )
        ).scalars().all()
        edge_rows = (
            await self.db.execute(
                select(ClaimGraphEdge)
                .where(ClaimGraphEdge.mission_id == mission_id)
                .order_by(ClaimGraphEdge.edge_weight.desc(), ClaimGraphEdge.created_at.desc())
            )
        ).scalars().all()

        if not node_rows:
            return {
                "mission_id": mission_id,
                "nodes": [],
                "edges": [],
                "stats": {
                    "total_nodes": 0,
                    "visible_nodes": 0,
                    "total_edges": 0,
                    "visible_edges": 0,
                    "edge_type_breakdown": {},
                },
            }

        node_map = {str(node.claim_id): node for node in node_rows}
        degrees: Counter[str] = Counter()
        contradiction_degrees: Counter[str] = Counter()
        for edge in edge_rows:
            left_id = str(edge.claim_a_id)
            right_id = str(edge.claim_b_id)
            degrees[left_id] += 1
            degrees[right_id] += 1
            if _enum_value(edge.edge_type) == GraphEdgeType.CONTRADICTS.value:
                contradiction_degrees[left_id] += 1
                contradiction_degrees[right_id] += 1

        ranked_nodes = sorted(
            node_rows,
            key=lambda node: (
                contradiction_degrees[str(node.claim_id)],
                degrees[str(node.claim_id)],
                float(node.composite_confidence or 0.0),
                float(node.study_design_score or 0.0),
            ),
            reverse=True,
        )
        selected_nodes = ranked_nodes[:max_nodes]
        selected_ids = {str(node.claim_id) for node in selected_nodes}

        selected_edges = [
            edge
            for edge in edge_rows
            if str(edge.claim_a_id) in selected_ids and str(edge.claim_b_id) in selected_ids
        ][:max_edges]

        claim_rows = (
            await self.db.execute(
                select(ResearchClaim)
                .where(ResearchClaim.id.in_([node.claim_id for node in selected_nodes]))
            )
        ).scalars().all()
        claims_by_id = {str(claim.id): claim for claim in claim_rows}

        paper_ids = list({claim.paper_id for claim in claim_rows if claim.paper_id})
        paper_titles: Dict[str, str] = {}
        if paper_ids:
            paper_rows = (
                await self.db.execute(
                    select(ResearchPaper).where(ResearchPaper.id.in_(paper_ids))
                )
            ).scalars().all()
            paper_titles = {str(paper.id): paper.title for paper in paper_rows}

        edge_type_breakdown = Counter(_enum_value(edge.edge_type, "UNKNOWN") for edge in selected_edges)

        nodes = []
        for node in selected_nodes:
            claim_id = str(node.claim_id)
            claim = claims_by_id.get(claim_id)
            intervention = (node.intervention_canonical or "Unspecified intervention").strip()
            outcome = (node.outcome_canonical or "Unspecified outcome").strip()
            statement = (node.normalized_statement or (_claim_statement(claim) if claim else "")).strip()
            paper_title = paper_titles.get(str(claim.paper_id), "") if claim and claim.paper_id else ""
            nodes.append(
                {
                    "id": claim_id,
                    "label": f"{intervention} -> {outcome}",
                    "statement": statement or f"{intervention} -> {outcome}",
                    "intervention_canonical": intervention,
                    "outcome_canonical": outcome,
                    "direction": (node.direction or "unclear").strip().lower(),
                    "claim_type": (node.claim_type or "unknown").strip().lower(),
                    "composite_confidence": float(node.composite_confidence or 0.0),
                    "study_design_score": float(node.study_design_score or 0.0),
                    "publication_year": node.publication_year,
                    "paper_title": paper_title or None,
                    "edge_count": int(degrees[claim_id]),
                    "contradiction_count": int(contradiction_degrees[claim_id]),
                    "topic_key": f"{intervention.lower()}::{outcome.lower()}",
                }
            )

        edges = [
            {
                "id": str(edge.id),
                "source": str(edge.claim_a_id),
                "target": str(edge.claim_b_id),
                "edge_type": _enum_value(edge.edge_type),
                "edge_weight": float(edge.edge_weight or 0.0),
                "study_design_delta": float(edge.study_design_delta or 0.0),
                "confidence_product": float(edge.confidence_product or 0.0),
                "recency_weight": float(edge.recency_weight or 0.0),
                "resolution_status": edge.resolution_status,
                "justification": edge.justification,
            }
            for edge in selected_edges
        ]

        return {
            "mission_id": mission_id,
            "nodes": nodes,
            "edges": edges,
            "stats": {
                "total_nodes": len(node_rows),
                "visible_nodes": len(nodes),
                "total_edges": len(edge_rows),
                "visible_edges": len(edges),
                "edge_type_breakdown": dict(edge_type_breakdown),
            },
        }

    async def get_latest_checkpoint(self, mission_id: str) -> Optional[Dict[str, Any]]:
        checkpoint = (
            await self.db.execute(
                select(MissionCheckpoint)
                .where(
                    MissionCheckpoint.mission_id == mission_id,
                    MissionCheckpoint.is_valid.is_(True),
                )
                .order_by(MissionCheckpoint.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if not checkpoint:
            return None
        return {
            "id": str(checkpoint.id),
            "mission_id": checkpoint.mission_id,
            "cycle_number": checkpoint.cycle_number,
            "created_at": checkpoint.created_at.isoformat() if checkpoint.created_at else None,
            "snapshot_payload": checkpoint.snapshot_payload,
            "graph_state": checkpoint.graph_state,
            "canonical_entity_index": checkpoint.canonical_entity_index,
            "processed_paper_ids": checkpoint.processed_paper_ids,
            "last_synthesis_version_id": str(checkpoint.last_synthesis_version_id) if checkpoint.last_synthesis_version_id else None,
            "pending_events": checkpoint.pending_events,
            "is_valid": checkpoint.is_valid,
        }

    async def backfill_mission_memory(self, mission_id: str) -> Dict[str, Any]:
        papers = (
            await self.db.execute(
                select(ResearchPaper).where(ResearchPaper.mission_id == mission_id)
            )
        ).scalars().all()
        claims = (
            await self.db.execute(
                select(ResearchClaim).where(ResearchClaim.mission_id == mission_id)
            )
        ).scalars().all()

        created_paper_records = 0
        created_claim_records = 0

        for paper in papers:
            existing = (
                await self.db.execute(
                    select(RawPaperRecord.id).where(RawPaperRecord.research_paper_id == paper.id)
                )
            ).first()
            if existing:
                continue
            await self.record_paper_record(paper, actor="memory_backfill", status=RawPaperStatus.INGESTED)
            created_paper_records += 1

        for claim in claims:
            existing = (
                await self.db.execute(
                    select(RawClaimRecord.id).where(RawClaimRecord.research_claim_id == claim.id)
                )
            ).first()
            if existing:
                continue
            await self.register_claim_creation(
                claim=claim,
                raw_payload=self._claim_state_payload(claim),
                actor="memory_backfill",
            )
            created_claim_records += 1

        latest_snapshot = (
            await self.db.execute(
                select(MissionSnapshot.id).where(MissionSnapshot.mission_id == mission_id).limit(1)
            )
        ).first()
        cycle = None
        if not latest_snapshot:
            result = await self.finalize_cycle(
                mission_id=mission_id,
                trigger=SynthesisTrigger.OPERATOR_REQUEST,
                actor="memory_backfill",
            )
            cycle = result.get("cycle_number")

        return {
            "mission_id": mission_id,
            "paper_records_created": created_paper_records,
            "claim_records_created": created_claim_records,
            "snapshot_cycle_created": cycle,
        }

    async def _next_version_number(self, claim_id: UUID) -> int:
        current = (
            await self.db.execute(
                select(func.max(ClaimVersionLedger.version_number)).where(ClaimVersionLedger.claim_id == claim_id)
            )
        ).scalar_one()
        return int((current or 0) + 1)

    def _claim_state_payload(self, claim: ResearchClaim) -> Dict[str, Any]:
        return {
            "id": str(claim.id),
            "mission_id": claim.mission_id,
            "paper_id": str(claim.paper_id),
            "statement_raw": claim.statement_raw,
            "statement_normalized": claim.statement_normalized,
            "intervention_canonical": claim.intervention_canonical,
            "outcome_canonical": claim.outcome_canonical,
            "direction": _enum_value(claim.direction, "unclear"),
            "claim_type": _enum_value(claim.claim_type, "correlational"),
            "composite_confidence": float(claim.composite_confidence or 0.0),
            "study_design_score": float(claim.study_design_score or 0.0),
            "validation_status": _enum_value(claim.validation_status, "unknown"),
            "provenance": _jsonable(claim.provenance or {}),
        }

    async def _update_entity_index(self, claim: ResearchClaim) -> None:
        await self._upsert_entity_record(claim.mission_id, claim.intervention_canonical, EntityType.INTERVENTION, claim.id)
        await self._upsert_entity_record(claim.mission_id, claim.outcome_canonical, EntityType.OUTCOME, claim.id)

    async def _upsert_entity_record(
        self,
        mission_id: str,
        entity_name: Optional[str],
        entity_type: EntityType,
        claim_id: UUID,
    ) -> None:
        entity_text = (entity_name or "").strip()
        if not entity_text:
            return

        existing = (
            await self.db.execute(
                select(CanonicalEntityIndexRecord).where(
                    CanonicalEntityIndexRecord.mission_id == mission_id,
                    CanonicalEntityIndexRecord.entity_name == entity_text,
                    CanonicalEntityIndexRecord.entity_type == entity_type,
                )
            )
        ).scalar_one_or_none()

        if existing:
            claim_ids = [str(item) for item in (existing.claim_ids or [])]
            claim_str = str(claim_id)
            if claim_str not in claim_ids:
                claim_ids.append(claim_str)
            existing.claim_ids = claim_ids
            existing.last_updated = datetime.utcnow()
            await self.db.flush()
            return

        self.db.add(
            CanonicalEntityIndexRecord(
                mission_id=mission_id,
                entity_name=entity_text,
                entity_type=entity_type,
                claim_ids=[str(claim_id)],
            )
        )
        await self.db.flush()

    async def _upsert_graph_node(self, claim: ResearchClaim) -> None:
        existing = await self.db.get(ClaimGraphNode, claim.id)
        if existing:
            existing.intervention_canonical = claim.intervention_canonical
            existing.outcome_canonical = claim.outcome_canonical
            existing.direction = _enum_value(claim.direction, "unclear")
            existing.claim_type = _enum_value(claim.claim_type, "correlational")
            existing.composite_confidence = float(claim.composite_confidence or 0.0)
            existing.publication_year = _claim_publication_year(claim)
            existing.study_design_score = float(claim.study_design_score or 0.5)
            existing.normalized_statement = _claim_statement(claim)
            return

        self.db.add(
            ClaimGraphNode(
                claim_id=claim.id,
                mission_id=claim.mission_id,
                intervention_canonical=claim.intervention_canonical,
                outcome_canonical=claim.outcome_canonical,
                direction=_enum_value(claim.direction, "unclear"),
                claim_type=_enum_value(claim.claim_type, "correlational"),
                composite_confidence=float(claim.composite_confidence or 0.0),
                publication_year=_claim_publication_year(claim),
                study_design_score=float(claim.study_design_score or 0.5),
                normalized_statement=_claim_statement(claim),
            )
        )

    async def _resolve_links_for_claim(self, claim: ResearchClaim) -> None:
        if not claim.intervention_canonical or not claim.outcome_canonical:
            return

        candidate_ids = await self._candidate_claim_ids(claim)
        if not candidate_ids:
            return

        existing_claims = (
            await self.db.execute(
                select(ResearchClaim).where(ResearchClaim.id.in_(candidate_ids))
            )
        ).scalars().all()

        for existing in existing_claims:
            if existing.id == claim.id:
                continue
            resolution = await self._resolve_edge_type_with_llm(claim, existing)
            if not resolution:
                await self.log_event(
                    event_type=MemoryEventType.LINK_RESOLUTION_FAILED,
                    mission_id=claim.mission_id,
                    actor="memory_link_resolver",
                    claim_id=claim.id,
                    previous_value=None,
                    new_value={"other_claim_id": str(existing.id)},
                )
                continue
            edge_type = GraphEdgeType(resolution["edge_type"])
            if edge_type == GraphEdgeType.CONTRADICTS:
                await self.log_event(
                    event_type=MemoryEventType.LINK_RESOLUTION_FAILED,
                    mission_id=claim.mission_id,
                    actor="memory_link_resolver",
                    claim_id=claim.id,
                    previous_value=None,
                    new_value={
                        "other_claim_id": str(existing.id),
                        "reason": "contradictions_reserved_for_module_6",
                    },
                )
                continue
            await self._create_or_update_edge(
                claim,
                existing,
                edge_type,
                justification=resolution["justification"],
                actor="memory_link_resolver",
            )

    async def _candidate_claim_ids(self, claim: ResearchClaim) -> List[UUID]:
        entity_rows = (
            await self.db.execute(
                select(CanonicalEntityIndexRecord).where(
                    CanonicalEntityIndexRecord.mission_id == claim.mission_id,
                    CanonicalEntityIndexRecord.entity_name.in_([
                        claim.intervention_canonical,
                        claim.outcome_canonical,
                    ]),
                )
            )
        ).scalars().all()
        buckets: Dict[str, set[str]] = {}
        for row in entity_rows:
            buckets[f"{row.entity_type.value}:{row.entity_name.lower()}"] = set(row.claim_ids or [])

        intervention_ids = buckets.get(f"intervention:{claim.intervention_canonical.lower()}", set())
        outcome_ids = buckets.get(f"outcome:{claim.outcome_canonical.lower()}", set())
        ids = intervention_ids.intersection(outcome_ids) if intervention_ids and outcome_ids else intervention_ids.union(outcome_ids)
        ids.discard(str(claim.id))
        return [_uuid(item) for item in ids if item]

    async def _resolve_edge_type_with_llm(self, new_claim: ResearchClaim, existing_claim: ResearchClaim) -> Optional[Dict[str, str]]:
        definitions = "\n".join(
            [
                "SUPPORTS - two claims pointing in the same direction for the same intervention/outcome pair",
                "CONTRADICTS - same intervention/outcome pair, opposite direction",
                "REPLICATES - near-identical study design and finding",
                "REFINES - one claim narrows the population or condition of another",
                "IS_SUBGROUP_OF - one claim is a subgroup analysis of another",
            ]
        )
        prompt = f"""You are the link resolver for LHAS memory.

Choose exactly one edge type from this list and provide a one-sentence justification:
{definitions}

Claim A (new):
- statement: {_claim_statement(new_claim)}
- direction: {_enum_value(new_claim.direction, 'unclear')}
- population: {new_claim.population or 'unknown'}
- study type: {new_claim.study_design or 'unknown'}

Claim B (existing):
- statement: {_claim_statement(existing_claim)}
- direction: {_enum_value(existing_claim.direction, 'unclear')}
- population: {existing_claim.population or 'unknown'}
- study type: {existing_claim.study_design or 'unknown'}

Return JSON only:
{{"edge_type": "SUPPORTS", "justification": "one sentence"}}"""

        for _ in range(2):
            try:
                response = await self.llm_provider.generate_async(
                    [
                        {"role": "system", "content": "Return strict JSON only."},
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=220,
                    temperature=0.0,
                )
                content = (response or {}).get("content", "").strip()
                parsed = json.loads(content)
                edge_type = str(parsed.get("edge_type", "")).strip().upper()
                justification = str(parsed.get("justification", "")).strip()
                if edge_type in VALID_EDGE_TYPES and justification:
                    return {"edge_type": edge_type, "justification": justification}
            except Exception as exc:
                logger.warning("Link resolver failed for %s -> %s: %s", new_claim.id, existing_claim.id, exc)
        return None

    async def _create_or_update_edge(
        self,
        left: ResearchClaim,
        right: ResearchClaim,
        edge_type: GraphEdgeType,
        justification: str,
        actor: str,
    ) -> ClaimGraphEdge:
        claim_a_id, claim_b_id = sorted([left.id, right.id], key=lambda item: str(item))
        components = _edge_weight(left, right)
        existing = (
            await self.db.execute(
                select(ClaimGraphEdge).where(
                    ClaimGraphEdge.claim_a_id == claim_a_id,
                    ClaimGraphEdge.claim_b_id == claim_b_id,
                    ClaimGraphEdge.edge_type == edge_type,
                )
            )
        ).scalar_one_or_none()

        if existing:
            previous = {
                "edge_weight": existing.edge_weight,
                "study_design_delta": existing.study_design_delta,
                "confidence_product": existing.confidence_product,
                "recency_weight": existing.recency_weight,
                "justification": existing.justification,
            }
            existing.justification = justification
            existing.study_design_delta = components["study_design_delta"]
            existing.confidence_product = components["confidence_product"]
            existing.recency_weight = components["recency_weight"]
            existing.edge_weight = components["edge_weight"]
            await self.log_event(
                event_type=MemoryEventType.CLAIM_LINKED,
                mission_id=left.mission_id,
                actor=actor,
                claim_id=left.id,
                previous_value=previous,
                new_value={
                    "other_claim_id": str(right.id),
                    "edge_type": edge_type.value,
                    **components,
                },
            )
            return existing

        edge = ClaimGraphEdge(
            mission_id=left.mission_id,
            claim_a_id=claim_a_id,
            claim_b_id=claim_b_id,
            edge_type=edge_type,
            justification=justification,
            study_design_delta=components["study_design_delta"],
            confidence_product=components["confidence_product"],
            recency_weight=components["recency_weight"],
            edge_weight=components["edge_weight"],
        )
        self.db.add(edge)
        await self.log_event(
            event_type=MemoryEventType.CLAIM_LINKED,
            mission_id=left.mission_id,
            actor=actor,
            claim_id=left.id,
            previous_value=None,
            new_value={
                "other_claim_id": str(right.id),
                "edge_type": edge_type.value,
                "justification": justification,
                **components,
            },
        )
        if edge_type == GraphEdgeType.CONTRADICTS:
            await self.log_event(
                event_type=MemoryEventType.CLAIM_FLAGGED_CONTRADICTION,
                mission_id=left.mission_id,
                actor=actor,
                claim_id=left.id,
                previous_value=None,
                new_value={
                    "other_claim_id": str(right.id),
                    **components,
                },
            )
            await self.log_event(
                event_type=MemoryEventType.CONTRADICTION_DETECTED,
                mission_id=left.mission_id,
                actor=actor,
                claim_id=left.id,
                previous_value=None,
                new_value={
                    "other_claim_id": str(right.id),
                    **components,
                },
            )
        return edge

    async def _edge_exists(self, claim_a_id: UUID, claim_b_id: UUID) -> bool:
        a_id, b_id = sorted([claim_a_id, claim_b_id], key=lambda item: str(item))
        edge = (
            await self.db.execute(
                select(ClaimGraphEdge.id).where(
                    ClaimGraphEdge.claim_a_id == a_id,
                    ClaimGraphEdge.claim_b_id == b_id,
                )
            )
        ).first()
        return edge is not None

    async def _sync_synthesis_history(
        self,
        mission_id: str,
        trigger: SynthesisTrigger,
    ) -> Optional[SynthesisHistory]:
        latest = (
            await self.db.execute(
                select(SynthesisHistory)
                .where(SynthesisHistory.mission_id == mission_id)
                .order_by(SynthesisHistory.version_number.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if latest:
            return latest

        synthesis = (
            await self.db.execute(select(SynthesisAnswer).where(SynthesisAnswer.mission_id == mission_id))
        ).scalar_one_or_none()
        if not synthesis or not synthesis.answer_text:
            return None

        if latest and (latest.full_text or "").strip() == (synthesis.answer_text or "").strip():
            return latest

        version_number = int((latest.version_number if latest else 0) + 1)
        claim_ids = await self._current_claim_ids(mission_id)
        contradictions = await self.get_active_contradictions(mission_id)
        history = SynthesisHistory(
            mission_id=mission_id,
            version_number=version_number,
            claim_ids_used=claim_ids,
            contradictions_acknowledged=[item["id"] for item in contradictions],
            full_text=synthesis.answer_text,
            confidence_at_time=float(synthesis.confidence_current or synthesis.answer_confidence or 0.0),
            trigger=trigger,
        )
        self.db.add(history)
        await self.log_event(
            event_type=MemoryEventType.SYNTHESIS_VERSION_CREATED,
            mission_id=mission_id,
            actor="memory_system",
            previous_value=None,
            new_value={"synthesis_version": version_number, "trigger": trigger.value},
        )
        return history

    async def _create_snapshot(
        self,
        mission_id: str,
        cycle_number: int,
        latest_synthesis: Optional[SynthesisHistory],
    ) -> MissionSnapshot:
        papers_count = (
            await self.db.execute(
                select(func.count(ResearchPaper.id)).where(ResearchPaper.mission_id == mission_id)
            )
        ).scalar_one()
        claims = (
            await self.db.execute(
                select(ResearchClaim).where(ResearchClaim.mission_id == mission_id)
            )
        ).scalars().all()
        contradictions_count = (
            await self.db.execute(
                select(func.count(ContradictionRecord.id)).where(ContradictionRecord.mission_id == mission_id)
            )
        ).scalar_one()
        belief_state = (
            await self.db.execute(
                select(BeliefState).where(BeliefState.mission_id == mission_id)
            )
        ).scalar_one_or_none()
        if belief_state:
            current_confidence = round(float(belief_state.current_confidence_score or 0.0), 4)
            direction = belief_state.dominant_evidence_direction
            belief_statement = belief_state.current_belief_statement
        else:
            current_confidence = round(
                (
                    sum(float(claim.composite_confidence or 0.0) for claim in claims) / len(claims)
                ) if claims else 0.0,
                4,
            )
            direction = self._dominant_direction(claims)
            belief_statement = self._belief_statement(claims, direction)
        snapshot = MissionSnapshot(
            mission_id=mission_id,
            cycle_number=cycle_number,
            papers_ingested_count=int(papers_count or 0),
            claims_extracted_count=len(claims),
            active_contradictions_count=int(contradictions_count or 0),
            current_belief_statement=belief_statement,
            current_confidence_score=current_confidence,
            dominant_evidence_direction=direction,
            synthesis_version_id=latest_synthesis.id if latest_synthesis else None,
        )
        self.db.add(snapshot)
        return snapshot

    async def _create_drift_metric(
        self,
        mission_id: str,
        cycle_number: int,
        snapshot: MissionSnapshot,
    ) -> DriftMetric:
        previous_snapshots = (
            await self.db.execute(
                select(MissionSnapshot)
                .where(MissionSnapshot.mission_id == mission_id)
                .order_by(MissionSnapshot.cycle_number.desc())
                .limit(3)
            )
        ).scalars().all()

        previous = previous_snapshots[0] if previous_snapshots else None
        if previous and previous.cycle_number == cycle_number:
            previous = previous_snapshots[1] if len(previous_snapshots) > 1 else None

        confidence_delta = round(
            float(snapshot.current_confidence_score or 0.0) - float(previous.current_confidence_score or 0.0),
            4,
        ) if previous else round(float(snapshot.current_confidence_score or 0.0), 4)

        recent_directions = [snapshot.dominant_evidence_direction.value]
        for row in previous_snapshots[:2]:
            if row.cycle_number != cycle_number:
                recent_directions.append(row.dominant_evidence_direction.value)
        direction_stability = len(set(recent_directions)) <= 1

        recent_contradictions = (
            await self.db.execute(
                select(MissionSnapshot.active_contradictions_count)
                .where(MissionSnapshot.mission_id == mission_id)
                .order_by(MissionSnapshot.cycle_number.desc())
                .limit(5)
            )
        ).scalars().all()
        contradiction_rate = 0.0
        if recent_contradictions:
            deltas: List[float] = []
            for idx in range(len(recent_contradictions) - 1):
                deltas.append(max(0, recent_contradictions[idx] - recent_contradictions[idx + 1]))
            if deltas:
                contradiction_rate = round(sum(deltas) / len(deltas), 4)

        drift = DriftMetric(
            mission_id=mission_id,
            cycle_number=cycle_number,
            confidence_delta=confidence_delta,
            direction_stability=direction_stability,
            contradiction_rate=contradiction_rate,
        )
        self.db.add(drift)
        return drift

    async def _write_checkpoint(
        self,
        mission_id: str,
        cycle_number: int,
        snapshot: MissionSnapshot,
        latest_synthesis: Optional[SynthesisHistory],
    ) -> Optional[MissionCheckpoint]:
        try:
            graph_nodes = (
                await self.db.execute(
                    select(ClaimGraphNode).where(ClaimGraphNode.mission_id == mission_id)
                )
            ).scalars().all()
            graph_edges = (
                await self.db.execute(
                    select(ClaimGraphEdge).where(ClaimGraphEdge.mission_id == mission_id)
                )
            ).scalars().all()
            entity_index = (
                await self.db.execute(
                    select(CanonicalEntityIndexRecord).where(CanonicalEntityIndexRecord.mission_id == mission_id)
                )
            ).scalars().all()
            paper_ids = await self._current_paper_ids(mission_id)

            checkpoint = MissionCheckpoint(
                mission_id=mission_id,
                cycle_number=cycle_number,
                snapshot_payload=self._snapshot_response(snapshot),
                graph_state={
                    "nodes": [
                        {
                            "claim_id": str(node.claim_id),
                            "intervention_canonical": node.intervention_canonical,
                            "outcome_canonical": node.outcome_canonical,
                            "direction": node.direction,
                            "claim_type": node.claim_type,
                            "composite_confidence": node.composite_confidence,
                            "publication_year": node.publication_year,
                        }
                        for node in graph_nodes
                    ],
                    "edges": [
                        {
                            "id": str(edge.id),
                            "claim_a_id": str(edge.claim_a_id),
                            "claim_b_id": str(edge.claim_b_id),
                            "edge_type": edge.edge_type.value,
                            "edge_weight": edge.edge_weight,
                            "study_design_delta": edge.study_design_delta,
                            "confidence_product": edge.confidence_product,
                            "recency_weight": edge.recency_weight,
                            "resolution_status": edge.resolution_status,
                        }
                        for edge in graph_edges
                    ],
                },
                canonical_entity_index=[
                    {
                        "entity_name": row.entity_name,
                        "entity_type": row.entity_type.value,
                        "claim_ids": row.claim_ids or [],
                        "first_seen": row.first_seen.isoformat() if row.first_seen else None,
                        "last_updated": row.last_updated.isoformat() if row.last_updated else None,
                    }
                    for row in entity_index
                ],
                processed_paper_ids=paper_ids,
                last_synthesis_version_id=latest_synthesis.id if latest_synthesis else None,
                pending_events=[],
            )
            self.db.add(checkpoint)
            await self.db.flush()

            old_rows = (
                await self.db.execute(
                    select(MissionCheckpoint)
                    .where(MissionCheckpoint.mission_id == mission_id)
                    .order_by(MissionCheckpoint.created_at.desc())
                )
            ).scalars().all()
            for stale in old_rows[3:]:
                await self.db.delete(stale)
            return checkpoint
        except Exception as exc:
            logger.exception("Checkpoint write failed for mission %s", mission_id)
            await self.log_event(
                event_type=MemoryEventType.CHECKPOINT_WRITE_FAILED,
                mission_id=mission_id,
                actor="memory_system",
                previous_value=None,
                new_value={"error": str(exc), "cycle_number": cycle_number},
            )
            return None

    async def _current_claim_ids(self, mission_id: str) -> List[str]:
        rows = (
            await self.db.execute(
                select(ResearchClaim.id).where(ResearchClaim.mission_id == mission_id)
            )
        ).scalars().all()
        return [str(row) for row in rows]

    async def _current_paper_ids(self, mission_id: str) -> List[str]:
        rows = (
            await self.db.execute(
                select(ResearchPaper.id).where(ResearchPaper.mission_id == mission_id)
            )
        ).scalars().all()
        return [str(row) for row in rows]

    def _dominant_direction(self, claims: Sequence[ResearchClaim]) -> DominantDirection:
        directions = Counter(_enum_value(claim.direction, "unclear").lower() for claim in claims)
        positive = directions.get("positive", 0)
        negative = directions.get("negative", 0)
        null_count = directions.get("null", 0)
        if positive > 0 and negative > 0:
            return DominantDirection.MIXED
        if positive >= negative and positive >= null_count and positive > 0:
            return DominantDirection.POSITIVE
        if negative > 0 and negative >= null_count:
            return DominantDirection.NEGATIVE
        if null_count > 0:
            return DominantDirection.NULL
        return DominantDirection.MIXED

    def _belief_statement(self, claims: Sequence[ResearchClaim], direction: DominantDirection) -> str:
        if not claims:
            return "No evidence-backed belief has been formed yet."
        top_claim = max(claims, key=lambda claim: float(claim.composite_confidence or 0.0))
        statement = _claim_statement(top_claim)
        if direction == DominantDirection.MIXED:
            return f"Evidence is mixed. Highest-confidence current finding: {statement}"
        return f"Current evidence trends {direction.value}. Highest-confidence current finding: {statement}"

    def _snapshot_response(self, snapshot: MissionSnapshot) -> Dict[str, Any]:
        return {
            "id": str(snapshot.id),
            "mission_id": snapshot.mission_id,
            "cycle_number": snapshot.cycle_number,
            "timestamp": snapshot.timestamp.isoformat() if snapshot.timestamp else None,
            "papers_ingested_count": snapshot.papers_ingested_count,
            "claims_extracted_count": snapshot.claims_extracted_count,
            "active_contradictions_count": snapshot.active_contradictions_count,
            "current_belief_statement": snapshot.current_belief_statement,
            "current_confidence_score": snapshot.current_confidence_score,
            "dominant_evidence_direction": snapshot.dominant_evidence_direction.value,
            "synthesis_version_id": str(snapshot.synthesis_version_id) if snapshot.synthesis_version_id else None,
        }

    def _drift_response(self, row: DriftMetric) -> Dict[str, Any]:
        return {
            "id": str(row.id),
            "mission_id": row.mission_id,
            "cycle_number": row.cycle_number,
            "timestamp": row.timestamp.isoformat() if row.timestamp else None,
            "confidence_delta": row.confidence_delta,
            "direction_stability": row.direction_stability,
            "contradiction_rate": row.contradiction_rate,
        }

    async def _belief_state_overview(self, mission_id: str) -> Dict[str, Any] | None:
        state = (
            await self.db.execute(
                select(BeliefState).where(BeliefState.mission_id == mission_id)
            )
        ).scalar_one_or_none()
        latest_revision = (
            await self.db.execute(
                select(BeliefRevisionRecord)
                .where(BeliefRevisionRecord.mission_id == mission_id)
                .order_by(BeliefRevisionRecord.cycle_number.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        active_escalation = (
            await self.db.execute(
                select(BeliefEscalation)
                .where(
                    BeliefEscalation.mission_id == mission_id,
                    BeliefEscalation.status.in_([EscalationStatusEnum.PENDING, EscalationStatusEnum.APPROVED]),
                )
                .order_by(BeliefEscalation.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if not state and not latest_revision and not active_escalation:
            return None
        return {
            "current_confidence_score": float(state.current_confidence_score or 0.0) if state else None,
            "dominant_evidence_direction": state.dominant_evidence_direction.value if state else None,
            "current_revision_type": state.current_revision_type.value if state and state.current_revision_type else None,
            "last_revised_at": state.last_revised_at.isoformat() if state and state.last_revised_at else None,
            "drift_trend": state.drift_trend.value if state and state.drift_trend else None,
            "operator_action_required": bool(state.operator_action_required) if state else False,
            "latest_revision_id": str(latest_revision.id) if latest_revision else None,
            "latest_revision_type": latest_revision.revision_type.value if latest_revision else None,
            "active_escalation_id": str(active_escalation.id) if active_escalation else None,
            "active_escalation_status": active_escalation.status.value if active_escalation else None,
        }

    def _cosine_similarity(self, left: Sequence[float], right: Sequence[float]) -> float:
        numerator = sum(float(a) * float(b) for a, b in zip(left, right))
        left_norm = math.sqrt(sum(float(a) * float(a) for a in left))
        right_norm = math.sqrt(sum(float(b) * float(b) for b in right))
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return numerator / (left_norm * right_norm)
