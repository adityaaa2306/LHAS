from __future__ import annotations

from datetime import datetime
from uuid import uuid4
import enum

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
)

from .mission import Base


class MemoryEventType(str, enum.Enum):
    CLAIM_CREATED = "claim_created"
    CLAIM_LINKED = "claim_linked"
    CLAIM_FLAGGED_CONTRADICTION = "claim_flagged_contradiction"
    CLAIM_CONFIDENCE_REVISED = "claim_confidence_revised"
    CLAIM_INTAKE_FILTERED = "claim_intake_filtered"
    CLAIM_EXCLUDED_BY_OPERATOR = "claim_excluded_by_operator"
    SYNTHESIS_VERSION_CREATED = "synthesis_version_created"
    SYNTHESIS_CREATED = "synthesis.created"
    SYNTHESIS_MAJOR_CHANGE = "synthesis.major_change"
    BELIEF_STATE_UPDATED = "belief_state_updated"
    BELIEF_REINFORCED = "belief.reinforced"
    BELIEF_WEAKENED = "belief.weakened"
    BELIEF_MATERIAL_UPDATE = "belief.material_update"
    BELIEF_ESCALATED = "belief.escalated"
    BELIEF_REVERSED = "belief.reversed"
    BELIEF_NO_UPDATE = "belief.no_update"
    BELIEF_DRIFT_INSTABILITY = "belief.drift_instability"
    REVISION_RECORD_CREATED = "revision_record_created"
    REVISION_FAILED = "revision.failed"
    CONTRADICTION_HIGH_SEVERITY = "contradiction.high_severity"
    CONTRADICTION_CONTEXT_RESOLVED = "contradiction.context_resolved"
    CONTRADICTION_AMBIGUOUS = "contradiction.ambiguous"
    CONTRADICTION_INSTABILITY_SIGNAL = "contradiction.instability_signal"
    CONTRADICTION_DIRECTION_COMPATIBLE = "contradiction.direction_compatible"
    CONTRADICTION_NO_CANDIDATES = "contradiction.no_candidates"
    CONTRADICTION_CANDIDATE_CAPPED = "contradiction.candidate_capped"
    MONITORING_SNAPSHOT_CREATED = "monitoring.snapshot_created"
    MONITORING_ALERT_FIRING = "monitoring.alert_firing"
    MONITORING_ALERT_RESOLVED = "monitoring.alert_resolved"
    MONITORING_HEALTH_DEGRADED = "monitoring.health_degraded"
    MONITORING_HEALTH_RESTORED = "monitoring.health_restored"
    LLM_VERIFICATION_FAILED = "llm_verification_failed"
    EXCESS_DROP_CAPPED = "excess_drop_capped"
    EXCESS_RISE_CAPPED = "excess_rise_capped"
    ESCALATION_EXPIRED = "escalation_expired"
    LINK_RESOLUTION_FAILED = "link_resolution_failed"
    STORAGE_FAILED = "storage.failed"
    CONTRADICTION_DETECTED = "contradiction.detected"
    CHECKPOINT_WRITE_FAILED = "checkpoint_write_failed"
    CLUSTER_PASS_FAILED = "cluster_pass_failed"
    CLUSTER_REVIEW_FLAGGED = "cluster_review_flagged"


class RawPaperStatus(str, enum.Enum):
    INGESTED = "ingested"
    EXTRACTION_COMPLETE = "extraction_complete"
    FAILED = "failed"


class EntityType(str, enum.Enum):
    INTERVENTION = "intervention"
    OUTCOME = "outcome"


class GraphEdgeType(str, enum.Enum):
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    REPLICATES = "REPLICATES"
    REFINES = "REFINES"
    IS_SUBGROUP_OF = "IS_SUBGROUP_OF"


class DominantDirection(str, enum.Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NULL = "null"
    MIXED = "mixed"


class SynthesisTrigger(str, enum.Enum):
    NEW_PAPER = "new_paper"
    CONTRADICTION = "contradiction"
    BELIEF_MATERIAL_UPDATE = "belief_material_update"
    BELIEF_REVERSED = "belief_reversed"
    OPERATOR_REQUEST = "operator_request"
    SCHEDULED = "scheduled"


class RawPaperRecord(Base):
    __tablename__ = "memory_raw_paper_records"

    id = Column(Uuid, primary_key=True, default=uuid4)
    mission_id = Column(String(36), ForeignKey("missions.id", ondelete="CASCADE"), nullable=False, index=True)
    research_paper_id = Column(Uuid, ForeignKey("research_papers.id", ondelete="SET NULL"), nullable=True, index=True)
    paper_external_id = Column(String(255), nullable=True, index=True)
    title = Column(Text, nullable=False)
    authors = Column(JSON, nullable=True)
    doi_or_url = Column(String(500), nullable=True)
    publication_year = Column(Integer, nullable=True)
    journal = Column(String(255), nullable=True)
    study_type = Column(String(100), nullable=True)
    ingestion_timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    full_text_available = Column(Boolean, default=False, nullable=False)
    abstract_text = Column(Text, nullable=True)
    status = Column(Enum(RawPaperStatus), default=RawPaperStatus.INGESTED, nullable=False)
    actor = Column(String(100), nullable=False, default="paper_ingestion")
    payload = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_memory_raw_paper_mission_created", "mission_id", "created_at"),
    )


