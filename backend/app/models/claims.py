"""Claims and Synthesis Models - MODULE 3 CLAIM EXTRACTION"""

from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import Column, DateTime, Float, Integer, String, Text, Uuid, ForeignKey, JSON, Index, Enum, Boolean
from .mission import Base
import enum


class ClaimTypeEnum(str, enum.Enum):
    """Epistemic classification of claims (Pass 2a)"""
    CAUSAL = "causal"
    CORRELATIONAL = "correlational"
    MECHANISTIC = "mechanistic"
    COMPARATIVE = "comparative"
    SAFETY = "safety"
    PREVALENCE = "prevalence"
    NULL_RESULT = "null_result"


class DirectionEnum(str, enum.Enum):
    """Direction of claimed effect"""
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NULL = "null"
    UNCLEAR = "unclear"


class SectionSourceEnum(str, enum.Enum):
    """Where the claim was extracted from"""
    ABSTRACT = "abstract"
    RESULTS = "results"
    DISCUSSION = "discussion"
    CONCLUSION = "conclusion"
    UNKNOWN = "unknown"


class MissionRelevanceEnum(str, enum.Enum):
    """How relevant this claim is to the mission"""
    PRIMARY = "primary"
    SECONDARY = "secondary"
    PERIPHERAL = "peripheral"


class ValidationStatusEnum(str, enum.Enum):
    """Validation status of extracted claim"""
    VALID = "VALID"
    EXTRACTION_DEGRADED = "EXTRACTION_DEGRADED"
    UNKNOWN_TYPE = "UNKNOWN_TYPE"


