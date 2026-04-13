from __future__ import annotations

import logging
import math
import re
from collections import Counter
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Alert,
    AlertSeverity,
    BeliefRevisionRecord,
    BeliefState,
    ContradictionRecord,
    DriftTrendEnum,
    HealthStatus,
    Mission,
    MissionSnapshot,
    MissionTimeline,
    MonitoringAlertRecord,
    MonitoringSnapshot,
    RawPaperRecord,
    ResearchClaim,
    ResearchPaper,
    SynthesisHistory,
)
from app.models.belief_revision import RevisionTypeEnum
from app.models.memory import MemoryEventType
from app.services.claim_curation import claim_direction_value
from app.services.embeddings import get_embedding_service
from app.services.llm import get_llm_provider
from app.services.memory_system import MemorySystemService

logger = logging.getLogger(__name__)

ALERT_SEVERITY_ORDER = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}
ACTIVE_ALERT_STATES = {"firing", "active"}
MONITORING_SNAPSHOT_INTERVAL = 5
BENCHMARK_INTERVAL = 10


def _enum_value(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(getattr(value, "value", value) or default)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


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


def _rolling_average(values: Sequence[float]) -> float:
    cleaned = [float(value) for value in values if value is not None]
    if not cleaned:
        return 0.0
    return round(sum(cleaned) / len(cleaned), 4)


def _reliability(level: str, reason: str, sample_size: Optional[int] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"level": level, "reason": reason}
    if sample_size is not None:
        payload["sample_size"] = int(sample_size)
    return payload


def _reliability_rank(level: str) -> int:
    return {"insufficient": 0, "low": 1, "medium": 2, "high": 3}.get((level or "").lower(), 0)


def _current_year() -> int:
    return datetime.utcnow().year


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def _text_similarity(left: str, right: str) -> float:
    left_tokens = Counter(_tokenize(left))
    right_tokens = Counter(_tokenize(right))
    if not left_tokens or not right_tokens:
        return 0.0
    shared = sum(min(left_tokens[token], right_tokens[token]) for token in set(left_tokens) & set(right_tokens))
    left_norm = math.sqrt(sum(count * count for count in left_tokens.values()))
    right_norm = math.sqrt(sum(count * count for count in right_tokens.values()))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return round(shared / (left_norm * right_norm), 4)


class AlignmentMonitoringService:
    def __init__(
        self,
        db: AsyncSession,
        llm_provider: Any = None,
        embedding_service: Any = None,
    ) -> None:
        self.db = db
        self.llm_provider = llm_provider or get_llm_provider()
        self.embedding_service = embedding_service or get_embedding_service()
        self.memory_system = MemorySystemService(db=db, llm_provider=self.llm_provider, embedding_service=self.embedding_service)

    async def run_monitoring_cycle(
        self,
        mission_id: str,
        actor: str = "alignment_monitor",
    ) -> Dict[str, Any]:
        mission = await self.db.get(Mission, mission_id)
        if not mission:
            raise ValueError(f"Mission not found: {mission_id}")

        cycle_number = int(mission.session_count or 0)
        metrics = await self._compute_metrics(mission_id, cycle_number)
        alert_result = await self._evaluate_alerts(mission, cycle_number, metrics, actor)
        overall_health = await self._determine_overall_health(mission_id, alert_result["active_alerts"])
        previous_health = _enum_value(mission.health, HealthStatus.HEALTHY.value)

        mission.health = overall_health
        await self.db.flush()
        mission.active_alerts = len(alert_result["active_alerts"])

        if previous_health != overall_health.value:
            await self.memory_system.log_event(
                event_type=(
                    MemoryEventType.MONITORING_HEALTH_DEGRADED
                    if self._health_rank(overall_health.value) > self._health_rank(previous_health)
                    else MemoryEventType.MONITORING_HEALTH_RESTORED
                ),
                mission_id=mission_id,
                actor=actor,
                previous_value={"health": previous_health},
                new_value={"health": overall_health.value, "cycle_number": cycle_number},
            )
            self.db.add(
                MissionTimeline(
                    mission_id=mission_id,
                    event_type=(
                        "monitoring.health_degraded"
                        if self._health_rank(overall_health.value) > self._health_rank(previous_health)
                        else "monitoring.health_restored"
                    ),
                    event_title=f"Mission health {overall_health.value.lower()}",
                    event_description=f"Overall monitoring health changed from {previous_health} to {overall_health.value}.",
                    cycle_number=cycle_number,
                    metrics_change={"previous_health": previous_health, "new_health": overall_health.value},
                )
            )

        snapshot = None
        if cycle_number > 0 and cycle_number % MONITORING_SNAPSHOT_INTERVAL == 0:
            snapshot = await self._create_monitoring_snapshot(
                mission_id=mission_id,
                cycle_number=cycle_number,
                metrics=metrics,
                active_alerts=alert_result["active_alerts"],
                alert_history=alert_result["history_events"],
                overall_health=overall_health,
                actor=actor,
            )

        await self.db.flush()
        return {
            "mission_id": mission_id,
            "cycle_number": cycle_number,
            "overall_health": overall_health.value,
            "active_alert_count": len(alert_result["active_alerts"]),
            "active_alerts": alert_result["active_alerts"],
            "metrics": _jsonable(metrics),
            "snapshot": self._snapshot_response(snapshot) if snapshot else None,
        }

    async def get_monitoring_overview(self, mission_id: str) -> Dict[str, Any]:
        mission = await self.db.get(Mission, mission_id)
        if not mission:
            raise ValueError(f"Mission not found: {mission_id}")

        cycle_number = int(mission.session_count or 0)
        metrics = await self._compute_metrics(mission_id, cycle_number)
        latest_snapshot = (
            await self.db.execute(
                select(MonitoringSnapshot)
                .where(MonitoringSnapshot.mission_id == mission_id)
                .order_by(MonitoringSnapshot.cycle_number.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        active_alerts = await self._load_alerts(mission_id, statuses=list(ACTIVE_ALERT_STATES), limit=100)
        history = await self._load_alerts(mission_id, statuses=["resolved", "expired"], limit=30)
        benchmark = await self._benchmark_status(mission, metrics)

        return {
            "mission_id": mission_id,
            "current_cycle": cycle_number,
            "overall_health": _enum_value(mission.health, HealthStatus.HEALTHY.value),
            "active_alert_count": len(active_alerts),
            "active_alerts": active_alerts,
            "recent_alert_history": history[:8],
            "metrics": _jsonable(metrics),
            "latest_snapshot": self._snapshot_response(latest_snapshot) if latest_snapshot else None,
            "benchmark": benchmark,
        }

    async def get_snapshot_history(self, mission_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        rows = (
            await self.db.execute(
                select(MonitoringSnapshot)
                .where(MonitoringSnapshot.mission_id == mission_id)
                .order_by(MonitoringSnapshot.cycle_number.desc())
                .limit(limit)
            )
        ).scalars().all()
        return [self._snapshot_response(row) for row in rows]

    async def get_alert_history(
        self,
        mission_id: str,
        statuses: Optional[Sequence[str]] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        return await self._load_alerts(mission_id, statuses=statuses, limit=limit)

    async def _compute_metrics(self, mission_id: str, cycle_number: int) -> Dict[str, Any]:
        revisions = (
            await self.db.execute(
                select(BeliefRevisionRecord)
                .where(BeliefRevisionRecord.mission_id == mission_id)
                .order_by(BeliefRevisionRecord.cycle_number.desc())
                .limit(12)
            )
        ).scalars().all()
        revisions = list(reversed(revisions))

        syntheses = (
            await self.db.execute(
                select(SynthesisHistory)
                .where(SynthesisHistory.mission_id == mission_id)
                .order_by(SynthesisHistory.version_number.desc())
                .limit(12)
            )
        ).scalars().all()
        syntheses = list(reversed(syntheses))

        snapshots = (
            await self.db.execute(
                select(MissionSnapshot)
                .where(MissionSnapshot.mission_id == mission_id)
                .order_by(MissionSnapshot.cycle_number.desc())
                .limit(12)
            )
        ).scalars().all()
        snapshots = list(reversed(snapshots))

        contradictions = (
            await self.db.execute(
                select(ContradictionRecord)
                .where(
                    ContradictionRecord.mission_id == mission_id,
                    ContradictionRecord.resolution_status == "unresolved",
                )
                .order_by(ContradictionRecord.timestamp.desc())
            )
        ).scalars().all()

        claims = (
            await self.db.execute(
                select(ResearchClaim)
                .where(ResearchClaim.mission_id == mission_id)
                .order_by(ResearchClaim.composite_confidence.desc())
            )
        ).scalars().all()

        papers = (
            await self.db.execute(
                select(ResearchPaper)
                .where(ResearchPaper.mission_id == mission_id)
                .order_by(ResearchPaper.retrieved_at.desc())
            )
        ).scalars().all()

        raw_papers = (
            await self.db.execute(
                select(RawPaperRecord)
                .where(RawPaperRecord.mission_id == mission_id)
                .order_by(RawPaperRecord.ingestion_timestamp.desc())
                .limit(50)
            )
        ).scalars().all()

        belief_state = (
            await self.db.execute(select(BeliefState).where(BeliefState.mission_id == mission_id))
        ).scalar_one_or_none()

        primary_cluster = self._select_primary_cluster(claims)

        metrics = {
            "cycle_number": cycle_number,
            "confidence": self._confidence_metrics(revisions),
            "synthesis": await self._synthesis_metrics(syntheses, revisions),
            "contradictions": self._contradiction_metrics(contradictions, syntheses, snapshots),
            "evidence_balance": self._evidence_balance_metrics(primary_cluster, claims, papers, raw_papers, belief_state),
            "freshness": self._evidence_freshness_metrics(primary_cluster, claims, papers, raw_papers, revisions),
            "revision_patterns": self._revision_pattern_metrics(revisions, belief_state),
            "primary_cluster": self._primary_cluster_payload(primary_cluster),
        }

        mission = await self.db.get(Mission, mission_id)
        if mission and mission.benchmark_text and cycle_number > 0 and cycle_number % BENCHMARK_INTERVAL == 0:
            metrics["benchmark"] = await self._benchmark_status(mission, metrics, syntheses[-1] if syntheses else None)

        return metrics

    def _confidence_metrics(self, revisions: Sequence[BeliefRevisionRecord]) -> Dict[str, Any]:
        recent = list(revisions[-5:])
        deltas = [_safe_float(row.confidence_delta) for row in recent]
        confidence_velocity = _rolling_average(deltas)
        evidence_justified_velocity = _rolling_average([self._expected_revision_delta(row) for row in recent])
        trajectory_divergence = round(abs(confidence_velocity - evidence_justified_velocity), 4)
        recent_reversal = any(_enum_value(row.revision_type) == RevisionTypeEnum.REVERSAL.value for row in recent)
        flatline_window = list(revisions[-10:])
        flatline_cycles = (
            len(flatline_window)
            if len(flatline_window) >= 10
            and all(abs(_safe_float(row.confidence_delta)) < 0.005 for row in flatline_window)
            and all(self._revision_has_new_evidence(row) for row in flatline_window)
            else 0
        )
        supportive_recent = any(
            self._incoming_supportive(row) and _enum_value(row.revision_type) != RevisionTypeEnum.NO_UPDATE.value
            for row in revisions[-3:]
        )
        return {
            "confidence_velocity": confidence_velocity,
            "evidence_justified_velocity": evidence_justified_velocity,
            "trajectory_divergence": trajectory_divergence,
            "recent_reversal": recent_reversal,
            "supportive_recent": supportive_recent,
            "flatline_cycles": flatline_cycles,
        }

    async def _synthesis_metrics(
        self,
        syntheses: Sequence[SynthesisHistory],
        revisions: Sequence[BeliefRevisionRecord],
    ) -> Dict[str, Any]:
        latest = syntheses[-1] if syntheses else None
        comparison = syntheses[-4] if len(syntheses) >= 4 else (syntheses[0] if len(syntheses) >= 2 else None)
        semantic_drift_score = 0.0
        evidence_delta = 0
        drift_justification_ratio = None
        if latest and comparison:
            semantic_drift_score = round(await self._semantic_distance(latest.full_text or "", comparison.full_text or ""), 4)
            evidence_delta = len(set(latest.claim_ids_tier1 or []) - set(comparison.claim_ids_tier1 or []))
            drift_justification_ratio = (
                round(evidence_delta / semantic_drift_score, 4) if semantic_drift_score > 0 else None
            )

        pairwise_scores: List[float] = []
        if len(syntheses) >= 2:
            for idx in range(1, len(syntheses)):
                pairwise_scores.append(
                    round(
                        await self._semantic_distance(
                            syntheses[idx - 1].full_text or "",
                            syntheses[idx].full_text or "",
                        ),
                        4,
                    )
                )
        stagnation_window = len(pairwise_scores[-8:]) if len(pairwise_scores) >= 8 and all(score < 0.02 for score in pairwise_scores[-8:]) else 0
        reversal_recent = any(_enum_value(row.revision_type) == RevisionTypeEnum.REVERSAL.value for row in revisions[-2:])
        return {
            "semantic_drift_score": semantic_drift_score,
            "evidence_delta": evidence_delta,
            "drift_justification_ratio": drift_justification_ratio,
            "trigger_type": latest.trigger.value if latest and latest.trigger else None,
            "stagnation_window": stagnation_window,
            "reversal_recent": reversal_recent,
        }

    def _contradiction_metrics(
        self,
        contradictions: Sequence[ContradictionRecord],
        syntheses: Sequence[SynthesisHistory],
        snapshots: Sequence[MissionSnapshot],
    ) -> Dict[str, Any]:
        active_contradiction_count = len(contradictions)
        active_contradiction_topic_count = len(
            {
                (
                    row.intervention_canonical or "unknown intervention",
                    row.outcome_canonical or "unknown outcome",
                )
                for row in contradictions
            }
        )
        recent_snapshot_window = list(snapshots[-6:])
        deltas: List[int] = []
        for idx in range(1, len(recent_snapshot_window)):
            current = _safe_int(recent_snapshot_window[idx].active_contradictions_count)
            previous = _safe_int(recent_snapshot_window[idx - 1].active_contradictions_count)
            deltas.append(max(0, current - previous))
        contradiction_arrival_rate = _rolling_average([float(delta) for delta in deltas[-5:]]) if deltas else 0.0
        new_contradictions = deltas[-1] if deltas else active_contradiction_count
        prior_arrival_rate = _rolling_average([float(delta) for delta in deltas[-6:-1]]) if len(deltas) >= 2 else 0.0

        latest_synthesis = syntheses[-1] if syntheses else None
        acknowledged = set(latest_synthesis.contradictions_included or []) if latest_synthesis else set()
        high_medium = [row for row in contradictions if _enum_value(row.severity) in {"HIGH", "MEDIUM"}]
        contradiction_acknowledgment_rate = (
            round(sum(1 for row in high_medium if str(row.id) in acknowledged) / len(high_medium), 4)
            if high_medium
            else 1.0
        )

        high_unacknowledged_cycles = 0
        for row in contradictions:
            if _enum_value(row.severity) != "HIGH" or str(row.id) in acknowledged:
                continue
            synth_cycles = 0
            for synthesis in syntheses:
                if synthesis.created_at and row.timestamp and synthesis.created_at >= row.timestamp:
                    synth_cycles += 1
            high_unacknowledged_cycles = max(high_unacknowledged_cycles, synth_cycles)

        return {
            "active_contradiction_count": active_contradiction_count,
            "active_contradiction_topic_count": active_contradiction_topic_count,
            "contradiction_arrival_rate": contradiction_arrival_rate,
            "contradiction_acknowledgment_rate": contradiction_acknowledgment_rate,
            "new_contradictions": new_contradictions,
            "prior_arrival_rate": prior_arrival_rate,
            "high_unacknowledged_cycles": high_unacknowledged_cycles,
        }

    def _evidence_balance_metrics(
        self,
        primary_cluster: Dict[str, Any],
        claims: Sequence[ResearchClaim],
        papers: Sequence[ResearchPaper],
        raw_papers: Sequence[RawPaperRecord],
        belief_state: Optional[BeliefState],
    ) -> Dict[str, Any]:
        cluster_claims: List[ResearchClaim] = primary_cluster["claims"]
        dominant_direction = (
            _enum_value(getattr(belief_state, "dominant_evidence_direction", None), "mixed").lower()
            if belief_state
            else "mixed"
        )
        support_ratio = None
        support_ratio_reliability = _reliability("insufficient", "Dominant direction is mixed, so support ratio is not meaningful.", len(cluster_claims))
        if dominant_direction != "mixed" and len(cluster_claims) >= 3:
            matching = sum(1 for claim in cluster_claims if claim_direction_value(claim) == dominant_direction)
            support_ratio = round(matching / len(cluster_claims), 4)
            support_ratio_reliability = _reliability(
                "high" if len(cluster_claims) >= 6 else "medium",
                "Primary evidence cluster contains enough directional claims for a stable support estimate.",
                len(cluster_claims),
            )
        elif dominant_direction != "mixed":
            support_ratio_reliability = _reliability(
                "low",
                "Primary evidence cluster is too small for a stable support estimate.",
                len(cluster_claims),
            )
        prior_support_ratio = primary_cluster.get("prior_support_ratio", support_ratio if support_ratio is not None else 0.0)

        study_designs = [self._paper_study_type(paper) for paper in papers]
        high_quality_present = any(design in {"rct", "meta-analysis", "systematic review"} for design in study_designs)
        study_design_distribution = {
            "observational_fraction": round(
                sum(1 for design in study_designs if design in {"observational", "cross-sectional", "case-control"}) / len(study_designs),
                4,
            ) if study_designs else 0.0,
            "has_high_quality_study": high_quality_present,
        }
        directional_retrieval_balance = None
        directional_retrieval_balance_reliability = _reliability(
            "insufficient",
            "Recent ingestion history is too sparse or direction is mixed, so retrieval balance is provisional.",
            len(raw_papers[:20]),
        )
        if dominant_direction != "mixed" and len(raw_papers[:20]) >= 5:
            directional_retrieval_balance = self._directional_retrieval_balance(raw_papers, dominant_direction)
            directional_retrieval_balance_reliability = _reliability(
                "high" if len(raw_papers[:20]) >= 10 else "medium",
                "Recent ingestion window is large enough to estimate directional retrieval balance.",
                len(raw_papers[:20]),
            )
        return {
            "support_ratio": support_ratio,
            "prior_support_ratio": prior_support_ratio,
            "support_ratio_reliability": support_ratio_reliability,
            "study_design_distribution": study_design_distribution,
            "directional_retrieval_balance": directional_retrieval_balance,
            "directional_retrieval_balance_reliability": directional_retrieval_balance_reliability,
            "dominant_direction": dominant_direction,
        }

    def _evidence_freshness_metrics(
        self,
        primary_cluster: Dict[str, Any],
        claims: Sequence[ResearchClaim],
        papers: Sequence[ResearchPaper],
        raw_papers: Sequence[RawPaperRecord],
        revisions: Sequence[BeliefRevisionRecord],
    ) -> Dict[str, Any]:
        weighted_years: List[float] = []
        weighted_weights: List[float] = []
        for claim in claims:
            year = self._claim_publication_year(claim)
            if year is None:
                continue
            weight = max(0.05, _safe_float(claim.composite_confidence, 0.1))
            weighted_years.append(float(year) * weight)
            weighted_weights.append(weight)
        mean_publication_year = (sum(weighted_years) / sum(weighted_weights)) if weighted_weights else None
        mean_paper_age = round(_current_year() - mean_publication_year, 4) if mean_publication_year else None
        mean_paper_age_reliability = (
            _reliability(
                "high" if len(weighted_weights) >= 5 else "medium",
                "Enough weighted claim years are available to estimate evidence age.",
                len(weighted_weights),
            )
            if weighted_weights
            else _reliability("insufficient", "Publication years are missing for the currently weighted claims.", 0)
        )

        recent_raw = list(raw_papers[:20])
        dated_recent_raw = [row for row in recent_raw if row.publication_year]
        recent_ingestion_rate = (
            round(
                sum(1 for row in dated_recent_raw if (_current_year() - int(row.publication_year)) <= 3)
                / len(dated_recent_raw),
                4,
            )
            if dated_recent_raw
            else None
        )
        recent_ingestion_rate_reliability = (
            _reliability(
                "high" if len(dated_recent_raw) >= 10 else "medium",
                "Recent ingestions include enough dated papers to estimate freshness.",
                len(dated_recent_raw),
            )
            if dated_recent_raw
            else _reliability("insufficient", "Recent ingestion metadata is missing publication years.", 0)
        )

        last_new_evidence_cycle = 0
        current_cycle = _safe_int(revisions[-1].cycle_number if revisions else 0)
        for row in reversed(revisions):
            if self._revision_has_new_evidence(row):
                last_new_evidence_cycle = max(0, current_cycle - _safe_int(row.cycle_number))
                break
        else:
            last_new_evidence_cycle = current_cycle if current_cycle else 0

        cluster_claims = sorted(primary_cluster["claims"], key=lambda claim: _safe_float(claim.composite_confidence), reverse=True)
        top_years = [self._claim_publication_year(claim) or 0 for claim in cluster_claims[:3]]
        recent_papers_exist = sum(1 for paper in papers if paper.year and (_current_year() - int(paper.year)) <= 3) >= 5

        return {
            "mean_paper_age": mean_paper_age,
            "mean_paper_age_reliability": mean_paper_age_reliability,
            "recent_ingestion_rate": recent_ingestion_rate,
            "recent_ingestion_rate_reliability": recent_ingestion_rate_reliability,
            "last_new_evidence_cycle": last_new_evidence_cycle,
            "recency_inversion": bool(
                recent_papers_exist and top_years and all(year and (_current_year() - year) > 10 for year in top_years)
            ),
        }

    def _revision_pattern_metrics(
        self,
        revisions: Sequence[BeliefRevisionRecord],
        belief_state: Optional[BeliefState],
    ) -> Dict[str, Any]:
        last_ten = list(revisions[-10:])
        reversal_rate = round(
            sum(1 for row in last_ten if _enum_value(row.revision_type) == RevisionTypeEnum.REVERSAL.value),
            4,
        )
        directions = [_enum_value(row.new_direction, "mixed") for row in last_ten]
        alternations = 0
        for idx in range(1, len(directions)):
            if directions[idx] != directions[idx - 1]:
                alternations += 1
        no_update_rate = round(
            sum(1 for row in last_ten if _enum_value(row.revision_type) == RevisionTypeEnum.NO_UPDATE.value) / len(last_ten),
            4,
        ) if last_ten else 0.0
        return {
            "reversal_rate": reversal_rate,
            "alternations": alternations,
            "no_update_rate": no_update_rate,
            "drift_trend": _enum_value(getattr(belief_state, "drift_trend", None), DriftTrendEnum.STABILIZING.value),
        }

    async def _evaluate_alerts(
        self,
        mission: Mission,
        cycle_number: int,
        metrics: Dict[str, Any],
        actor: str,
    ) -> Dict[str, Any]:
        alert_specs = self._alert_specs(mission, cycle_number, metrics)
        existing = (
            await self.db.execute(
                select(MonitoringAlertRecord).where(MonitoringAlertRecord.mission_id == mission.id)
            )
        ).scalars().all()
        existing_by_type = {row.alert_type: row for row in existing if row.lifecycle_status in ACTIVE_ALERT_STATES}
        expired_this_cycle: set[str] = set()
        history_events: List[Dict[str, Any]] = []

        for row in existing_by_type.values():
            if cycle_number - _safe_int(row.first_cycle_number) > 10:
                row.lifecycle_status = "expired"
                row.resolved_at = datetime.utcnow()
                row.resolution_record = {"cycle_number": cycle_number, "reason": "expired_after_10_cycles"}
                await self._sync_legacy_alert(row, resolved=True)
                expired_this_cycle.add(row.alert_type)
                history_events.append(self._alert_response(row))

        active_alerts: List[Dict[str, Any]] = []
        for spec in alert_specs:
            alert_type = spec["alert_type"]
            is_active = bool(spec["active"])
            if is_active and alert_type in expired_this_cycle:
                continue

            existing_row = existing_by_type.get(alert_type)
            if is_active:
                if existing_row:
                    existing_row.lifecycle_status = "active"
                    existing_row.last_cycle_number = cycle_number
                    existing_row.metric_values = _jsonable(spec["metric_values"])
                    existing_row.message = spec["message"]
                    await self._sync_legacy_alert(existing_row, resolved=False)
                    active_alerts.append(self._alert_response(existing_row))
                else:
                    new_row = MonitoringAlertRecord(
                        mission_id=mission.id,
                        alert_type=alert_type,
                        severity=spec["severity"],
                        lifecycle_status="firing",
                        first_cycle_number=cycle_number,
                        last_cycle_number=cycle_number,
                        message=spec["message"],
                        metric_values=_jsonable(spec["metric_values"]),
                    )
                    self.db.add(new_row)
                    await self.db.flush()
                    await self.memory_system.log_event(
                        event_type=MemoryEventType.MONITORING_ALERT_FIRING,
                        mission_id=mission.id,
                        actor=actor,
                        previous_value=None,
                        new_value={
                            "alert_id": str(new_row.id),
                            "alert_type": alert_type,
                            "severity": spec["severity"],
                            "cycle_number": cycle_number,
                            "metric_values": spec["metric_values"],
                        },
                    )
                    self.db.add(
                        MissionTimeline(
                            mission_id=mission.id,
                            event_type="monitoring.alert_firing",
                            event_title=f"{alert_type.replace('_', ' ').title()} alert",
                            event_description=spec["message"],
                            cycle_number=cycle_number,
                            metrics_change=_jsonable(spec["metric_values"]),
                        )
                    )
                    await self._sync_legacy_alert(new_row, resolved=False)
                    alert_payload = self._alert_response(new_row)
                    active_alerts.append(alert_payload)
                    history_events.append(alert_payload)
            elif existing_row:
                existing_row.lifecycle_status = "resolved"
                existing_row.last_cycle_number = cycle_number
                existing_row.resolved_at = datetime.utcnow()
                existing_row.resolution_record = {
                    "cycle_number": cycle_number,
                    "message": spec["resolution_message"],
                }
                await self.memory_system.log_event(
                    event_type=MemoryEventType.MONITORING_ALERT_RESOLVED,
                    mission_id=mission.id,
                    actor=actor,
                    previous_value={"alert_id": str(existing_row.id), "alert_type": alert_type},
                    new_value={
                        "resolution_cycle": cycle_number,
                        "cycles_active": cycle_number - _safe_int(existing_row.first_cycle_number) + 1,
                        "message": spec["resolution_message"],
                    },
                )
                self.db.add(
                    MissionTimeline(
                        mission_id=mission.id,
                        event_type="monitoring.alert_resolved",
                        event_title=f"{alert_type.replace('_', ' ').title()} resolved",
                        event_description=spec["resolution_message"],
                        cycle_number=cycle_number,
                        metrics_change=_jsonable(spec["metric_values"]),
                    )
                )
                await self._sync_legacy_alert(existing_row, resolved=True)
                history_events.append(self._alert_response(existing_row))

        active_alerts.sort(key=lambda item: (-ALERT_SEVERITY_ORDER.get(item["severity"], 0), item["alert_type"]))
        return {"active_alerts": active_alerts, "history_events": history_events}

    async def _create_monitoring_snapshot(
        self,
        mission_id: str,
        cycle_number: int,
        metrics: Dict[str, Any],
        active_alerts: Sequence[Dict[str, Any]],
        alert_history: Sequence[Dict[str, Any]],
        overall_health: HealthStatus,
        actor: str,
    ) -> MonitoringSnapshot:
        snapshot = (
            await self.db.execute(
                select(MonitoringSnapshot).where(
                    MonitoringSnapshot.mission_id == mission_id,
                    MonitoringSnapshot.cycle_number == cycle_number,
                )
            )
        ).scalar_one_or_none()
        if not snapshot:
            snapshot = MonitoringSnapshot(mission_id=mission_id, cycle_number=cycle_number)
            self.db.add(snapshot)

        snapshot.confidence_velocity = metrics["confidence"]["confidence_velocity"]
        snapshot.evidence_justified_velocity = metrics["confidence"]["evidence_justified_velocity"]
        snapshot.trajectory_divergence = metrics["confidence"]["trajectory_divergence"]
        snapshot.semantic_drift_score = metrics["synthesis"]["semantic_drift_score"]
        snapshot.active_contradiction_count = metrics["contradictions"]["active_contradiction_count"]
        snapshot.contradiction_acknowledgment_rate = metrics["contradictions"]["contradiction_acknowledgment_rate"]
        snapshot.support_ratio = metrics["evidence_balance"]["support_ratio"]
        snapshot.directional_retrieval_balance = metrics["evidence_balance"]["directional_retrieval_balance"]
        snapshot.mean_paper_age = metrics["freshness"]["mean_paper_age"]
        snapshot.recent_ingestion_rate = metrics["freshness"]["recent_ingestion_rate"]
        snapshot.reversal_rate = metrics["revision_patterns"]["reversal_rate"]
        snapshot.no_update_rate = metrics["revision_patterns"]["no_update_rate"]
        snapshot.active_alerts = [item["id"] for item in active_alerts]
        snapshot.alert_history = [item["id"] for item in alert_history]
        snapshot.overall_health = overall_health
        snapshot.metrics_payload = _jsonable(metrics)
        await self.db.flush()
        await self.memory_system.log_event(
            event_type=MemoryEventType.MONITORING_SNAPSHOT_CREATED,
            mission_id=mission_id,
            actor=actor,
            previous_value=None,
            new_value={
                "snapshot_id": str(snapshot.id),
                "cycle_number": cycle_number,
                "overall_health": overall_health.value,
                "active_alert_count": len(active_alerts),
            },
        )
        self.db.add(
            MissionTimeline(
                mission_id=mission_id,
                event_type="monitoring.snapshot_created",
                event_title=f"Monitoring snapshot cycle {cycle_number}",
                event_description=f"Overall monitoring health recorded as {overall_health.value}.",
                cycle_number=cycle_number,
                metrics_change={"overall_health": overall_health.value, "active_alert_count": len(active_alerts)},
            )
        )
        return snapshot

    async def _determine_overall_health(
        self,
        mission_id: str,
        active_alerts: Sequence[Dict[str, Any]],
    ) -> HealthStatus:
        high = [item for item in active_alerts if item["severity"] == "HIGH"]
        medium = [item for item in active_alerts if item["severity"] == "MEDIUM"]
        low = [item for item in active_alerts if item["severity"] == "LOW"]
        if high:
            return HealthStatus.CRITICAL

        recent_snapshots = (
            await self.db.execute(
                select(MonitoringSnapshot)
                .where(MonitoringSnapshot.mission_id == mission_id)
                .order_by(MonitoringSnapshot.cycle_number.desc())
                .limit(3)
            )
        ).scalars().all()
        if len(medium) >= 2:
            return HealthStatus.DEGRADED
        if len(medium) == 1:
            medium_type = medium[0]["alert_type"]
            persisted = len(recent_snapshots) == 3 and all(
                medium_type in str(snapshot.metrics_payload or {}) for snapshot in recent_snapshots
            )
            return HealthStatus.DEGRADED if persisted else HealthStatus.WATCH
        if len(low) >= 2:
            return HealthStatus.WATCH
        return HealthStatus.HEALTHY

    def _alert_specs(self, mission: Mission, cycle_number: int, metrics: Dict[str, Any]) -> List[Dict[str, Any]]:
        confidence = metrics["confidence"]
        synthesis = metrics["synthesis"]
        contradictions = metrics["contradictions"]
        evidence = metrics["evidence_balance"]
        freshness = metrics["freshness"]
        revisions = metrics["revision_patterns"]
        benchmark = metrics.get("benchmark") or {}
        support_reliable = _reliability_rank((evidence.get("support_ratio_reliability") or {}).get("level", "")) >= 2
        retrieval_reliable = _reliability_rank((evidence.get("directional_retrieval_balance_reliability") or {}).get("level", "")) >= 2
        age_reliable = _reliability_rank((freshness.get("mean_paper_age_reliability") or {}).get("level", "")) >= 2
        ingestion_reliable = _reliability_rank((freshness.get("recent_ingestion_rate_reliability") or {}).get("level", "")) >= 2

        return [
            self._build_alert(
                "CONFIDENCE_INFLATION",
                "MEDIUM",
                confidence["confidence_velocity"] > 0 and confidence["trajectory_divergence"] > 0.08 and not confidence["recent_reversal"],
                confidence,
            ),
            self._build_alert(
                "CONFIDENCE_SUPPRESSION",
                "LOW",
                confidence["confidence_velocity"] < 0 and confidence["trajectory_divergence"] > 0.08 and confidence["supportive_recent"],
                confidence,
            ),
            self._build_alert("CONFIDENCE_FLATLINE", "MEDIUM", confidence["flatline_cycles"] >= 10, confidence),
            self._build_alert(
                "UNJUSTIFIED_DRIFT",
                "MEDIUM",
                synthesis["semantic_drift_score"] > 0.25 and synthesis["evidence_delta"] < 2 and synthesis.get("trigger_type") == "scheduled",
                synthesis,
            ),
            self._build_alert(
                "SYNTHESIS_STAGNATION",
                "MEDIUM" if contradictions["active_contradiction_count"] > 0 else "LOW",
                synthesis["stagnation_window"] >= 8,
                synthesis,
            ),
            self._build_alert(
                "REVERSAL_WITHOUT_SYNTHESIS_UPDATE",
                "HIGH",
                synthesis["reversal_recent"] and synthesis["semantic_drift_score"] < 0.15,
                synthesis,
            ),
            self._build_alert(
                "CONTRADICTION_BACKLOG",
                "HIGH",
                contradictions["active_contradiction_count"] > 5
                and contradictions["contradiction_acknowledgment_rate"] < 0.6
                and contradictions["contradiction_arrival_rate"] > 0.5,
                contradictions,
            ),
            self._build_alert(
                "UNACKNOWLEDGED_HIGH_SEVERITY",
                "HIGH",
                contradictions["high_unacknowledged_cycles"] > 3,
                contradictions,
            ),
            self._build_alert(
                "CONTRADICTION_SPIKE",
                "MEDIUM",
                contradictions["prior_arrival_rate"] > 0
                and contradictions["contradiction_arrival_rate"] >= contradictions["prior_arrival_rate"] * 2
                and contradictions["new_contradictions"] > 3,
                contradictions,
            ),
            self._build_alert(
                "RETRIEVAL_BIAS_SUSPECTED",
                "HIGH",
                retrieval_reliable
                and support_reliable
                and float(evidence["directional_retrieval_balance"] or 0.0) > 0.80
                and float(evidence["support_ratio"] or 0.0) > 0.85,
                evidence,
            ),
            self._build_alert(
                "EVIDENCE_BASE_SHALLOW",
                "MEDIUM",
                not evidence["study_design_distribution"]["has_high_quality_study"] and cycle_number > 15 and mission.total_papers >= 10,
                evidence,
            ),
            self._build_alert(
                "SUPPORT_COLLAPSE",
                "MEDIUM",
                support_reliable
                and evidence["support_ratio"] is not None
                and evidence["support_ratio"] < 0.45
                and float(evidence["prior_support_ratio"] or 0.0) > 0.60,
                evidence,
            ),
            self._build_alert(
                "STALE_EVIDENCE_BASE",
                "MEDIUM",
                age_reliable
                and ingestion_reliable
                and float(freshness["mean_paper_age"] or 0.0) > 7
                and float(freshness["recent_ingestion_rate"] or 0.0) < 0.15,
                freshness,
            ),
            self._build_alert(
                "EVIDENCE_DROUGHT",
                "HIGH",
                freshness["last_new_evidence_cycle"] > 8 and _enum_value(mission.status, "idle") == "active",
                freshness,
            ),
            self._build_alert("RECENCY_INVERSION", "LOW", age_reliable and freshness["recency_inversion"], freshness),
            self._build_alert(
                "OSCILLATION_DETECTED",
                "HIGH",
                revisions["reversal_rate"] > 2 and revisions["alternations"] >= 2,
                revisions,
            ),
            self._build_alert(
                "BELIEF_INERTIA",
                "MEDIUM",
                revisions["no_update_rate"] > 0.65 and contradictions["contradiction_arrival_rate"] > 0.3,
                {**revisions, "contradiction_arrival_rate": contradictions["contradiction_arrival_rate"]},
            ),
            self._build_alert(
                "BENCHMARK_DIVERGENCE",
                "HIGH" if benchmark.get("classification") == "MISALIGNED" else "MEDIUM",
                benchmark.get("classification") in {"DIVERGING", "MISALIGNED"},
                benchmark,
            ),
        ]

    def _build_alert(
        self,
        alert_type: str,
        severity: str,
        active: bool,
        metric_values: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "alert_type": alert_type,
            "severity": severity,
            "active": active,
            "metric_values": metric_values,
            "message": self._alert_message(alert_type, metric_values),
            "resolution_message": f"{alert_type.replace('_', ' ').title()} returned to normal range.",
        }

    async def _load_alerts(
        self,
        mission_id: str,
        statuses: Optional[Sequence[str]] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        query = select(MonitoringAlertRecord).where(MonitoringAlertRecord.mission_id == mission_id)
        if statuses:
            query = query.where(MonitoringAlertRecord.lifecycle_status.in_(list(statuses)))
        rows = (
            await self.db.execute(
                query.order_by(MonitoringAlertRecord.updated_at.desc(), MonitoringAlertRecord.created_at.desc()).limit(limit)
            )
        ).scalars().all()
        return [self._alert_response(row) for row in rows]

    async def _sync_legacy_alert(self, alert_record: MonitoringAlertRecord, resolved: bool) -> None:
        legacy = await self.db.get(Alert, str(alert_record.id))
        severity = self._legacy_severity(alert_record.severity)
        if not legacy:
            legacy = Alert(
                id=str(alert_record.id),
                mission_id=alert_record.mission_id,
                alert_type=alert_record.alert_type,
                severity=severity,
                cycle_number=alert_record.first_cycle_number,
                lifecycle_status="resolved" if resolved else alert_record.lifecycle_status,
                message=alert_record.message,
            )
            self.db.add(legacy)
        else:
            legacy.severity = severity
            legacy.lifecycle_status = "resolved" if resolved else alert_record.lifecycle_status
            legacy.message = alert_record.message
            legacy.cycle_number = alert_record.last_cycle_number
        if resolved:
            legacy.resolved_at = alert_record.resolved_at or datetime.utcnow()
            legacy.resolution_record = str(alert_record.resolution_record)

    async def _count_active_legacy_alerts(self, mission_id: str) -> int:
        count = (
            await self.db.execute(
                select(func.count(Alert.id)).where(
                    Alert.mission_id == mission_id,
                    Alert.lifecycle_status.in_(["firing", "active"]),
                )
            )
        ).scalar_one()
        return int(count or 0)

    async def _benchmark_status(
        self,
        mission: Mission,
        metrics: Dict[str, Any],
        latest_synthesis: Optional[SynthesisHistory] = None,
    ) -> Optional[Dict[str, Any]]:
        if not mission.benchmark_text:
            return None
        synthesis = latest_synthesis
        if synthesis is None:
            synthesis = (
                await self.db.execute(
                    select(SynthesisHistory)
                    .where(SynthesisHistory.mission_id == mission.id)
                    .order_by(SynthesisHistory.version_number.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
        if not synthesis or not synthesis.full_text:
            return None

        similarity = round(1.0 - await self._semantic_distance(synthesis.full_text, mission.benchmark_text), 4)
        classification = "ALIGNED" if similarity > 0.75 else "DIVERGING" if similarity >= 0.50 else "MISALIGNED"
        result: Dict[str, Any] = {
            "classification": classification,
            "benchmark_similarity": similarity,
            "benchmark_source": mission.benchmark_source,
            "disagreements": [],
        }
        if classification in {"DIVERGING", "MISALIGNED"}:
            result["disagreements"] = await self._benchmark_disagreements(mission.benchmark_text, synthesis.full_text)
        return result

    async def _benchmark_disagreements(self, benchmark_text: str, synthesis_text: str) -> List[Dict[str, Any]]:
        allowed_tags = {"direction_conflict", "confidence_gap", "omission", "overstatement"}
        prompt = (
            "Compare the current synthesis to the benchmark. "
            "Return JSON with key 'disagreements' as a list of objects with 'tag' and 'description'. "
            "Allowed tags only: direction_conflict, confidence_gap, omission, overstatement.\n\n"
            f"Benchmark:\n{benchmark_text}\n\nSynthesis:\n{synthesis_text}"
        )
        try:
            response = await self.llm_provider.generate_async(
                [
                    {"role": "system", "content": "Return valid JSON only."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.0,
                max_tokens=400,
            )
            import json

            parsed = json.loads((response or {}).get("content", "").strip())
            disagreements = parsed.get("disagreements") or []
            cleaned = []
            for item in disagreements:
                tag = str((item or {}).get("tag") or "").strip()
                description = str((item or {}).get("description") or "").strip()
                if tag in allowed_tags and description:
                    cleaned.append({"tag": tag, "description": description})
            return cleaned
        except Exception as exc:
            logger.warning("Benchmark disagreement analysis failed: %s", exc)
            return []

    async def _semantic_distance(self, left: str, right: str) -> float:
        if not left.strip() or not right.strip():
            return 1.0
        try:
            if self.embedding_service:
                left_vec = await self.embedding_service.embed_text(left, input_type="passage")
                right_vec = await self.embedding_service.embed_text(right, input_type="passage")
                if left_vec and right_vec:
                    if hasattr(self.embedding_service, "embedding_distance"):
                        return float(self.embedding_service.embedding_distance(left_vec, right_vec))
                    if hasattr(self.embedding_service, "cosine_similarity"):
                        return max(0.0, 1.0 - float(self.embedding_service.cosine_similarity(left_vec, right_vec)))
        except Exception as exc:
            logger.warning("Embedding semantic distance failed, falling back to lexical comparison: %s", exc)
        return round(max(0.0, 1.0 - _text_similarity(left, right)), 4)

    def _expected_revision_delta(self, row: BeliefRevisionRecord) -> float:
        revision_type = _enum_value(row.revision_type)
        evidence = row.evidence_summary or {}
        incoming_weight = _safe_float(evidence.get("incoming_weight"))
        previous_conf = _safe_float(row.previous_confidence)
        if revision_type == RevisionTypeEnum.REINFORCE.value:
            return round(incoming_weight * 0.08, 4)
        if revision_type == RevisionTypeEnum.WEAK_REINFORCE.value:
            return round(incoming_weight * 0.03, 4)
        if revision_type == RevisionTypeEnum.WEAKEN.value:
            return round(-(incoming_weight * 0.06), 4)
        if revision_type in {RevisionTypeEnum.MATERIAL_UPDATE.value, RevisionTypeEnum.REVERSAL.value, RevisionTypeEnum.CONTRADICTION_PENALTY.value}:
            return round(_safe_float(row.new_confidence) - previous_conf, 4)
        return 0.0

    def _revision_has_new_evidence(self, row: BeliefRevisionRecord) -> bool:
        evidence = row.evidence_summary or {}
        return _safe_int(evidence.get("incoming_claim_count")) > 0 or bool(row.claims_considered)

    def _incoming_supportive(self, row: BeliefRevisionRecord) -> bool:
        evidence = row.evidence_summary or {}
        incoming_direction = str(evidence.get("incoming_direction") or "").lower()
        new_direction = _enum_value(row.new_direction, "mixed").lower()
        return bool(incoming_direction and incoming_direction == new_direction)

    def _select_primary_cluster(self, claims: Sequence[ResearchClaim]) -> Dict[str, Any]:
        grouped: Dict[tuple[str, str], List[ResearchClaim]] = {}
        for claim in claims:
            intervention = (claim.intervention_canonical or claim.intervention or "").strip()
            outcome = (claim.outcome_canonical or claim.outcome or "").strip()
            if intervention and outcome:
                grouped.setdefault((intervention, outcome), []).append(claim)
        if not grouped:
            return {"pair": ("mission evidence", "overall outcome"), "claims": list(claims[:20]), "prior_support_ratio": 0.0}

        def cluster_score(items: Sequence[ResearchClaim]) -> float:
            return sum(_safe_float(item.composite_confidence) for item in items)

        pair, cluster_claims = max(grouped.items(), key=lambda item: (cluster_score(item[1]), len(item[1])))
        cluster_claims = sorted(cluster_claims, key=lambda claim: _safe_float(claim.composite_confidence), reverse=True)
        prior_support_ratio = 0.0
        if len(cluster_claims) > 4:
            earlier = cluster_claims[2:]
            dominant = Counter(claim_direction_value(claim) for claim in earlier).most_common(1)
            if dominant:
                prior_support_ratio = round(sum(1 for claim in earlier if claim_direction_value(claim) == dominant[0][0]) / len(earlier), 4)
        return {"pair": pair, "claims": cluster_claims[:20], "prior_support_ratio": prior_support_ratio}

    def _primary_cluster_payload(self, cluster: Dict[str, Any]) -> Dict[str, Any]:
        pair = cluster.get("pair") or ("", "")
        claims = cluster.get("claims") or []
        directions = Counter(claim_direction_value(claim) for claim in claims)
        return {
            "intervention": pair[0],
            "outcome": pair[1],
            "claim_count": len(claims),
            "direction_breakdown": dict(directions),
        }

    def _directional_retrieval_balance(self, raw_papers: Sequence[RawPaperRecord], dominant_direction: str) -> float:
        if not raw_papers or not dominant_direction or dominant_direction == "mixed":
            return 0.0
        aligned = 0
        considered = 0
        for row in raw_papers[:20]:
            payload = row.payload or {}
            title = str(payload.get("title") or row.title or "").lower()
            abstract = str(payload.get("abstract_text") or row.abstract_text or "").lower()
            considered += 1
            if dominant_direction == "positive" and any(token in title or token in abstract for token in ["improv", "reduc", "benefit", "superior"]):
                aligned += 1
            elif dominant_direction == "negative" and any(token in title or token in abstract for token in ["harm", "risk", "adverse", "worse"]):
                aligned += 1
            elif dominant_direction == "null" and any(token in title or token in abstract for token in ["no difference", "no significant", "null"]):
                aligned += 1
        return round(aligned / considered, 4) if considered else 0.0

    def _paper_study_type(self, paper: ResearchPaper) -> str:
        breakdown = paper.score_breakdown or {}
        study_type = breakdown.get("study_type") or paper.mechanism_description or ""
        return str(study_type).strip().lower()

    def _claim_publication_year(self, claim: ResearchClaim) -> Optional[int]:
        provenance = claim.provenance or {}
        document_frame = provenance.get("document_frame") or {}
        for candidate in (document_frame.get("publication_year"), provenance.get("publication_year"), provenance.get("paper_year")):
            try:
                if candidate is not None:
                    return int(candidate)
            except (TypeError, ValueError):
                continue
        return None

    def _health_rank(self, value: str) -> int:
        return {
            HealthStatus.HEALTHY.value: 0,
            HealthStatus.WATCH.value: 1,
            HealthStatus.DEGRADED.value: 2,
            HealthStatus.CRITICAL.value: 3,
        }.get(value, 0)

    def _legacy_severity(self, severity: str) -> AlertSeverity:
        if (severity or "").upper() == "HIGH":
            return AlertSeverity.CRITICAL
        if (severity or "").upper() == "MEDIUM":
            return AlertSeverity.DEGRADED
        return AlertSeverity.WATCH

    def _alert_message(self, alert_type: str, metric_values: Dict[str, Any]) -> str:
        if alert_type == "CONFIDENCE_INFLATION":
            return "Confidence is rising faster than recent evidence-weighted revisions justify."
        if alert_type == "CONFIDENCE_SUPPRESSION":
            return "Confidence is falling despite supportive evidence arriving in recent cycles."
        if alert_type == "CONFIDENCE_FLATLINE":
            return "Confidence has stopped moving even though new evidence is still arriving."
        if alert_type == "UNJUSTIFIED_DRIFT":
            return "The synthesis changed substantially without enough new Tier 1 evidence to explain it."
        if alert_type == "SYNTHESIS_STAGNATION":
            return "The synthesis is barely changing even as new evidence continues to arrive."
        if alert_type == "REVERSAL_WITHOUT_SYNTHESIS_UPDATE":
            return "Belief revision reversed, but the synthesis text did not change enough to reflect it."
        if alert_type == "CONTRADICTION_BACKLOG":
            return "Contradictions are accumulating faster than the synthesis is acknowledging them."
        if alert_type == "UNACKNOWLEDGED_HIGH_SEVERITY":
            return "A high-severity contradiction has persisted across multiple syntheses without being surfaced."
        if alert_type == "CONTRADICTION_SPIKE":
            return "Contradictions spiked sharply relative to the recent baseline."
        if alert_type == "RETRIEVAL_BIAS_SUSPECTED":
            return "Recent retrieval appears overly aligned with the current dominant conclusion."
        if alert_type == "EVIDENCE_BASE_SHALLOW":
            return "The mission has run too long without any RCT or meta-analysis support."
        if alert_type == "SUPPORT_COLLAPSE":
            return "Support for the dominant conclusion dropped sharply relative to the prior window."
        if alert_type == "STALE_EVIDENCE_BASE":
            return "The mission is relying too heavily on older literature."
        if alert_type == "EVIDENCE_DROUGHT":
            return "No new evidence has passed intake for many cycles while the mission remains active."
        if alert_type == "RECENCY_INVERSION":
            return "Recent papers are arriving, but the strongest claims are still dominated by much older work."
        if alert_type == "OSCILLATION_DETECTED":
            return "Belief direction has reversed too often in a short window."
        if alert_type == "BELIEF_INERTIA":
            return "Contradictions are arriving, but belief revision is still mostly returning no update."
        if alert_type == "BENCHMARK_DIVERGENCE":
            similarity = metric_values.get("benchmark_similarity")
            if similarity is not None:
                return f"Mission synthesis is diverging from the configured benchmark (similarity {float(similarity):.2f})."
            return "Mission synthesis is diverging from the configured benchmark."
        return f"{alert_type.replace('_', ' ').title()} triggered."

    def _alert_response(self, row: MonitoringAlertRecord) -> Dict[str, Any]:
        return {
            "id": str(row.id),
            "mission_id": row.mission_id,
            "alert_type": row.alert_type,
            "severity": row.severity,
            "lifecycle_status": row.lifecycle_status,
            "first_cycle_number": row.first_cycle_number,
            "last_cycle_number": row.last_cycle_number,
            "message": row.message,
            "metric_values": row.metric_values or {},
            "resolution_record": row.resolution_record,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
        }

    def _snapshot_response(self, snapshot: Optional[MonitoringSnapshot]) -> Optional[Dict[str, Any]]:
        if not snapshot:
            return None
        return {
            "id": str(snapshot.id),
            "mission_id": snapshot.mission_id,
            "cycle_number": snapshot.cycle_number,
            "timestamp": snapshot.timestamp.isoformat() if snapshot.timestamp else None,
            "confidence_velocity": snapshot.confidence_velocity,
            "evidence_justified_velocity": snapshot.evidence_justified_velocity,
            "trajectory_divergence": snapshot.trajectory_divergence,
            "semantic_drift_score": snapshot.semantic_drift_score,
            "active_contradiction_count": snapshot.active_contradiction_count,
            "contradiction_acknowledgment_rate": snapshot.contradiction_acknowledgment_rate,
            "support_ratio": snapshot.support_ratio,
            "directional_retrieval_balance": snapshot.directional_retrieval_balance,
            "mean_paper_age": snapshot.mean_paper_age,
            "recent_ingestion_rate": snapshot.recent_ingestion_rate,
            "reversal_rate": snapshot.reversal_rate,
            "no_update_rate": snapshot.no_update_rate,
            "active_alerts": snapshot.active_alerts or [],
            "alert_history": snapshot.alert_history or [],
            "overall_health": _enum_value(snapshot.overall_health, HealthStatus.HEALTHY.value),
            "metrics_payload": snapshot.metrics_payload or {},
        }
