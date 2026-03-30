from sqlalchemy import Column, String, Integer, Float, DateTime, Enum, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import enum

Base = declarative_base()


class MissionStatus(str, enum.Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    IDLE = "idle"
    ARCHIVED = "archived"


class HealthStatus(str, enum.Enum):
    HEALTHY = "HEALTHY"
    WATCH = "WATCH"
    DEGRADED = "DEGRADED"
    CRITICAL = "CRITICAL"


class IntentType(str, enum.Enum):
    CAUSAL = "Causal"
    COMPARATIVE = "Comparative"
    EXPLORATORY = "Exploratory"
    DESCRIPTIVE = "Descriptive"


class AlertSeverity(str, enum.Enum):
    CRITICAL = "critical"
    DEGRADED = "degraded"
    WATCH = "watch"
    INFO = "info"


class Mission(Base):
    __tablename__ = "missions"

    id = Column(String(36), primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    normalized_query = Column(Text, nullable=False)
    intent_type = Column(Enum(IntentType), nullable=False)
    status = Column(Enum(MissionStatus), default=MissionStatus.IDLE, nullable=False)
    health = Column(Enum(HealthStatus), default=HealthStatus.HEALTHY, nullable=False)
    
    # PICO breakdown
    pico_population = Column(String(500), nullable=True)
    pico_intervention = Column(String(500), nullable=True)
    pico_comparator = Column(String(500), nullable=True)
    pico_outcome = Column(String(500), nullable=True)
    
    # Decision from Module 1
    decision = Column(String(50), nullable=True)  # PROCEED, PROCEED_WITH_CAUTION, NEED_CLARIFICATION
    key_concepts = Column(Text, nullable=True)  # JSON array stored as text
    ambiguity_flags = Column(Text, nullable=True)  # JSON array stored as text
    
    # Stats
    total_papers = Column(Integer, default=0)
    total_claims = Column(Integer, default=0)
    confidence_score = Column(Float, default=0.0)
    confidence_from_module1 = Column(Float, nullable=True)
    active_alerts = Column(Integer, default=0)
    session_count = Column(Integer, default=0)

    # Ingestion status tracking (for background job pattern)
    ingestion_status = Column(String(20), default="idle", nullable=False)  # idle|pending|processing|completed|failed
    ingestion_progress = Column(Integer, default=0, nullable=False)  # 0-100
    ingestion_error = Column(Text, nullable=True)
    ingestion_started_at = Column(DateTime, nullable=True)
    ingestion_completed_at = Column(DateTime, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_run = Column(DateTime, nullable=True)


class Session(Base):
    __tablename__ = "sessions"

    id = Column(String(36), primary_key=True, index=True)
    mission_id = Column(String(36), ForeignKey("missions.id"), nullable=False, index=True)
    session_number = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False)  # Completed, Failed, Running
    papers_ingested = Column(Integer, default=0)
    claims_extracted = Column(Integer, default=0)
    health = Column(Enum(HealthStatus), default=HealthStatus.HEALTHY, nullable=False)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(String(36), primary_key=True, index=True)
    mission_id = Column(String(36), ForeignKey("missions.id"), nullable=False, index=True)
    alert_type = Column(String(100), nullable=False)
    severity = Column(Enum(AlertSeverity), nullable=False)
    cycle_number = Column(Integer, nullable=False)
    lifecycle_status = Column(String(20), nullable=False)  # firing, active, resolved
    message = Column(Text, nullable=True)
    resolution_record = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    resolved_at = Column(DateTime, nullable=True)