class ResearchClaim(Base):
    """
    Research claims extracted from papers via three-pass pipeline.
    
    Pass 1: LLM semantic identification → statement_raw, intervention, outcome, population, hedging_text
    Pass 2a: LLM causal classification → claim_type, study_design_consistent
    Pass 2b: LLM entity normalization → intervention_canonical, outcome_canonical
    Pass 3: Rule-based confidence assembly → composite_confidence, confidence_components
    """

    __tablename__ = "research_claims"

    # Core identity
    id = Column(Uuid, primary_key=True, default=uuid4)
    mission_id = Column(String(36), ForeignKey('missions.id', ondelete='CASCADE'), nullable=False, index=True)
    paper_id = Column(Uuid, ForeignKey('research_papers.id', ondelete='CASCADE'), nullable=False, index=True)

    # ==================== PASS 1: SEMANTIC IDENTIFICATION ====================
    
    # Raw claim text (from paper, verbatim or near-verbatim)
    statement_raw = Column(Text, nullable=False)
    statement_normalized = Column(Text, nullable=True)  # Cleaned version
    
    # PICO extraction
    intervention = Column(Text, nullable=True)  # What agent/treatment/variable is acting
    outcome = Column(Text, nullable=True)  # What is being affected/measured
    population = Column(Text, nullable=True)  # Who/what the claim applies to
    
    # Direction of effect
    direction = Column(Enum(DirectionEnum), default=DirectionEnum.UNCLEAR, nullable=False)
    
    # Hedging language from source
    hedging_text = Column(Text, nullable=True)  # e.g. "may", "suggests", "was associated with"
    
    # Section location
    section_source = Column(Enum(SectionSourceEnum), default=SectionSourceEnum.UNKNOWN, nullable=False)
    
    # Pass 1 confidence (model's faith in extraction)
    extraction_certainty = Column(Float, default=0.5, nullable=False)  # 0.0-1.0
    
    # Failure logging (next-gen)
    pass1_prompt_version = Column(String(255), nullable=True)  # Hash of Pass 1 prompt template for A/B testing
    verification_failure_logged = Column(Boolean, default=False, nullable=False)  # Flag: verification failure logged
    verification_success_logged = Column(Boolean, default=False, nullable=False)  # Flag: verification success logged

    # ==================== PASS 2A: CAUSAL CLASSIFICATION ====================
    
    claim_type = Column(Enum(ClaimTypeEnum), default=ClaimTypeEnum.CORRELATIONAL, nullable=False)
    causal_justification = Column(Text, nullable=True)  # Brief reason for classification
    study_design_consistent = Column(Boolean, default=True, nullable=False)  # Does claim match study design?
    causal_downgrade_applied = Column(Boolean, default=False, nullable=False)  # Was it downgraded due to study design?
    
    # Argument coherence (next-gen)
    internal_conflict = Column(Boolean, default=False, nullable=False)  # Paper has internal direction conflict
    coherence_flags = Column(JSON, nullable=True)  # Array of coherence issues detected
    coherence_confidence_adjustment = Column(Float, default=1.0, nullable=False)  # Multiplicative factor for composite_confidence

    # ==================== PASS 2B: ENTITY NORMALIZATION ====================
    
    # Canonical entity names
    intervention_canonical = Column(String(255), nullable=True)
    outcome_canonical = Column(String(255), nullable=True)
    
    # Normalization quality signals
    normalization_confidence = Column(Float, default=0.0, nullable=False)  # 0.0-1.0
    normalization_uncertain = Column(Boolean, default=False, nullable=False)  # Flag uncertain mappings
    
    # Entity evolution status (next-gen)
    intervention_normalization_status = Column(String(50), nullable=True)  # confirmed, merge_candidate, new_entity_pending, rejected
    outcome_normalization_status = Column(String(50), nullable=True)  # confirmed, merge_candidate, new_entity_pending, rejected
    glossary_version = Column(Integer, default=1, nullable=False)  # Version of glossary used for normalization

    # ==================== PASS 3: CONFIDENCE ASSEMBLY ====================
    
    # Composite confidence score (deterministic, auditable)
    composite_confidence = Column(Float, default=0.4, nullable=False)  # 0.05-0.95
    
    # Decomposed confidence components (for auditability)
    study_design_score = Column(Float, default=0.4, nullable=False)  # Signal A
    hedging_penalty = Column(Float, default=0.0, nullable=False)  # Signal B
    
    # Next-generation uncertainty decomposition (4-component model)
    extraction_uncertainty = Column(Float, default=0.5, nullable=False)  # 0.05-0.95
    study_uncertainty = Column(Float, default=0.5, nullable=False)  # 0.05-0.95
    generalizability_uncertainty = Column(Float, default=0.5, nullable=False)  # 0.05-1.0
    replication_uncertainty = Column(Float, default=0.5, nullable=False)  # 0.05-0.95
    
    # Full confidence breakdown for auditability
    confidence_components = Column(JSON, nullable=True)  # {extraction, study, generalizability, replication}
    
    # ==================== VALIDATION & METADATA ====================
    
    validation_status = Column(Enum(ValidationStatusEnum), default=ValidationStatusEnum.VALID, nullable=False)
    mission_relevance = Column(Enum(MissionRelevanceEnum), default=MissionRelevanceEnum.SECONDARY, nullable=False)
    
    # Paper provenance
    paper_title = Column(String(500), nullable=True)
    doi_or_url = Column(String(500), nullable=True)
    study_design = Column(String(100), nullable=True)  # RCT, observational, etc.

    # ==================== PROCESSING METADATA ====================
    
    # Timestamps
    extraction_timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Extraction cycle
    discovery_cycle = Column(Integer, nullable=True)

    # ==================== FULL PROVENANCE (JSON) ====================
    
    provenance = Column(JSON, nullable=False)  # Stores complete provenance record
    
    # ==================== INDEXING ====================
    
    __table_args__ = (
        Index('ix_claim_mission', 'mission_id'),
        Index('ix_claim_paper', 'paper_id'),
        Index('ix_claim_mission_paper', 'mission_id', 'paper_id'),
        Index('ix_claim_confidence', 'mission_id', 'composite_confidence'),
        Index('ix_claim_type', 'mission_id', 'claim_type'),
        Index('ix_claim_validation', 'mission_id', 'validation_status'),
    )

    def __repr__(self) -> str:
        return f"<ResearchClaim id={self.id} type={self.claim_type} conf={self.composite_confidence:.2f}>"