class RawClaimRecord(Base):
    __tablename__ = "memory_raw_claim_records"

    id = Column(Uuid, primary_key=True, default=uuid4)
    mission_id = Column(String(36), ForeignKey("missions.id", ondelete="CASCADE"), nullable=False, index=True)
    research_claim_id = Column(Uuid, ForeignKey("research_claims.id", ondelete="SET NULL"), nullable=True, index=True)
    paper_id = Column(Uuid, ForeignKey("research_papers.id", ondelete="SET NULL"), nullable=True, index=True)
    actor = Column(String(100), nullable=False, default="claim_extraction")
    extraction_timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    payload = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_memory_raw_claim_mission_created", "mission_id", "created_at"),
    )


class ProvenanceLogEntry(Base):
    __tablename__ = "memory_provenance_log"

    id = Column(Uuid, primary_key=True, default=uuid4)
    event_type = Column(Enum(MemoryEventType), nullable=False, index=True)
    claim_id = Column(Uuid, ForeignKey("research_claims.id", ondelete="SET NULL"), nullable=True, index=True)
    paper_id = Column(Uuid, ForeignKey("research_papers.id", ondelete="SET NULL"), nullable=True, index=True)
    mission_id = Column(String(36), ForeignKey("missions.id", ondelete="CASCADE"), nullable=False, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    actor = Column(String(100), nullable=False)
    previous_value = Column(JSON, nullable=True)
    new_value = Column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_memory_provenance_mission_time", "mission_id", "timestamp"),
    )


class ClaimVersionLedger(Base):
    __tablename__ = "memory_claim_version_ledger"

    id = Column(Uuid, primary_key=True, default=uuid4)
    claim_id = Column(Uuid, ForeignKey("research_claims.id", ondelete="SET NULL"), nullable=True, index=True)
    mission_id = Column(String(36), ForeignKey("missions.id", ondelete="CASCADE"), nullable=False, index=True)
    version_number = Column(Integer, nullable=False)
    changed_field = Column(String(100), nullable=False)
    old_value = Column(JSON, nullable=True)
    new_value = Column(JSON, nullable=True)
    changed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    changed_by_module = Column(String(100), nullable=False)

    __table_args__ = (
        Index("ix_memory_claim_version_claim_version", "claim_id", "version_number"),
    )


class CanonicalEntityIndexRecord(Base):
    __tablename__ = "memory_canonical_entity_index"

    id = Column(Uuid, primary_key=True, default=uuid4)
    mission_id = Column(String(36), ForeignKey("missions.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_name = Column(String(255), nullable=False, index=True)
    entity_type = Column(Enum(EntityType), nullable=False, index=True)
    claim_ids = Column(JSON, nullable=False, default=list)
    first_seen = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_updated = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_memory_entity_unique_lookup", "mission_id", "entity_name", "entity_type", unique=True),
    )


class ClaimGraphNode(Base):
    __tablename__ = "memory_claim_graph_nodes"

    claim_id = Column(Uuid, ForeignKey("research_claims.id", ondelete="CASCADE"), primary_key=True)
    mission_id = Column(String(36), ForeignKey("missions.id", ondelete="CASCADE"), nullable=False, index=True)
    intervention_canonical = Column(String(255), nullable=True, index=True)
    outcome_canonical = Column(String(255), nullable=True, index=True)
    direction = Column(String(32), nullable=True)
    claim_type = Column(String(50), nullable=True)
    composite_confidence = Column(Float, nullable=False, default=0.0)
    publication_year = Column(Integer, nullable=True)
    study_design_score = Column(Float, nullable=False, default=0.5)
    normalized_statement = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_memory_graph_node_pair", "mission_id", "intervention_canonical", "outcome_canonical"),
    )


class ClaimGraphEdge(Base):
    __tablename__ = "memory_claim_graph_edges"

    id = Column(Uuid, primary_key=True, default=uuid4)
    mission_id = Column(String(36), ForeignKey("missions.id", ondelete="CASCADE"), nullable=False, index=True)
    claim_a_id = Column(Uuid, ForeignKey("research_claims.id", ondelete="CASCADE"), nullable=False, index=True)
    claim_b_id = Column(Uuid, ForeignKey("research_claims.id", ondelete="CASCADE"), nullable=False, index=True)
    edge_type = Column(Enum(GraphEdgeType), nullable=False, index=True)
    justification = Column(Text, nullable=True)
    study_design_delta = Column(Float, nullable=False)
    confidence_product = Column(Float, nullable=False)
    recency_weight = Column(Float, nullable=False)
    edge_weight = Column(Float, nullable=False)
    resolution_status = Column(String(32), nullable=False, default="unresolved")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_memory_graph_edge_pair_type", "claim_a_id", "claim_b_id", "edge_type", unique=True),
        Index("ix_memory_graph_edge_mission_type", "mission_id", "edge_type"),
    )


