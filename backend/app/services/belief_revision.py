from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Alert,
    AlertSeverity,
    BeliefEscalation,
    BeliefRevisionRecord,
    BeliefState,
    DominantDirection,
    DriftTrendEnum,
    EscalationStatusEnum,
    Mission,
    MissionTimeline,
    ReasoningStep,
    ResearchClaim,
    RevisionTypeEnum,
)
from app.models.belief_revision import ContradictionSeverityEnum
from app.models.memory import MemoryEventType
from app.services.claim_curation import claim_direction_value
from app.services.llm import get_llm_provider
from app.services.memory_system import MemorySystemService

logger = logging.getLogger(__name__)


class BeliefRevisionService:
    def __init__(
        self,
        db: AsyncSession,
        llm_provider: Any = None,
    ):
        self.db = db
        self.llm_provider = llm_provider or get_llm_provider()
        self.memory_system = MemorySystemService(db=db, llm_provider=self.llm_provider)

    async def run_revision_cycle(
        self,
        mission_id: str,
        actor: str = "belief_revision",
    ) -> Dict[str, Any]:
        mission = await self.db.get(Mission, mission_id)
        if not mission:
            raise ValueError(f"Mission not found: {mission_id}")

        current_state = await self._get_or_initialize_state(mission)
        next_cycle_number = await self._next_cycle_number(mission_id, mission.session_count or 0)
        latest_snapshot = await self._latest_snapshot(mission_id)
        since_timestamp = latest_snapshot["timestamp_obj"] if latest_snapshot else None

        active_escalation = await self._get_active_escalation(mission_id)
        expired_escalation = await self._expire_stale_escalation(
            mission_id=mission_id,
            current_cycle_number=next_cycle_number,
            active_escalation=active_escalation,
            actor=actor,
        )
        if expired_escalation:
            active_escalation = None

        new_claims = await self._get_new_claims(mission_id, since_timestamp)
        filtered_claims, considered_claims = await self._filter_incoming_claims(
            mission_id=mission_id,
            claims=new_claims,
            cycle_number=next_cycle_number,
            actor=actor,
        )
        contradiction_edges = await self._get_cycle_contradictions(
            mission_id=mission_id,
            since_timestamp=since_timestamp,
            claim_ids=[str(claim.id) for claim in new_claims],
        )

        if not considered_claims:
            summary = self._build_no_update_summary(
                reason="No claims passed the intake filter for this cycle.",
                contradiction_edges=contradiction_edges,
            )
            revision_payload = await self._create_revision_record(
                mission_id=mission_id,
                cycle_number=next_cycle_number,
                revision_type=RevisionTypeEnum.NO_UPDATE,
                previous_confidence=current_state.current_confidence_score,
                new_confidence=current_state.current_confidence_score,
                previous_direction=current_state.dominant_evidence_direction,
                new_direction=current_state.dominant_evidence_direction,
                evidence_summary=summary,
                claims_considered=[],
                claims_filtered=filtered_claims,
                condition_fired="FILTERED_EMPTY",
                triggered_synthesis_regen=False,
                operator_action_required=False,
                applied_automatically=True,
                actor=actor,
                contradiction_edges=contradiction_edges,
            )
            if not revision_payload["success"]:
                return revision_payload

            await self._apply_revision_state(
                mission=mission,
                state=current_state,
                revision_record=revision_payload["record"],
                new_confidence=current_state.current_confidence_score,
                new_direction=current_state.dominant_evidence_direction,
                new_statement=current_state.current_belief_statement,
                drift_trend=current_state.drift_trend or DriftTrendEnum.STABILIZING,
                operator_action_required=False,
                actor=actor,
            )
            return self._result_payload(revision_payload["record"], current_state, contradiction_edges)

        batch_characterization = await self._characterize_batch(
            claims=considered_claims,
            contradiction_edges=contradiction_edges,
        )
        decision = self._decide_revision(
            current_state=current_state,
            batch=batch_characterization,
            active_escalation=active_escalation,
        )
        contradiction_penalty = await self._process_contradictions(
            mission=mission,
            contradiction_edges=contradiction_edges,
            cycle_number=next_cycle_number,
            actor=actor,
        )

        candidate_confidence = current_state.current_confidence_score
        if decision["apply_table_result"]:
            candidate_confidence = decision["new_confidence"]
        if contradiction_penalty["penalty_factor"] < 1.0:
            candidate_confidence = round(candidate_confidence * contradiction_penalty["penalty_factor"], 4)

        guarded = await self._apply_confidence_guards(
            mission_id=mission_id,
            actor=actor,
            current_confidence=current_state.current_confidence_score,
            candidate_confidence=candidate_confidence,
        )
        new_confidence = guarded["confidence"]
        effective_direction = decision["new_direction"]

        prospective_drift_trend = await self._compute_drift_trend(
            mission_id=mission_id,
            prospective_direction=effective_direction,
        )
        if await self._should_pause_for_drift_instability(mission_id, prospective_drift_trend):
            evidence_summary = {
                **batch_characterization,
                "drift_trend": prospective_drift_trend.value,
                "contradiction_events_processed": contradiction_penalty["summaries"],
                "guard_events": guarded["events"],
            }
            revision_payload = await self._create_revision_record(
                mission_id=mission_id,
                cycle_number=next_cycle_number,
                revision_type=RevisionTypeEnum.NO_UPDATE,
                previous_confidence=current_state.current_confidence_score,
                new_confidence=current_state.current_confidence_score,
                previous_direction=current_state.dominant_evidence_direction,
                new_direction=current_state.dominant_evidence_direction,
                evidence_summary=evidence_summary,
                claims_considered=[str(claim.id) for claim in considered_claims],
                claims_filtered=filtered_claims,
                condition_fired="DRIFT_GUARD",
                triggered_synthesis_regen=False,
                operator_action_required=True,
                applied_automatically=False,
                actor=actor,
                contradiction_edges=contradiction_edges,
            )
            if not revision_payload["success"]:
                return revision_payload

            await self._emit_event(
                mission_id=mission_id,
                actor=actor,
                event_type=MemoryEventType.BELIEF_DRIFT_INSTABILITY,
                new_value={
                    "cycle_number": next_cycle_number,
                    "drift_trend": prospective_drift_trend.value,
                },
            )
            await self._create_alert(
                mission=mission,
                alert_type="BELIEF_DRIFT_INSTABILITY",
                severity=AlertSeverity.WATCH,
                cycle_number=next_cycle_number,
                message="Automatic belief revisions paused because the mission has been reversing for multiple consecutive cycles.",
            )
            return self._result_payload(revision_payload["record"], current_state, contradiction_edges)

        final_revision_type = decision["revision_type"]
        if final_revision_type == RevisionTypeEnum.NO_UPDATE and contradiction_penalty["penalty_factor"] < 1.0:
            final_revision_type = RevisionTypeEnum.CONTRADICTION_PENALTY

        if final_revision_type == RevisionTypeEnum.ESCALATE_FOR_REVIEW:
            new_confidence = current_state.current_confidence_score
            effective_direction = current_state.dominant_evidence_direction
        elif final_revision_type == RevisionTypeEnum.REVERSAL:
            new_confidence = round(batch_characterization["incoming_weight"] * 0.7, 4)

        evidence_summary = {
            **batch_characterization,
            "drift_trend": prospective_drift_trend.value,
            "contradiction_events_processed": contradiction_penalty["summaries"],
            "guard_events": guarded["events"],
            "incoming_claim_ids": [str(claim.id) for claim in considered_claims],
        }
        triggered_synthesis_regen = bool(
            decision["triggered_synthesis_regen"] or contradiction_penalty["trigger_synthesis_regen"]
        )
        operator_action_required = bool(decision["operator_action_required"])

        revision_payload = await self._create_revision_record(
            mission_id=mission_id,
            cycle_number=next_cycle_number,
            revision_type=final_revision_type,
            previous_confidence=current_state.current_confidence_score,
            new_confidence=new_confidence,
            previous_direction=current_state.dominant_evidence_direction,
            new_direction=effective_direction,
            evidence_summary=evidence_summary,
            claims_considered=[str(claim.id) for claim in considered_claims],
            claims_filtered=filtered_claims,
            condition_fired=decision["condition_fired"],
            triggered_synthesis_regen=triggered_synthesis_regen,
            operator_action_required=operator_action_required,
            applied_automatically=not operator_action_required,
            actor=actor,
            contradiction_edges=contradiction_edges,
        )
        if not revision_payload["success"]:
            return revision_payload

        revision_record = revision_payload["record"]
        if final_revision_type == RevisionTypeEnum.ESCALATE_FOR_REVIEW:
            escalation = await self._create_or_refresh_escalation(
                mission_id=mission_id,
                revision_record=revision_record,
                target_direction=batch_characterization["incoming_direction"],
                evidence_summary=evidence_summary,
            )
            await self._emit_event(
                mission_id=mission_id,
                actor=actor,
                event_type=MemoryEventType.BELIEF_ESCALATED,
                new_value={
                    "cycle_number": next_cycle_number,
                    "escalation_id": str(escalation.id),
                    "target_direction": batch_characterization["incoming_direction"],
                },
            )
            await self._create_alert(
                mission=mission,
                alert_type="BELIEF_ESCALATED",
                severity=AlertSeverity.WATCH,
                cycle_number=next_cycle_number,
                message="A potential belief reversal met escalation criteria and now requires review.",
            )
        elif active_escalation and final_revision_type == RevisionTypeEnum.REVERSAL:
            active_escalation.status = EscalationStatusEnum.APPLIED
            active_escalation.updated_at = datetime.utcnow()
        elif active_escalation and final_revision_type != RevisionTypeEnum.ESCALATE_FOR_REVIEW:
            active_escalation.status = EscalationStatusEnum.CLEARED
            active_escalation.updated_at = datetime.utcnow()

        new_statement = self._compose_belief_statement(
            previous_statement=current_state.current_belief_statement,
            revision_type=final_revision_type,
            claims=considered_claims,
            new_direction=effective_direction,
        )
        await self._apply_revision_state(
            mission=mission,
            state=current_state,
            revision_record=revision_record,
            new_confidence=new_confidence,
            new_direction=effective_direction,
            new_statement=new_statement,
            drift_trend=prospective_drift_trend,
            operator_action_required=operator_action_required,
            actor=actor,
        )
        return self._result_payload(revision_record, current_state, contradiction_edges)

    async def approve_pending_reversal(
        self,
        mission_id: str,
        actor: str = "operator",
        operator_notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        mission = await self.db.get(Mission, mission_id)
        if not mission:
            raise ValueError(f"Mission not found: {mission_id}")

        state = await self._get_or_initialize_state(mission)
        escalation = await self._get_active_escalation(mission_id, include_approved=True)
        if not escalation:
            raise ValueError("No pending reversal escalation found for this mission.")

        escalation.status = EscalationStatusEnum.APPROVED
        escalation.operator_approved = True
        escalation.operator_notes = operator_notes
        escalation.approved_at = datetime.utcnow()
        escalation.updated_at = datetime.utcnow()

        next_cycle_number = await self._next_cycle_number(mission_id, mission.session_count or 0)
        evidence_summary = escalation.evidence_summary or {}
        incoming_direction = self._dominant_direction_from_text(
            evidence_summary.get("incoming_direction") or state.dominant_evidence_direction.value
        )
        new_confidence = round(
            float(evidence_summary.get("incoming_weight") or state.current_confidence_score or 0.5) * 0.7,
            4,
        )
        new_statement = self._compose_belief_statement(
            previous_statement=state.current_belief_statement,
            revision_type=RevisionTypeEnum.REVERSAL,
            claims=[],
            new_direction=incoming_direction,
            fallback_claim_text=evidence_summary.get("top_incoming_statement"),
        )
        revision_payload = await self._create_revision_record(
            mission_id=mission_id,
            cycle_number=next_cycle_number,
            revision_type=RevisionTypeEnum.REVERSAL,
            previous_confidence=state.current_confidence_score,
            new_confidence=new_confidence,
            previous_direction=state.dominant_evidence_direction,
            new_direction=incoming_direction,
            evidence_summary={
                **evidence_summary,
                "operator_approved": True,
                "approval_notes": operator_notes,
            },
            claims_considered=evidence_summary.get("incoming_claim_ids", []),
            claims_filtered=[],
            condition_fired="OPERATOR_APPROVED_REVERSAL",
            triggered_synthesis_regen=True,
            operator_action_required=False,
            applied_automatically=False,
            actor=actor,
            contradiction_edges=[],
        )
        if not revision_payload["success"]:
            return revision_payload

        escalation.status = EscalationStatusEnum.APPLIED
        escalation.updated_at = datetime.utcnow()
        await self._apply_revision_state(
            mission=mission,
            state=state,
            revision_record=revision_payload["record"],
            new_confidence=new_confidence,
            new_direction=incoming_direction,
            new_statement=new_statement,
            drift_trend=DriftTrendEnum.DRIFTING,
            operator_action_required=False,
            actor=actor,
        )
        await self._emit_event(
            mission_id=mission_id,
            actor=actor,
            event_type=MemoryEventType.BELIEF_REVERSED,
            new_value={
                "cycle_number": next_cycle_number,
                "approved_by_operator": True,
                "new_direction": incoming_direction.value,
            },
        )
        return {
            "success": True,
            "cycle_number": next_cycle_number,
            "revision_id": str(revision_payload["record"].id),
            "revision_type": RevisionTypeEnum.REVERSAL.value,
            "new_confidence": new_confidence,
            "new_direction": incoming_direction.value,
        }

    async def get_belief_overview(self, mission_id: str) -> Dict[str, Any]:
        state = await self._belief_state_for_mission(mission_id)
        latest_revision = await self._latest_revision(mission_id)
        active_escalation = await self._get_active_escalation(mission_id, include_approved=True)
        revisions_count = (
            await self.db.execute(
                select(func.count(BeliefRevisionRecord.id)).where(BeliefRevisionRecord.mission_id == mission_id)
            )
        ).scalar_one()
        return {
            "mission_id": mission_id,
            "state": self._belief_state_response(state),
            "latest_revision": self._revision_response(latest_revision) if latest_revision else None,
            "active_escalation": self._escalation_response(active_escalation) if active_escalation else None,
            "revision_count": int(revisions_count or 0),
        }

    async def get_revision_history(self, mission_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        rows = (
            await self.db.execute(
                select(BeliefRevisionRecord)
                .where(BeliefRevisionRecord.mission_id == mission_id)
                .order_by(BeliefRevisionRecord.cycle_number.desc())
                .limit(limit)
            )
        ).scalars().all()
        return [self._revision_response(row) for row in rows]

    async def _get_or_initialize_state(self, mission: Mission) -> BeliefState:
        state = await self._belief_state_for_mission(mission.id)
        if state:
            return state

        latest_snapshot = await self._latest_snapshot(mission.id)
        statement = latest_snapshot["current_belief_statement"] if latest_snapshot else "No evidence-backed belief has been formed yet."
        confidence = float(
            (latest_snapshot["current_confidence_score"] if latest_snapshot else None)
            or mission.confidence_score
            or mission.confidence_from_module1
            or 0.5
        )
        direction = self._dominant_direction_from_text(
            (latest_snapshot["dominant_evidence_direction"] if latest_snapshot else None) or "mixed"
        )
        state = BeliefState(
            mission_id=mission.id,
            current_belief_statement=statement,
            current_confidence_score=round(confidence, 4),
            dominant_evidence_direction=direction,
            current_revision_type=None,
            last_cycle_number=int(mission.session_count or 0),
            operator_action_required=False,
            drift_trend=DriftTrendEnum.STABILIZING,
        )
        self.db.add(state)
        await self.db.flush()
        return state

    async def _belief_state_for_mission(self, mission_id: str) -> Optional[BeliefState]:
        return (
            await self.db.execute(
                select(BeliefState).where(BeliefState.mission_id == mission_id)
            )
        ).scalar_one_or_none()

    async def _latest_snapshot(self, mission_id: str) -> Optional[Dict[str, Any]]:
        from app.models import MissionSnapshot

        latest = (
            await self.db.execute(
                select(MissionSnapshot)
                .where(MissionSnapshot.mission_id == mission_id)
                .order_by(MissionSnapshot.cycle_number.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if not latest:
            return None
        return {
            "id": str(latest.id),
            "cycle_number": latest.cycle_number,
            "timestamp": latest.timestamp.isoformat() if latest.timestamp else None,
            "timestamp_obj": latest.timestamp,
            "current_belief_statement": latest.current_belief_statement,
            "current_confidence_score": float(latest.current_confidence_score or 0.0),
            "dominant_evidence_direction": latest.dominant_evidence_direction.value,
        }

    async def _next_cycle_number(self, mission_id: str, mission_session_count: int) -> int:
        max_revision = (
            await self.db.execute(
                select(func.max(BeliefRevisionRecord.cycle_number)).where(BeliefRevisionRecord.mission_id == mission_id)
            )
        ).scalar_one()
        from app.models import MissionSnapshot

        max_snapshot = (
            await self.db.execute(
                select(func.max(MissionSnapshot.cycle_number)).where(MissionSnapshot.mission_id == mission_id)
            )
        ).scalar_one()
        baseline = max(int(mission_session_count or 0), int(max_revision or 0), int(max_snapshot or 0))
        return baseline + 1

    async def _get_new_claims(self, mission_id: str, since_timestamp: Optional[datetime]) -> List[ResearchClaim]:
        query = select(ResearchClaim).where(ResearchClaim.mission_id == mission_id)
        if since_timestamp:
            query = query.where(ResearchClaim.extraction_timestamp > since_timestamp)
        query = query.order_by(ResearchClaim.extraction_timestamp.asc(), ResearchClaim.created_at.asc())
        return (await self.db.execute(query)).scalars().all()

    async def _filter_incoming_claims(
        self,
        mission_id: str,
        claims: Sequence[ResearchClaim],
        cycle_number: int,
        actor: str,
    ) -> tuple[List[Dict[str, Any]], List[ResearchClaim]]:
        filtered: List[Dict[str, Any]] = []
        considered: List[ResearchClaim] = []
        for claim in claims:
            reason = None
            if float(claim.composite_confidence or 0.0) < 0.20:
                reason = "composite_confidence_below_0_20"
            elif bool(claim.normalization_uncertain) and not (claim.intervention_canonical or "").strip():
                reason = "normalization_uncertain_without_canonical_intervention"
            elif getattr(claim.validation_status, "value", claim.validation_status) == "EXTRACTION_DEGRADED":
                reason = "validation_status_extraction_degraded"
            elif not bool(claim.study_design_consistent) and not bool((claim.provenance or {}).get("manual_override_flag")):
                reason = "study_design_inconsistent_without_manual_override"

            if reason:
                payload = {
                    "claim_id": str(claim.id),
                    "reason": reason,
                    "cycle_number": cycle_number,
                    "intake_filtered": True,
                }
                filtered.append(payload)
                await self._emit_event(
                    mission_id=mission_id,
                    actor=actor,
                    event_type=MemoryEventType.CLAIM_INTAKE_FILTERED,
                    claim_id=claim.id,
                    paper_id=claim.paper_id,
                    new_value=payload,
                )
            else:
                considered.append(claim)
        return filtered, considered

    async def _characterize_batch(
        self,
        claims: Sequence[ResearchClaim],
        contradiction_edges: Sequence[Dict[str, Any]],
    ) -> Dict[str, Any]:
        direction_counts = Counter(claim_direction_value(claim) for claim in claims)
        incoming_direction = "mixed"
        if claims:
            most_common_direction, count = direction_counts.most_common(1)[0]
            if (count / len(claims)) > 0.70:
                incoming_direction = most_common_direction

        total_weight = 0.0
        weighted_confidence = 0.0
        best_study_design = 0.0
        for claim in claims:
            study_weight = max(float(claim.study_design_score or 0.0), 0.05)
            total_weight += study_weight
            weighted_confidence += float(claim.composite_confidence or 0.0) * study_weight
            best_study_design = max(best_study_design, float(claim.study_design_score or 0.0))

        incoming_weight = round((weighted_confidence / total_weight), 4) if total_weight else 0.0
        claim_ids = {str(claim.id) for claim in claims}
        contradictions_in_batch = [
            edge for edge in contradiction_edges
            if claim_ids.intersection(edge.get("claim_ids") or {edge.get("claim_a_id"), edge.get("claim_b_id")})
        ]
        top_claim = max(claims, key=lambda claim: float(claim.composite_confidence or 0.0)) if claims else None
        return {
            "incoming_direction": incoming_direction,
            "incoming_weight": incoming_weight,
            "incoming_claim_count": len(claims),
            "incoming_best_study_design": round(best_study_design, 4),
            "contradictions_in_batch": len(contradictions_in_batch),
            "contradiction_pairs_in_batch": sum(int(edge.get("pair_count") or 1) for edge in contradictions_in_batch),
            "internally_conflicted": len(contradictions_in_batch) > 0,
            "top_incoming_statement": (top_claim.statement_raw if top_claim else None),
        }

    def _decide_revision(
        self,
        current_state: BeliefState,
        batch: Dict[str, Any],
        active_escalation: Optional[BeliefEscalation],
    ) -> Dict[str, Any]:
        current_direction = current_state.dominant_evidence_direction.value
        incoming_direction = batch["incoming_direction"]
        incoming_weight = float(batch["incoming_weight"] or 0.0)
        incoming_best_study_design = float(batch["incoming_best_study_design"] or 0.0)
        incoming_claim_count = int(batch["incoming_claim_count"] or 0)
        internally_conflicted = bool(batch["internally_conflicted"])

        def matches() -> bool:
            return incoming_direction == current_direction

        def opposite() -> bool:
            return (incoming_direction, current_direction) in {
                ("positive", "negative"),
                ("negative", "positive"),
                ("positive", "null"),
                ("null", "positive"),
            }

        if (
            active_escalation
            and active_escalation.status in {EscalationStatusEnum.PENDING, EscalationStatusEnum.APPROVED}
            and active_escalation.originating_cycle_number >= max(0, current_state.last_cycle_number)
            and (
                active_escalation.operator_approved
                or (
                    opposite()
                    and incoming_weight >= 0.6
                    and incoming_best_study_design >= 0.85
                    and incoming_claim_count >= 3
                    and not internally_conflicted
                )
            )
        ):
            return {
                "revision_type": RevisionTypeEnum.REVERSAL,
                "new_confidence": round(incoming_weight * 0.7, 4),
                "new_direction": self._dominant_direction_from_text(incoming_direction),
                "condition_fired": "G_CONFIRMED_REVERSAL",
                "triggered_synthesis_regen": True,
                "operator_action_required": False,
                "apply_table_result": True,
            }

        if matches() and incoming_weight >= 0.5 and not internally_conflicted:
            return {
                "revision_type": RevisionTypeEnum.REINFORCE,
                "new_confidence": round(current_state.current_confidence_score + (incoming_weight * 0.08), 4),
                "new_direction": current_state.dominant_evidence_direction,
                "condition_fired": "A_REINFORCE",
                "triggered_synthesis_regen": False,
                "operator_action_required": False,
                "apply_table_result": True,
            }
        if matches() and incoming_weight < 0.5:
            return {
                "revision_type": RevisionTypeEnum.WEAK_REINFORCE,
                "new_confidence": round(current_state.current_confidence_score + (incoming_weight * 0.03), 4),
                "new_direction": current_state.dominant_evidence_direction,
                "condition_fired": "B_WEAK_REINFORCEMENT",
                "triggered_synthesis_regen": False,
                "operator_action_required": False,
                "apply_table_result": True,
            }
        if incoming_direction == "mixed" and incoming_claim_count <= 2:
            return {
                "revision_type": RevisionTypeEnum.NO_UPDATE,
                "new_confidence": current_state.current_confidence_score,
                "new_direction": current_state.dominant_evidence_direction,
                "condition_fired": "C_NOISE_NO_SIGNAL",
                "triggered_synthesis_regen": False,
                "operator_action_required": False,
                "apply_table_result": False,
            }
        if (
            incoming_direction != current_direction
            and incoming_weight < 0.4
            and incoming_best_study_design <= 0.6
        ):
            return {
                "revision_type": RevisionTypeEnum.WEAKEN,
                "new_confidence": round(current_state.current_confidence_score - (incoming_weight * 0.06), 4),
                "new_direction": current_state.dominant_evidence_direction,
                "condition_fired": "D_WEAKEN",
                "triggered_synthesis_regen": False,
                "operator_action_required": False,
                "apply_table_result": True,
            }
        if (
            incoming_direction != current_direction
            and incoming_weight >= 0.4
            and incoming_best_study_design >= 0.7
            and not internally_conflicted
        ):
            return {
                "revision_type": RevisionTypeEnum.MATERIAL_UPDATE,
                "new_confidence": round(current_state.current_confidence_score * 0.65, 4),
                "new_direction": DominantDirection.MIXED,
                "condition_fired": "E_MATERIAL_UPDATE",
                "triggered_synthesis_regen": True,
                "operator_action_required": False,
                "apply_table_result": True,
            }
        if (
            opposite()
            and incoming_weight >= 0.6
            and incoming_best_study_design >= 0.85
            and incoming_claim_count >= 3
            and not internally_conflicted
        ):
            return {
                "revision_type": RevisionTypeEnum.ESCALATE_FOR_REVIEW,
                "new_confidence": current_state.current_confidence_score,
                "new_direction": current_state.dominant_evidence_direction,
                "condition_fired": "F_POTENTIAL_REVERSAL",
                "triggered_synthesis_regen": False,
                "operator_action_required": True,
                "apply_table_result": False,
            }
        return {
            "revision_type": RevisionTypeEnum.NO_UPDATE,
            "new_confidence": current_state.current_confidence_score,
            "new_direction": current_state.dominant_evidence_direction,
            "condition_fired": "DEFAULT_NO_UPDATE",
            "triggered_synthesis_regen": False,
            "operator_action_required": False,
            "apply_table_result": False,
        }

    async def _get_cycle_contradictions(
        self,
        mission_id: str,
        since_timestamp: Optional[datetime],
        claim_ids: Sequence[str],
    ) -> List[Dict[str, Any]]:
        contradictions = await self.memory_system.get_active_contradictions(mission_id)
        if not since_timestamp:
            filtered = contradictions
        else:
            filtered = [
                edge for edge in contradictions
                if edge.get("created_at")
                and datetime.fromisoformat(edge["created_at"]) > since_timestamp
            ]
        if not claim_ids:
            return self._aggregate_contradiction_topics(filtered)
        claim_set = set(claim_ids)
        return self._aggregate_contradiction_topics([
            edge for edge in filtered
            if edge["claim_a_id"] in claim_set or edge["claim_b_id"] in claim_set
        ])

    def _aggregate_contradiction_topics(
        self,
        contradiction_edges: Sequence[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        severity_rank = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}
        grouped: Dict[str, Dict[str, Any]] = {}
        for edge in contradiction_edges:
            intervention = edge.get("intervention_canonical") or "unknown intervention"
            outcome = edge.get("outcome_canonical") or "unknown outcome"
            key = f"{intervention.strip().lower()}::{outcome.strip().lower()}"
            severity = str(edge.get("severity") or self._contradiction_severity(edge).value).upper()
            group = grouped.setdefault(
                key,
                {
                    "id": key,
                    "topic_key": key,
                    "intervention_canonical": intervention,
                    "outcome_canonical": outcome,
                    "claim_ids": set(),
                    "contradiction_ids": [],
                    "graph_edge_ids": [],
                    "direction_patterns": Counter(),
                    "pair_count": 0,
                    "highest_severity": severity,
                    "edge_weight": 0.0,
                    "study_design_delta": 0.0,
                    "severity_breakdown": Counter(),
                },
            )
            group["pair_count"] += 1
            group["claim_ids"].update([edge["claim_a_id"], edge["claim_b_id"]])
            group["contradiction_ids"].append(edge["id"])
            if edge.get("graph_edge_id"):
                group["graph_edge_ids"].append(edge["graph_edge_id"])
            pattern = f"{edge.get('direction_a', 'unknown')} vs {edge.get('direction_b', 'unknown')}"
            group["direction_patterns"][pattern] += 1
            group["severity_breakdown"][severity] += 1
            if severity_rank[severity] > severity_rank[group["highest_severity"]]:
                group["highest_severity"] = severity
            group["edge_weight"] = max(float(group["edge_weight"] or 0.0), float(edge.get("edge_weight") or 0.0))
            group["study_design_delta"] = min(
                float(group["study_design_delta"] or edge.get("study_design_delta") or 0.0),
                float(edge.get("study_design_delta") or 0.0),
            ) if group["pair_count"] > 1 else float(edge.get("study_design_delta") or 0.0)

        topics = []
        for group in grouped.values():
            topics.append(
                {
                    **group,
                    "severity": group["highest_severity"],
                    "claim_ids": sorted(group["claim_ids"]),
                    "claim_count": len(group["claim_ids"]),
                    "contradiction_ids": sorted(group["contradiction_ids"]),
                    "graph_edge_ids": sorted(set(group["graph_edge_ids"])),
                    "direction_patterns": dict(group["direction_patterns"]),
                    "severity_breakdown": dict(group["severity_breakdown"]),
                }
            )
        topics.sort(
            key=lambda item: (
                -severity_rank.get(item["severity"], 0),
                -int(item["pair_count"]),
                -float(item.get("edge_weight") or 0.0),
            )
        )
        return topics

    async def _process_contradictions(
        self,
        mission: Mission,
        contradiction_edges: Sequence[Dict[str, Any]],
        cycle_number: int,
        actor: str,
    ) -> Dict[str, Any]:
        penalty_factor = 1.0
        summaries: List[Dict[str, Any]] = []
        trigger_synthesis_regen = False
        for edge in contradiction_edges:
            severity = self._contradiction_severity(edge)
            penalty = 1.0
            resolution_status = "unresolved"
            if severity == ContradictionSeverityEnum.LOW:
                penalty = 0.97
                resolution_status = "acknowledged_noise"
            elif severity == ContradictionSeverityEnum.MEDIUM:
                penalty = 0.90
                resolution_status = "active_unresolved"
            elif severity == ContradictionSeverityEnum.HIGH:
                penalty = 0.75
                resolution_status = "high_priority_unresolved"
                trigger_synthesis_regen = True
                await self._emit_event(
                    mission_id=mission.id,
                    actor=actor,
                    event_type=MemoryEventType.CONTRADICTION_HIGH_SEVERITY,
                    new_value={
                        "cycle_number": cycle_number,
                        "topic_key": edge["topic_key"],
                        "edge_weight": edge["edge_weight"],
                        "pair_count": edge.get("pair_count", 1),
                    },
                )
                await self._create_alert(
                    mission=mission,
                    alert_type="HIGH_SEVERITY_CONTRADICTION",
                    severity=AlertSeverity.DEGRADED,
                    cycle_number=cycle_number,
                    message="A high-severity contradiction between roughly equal-quality studies was detected and needs review.",
                )

            penalty_factor *= penalty
            for graph_edge_id in edge.get("graph_edge_ids") or []:
                edge_row = await self._get_graph_edge(graph_edge_id)
                if edge_row:
                    edge_row.resolution_status = resolution_status
                    edge_row.updated_at = datetime.utcnow()

            summaries.append(
                {
                    "topic_key": edge["topic_key"],
                    "contradiction_ids": edge.get("contradiction_ids") or [],
                    "severity": severity.value,
                    "penalty_factor": penalty,
                    "study_design_delta": edge["study_design_delta"],
                    "edge_weight": edge["edge_weight"],
                    "pair_count": edge.get("pair_count", 1),
                    "claim_count": edge.get("claim_count", 2),
                    "intervention_canonical": edge.get("intervention_canonical"),
                    "outcome_canonical": edge.get("outcome_canonical"),
                }
            )
        return {
            "penalty_factor": round(penalty_factor, 6),
            "confidence_after_penalty": round((mission.confidence_score or 0.0) * penalty_factor, 4),
            "summaries": summaries,
            "trigger_synthesis_regen": trigger_synthesis_regen,
        }

    def _contradiction_severity(self, edge: Dict[str, Any]) -> ContradictionSeverityEnum:
        stored = str(edge.get("severity") or "").upper()
        if stored in {"LOW", "MEDIUM", "HIGH"}:
            return ContradictionSeverityEnum(stored)
        edge_weight = float(edge.get("edge_weight") or 0.0)
        study_design_delta = float(edge.get("study_design_delta") or 0.0)
        if edge_weight > 0.6 and study_design_delta < 0.1:
            return ContradictionSeverityEnum.HIGH
        if edge_weight < 0.3 or study_design_delta > 0.4:
            return ContradictionSeverityEnum.LOW
        return ContradictionSeverityEnum.MEDIUM

    async def _apply_confidence_guards(
        self,
        mission_id: str,
        actor: str,
        current_confidence: float,
        candidate_confidence: float,
    ) -> Dict[str, Any]:
        events: List[Dict[str, Any]] = []
        bounded = max(0.05, min(0.95, round(candidate_confidence, 4)))
        delta = round(bounded - current_confidence, 4)
        if delta < -0.25:
            bounded = round(current_confidence - 0.25, 4)
            events.append({"type": "excess_drop_capped", "applied_confidence": bounded})
            await self._emit_event(
                mission_id=mission_id,
                actor=actor,
                event_type=MemoryEventType.EXCESS_DROP_CAPPED,
                new_value={"previous_confidence": current_confidence, "capped_confidence": bounded},
            )
        elif delta > 0.12:
            bounded = round(current_confidence + 0.12, 4)
            events.append({"type": "excess_rise_capped", "applied_confidence": bounded})
            await self._emit_event(
                mission_id=mission_id,
                actor=actor,
                event_type=MemoryEventType.EXCESS_RISE_CAPPED,
                new_value={"previous_confidence": current_confidence, "capped_confidence": bounded},
            )
        bounded = max(0.05, min(0.95, bounded))
        return {"confidence": bounded, "events": events}

    async def _should_pause_for_drift_instability(
        self,
        mission_id: str,
        prospective_trend: DriftTrendEnum,
    ) -> bool:
        recent = (
            await self.db.execute(
                select(BeliefRevisionRecord)
                .where(BeliefRevisionRecord.mission_id == mission_id)
                .order_by(BeliefRevisionRecord.cycle_number.desc())
                .limit(2)
            )
        ).scalars().all()
        recent_trends = [
            str((row.evidence_summary or {}).get("drift_trend") or "")
            for row in recent
        ]
        recent_trends.insert(0, prospective_trend.value)
        return len(recent_trends) >= 3 and all(trend == DriftTrendEnum.REVERSING.value for trend in recent_trends[:3])

    async def _compute_drift_trend(
        self,
        mission_id: str,
        prospective_direction: DominantDirection,
    ) -> DriftTrendEnum:
        recent = (
            await self.db.execute(
                select(BeliefRevisionRecord.new_direction)
                .where(BeliefRevisionRecord.mission_id == mission_id)
                .order_by(BeliefRevisionRecord.cycle_number.desc())
                .limit(2)
            )
        ).scalars().all()
        directions = [prospective_direction.value] + [row.value if hasattr(row, "value") else str(row) for row in recent]
        if len(directions) <= 1:
            return DriftTrendEnum.STABILIZING
        changes = sum(1 for idx in range(len(directions) - 1) if directions[idx] != directions[idx + 1])
        if changes == 0:
            return DriftTrendEnum.STABILIZING
        if changes >= 2:
            return DriftTrendEnum.REVERSING
        return DriftTrendEnum.DRIFTING

    async def _create_revision_record(
        self,
        mission_id: str,
        cycle_number: int,
        revision_type: RevisionTypeEnum,
        previous_confidence: float,
        new_confidence: float,
        previous_direction: DominantDirection,
        new_direction: DominantDirection,
        evidence_summary: Dict[str, Any],
        claims_considered: List[str],
        claims_filtered: List[Dict[str, Any]],
        condition_fired: str,
        triggered_synthesis_regen: bool,
        operator_action_required: bool,
        applied_automatically: bool,
        actor: str,
        contradiction_edges: Sequence[Dict[str, Any]],
    ) -> Dict[str, Any]:
        rationale = await self._generate_rationale(
            revision_type=revision_type,
            previous_confidence=previous_confidence,
            new_confidence=new_confidence,
            evidence_summary=evidence_summary,
            contradiction_edges=contradiction_edges,
        )
        record = BeliefRevisionRecord(
            mission_id=mission_id,
            cycle_number=cycle_number,
            revision_type=revision_type,
            previous_confidence=round(previous_confidence, 4),
            new_confidence=round(new_confidence, 4),
            confidence_delta=round(new_confidence - previous_confidence, 4),
            previous_direction=previous_direction,
            new_direction=new_direction,
            evidence_summary=evidence_summary,
            decision_rationale=rationale,
            claims_considered=claims_considered,
            claims_filtered=claims_filtered,
            triggered_synthesis_regen=triggered_synthesis_regen,
            operator_action_required=operator_action_required,
            applied_automatically=applied_automatically,
            condition_fired=condition_fired,
        )
        self.db.add(record)
        try:
            await self.db.flush()
        except Exception as exc:
            logger.exception("Revision record write failed for mission %s", mission_id)
            await self.db.rollback()
            await self._emit_event(
                mission_id=mission_id,
                actor=actor,
                event_type=MemoryEventType.REVISION_FAILED,
                new_value={
                    "cycle_number": cycle_number,
                    "error": str(exc),
                },
            )
            return {"success": False, "error": str(exc)}

        await self._emit_event(
            mission_id=mission_id,
            actor=actor,
            event_type=MemoryEventType.REVISION_RECORD_CREATED,
            new_value={
                "revision_id": str(record.id),
                "cycle_number": cycle_number,
                "revision_type": revision_type.value,
                "condition_fired": condition_fired,
            },
        )
        return {"success": True, "record": record}

    async def _apply_revision_state(
        self,
        mission: Mission,
        state: BeliefState,
        revision_record: BeliefRevisionRecord,
        new_confidence: float,
        new_direction: DominantDirection,
        new_statement: Optional[str],
        drift_trend: DriftTrendEnum,
        operator_action_required: bool,
        actor: str,
    ) -> None:
        state.current_confidence_score = round(new_confidence, 4)
        state.dominant_evidence_direction = new_direction
        state.current_belief_statement = new_statement
        state.current_revision_type = revision_record.revision_type
        state.last_revised_at = datetime.utcnow()
        state.last_cycle_number = revision_record.cycle_number
        state.operator_action_required = operator_action_required
        state.drift_trend = drift_trend
        state.updated_at = datetime.utcnow()

        await self._emit_event(
            mission_id=mission.id,
            actor=actor,
            event_type=self._belief_event_for_revision(revision_record.revision_type),
            new_value={
                "revision_id": str(revision_record.id),
                "cycle_number": revision_record.cycle_number,
                "revision_type": revision_record.revision_type.value,
                "new_confidence": state.current_confidence_score,
                "new_direction": state.dominant_evidence_direction.value,
            },
        )
        await self._emit_event(
            mission_id=mission.id,
            actor=actor,
            event_type=MemoryEventType.BELIEF_STATE_UPDATED,
            new_value={
                "revision_id": str(revision_record.id),
                "cycle_number": revision_record.cycle_number,
                "current_confidence_score": state.current_confidence_score,
                "dominant_evidence_direction": state.dominant_evidence_direction.value,
            },
        )
        await self._append_reasoning_step(mission.id, revision_record)
        await self._append_timeline_event(mission.id, revision_record)
        await self._sync_mission_alert_count(mission)

    async def _append_reasoning_step(self, mission_id: str, revision_record: BeliefRevisionRecord) -> None:
        current_max = (
            await self.db.execute(
                select(func.max(ReasoningStep.step_number)).where(ReasoningStep.mission_id == mission_id)
            )
        ).scalar_one()
        step = ReasoningStep(
            mission_id=mission_id,
            step_number=int(current_max or 0) + 1,
            reasoning_type="belief_revision",
            premise=f"Cycle {revision_record.cycle_number} evidence was compared against the current belief state.",
            logic=revision_record.decision_rationale,
            conclusion=f"{revision_record.revision_type.value} -> confidence {revision_record.new_confidence:.2f}, direction {revision_record.new_direction.value}.",
            supporting_paper_ids=[],
            supporting_claims=revision_record.claims_considered[:10],
            confidence_score=revision_record.new_confidence,
            generation_cycle=revision_record.cycle_number,
        )
        self.db.add(step)

    async def _append_timeline_event(self, mission_id: str, revision_record: BeliefRevisionRecord) -> None:
        event = MissionTimeline(
            mission_id=mission_id,
            event_type=f"belief.{revision_record.revision_type.value.lower()}",
            event_title=self._timeline_title(revision_record.revision_type),
            event_description=revision_record.decision_rationale,
            cycle_number=revision_record.cycle_number,
            metrics_change={
                "confidence_delta": revision_record.confidence_delta,
                "direction": revision_record.new_direction.value,
                "operator_action_required": revision_record.operator_action_required,
            },
        )
        self.db.add(event)

    async def _create_or_refresh_escalation(
        self,
        mission_id: str,
        revision_record: BeliefRevisionRecord,
        target_direction: str,
        evidence_summary: Dict[str, Any],
    ) -> BeliefEscalation:
        current = await self._get_active_escalation(mission_id, include_approved=True)
        if current:
            current.source_revision_id = revision_record.id
            current.originating_cycle_number = revision_record.cycle_number
            current.target_direction = self._dominant_direction_from_text(target_direction)
            current.evidence_summary = evidence_summary
            current.status = EscalationStatusEnum.PENDING
            current.operator_approved = False
            current.operator_notes = None
            current.approved_at = None
            current.expires_after_cycle = revision_record.cycle_number + 1
            current.updated_at = datetime.utcnow()
            return current

        escalation = BeliefEscalation(
            mission_id=mission_id,
            source_revision_id=revision_record.id,
            originating_cycle_number=revision_record.cycle_number,
            target_direction=self._dominant_direction_from_text(target_direction),
            evidence_summary=evidence_summary,
            status=EscalationStatusEnum.PENDING,
            expires_after_cycle=revision_record.cycle_number + 1,
        )
        self.db.add(escalation)
        await self.db.flush()
        state = await self._belief_state_for_mission(mission_id)
        if state:
            state.active_escalation_id = escalation.id
        return escalation

    async def _expire_stale_escalation(
        self,
        mission_id: str,
        current_cycle_number: int,
        active_escalation: Optional[BeliefEscalation],
        actor: str,
    ) -> bool:
        if not active_escalation:
            return False
        if active_escalation.status != EscalationStatusEnum.PENDING:
            return False
        if current_cycle_number - int(active_escalation.originating_cycle_number or 0) < 2:
            return False

        active_escalation.status = EscalationStatusEnum.EXPIRED
        active_escalation.updated_at = datetime.utcnow()
        state = await self._belief_state_for_mission(mission_id)
        if state:
            state.active_escalation_id = None
            state.operator_action_required = False
        await self._emit_event(
            mission_id=mission_id,
            actor=actor,
            event_type=MemoryEventType.ESCALATION_EXPIRED,
            new_value={
                "escalation_id": str(active_escalation.id),
                "originating_cycle_number": active_escalation.originating_cycle_number,
            },
        )
        return True

    async def _get_active_escalation(
        self,
        mission_id: str,
        include_approved: bool = False,
    ) -> Optional[BeliefEscalation]:
        valid_statuses = [EscalationStatusEnum.PENDING]
        if include_approved:
            valid_statuses.append(EscalationStatusEnum.APPROVED)
        return (
            await self.db.execute(
                select(BeliefEscalation)
                .where(
                    BeliefEscalation.mission_id == mission_id,
                    BeliefEscalation.status.in_(valid_statuses),
                )
                .order_by(BeliefEscalation.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    async def _latest_revision(self, mission_id: str) -> Optional[BeliefRevisionRecord]:
        return (
            await self.db.execute(
                select(BeliefRevisionRecord)
                .where(BeliefRevisionRecord.mission_id == mission_id)
                .order_by(BeliefRevisionRecord.cycle_number.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    async def _generate_rationale(
        self,
        revision_type: RevisionTypeEnum,
        previous_confidence: float,
        new_confidence: float,
        evidence_summary: Dict[str, Any],
        contradiction_edges: Sequence[Dict[str, Any]],
    ) -> str:
        contradiction_summary = [
            {
                "edge_weight": edge.get("edge_weight"),
                "study_design_delta": edge.get("study_design_delta"),
            }
            for edge in contradiction_edges[:5]
        ]
        prompt = {
            "revision_type": revision_type.value,
            "previous_confidence": round(previous_confidence, 4),
            "new_confidence": round(new_confidence, 4),
            "evidence_summary": evidence_summary,
            "contradictions": contradiction_summary,
        }
        try:
            response = await self.llm_provider.generate_async(
                [
                    {
                        "role": "system",
                        "content": "You write audit-log rationales for scientific belief revision. Return two or three concise sentences only.",
                    },
                    {
                        "role": "user",
                        "content": (
                            "Explain why this belief revision occurred. "
                            "Do not restate formulas. Be specific, concise, and researcher-facing.\n"
                            f"{json.dumps(prompt)}"
                        ),
                    },
                ],
                temperature=0.0,
                max_tokens=180,
            )
            content = (response or {}).get("content", "").strip()
            if content:
                return content
        except Exception as exc:
            logger.warning("Belief rationale generation failed: %s", exc)
        return (
            f"{revision_type.value} fired because the incoming batch direction was {evidence_summary.get('incoming_direction', 'mixed')} "
            f"with weighted confidence {float(evidence_summary.get('incoming_weight', 0.0)):.2f}. "
            f"Confidence changed from {previous_confidence:.2f} to {new_confidence:.2f} after applying contradiction penalties and stability guards."
        )

    async def _emit_event(
        self,
        mission_id: str,
        actor: str,
        event_type: MemoryEventType,
        claim_id: Optional[Any] = None,
        paper_id: Optional[Any] = None,
        previous_value: Any = None,
        new_value: Any = None,
    ) -> None:
        await self.memory_system.log_event(
            event_type=event_type,
            mission_id=mission_id,
            actor=actor,
            claim_id=claim_id,
            paper_id=paper_id,
            previous_value=previous_value,
            new_value=new_value,
        )

    async def _get_graph_edge(self, edge_id: str):
        from app.models import ClaimGraphEdge

        return await self.db.get(ClaimGraphEdge, edge_id)

    async def _create_alert(
        self,
        mission: Mission,
        alert_type: str,
        severity: AlertSeverity,
        cycle_number: int,
        message: str,
    ) -> None:
        existing = (
            await self.db.execute(
                select(Alert).where(
                    Alert.mission_id == mission.id,
                    Alert.alert_type == alert_type,
                    Alert.lifecycle_status.in_(["firing", "active"]),
                )
            )
        ).scalar_one_or_none()
        if existing:
            existing.message = message
            existing.severity = severity
            existing.cycle_number = cycle_number
            return

        alert = Alert(
            id=str(uuid4()),
            mission_id=mission.id,
            alert_type=alert_type,
            severity=severity,
            cycle_number=cycle_number,
            lifecycle_status="active",
            message=message,
        )
        self.db.add(alert)

    async def _sync_mission_alert_count(self, mission: Mission) -> None:
        active_count = (
            await self.db.execute(
                select(func.count(Alert.id)).where(
                    Alert.mission_id == mission.id,
                    Alert.lifecycle_status.in_(["firing", "active"]),
                )
            )
        ).scalar_one()
        mission.active_alerts = int(active_count or 0)

    def _compose_belief_statement(
        self,
        previous_statement: Optional[str],
        revision_type: RevisionTypeEnum,
        claims: Sequence[ResearchClaim],
        new_direction: DominantDirection,
        fallback_claim_text: Optional[str] = None,
    ) -> str:
        lead_claim = None
        if claims:
            lead_claim = max(claims, key=lambda claim: float(claim.composite_confidence or 0.0))
        lead_text = (lead_claim.statement_raw if lead_claim else fallback_claim_text) or previous_statement or "No evidence-backed belief has been formed yet."

        if revision_type == RevisionTypeEnum.MATERIAL_UPDATE:
            return f"Evidence is now mixed after a material update. Leading incoming finding: {lead_text}"
        if revision_type == RevisionTypeEnum.REVERSAL:
            return f"Belief direction reversed toward {new_direction.value}. Leading supporting finding: {lead_text}"
        if revision_type == RevisionTypeEnum.ESCALATE_FOR_REVIEW:
            return previous_statement or f"Potential reversal toward {new_direction.value} is under review."
        if revision_type == RevisionTypeEnum.NO_UPDATE:
            return previous_statement or lead_text
        return previous_statement or f"Current evidence trends {new_direction.value}. Highest-confidence finding: {lead_text}"

    def _timeline_title(self, revision_type: RevisionTypeEnum) -> str:
        return {
            RevisionTypeEnum.REINFORCE: "Belief reinforced",
            RevisionTypeEnum.WEAK_REINFORCE: "Belief weakly reinforced",
            RevisionTypeEnum.WEAKEN: "Belief weakened",
            RevisionTypeEnum.MATERIAL_UPDATE: "Material evidence update",
            RevisionTypeEnum.ESCALATE_FOR_REVIEW: "Potential reversal escalated",
            RevisionTypeEnum.REVERSAL: "Belief reversal applied",
            RevisionTypeEnum.CONTRADICTION_PENALTY: "Contradiction penalty applied",
            RevisionTypeEnum.NO_UPDATE: "No belief change",
        }[revision_type]

    def _belief_event_for_revision(self, revision_type: RevisionTypeEnum) -> MemoryEventType:
        return {
            RevisionTypeEnum.REINFORCE: MemoryEventType.BELIEF_REINFORCED,
            RevisionTypeEnum.WEAK_REINFORCE: MemoryEventType.BELIEF_REINFORCED,
            RevisionTypeEnum.WEAKEN: MemoryEventType.BELIEF_WEAKENED,
            RevisionTypeEnum.MATERIAL_UPDATE: MemoryEventType.BELIEF_MATERIAL_UPDATE,
            RevisionTypeEnum.ESCALATE_FOR_REVIEW: MemoryEventType.BELIEF_ESCALATED,
            RevisionTypeEnum.REVERSAL: MemoryEventType.BELIEF_REVERSED,
            RevisionTypeEnum.CONTRADICTION_PENALTY: MemoryEventType.BELIEF_WEAKENED,
            RevisionTypeEnum.NO_UPDATE: MemoryEventType.BELIEF_NO_UPDATE,
        }[revision_type]

    def _dominant_direction_from_text(self, value: str) -> DominantDirection:
        normalized = (value or "mixed").strip().lower()
        if normalized == "positive":
            return DominantDirection.POSITIVE
        if normalized == "negative":
            return DominantDirection.NEGATIVE
        if normalized == "null":
            return DominantDirection.NULL
        return DominantDirection.MIXED

    def _belief_state_response(self, state: Optional[BeliefState]) -> Optional[Dict[str, Any]]:
        if not state:
            return None
        return {
            "id": str(state.id),
            "mission_id": state.mission_id,
            "current_belief_statement": state.current_belief_statement,
            "current_confidence_score": state.current_confidence_score,
            "dominant_evidence_direction": state.dominant_evidence_direction.value,
            "current_revision_type": state.current_revision_type.value if state.current_revision_type else None,
            "last_revised_at": state.last_revised_at.isoformat() if state.last_revised_at else None,
            "last_cycle_number": state.last_cycle_number,
            "operator_action_required": state.operator_action_required,
            "drift_trend": state.drift_trend.value if state.drift_trend else DriftTrendEnum.STABILIZING.value,
            "active_escalation_id": str(state.active_escalation_id) if state.active_escalation_id else None,
        }

    def _revision_response(self, row: BeliefRevisionRecord) -> Dict[str, Any]:
        return {
            "id": str(row.id),
            "mission_id": row.mission_id,
            "cycle_number": row.cycle_number,
            "timestamp": row.timestamp.isoformat() if row.timestamp else None,
            "revision_type": row.revision_type.value,
            "previous_confidence": row.previous_confidence,
            "new_confidence": row.new_confidence,
            "confidence_delta": row.confidence_delta,
            "previous_direction": row.previous_direction.value,
            "new_direction": row.new_direction.value,
            "evidence_summary": row.evidence_summary or {},
            "decision_rationale": row.decision_rationale,
            "claims_considered": row.claims_considered or [],
            "claims_filtered": row.claims_filtered or [],
            "triggered_synthesis_regen": row.triggered_synthesis_regen,
            "operator_action_required": row.operator_action_required,
            "applied_automatically": row.applied_automatically,
            "condition_fired": row.condition_fired,
        }

    def _escalation_response(self, row: BeliefEscalation) -> Dict[str, Any]:
        return {
            "id": str(row.id),
            "mission_id": row.mission_id,
            "source_revision_id": str(row.source_revision_id) if row.source_revision_id else None,
            "originating_cycle_number": row.originating_cycle_number,
            "target_direction": row.target_direction.value,
            "evidence_summary": row.evidence_summary or {},
            "status": row.status.value,
            "operator_approved": row.operator_approved,
            "operator_notes": row.operator_notes,
            "approved_at": row.approved_at.isoformat() if row.approved_at else None,
            "expires_after_cycle": row.expires_after_cycle,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    def _build_no_update_summary(
        self,
        reason: str,
        contradiction_edges: Sequence[Dict[str, Any]],
    ) -> Dict[str, Any]:
        return {
            "reason": reason,
            "incoming_direction": "mixed",
            "incoming_weight": 0.0,
            "incoming_claim_count": 0,
            "incoming_best_study_design": 0.0,
            "internally_conflicted": False,
            "contradiction_events_processed": len(contradiction_edges),
            "low_signal_cycle": True,
        }

    def _result_payload(
        self,
        revision_record: BeliefRevisionRecord,
        previous_state: BeliefState,
        contradiction_edges: Sequence[Dict[str, Any]],
    ) -> Dict[str, Any]:
        return {
            "success": True,
            "revision_id": str(revision_record.id),
            "cycle_number": revision_record.cycle_number,
            "revision_type": revision_record.revision_type.value,
            "previous_confidence": previous_state.current_confidence_score,
            "new_confidence": revision_record.new_confidence,
            "new_direction": revision_record.new_direction.value,
            "operator_action_required": revision_record.operator_action_required,
            "triggered_synthesis_regen": revision_record.triggered_synthesis_regen,
            "contradictions_processed": len(contradiction_edges),
        }