class SynthesisAnswer(Base):
    """Current synthesized answer to the research question."""

    __tablename__ = "synthesis_answers"

    id = Column(Uuid, primary_key=True, default=uuid4)
    mission_id = Column(Uuid, nullable=False, unique=True, index=True)
    
    # Current answer
    answer_text = Column(Text, nullable=True)
    answer_confidence = Column(Float, default=0.0, nullable=False)
    
    # Key findings
    key_findings = Column(JSON, nullable=True)  # List of key finding strings
    
    # Uncertainty & limitations
    uncertainty_statement = Column(Text, nullable=True)
    limitations = Column(JSON, nullable=True)  # List of limitation statements
    knowledge_gaps = Column(JSON, nullable=True)  # Areas needing more research
    
    # Supporting evidence
    supporting_claims_count = Column(Integer, default=0, nullable=False)
    contradicting_claims_count = Column(Integer, default=0, nullable=False)
    neutral_claims_count = Column(Integer, default=0, nullable=False)
    
    # Confidence trajectory
    confidence_at_creation = Column(Float, default=0.0, nullable=True)
    confidence_current = Column(Float, default=0.0, nullable=True)
    
    # Generation metadata
    generated_by = Column(String(100), default="llm", nullable=False)  # llm, hybrid, manual
    generation_cycle = Column(Integer, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_reviewed_at = Column(DateTime, nullable=True)
    
    def __repr__(self) -> str:
        return f"<SynthesisAnswer mission={self.mission_id} conf={self.confidence_current}>"


class ReasoningStep(Base):
    """Structured reasoning steps for how the system arrived at conclusions."""

    __tablename__ = "reasoning_steps"

    id = Column(Uuid, primary_key=True, default=uuid4)
    mission_id = Column(Uuid, nullable=False, index=True)
    
    # Reasoning structure
    step_number = Column(Integer, nullable=False)
    reasoning_type = Column(String(50), nullable=False)  # observation, inference, synthesis, decision, etc.
    
    # Content
    premise = Column(Text, nullable=True)  # What we're reasoning about
    logic = Column(Text, nullable=True)  # The reasoning logic/explanation
    conclusion = Column(Text, nullable=True)  # What we concluded
    
    # Supporting evidence
    supporting_paper_ids = Column(JSON, nullable=True)  # List of paper IDs
    supporting_claims = Column(JSON, nullable=True)  # List of claim texts
    
    # Confidence
    confidence_score = Column(Float, nullable=True)
    
    # Metadata
    generation_cycle = Column(Integer, nullable=True)
    generated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index('ix_reasoning_mission_step', 'mission_id', 'step_number'),
    )

    def __repr__(self) -> str:
        return f"<ReasoningStep mission={self.mission_id} step={self.step_number} type={self.reasoning_type}>"


class MissionTimeline(Base):
    """Events in mission lifecycle for timeline visualization."""

    __tablename__ = "mission_timeline"

    id = Column(Uuid, primary_key=True, default=uuid4)
    mission_id = Column(Uuid, nullable=False, index=True)
    
    # Event info
    event_type = Column(String(50), nullable=False)  # ingestion_started, papers_added, belief_updated, alert_fired, etc.
    event_title = Column(String(200), nullable=False)
    event_description = Column(Text, nullable=True)
    
    # Metadata
    cycle_number = Column(Integer, nullable=True)  # Which cycle this event occurred in
    related_entity_id = Column(Uuid, nullable=True)  # Paper ID, claim ID, alert ID, etc.
    
    # Impact
    metrics_change = Column(JSON, nullable=True)  # {"papers": +5, "confidence": +0.1, etc.}
    
    # Timestamp
    occurred_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index('ix_timeline_mission_time', 'mission_id', 'occurred_at'),
    )

    def __repr__(self) -> str:
        return f"<MissionTimeline mission={self.mission_id} event={self.event_type}>"
