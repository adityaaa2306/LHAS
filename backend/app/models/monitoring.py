from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import JSON, Column, DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text, Uuid

from .mission import Base, HealthStatus


class MonitoringSnapshot(Base):
    __tablename__ = "monitoring_snapshots"

    id = Column(Uuid, primary_key=True, default=uuid4)
    mission_id = Column(String(36), ForeignKey("missions.id", ondelete="CASCADE"), nullable=False, index=True)
    cycle_number = Column(Integer, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    confidence_velocity = Column(Float, nullable=True)
    evidence_justified_velocity = Column(Float, nullable=True)
    trajectory_divergence = Column(Float, nullable=True)
    semantic_drift_score = Column(Float, nullable=True)
    active_contradiction_count = Column(Integer, nullable=False, default=0)
    contradiction_acknowledgment_rate = Column(Float, nullable=True)
    support_ratio = Column(Float, nullable=True)
    directional_retrieval_balance = Column(Float, nullable=True)
    mean_paper_age = Column(Float, nullable=True)
    recent_ingestion_rate = Column(Float, nullable=True)
    reversal_rate = Column(Float, nullable=True)
    no_update_rate = Column(Float, nullable=True)
    active_alerts = Column(JSON, nullable=False, default=list)
    alert_history = Column(JSON, nullable=False, default=list)
    overall_health = Column(Enum(HealthStatus), nullable=False, default=HealthStatus.HEALTHY)
    metrics_payload = Column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_monitoring_snapshot_mission_cycle", "mission_id", "cycle_number", unique=True),
        Index("ix_monitoring_snapshot_mission_time", "mission_id", "timestamp"),
    )


class MonitoringAlertRecord(Base):
    __tablename__ = "monitoring_alerts"

    id = Column(Uuid, primary_key=True, default=uuid4)
    mission_id = Column(String(36), ForeignKey("missions.id", ondelete="CASCADE"), nullable=False, index=True)
    alert_type = Column(String(100), nullable=False, index=True)
    severity = Column(String(16), nullable=False, index=True)  # LOW / MEDIUM / HIGH
    lifecycle_status = Column(String(20), nullable=False, default="firing", index=True)  # firing/active/resolved/expired
    first_cycle_number = Column(Integer, nullable=False)
    last_cycle_number = Column(Integer, nullable=False)
    message = Column(Text, nullable=True)
    metric_values = Column(JSON, nullable=True)
    resolution_record = Column(JSON, nullable=True)
    snapshot_id = Column(Uuid, ForeignKey("monitoring_snapshots.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    resolved_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_monitoring_alert_mission_type_state", "mission_id", "alert_type", "lifecycle_status"),
        Index("ix_monitoring_alert_mission_created", "mission_id", "created_at"),
    )
