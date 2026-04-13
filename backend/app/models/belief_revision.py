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
from .memory import DominantDirection


class RevisionTypeEnum(str, enum.Enum):
    REINFORCE = "REINFORCE"
    WEAK_REINFORCE = "WEAK_REINFORCE"
    WEAKEN = "WEAKEN"
    MATERIAL_UPDATE = "MATERIAL_UPDATE"
    ESCALATE_FOR_REVIEW = "ESCALATE_FOR_REVIEW"
    REVERSAL = "REVERSAL"
    CONTRADICTION_PENALTY = "CONTRADICTION_PENALTY"
    NO_UPDATE = "NO_UPDATE"


class ContradictionSeverityEnum(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class EscalationStatusEnum(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    APPLIED = "APPLIED"
    EXPIRED = "EXPIRED"
    CLEARED = "CLEARED"


class DriftTrendEnum(str, enum.Enum):
    STABILIZING = "stabilizing"
    DRIFTING = "drifting"
    REVERSING = "reversing"


class BeliefState(Base):
    __tablename__ = "belief_states"

    id = Column(Uuid, primary_key=True, default=uuid4)
    mission_id = Column(String(36), ForeignKey("missions.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    current_belief_statement = Column(Text, nullable=True)
    current_confidence_score = Column(Float, nullable=False, default=0.0)
    dominant_evidence_direction = Column(
        Enum(DominantDirection, native_enum=False),
        nullable=False,
        default=DominantDirection.MIXED,
    )
    current_revision_type = Column(
        Enum(RevisionTypeEnum, native_enum=False),
        nullable=True,
    )
    last_revised_at = Column(DateTime, nullable=True)
    last_cycle_number = Column(Integer, nullable=False, default=0)
    operator_action_required = Column(Boolean, nullable=False, default=False)
    drift_trend = Column(
        Enum(DriftTrendEnum, native_enum=False),
        nullable=False,
        default=DriftTrendEnum.STABILIZING,
    )
    active_escalation_id = Column(Uuid, nullable=True)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class BeliefRevisionRecord(Base):
    __tablename__ = "belief_revision_records"

    id = Column(Uuid, primary_key=True, default=uuid4)
    mission_id = Column(String(36), ForeignKey("missions.id", ondelete="CASCADE"), nullable=False, index=True)
    cycle_number = Column(Integer, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    revision_type = Column(Enum(RevisionTypeEnum, native_enum=False), nullable=False)
    previous_confidence = Column(Float, nullable=False, default=0.0)
    new_confidence = Column(Float, nullable=False, default=0.0)
    confidence_delta = Column(Float, nullable=False, default=0.0)
    previous_direction = Column(Enum(DominantDirection, native_enum=False), nullable=False, default=DominantDirection.MIXED)
    new_direction = Column(Enum(DominantDirection, native_enum=False), nullable=False, default=DominantDirection.MIXED)
    evidence_summary = Column(JSON, nullable=False, default=dict)
    decision_rationale = Column(Text, nullable=True)
    claims_considered = Column(JSON, nullable=False, default=list)
    claims_filtered = Column(JSON, nullable=False, default=list)
    triggered_synthesis_regen = Column(Boolean, nullable=False, default=False)
    operator_action_required = Column(Boolean, nullable=False, default=False)
    applied_automatically = Column(Boolean, nullable=False, default=True)
    condition_fired = Column(String(64), nullable=True)

    __table_args__ = (
        Index("ix_belief_revision_mission_cycle", "mission_id", "cycle_number", unique=True),
        Index("ix_belief_revision_mission_time", "mission_id", "timestamp"),
    )


class BeliefEscalation(Base):
    __tablename__ = "belief_escalations"

    id = Column(Uuid, primary_key=True, default=uuid4)
    mission_id = Column(String(36), ForeignKey("missions.id", ondelete="CASCADE"), nullable=False, index=True)
    source_revision_id = Column(Uuid, ForeignKey("belief_revision_records.id", ondelete="SET NULL"), nullable=True)
    originating_cycle_number = Column(Integer, nullable=False)
    target_direction = Column(Enum(DominantDirection, native_enum=False), nullable=False)
    evidence_summary = Column(JSON, nullable=False, default=dict)
    status = Column(Enum(EscalationStatusEnum, native_enum=False), nullable=False, default=EscalationStatusEnum.PENDING)
    operator_approved = Column(Boolean, nullable=False, default=False)
    operator_notes = Column(Text, nullable=True)
    approved_at = Column(DateTime, nullable=True)
    expires_after_cycle = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_belief_escalation_mission_status", "mission_id", "status"),
        Index("ix_belief_escalation_mission_cycle", "mission_id", "originating_cycle_number"),
    )
