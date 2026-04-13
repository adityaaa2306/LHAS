from __future__ import annotations

from datetime import datetime
from uuid import uuid4
import enum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    Uuid,
)

from .belief_revision import ContradictionSeverityEnum
from .mission import Base


class PopulationOverlapEnum(str, enum.Enum):
    IDENTICAL = "identical"
    PARTIAL = "partial"
    DIFFERENT = "different"


class ContextResolutionResultEnum(str, enum.Enum):
    POPULATION_DIFFERENCE = "population_difference"
    CONDITION_DIFFERENCE = "condition_difference"
    STUDY_DESIGN_ASYMMETRY = "study_design_asymmetry"
    NONE_RESOLVED = "none_resolved"


class SemanticVerificationResultEnum(str, enum.Enum):
    GENUINE_CONTRADICTION = "GENUINE_CONTRADICTION"
    COMPATIBLE = "COMPATIBLE"
    AMBIGUOUS = "AMBIGUOUS"


class VerificationStageEnum(str, enum.Enum):
    POPULATION_COMPARE = "population_compare"
    CONDITION_COMPARE = "condition_compare"
    SEMANTIC_VERIFICATION = "semantic_verification"


class ContradictionRecord(Base):
    __tablename__ = "contradiction_records"

    id = Column(Uuid, primary_key=True, default=uuid4)
    mission_id = Column(String(36), ForeignKey("missions.id", ondelete="CASCADE"), nullable=False, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    claim_a_id = Column(Uuid, ForeignKey("research_claims.id", ondelete="CASCADE"), nullable=False, index=True)
    claim_b_id = Column(Uuid, ForeignKey("research_claims.id", ondelete="CASCADE"), nullable=False, index=True)
    graph_edge_id = Column(Uuid, ForeignKey("memory_claim_graph_edges.id", ondelete="SET NULL"), nullable=True, index=True)
    severity = Column(Enum(ContradictionSeverityEnum, native_enum=False), nullable=False)
    direction_a = Column(String(32), nullable=False)
    direction_b = Column(String(32), nullable=False)
    intervention_canonical = Column(String(255), nullable=True, index=True)
    outcome_canonical = Column(String(255), nullable=True, index=True)
    quality_parity_delta = Column(Float, nullable=False, default=0.0)
    confidence_product = Column(Float, nullable=False, default=0.0)
    population_overlap = Column(Enum(PopulationOverlapEnum, native_enum=False), nullable=False)
    context_resolution_attempted = Column(Boolean, nullable=False, default=True)
    context_resolution_result = Column(
        Enum(ContextResolutionResultEnum, native_enum=False),
        nullable=False,
        default=ContextResolutionResultEnum.NONE_RESOLVED,
    )
    semantic_verification_result = Column(
        Enum(SemanticVerificationResultEnum, native_enum=False),
        nullable=False,
        default=SemanticVerificationResultEnum.GENUINE_CONTRADICTION,
    )
    llm_verification_call_id = Column(
        Uuid,
        ForeignKey("contradiction_verification_calls.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    resolution_status = Column(String(32), nullable=False, default="unresolved")
    resolution_timestamp = Column(DateTime, nullable=True)
    resolved_by = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_contradiction_record_pair", "mission_id", "claim_a_id", "claim_b_id", unique=True),
        Index("ix_contradiction_record_mission_time", "mission_id", "timestamp"),
        Index("ix_contradiction_record_mission_severity", "mission_id", "severity"),
    )


class ContextResolvedPairRecord(Base):
    __tablename__ = "contradiction_context_resolved_pairs"

    id = Column(Uuid, primary_key=True, default=uuid4)
    mission_id = Column(String(36), ForeignKey("missions.id", ondelete="CASCADE"), nullable=False, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    claim_a_id = Column(Uuid, ForeignKey("research_claims.id", ondelete="CASCADE"), nullable=False, index=True)
    claim_b_id = Column(Uuid, ForeignKey("research_claims.id", ondelete="CASCADE"), nullable=False, index=True)
    direction_a = Column(String(32), nullable=False)
    direction_b = Column(String(32), nullable=False)
    intervention_canonical = Column(String(255), nullable=True, index=True)
    outcome_canonical = Column(String(255), nullable=True, index=True)
    resolution_reason = Column(Enum(ContextResolutionResultEnum, native_enum=False), nullable=False)
    stronger_claim_id = Column(Uuid, ForeignKey("research_claims.id", ondelete="SET NULL"), nullable=True)
    llm_call_id = Column(Uuid, ForeignKey("contradiction_verification_calls.id", ondelete="SET NULL"), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_contradiction_context_pair", "mission_id", "claim_a_id", "claim_b_id", unique=True),
        Index("ix_contradiction_context_reason", "mission_id", "resolution_reason"),
    )


class AmbiguousContradictionRecord(Base):
    __tablename__ = "contradiction_ambiguous_pairs"

    id = Column(Uuid, primary_key=True, default=uuid4)
    mission_id = Column(String(36), ForeignKey("missions.id", ondelete="CASCADE"), nullable=False, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    claim_a_id = Column(Uuid, ForeignKey("research_claims.id", ondelete="CASCADE"), nullable=False, index=True)
    claim_b_id = Column(Uuid, ForeignKey("research_claims.id", ondelete="CASCADE"), nullable=False, index=True)
    direction_a = Column(String(32), nullable=False)
    direction_b = Column(String(32), nullable=False)
    intervention_canonical = Column(String(255), nullable=True, index=True)
    outcome_canonical = Column(String(255), nullable=True, index=True)
    ambiguity_reason = Column(String(100), nullable=False, default="semantic_verification_ambiguous")
    llm_verification_call_id = Column(
        Uuid,
        ForeignKey("contradiction_verification_calls.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    review_status = Column(String(32), nullable=False, default="pending_review")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_contradiction_ambiguous_pair", "mission_id", "claim_a_id", "claim_b_id", unique=True),
        Index("ix_contradiction_ambiguous_review", "mission_id", "review_status"),
    )


class ContradictionVerificationCall(Base):
    __tablename__ = "contradiction_verification_calls"

    id = Column(Uuid, primary_key=True, default=uuid4)
    mission_id = Column(String(36), ForeignKey("missions.id", ondelete="CASCADE"), nullable=False, index=True)
    pair_key = Column(String(100), nullable=False, index=True)
    claim_a_id = Column(Uuid, ForeignKey("research_claims.id", ondelete="CASCADE"), nullable=False, index=True)
    claim_b_id = Column(Uuid, ForeignKey("research_claims.id", ondelete="CASCADE"), nullable=False, index=True)
    stage = Column(Enum(VerificationStageEnum, native_enum=False), nullable=False)
    prompt_text = Column(Text, nullable=False)
    response_text = Column(Text, nullable=True)
    validated_output = Column(String(64), nullable=False)
    attempt_number = Column(String(16), nullable=False, default="1")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    __table_args__ = (
        Index("ix_contradiction_verification_pair_stage", "pair_key", "stage", "created_at"),
    )