class MissionSnapshot(Base):
    __tablename__ = "memory_mission_snapshots"

    id = Column(Uuid, primary_key=True, default=uuid4)
    mission_id = Column(String(36), ForeignKey("missions.id", ondelete="CASCADE"), nullable=False, index=True)
    cycle_number = Column(Integer, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    papers_ingested_count = Column(Integer, nullable=False, default=0)
    claims_extracted_count = Column(Integer, nullable=False, default=0)
    active_contradictions_count = Column(Integer, nullable=False, default=0)
    current_belief_statement = Column(Text, nullable=True)
    current_confidence_score = Column(Float, nullable=False, default=0.0)
    dominant_evidence_direction = Column(Enum(DominantDirection), nullable=False, default=DominantDirection.MIXED)
    synthesis_version_id = Column(Uuid, ForeignKey("memory_synthesis_history.id", ondelete="SET NULL"), nullable=True)

    __table_args__ = (
        Index("ix_memory_snapshot_mission_cycle", "mission_id", "cycle_number", unique=True),
    )


class SynthesisLLMCall(Base):
    __tablename__ = "memory_synthesis_llm_calls"

    id = Column(Uuid, primary_key=True, default=uuid4)
    mission_id = Column(String(36), ForeignKey("missions.id", ondelete="CASCADE"), nullable=False, index=True)
    prompt_text = Column(Text, nullable=False)
    response_text = Column(Text, nullable=True)
    validation_status = Column(String(32), nullable=False, default="passed")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class SynthesisHistory(Base):
    __tablename__ = "memory_synthesis_history"

    id = Column(Uuid, primary_key=True, default=uuid4)
    mission_id = Column(String(36), ForeignKey("missions.id", ondelete="CASCADE"), nullable=False, index=True)
    version_number = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    claim_ids_used = Column(JSON, nullable=False, default=list)
    contradictions_acknowledged = Column(JSON, nullable=False, default=list)
    full_text = Column(Text, nullable=True)
    confidence_at_time = Column(Float, nullable=False, default=0.0)
    trigger = Column(Enum(SynthesisTrigger), nullable=False, default=SynthesisTrigger.NEW_PAPER)
    confidence_tier = Column(String(16), nullable=True)
    dominant_direction = Column(String(32), nullable=True)
    claim_ids_tier1 = Column(JSON, nullable=False, default=list)
    claim_ids_tier2 = Column(JSON, nullable=False, default=list)
    claim_ids_tier3 = Column(JSON, nullable=False, default=list)
    contradictions_included = Column(JSON, nullable=False, default=list)
    change_magnitude = Column(String(16), nullable=True)
    confidence_delta = Column(Float, nullable=True)
    direction_changed = Column(Boolean, nullable=False, default=False)
    prior_synthesis_id = Column(Uuid, ForeignKey("memory_synthesis_history.id", ondelete="SET NULL"), nullable=True)
    llm_call_id = Column(Uuid, ForeignKey("memory_synthesis_llm_calls.id", ondelete="SET NULL"), nullable=True)
    validation_passed = Column(Boolean, nullable=False, default=False)
    llm_fallback = Column(Boolean, nullable=False, default=False)
    word_count = Column(Integer, nullable=False, default=0)
    evidence_package = Column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_memory_synthesis_mission_version", "mission_id", "version_number", unique=True),
    )


class DriftMetric(Base):
    __tablename__ = "memory_drift_metrics"

    id = Column(Uuid, primary_key=True, default=uuid4)
    mission_id = Column(String(36), ForeignKey("missions.id", ondelete="CASCADE"), nullable=False, index=True)
    cycle_number = Column(Integer, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    confidence_delta = Column(Float, nullable=False, default=0.0)
    direction_stability = Column(Boolean, nullable=False, default=True)
    contradiction_rate = Column(Float, nullable=False, default=0.0)

    __table_args__ = (
        Index("ix_memory_drift_mission_cycle", "mission_id", "cycle_number", unique=True),
    )


class MissionCheckpoint(Base):
    __tablename__ = "memory_mission_checkpoints"

    id = Column(Uuid, primary_key=True, default=uuid4)
    mission_id = Column(String(36), ForeignKey("missions.id", ondelete="CASCADE"), nullable=False, index=True)
    cycle_number = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    snapshot_payload = Column(JSON, nullable=False)
    graph_state = Column(JSON, nullable=False)
    canonical_entity_index = Column(JSON, nullable=False)
    processed_paper_ids = Column(JSON, nullable=False)
    last_synthesis_version_id = Column(Uuid, ForeignKey("memory_synthesis_history.id", ondelete="SET NULL"), nullable=True)
    pending_events = Column(JSON, nullable=False, default=list)
    is_valid = Column(Boolean, nullable=False, default=True)

    __table_args__ = (
        Index("ix_memory_checkpoint_mission_cycle", "mission_id", "cycle_number"),
    )
