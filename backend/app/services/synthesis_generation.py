from __future__ import annotations

import json
import logging
import math
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    BeliefRevisionRecord,
    BeliefState,
    ClaimGraphEdge,
    ContradictionRecord,
    GraphEdgeType,
    Mission,
    MissionTimeline,
    ResearchClaim,
    SynthesisAnswer,
    SynthesisHistory,
    SynthesisLLMCall,
    SynthesisTrigger,
)
from app.models.memory import MemoryEventType
from app.models.belief_revision import DriftTrendEnum, RevisionTypeEnum
from app.services.claim_curation import claim_direction_value
from app.services.llm import get_llm_provider
from app.services.memory_system import MemorySystemService

logger = logging.getLogger(__name__)

CONFIDENCE_LANGUAGE_BANS = {
    "MIXED": [
        "the evidence consistently shows",
        "strong evidence supports",
        "multiple high-quality studies demonstrate",
        "clearly proves",
        "clearly shows",
    ],
    "WEAK": [
        "the evidence consistently shows",
        "strong evidence supports",
        "multiple high-quality studies demonstrate",
        "clearly proves",
        "clearly shows",
    ],
}


def _enum_value(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(getattr(value, "value", value) or default)


def _claim_statement(claim: ResearchClaim) -> str:
    return (claim.statement_normalized or claim.statement_raw or "").strip()


def _mission_relevance_weight(claim: ResearchClaim) -> float:
    relevance = _enum_value(claim.mission_relevance, "secondary").lower()
    return {"primary": 1.0, "secondary": 0.7, "peripheral": 0.4}.get(relevance, 0.7)


def _current_year() -> int:
    return datetime.utcnow().year


def _publication_year(claim: ResearchClaim) -> Optional[int]:
    provenance = claim.provenance or {}
    document_frame = provenance.get("document_frame") or {}
    for candidate in (document_frame.get("publication_year"), provenance.get("publication_year"), provenance.get("paper_year")):
        try:
            if candidate is not None:
                return int(candidate)
        except (TypeError, ValueError):
            continue
    return None


def _recency_weight(year: Optional[int]) -> float:
    if not year:
        return 0.8
    age = max(0, _current_year() - year)
    if age <= 3:
        return 1.0
    if age >= 10:
        return 0.6
    step = (age - 3) / 7
    return round(1.0 - (0.4 * step), 4)


def _word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text or ""))


def _jsonable(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _jsonable(inner) for key, inner in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    return value


def _safe_json_list(raw_text: Optional[str]) -> List[str]:
    if not raw_text:
        return []
    try:
        value = json.loads(raw_text)
        if isinstance(value, list):
            return [str(item) for item in value]
    except Exception:
        pass
    return []


class SynthesisGenerationService:
    def __init__(self, db: AsyncSession, llm_provider: Any = None) -> None:
        self.db = db
        self.llm_provider = llm_provider or get_llm_provider()
        self.memory_system = MemorySystemService(db=db, llm_provider=self.llm_provider)

    async def generate_synthesis(
        self,
        mission_id: str,
        trigger: SynthesisTrigger = SynthesisTrigger.OPERATOR_REQUEST,
        actor: str = "synthesis_generation",
    ) -> Dict[str, Any]:
        mission = await self.db.get(Mission, mission_id)
        if not mission:
            raise ValueError(f"Mission not found: {mission_id}")

        evidence_package = await self._assemble_evidence_package(mission, trigger)
        prior = await self._latest_history(mission_id)
        generated = await self._generate_synthesis_text(evidence_package, prior, trigger)
        change = self._detect_change(prior, evidence_package, generated["contradiction_ids"])

        version_number = int((prior.version_number if prior else 0) + 1)
        record = SynthesisHistory(
            mission_id=mission_id,
            version_number=version_number,
            claim_ids_used=evidence_package["claim_ids_used"],
            contradictions_acknowledged=generated["contradiction_ids"],
            full_text=generated["text"],
            confidence_at_time=evidence_package["current_confidence"],
            trigger=trigger,
            confidence_tier=evidence_package["confidence_tier"],
            dominant_direction=evidence_package["dominant_direction"],
            claim_ids_tier1=evidence_package["tier1_ids"],
            claim_ids_tier2=evidence_package["tier2_ids"],
            claim_ids_tier3=evidence_package["tier3_ids"],
            contradictions_included=generated["contradiction_ids"],
            change_magnitude=change["change_magnitude"],
            confidence_delta=change["confidence_delta"],
            direction_changed=change["direction_changed"],
            prior_synthesis_id=prior.id if prior else None,
            llm_call_id=generated.get("llm_call_id"),
            validation_passed=generated["validation_passed"],
            llm_fallback=generated["llm_fallback"],
            word_count=generated["word_count"],
            evidence_package=_jsonable(evidence_package),
        )
        self.db.add(record)
        await self.db.flush()

        await self._sync_compatibility_answer(mission_id, record, evidence_package)
        await self.memory_system.log_event(
            event_type=MemoryEventType.SYNTHESIS_VERSION_CREATED,
            mission_id=mission_id,
            actor=actor,
            previous_value=None,
            new_value={"synthesis_id": str(record.id), "version_number": version_number, "trigger": trigger.value},
        )
        await self.memory_system.log_event(
            event_type=MemoryEventType.SYNTHESIS_CREATED,
            mission_id=mission_id,
            actor=actor,
            previous_value=None,
            new_value={
                "synthesis_id": str(record.id),
                "version_number": version_number,
                "confidence_tier": record.confidence_tier,
                "change_magnitude": record.change_magnitude,
            },
        )
        if record.change_magnitude == "MAJOR":
            await self.memory_system.log_event(
                event_type=MemoryEventType.SYNTHESIS_MAJOR_CHANGE,
                mission_id=mission_id,
                actor=actor,
                previous_value=None,
                new_value={
                    "synthesis_id": str(record.id),
                    "version_number": version_number,
                    "description": self._major_change_description(change, evidence_package),
                },
            )
        self.db.add(
            MissionTimeline(
                mission_id=mission_id,
                event_type="synthesis.created",
                event_title=f"Synthesis v{version_number} generated",
                event_description=self._timeline_description(record, evidence_package, change),
                cycle_number=evidence_package.get("cycle_number"),
                metrics_change={
                    "confidence": evidence_package["current_confidence"],
                    "confidence_delta": change["confidence_delta"],
                    "change_magnitude": change["change_magnitude"],
                },
            )
        )
        return {"mission_id": mission_id, "synthesis": self._history_response(record)}

    async def get_latest_synthesis(self, mission_id: str) -> Optional[Dict[str, Any]]:
        latest = await self._latest_history(mission_id)
        if latest:
            return self._history_response(latest)

        legacy = (
            await self.db.execute(select(SynthesisAnswer).where(SynthesisAnswer.mission_id == mission_id))
        ).scalar_one_or_none()
        if not legacy or not legacy.answer_text:
            return None

        answer_confidence = float(legacy.confidence_current or legacy.answer_confidence or 0.0)
        return {
            "id": str(legacy.id),
            "mission_id": mission_id,
            "version_number": 0,
            "created_at": legacy.created_at.isoformat() if legacy.created_at else None,
            "trigger_type": "legacy",
            "synthesis_text": legacy.answer_text,
            "confidence_tier": self._confidence_tier(answer_confidence, "mixed", None, []),
            "confidence_score": answer_confidence,
            "dominant_direction": "mixed",
            "claim_ids_tier1": [],
            "claim_ids_tier2": [],
            "claim_ids_tier3": [],
            "contradictions_included": [],
            "change_magnitude": "MINOR",
            "confidence_delta": 0.0,
            "direction_changed": False,
            "prior_synthesis_id": None,
            "validation_passed": True,
            "word_count": _word_count(legacy.answer_text),
            "llm_fallback": False,
            "change_summary": {
                "confidence_delta": 0.0,
                "direction_changed": False,
                "new_contradictions_surfaced": 0,
                "contradictions_resolved": 0,
            },
            "summary_metrics": {
                "tier1_count": 0,
                "tier2_count": 0,
                "tier3_count": 0,
                "high_contradictions": 0,
                "medium_contradictions": 0,
            },
        }

    async def get_synthesis_history(self, mission_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        rows = (
            await self.db.execute(
                select(SynthesisHistory)
                .where(SynthesisHistory.mission_id == mission_id)
                .order_by(SynthesisHistory.version_number.desc())
                .limit(limit)
            )
        ).scalars().all()
        return [self._history_response(row) for row in rows]

    @staticmethod
    def trigger_from_revision(
        revision_type: Optional[str],
        cycle_number: Optional[int] = None,
        schedule_interval: int = 5,
    ) -> Optional[SynthesisTrigger]:
        normalized = (revision_type or "").strip().upper()
        if normalized == RevisionTypeEnum.MATERIAL_UPDATE.value:
            return SynthesisTrigger.BELIEF_MATERIAL_UPDATE
        if normalized == RevisionTypeEnum.REVERSAL.value:
            return SynthesisTrigger.BELIEF_REVERSED
        if cycle_number and schedule_interval > 0 and cycle_number % schedule_interval == 0:
            return SynthesisTrigger.SCHEDULED
        return None

    async def _assemble_evidence_package(
        self,
        mission: Mission,
        trigger: SynthesisTrigger,
    ) -> Dict[str, Any]:
        claims = (
            await self.db.execute(
                select(ResearchClaim)
                .where(ResearchClaim.mission_id == mission.id)
                .order_by(ResearchClaim.composite_confidence.desc())
            )
        ).scalars().all()

        belief_state = (
            await self.db.execute(select(BeliefState).where(BeliefState.mission_id == mission.id))
        ).scalar_one_or_none()
        latest_revision = (
            await self.db.execute(
                select(BeliefRevisionRecord)
                .where(BeliefRevisionRecord.mission_id == mission.id)
                .order_by(BeliefRevisionRecord.cycle_number.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        primary_pair, primary_claims = self._select_primary_cluster(claims)
        ranked_claims = sorted(primary_claims[:20], key=lambda claim: self._evidence_score(claim), reverse=True)
        tier1, tier2, tier3 = self._partition_tiers(ranked_claims)
        contradictions = await self._load_contradictions(mission.id, primary_pair)
        refinements = await self._load_refinements(mission.id, [claim.id for claim in ranked_claims])
        drift_trend = _enum_value(getattr(belief_state, "drift_trend", None), DriftTrendEnum.STABILIZING.value)
        dominant_direction = _enum_value(getattr(belief_state, "dominant_evidence_direction", None), "mixed") or "mixed"
        current_confidence = float(
            getattr(belief_state, "current_confidence_score", None)
            or mission.confidence_score
            or mission.confidence_from_module1
            or 0.0
        )
        confidence_tier = self._confidence_tier(current_confidence, dominant_direction, drift_trend, contradictions)

        return {
            "mission_id": mission.id,
            "mission_question": mission.normalized_query,
            "mission_domain": mission.name,
            "focus_areas": _safe_json_list(mission.key_concepts),
            "operator_defined_focus": _safe_json_list(mission.ambiguity_flags),
            "trigger_type": trigger.value,
            "current_confidence": round(current_confidence, 4),
            "dominant_direction": dominant_direction,
            "revision_type": _enum_value(getattr(latest_revision, "revision_type", None), "NO_UPDATE"),
            "drift_trend": drift_trend,
            "cycle_number": int(getattr(belief_state, "last_cycle_number", None) or mission.session_count or 0),
            "primary_pair": {"intervention": primary_pair[0], "outcome": primary_pair[1]},
            "tier1": [self._claim_payload(claim) for claim in tier1],
            "tier2": [self._claim_payload(claim) for claim in tier2],
            "tier3": [self._claim_payload(claim) for claim in tier3],
            "tier1_ids": [str(claim.id) for claim in tier1],
            "tier2_ids": [str(claim.id) for claim in tier2],
            "tier3_ids": [str(claim.id) for claim in tier3],
            "claim_ids_used": [str(claim.id) for claim in ranked_claims],
            "contradictions": contradictions,
            "subgroups_and_refinements": refinements,
            "paper_count": len({str(claim.paper_id) for claim in ranked_claims}),
            "confidence_tier": confidence_tier,
        }

    def _select_primary_cluster(self, claims: Sequence[ResearchClaim]) -> Tuple[Tuple[str, str], List[ResearchClaim]]:
        grouped: Dict[Tuple[str, str], List[ResearchClaim]] = {}
        for claim in claims:
            intervention = (claim.intervention_canonical or claim.intervention or "").strip()
            outcome = (claim.outcome_canonical or claim.outcome or "").strip()
            if not intervention or not outcome:
                continue
            grouped.setdefault((intervention, outcome), []).append(claim)

        if not grouped:
            fallback = list(claims[:20])
            top = fallback[0] if fallback else None
            return (
                (
                    (top.intervention_canonical or top.intervention or "mission evidence") if top else "mission evidence",
                    (top.outcome_canonical or top.outcome or "overall outcome") if top else "overall outcome",
                ),
                fallback,
            )

        def cluster_score(items: Sequence[ResearchClaim]) -> float:
            return round(sum(self._evidence_score(claim) for claim in items), 6)

        primary_pair = max(grouped.items(), key=lambda item: (cluster_score(item[1]), len(item[1])))[0]
        ranked = sorted(grouped[primary_pair], key=lambda claim: self._evidence_score(claim), reverse=True)
        return primary_pair, ranked

    def _partition_tiers(
        self,
        claims: Sequence[ResearchClaim],
    ) -> Tuple[List[ResearchClaim], List[ResearchClaim], List[ResearchClaim]]:
        if not claims:
            return [], [], []
        total = len(claims)
        tier1_end = max(1, math.ceil(total * 0.4))
        tier2_end = max(tier1_end + 1, math.ceil(total * 0.8))
        return (list(claims[:tier1_end]), list(claims[tier1_end:tier2_end]), list(claims[tier2_end:]))

    def _evidence_score(self, claim: ResearchClaim) -> float:
        try:
            score = (
                float(claim.composite_confidence or 0.0)
                * float(claim.study_design_score or 0.0)
                * _recency_weight(_publication_year(claim))
                * _mission_relevance_weight(claim)
            )
        except (TypeError, ValueError):
            score = 0.0
        return round(score, 6)

    async def _load_contradictions(
        self,
        mission_id: str,
        primary_pair: Tuple[str, str],
    ) -> List[Dict[str, Any]]:
        rows = (
            await self.db.execute(
                select(ContradictionRecord)
                .where(
                    ContradictionRecord.mission_id == mission_id,
                    ContradictionRecord.resolution_status == "unresolved",
                )
                .order_by(ContradictionRecord.timestamp.desc())
                .limit(25)
            )
        ).scalars().all()

        severity_rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        grouped: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for row in rows:
            key = (
                row.intervention_canonical or "unknown intervention",
                row.outcome_canonical or "unknown outcome",
            )
            group = grouped.setdefault(
                key,
                {
                    "intervention_canonical": key[0],
                    "outcome_canonical": key[1],
                    "contradiction_ids": [],
                    "pair_count": 0,
                    "highest_severity": row.severity.value,
                    "severity_breakdown": {"HIGH": 0, "MEDIUM": 0, "LOW": 0},
                    "direction_patterns": {},
                    "population_overlaps": set(),
                    "claim_pairs": [],
                    "max_confidence_product": 0.0,
                },
            )
            severity = row.severity.value
            group["contradiction_ids"].append(str(row.id))
            group["pair_count"] += 1
            group["severity_breakdown"][severity] = group["severity_breakdown"].get(severity, 0) + 1
            pattern = f"{row.direction_a} vs {row.direction_b}"
            group["direction_patterns"][pattern] = group["direction_patterns"].get(pattern, 0) + 1
            group["population_overlaps"].add(row.population_overlap.value)
            group["claim_pairs"].append(row)
            group["max_confidence_product"] = max(float(group["max_confidence_product"] or 0.0), float(row.confidence_product or 0.0))
            if severity_rank[severity] < severity_rank[group["highest_severity"]]:
                group["highest_severity"] = severity

        prioritized = sorted(
            grouped.values(),
            key=lambda item: (
                0 if (item["intervention_canonical"], item["outcome_canonical"]) == primary_pair else 1,
                severity_rank.get(item["highest_severity"], 3),
                -float(item["max_confidence_product"] or 0.0),
                -int(item["pair_count"] or 0),
            ),
        )

        summaries: List[Dict[str, Any]] = []
        for item in prioritized[:10]:
            exemplar = max(item["claim_pairs"], key=lambda row: float(row.confidence_product or 0.0))
            claim_a = await self.db.get(ResearchClaim, exemplar.claim_a_id)
            claim_b = await self.db.get(ResearchClaim, exemplar.claim_b_id)
            direction_summary = ", ".join(
                f"{pattern} ({count})" for pattern, count in sorted(item["direction_patterns"].items(), key=lambda entry: (-entry[1], entry[0]))
            )
            summaries.append(
                {
                    "id": f"{item['intervention_canonical']}::{item['outcome_canonical']}",
                    "severity": item["highest_severity"],
                    "intervention_canonical": item["intervention_canonical"],
                    "outcome_canonical": item["outcome_canonical"],
                    "pair_count": item["pair_count"],
                    "contradiction_ids": sorted(item["contradiction_ids"]),
                    "population_overlap": "partial" if len(item["population_overlaps"]) > 1 else next(iter(item["population_overlaps"]), "different"),
                    "direction_patterns": item["direction_patterns"],
                    "summary": (
                        f"{item['highest_severity']} contradiction topic for {item['intervention_canonical']} and {item['outcome_canonical']} "
                        f"across {item['pair_count']} confirmed pair(s), with direction patterns {direction_summary}."
                    ),
                    "claim_a": self._claim_payload(claim_a) if claim_a else None,
                    "claim_b": self._claim_payload(claim_b) if claim_b else None,
                    "severity_breakdown": item["severity_breakdown"],
                }
            )
        return summaries

    async def _load_refinements(self, mission_id: str, claim_ids: Sequence[UUID]) -> List[Dict[str, Any]]:
        if not claim_ids:
            return []
        rows = (
            await self.db.execute(
                select(ClaimGraphEdge).where(
                    ClaimGraphEdge.mission_id == mission_id,
                    ClaimGraphEdge.edge_type.in_([GraphEdgeType.REFINES, GraphEdgeType.IS_SUBGROUP_OF]),
                    or_(ClaimGraphEdge.claim_a_id.in_(claim_ids), ClaimGraphEdge.claim_b_id.in_(claim_ids)),
                )
            )
        ).scalars().all()

        refinements: List[Dict[str, Any]] = []
        for edge in rows[:10]:
            claim_a = await self.db.get(ResearchClaim, edge.claim_a_id)
            claim_b = await self.db.get(ResearchClaim, edge.claim_b_id)
            if not claim_a or not claim_b:
                continue
            refinements.append(
                {
                    "edge_type": edge.edge_type.value,
                    "claim_a_id": str(claim_a.id),
                    "claim_b_id": str(claim_b.id),
                    "summary": edge.justification or f"{edge.edge_type.value} relationship between subgroup or refined claims.",
                    "claim_a": self._claim_payload(claim_a),
                    "claim_b": self._claim_payload(claim_b),
                }
            )
        return refinements

    def _confidence_tier(
        self,
        confidence: float,
        dominant_direction: str,
        drift_trend: Optional[str],
        contradictions: Sequence[Dict[str, Any]],
    ) -> str:
        high_contradictions = sum(1 for item in contradictions if item["severity"] == "HIGH")
        if confidence < 0.30 or drift_trend == DriftTrendEnum.REVERSING.value:
            return "WEAK"
        if confidence < 0.50 or dominant_direction == "mixed" or high_contradictions >= 2:
            return "MIXED"
        if confidence < 0.75 or high_contradictions >= 1:
            return "MODERATE"
        return "STRONG"

    def _claim_payload(self, claim: Optional[ResearchClaim]) -> Optional[Dict[str, Any]]:
        if not claim:
            return None
        return {
            "id": str(claim.id),
            "statement": _claim_statement(claim),
            "study_type": claim.study_design or "unknown",
            "direction": claim_direction_value(claim),
            "confidence": round(float(claim.composite_confidence or 0.0), 4),
            "study_design_score": round(float(claim.study_design_score or 0.0), 4),
            "population": claim.population,
            "mission_relevance": _enum_value(claim.mission_relevance, "secondary"),
            "evidence_score": self._evidence_score(claim),
        }

    async def _generate_synthesis_text(
        self,
        evidence_package: Dict[str, Any],
        prior: Optional[SynthesisHistory],
        trigger: SynthesisTrigger,
    ) -> Dict[str, Any]:
        paragraphs_needed = 5 if trigger == SynthesisTrigger.BELIEF_REVERSED else 4
        prior_text = prior.full_text if prior else None
        payload = {
            "research_question": evidence_package["mission_question"],
            "confidence_tier": evidence_package["confidence_tier"],
            "dominant_evidence_direction": evidence_package["dominant_direction"],
            "trigger_type": trigger.value,
            "tier_1_claims": evidence_package["tier1"],
            "tier_2_claims": evidence_package["tier2"],
            "tier_3_claims": evidence_package["tier3"],
            "high_severity_contradictions": [item for item in evidence_package["contradictions"] if item["severity"] == "HIGH"],
            "medium_severity_contradictions": [item for item in evidence_package["contradictions"] if item["severity"] == "MEDIUM"],
            "low_severity_contradictions": [item for item in evidence_package["contradictions"] if item["severity"] == "LOW"],
            "subgroup_and_refinement_claims": evidence_package["subgroups_and_refinements"],
            "prior_synthesis_summary": prior_text,
            "current_confidence": evidence_package["current_confidence"],
            "drift_trend": evidence_package["drift_trend"],
        }

        llm_call_id: Optional[UUID] = None
        for attempt in range(2):
            prompt_text = self._build_llm_prompt(payload, paragraphs_needed, attempt)
            response_text = ""
            try:
                response = await self.llm_provider.generate_async(
                    [
                        {
                            "role": "system",
                            "content": (
                                "You write concise scientific evidence syntheses for researchers. "
                                "Write only from the evidence package. No headers, no bullet lists, no citations."
                            ),
                        },
                        {"role": "user", "content": prompt_text},
                    ],
                    temperature=0.15,
                    max_tokens=600,
                )
                response_text = (response or {}).get("content", "").strip()
            except Exception as exc:
                logger.warning("Synthesis generation failed on attempt %s: %s", attempt + 1, exc)

            validation = self._validate_synthesis_text(
                response_text,
                evidence_package["confidence_tier"],
                evidence_package["contradictions"],
                paragraphs_needed,
            )
            call = SynthesisLLMCall(
                mission_id=evidence_package["mission_id"],
                prompt_text=prompt_text,
                response_text=response_text,
                validation_status="passed" if validation["valid"] else "failed",
            )
            self.db.add(call)
            await self.db.flush()
            llm_call_id = call.id

            if validation["valid"]:
                return {
                    "text": response_text,
                    "validation_passed": True,
                    "llm_fallback": False,
                    "word_count": validation["word_count"],
                    "llm_call_id": llm_call_id,
                    "contradiction_ids": sorted(
                        {
                            contradiction_id
                            for item in evidence_package["contradictions"]
                            if item["severity"] in {"HIGH", "MEDIUM"}
                            for contradiction_id in item.get("contradiction_ids", [])
                        }
                    ),
                }

        fallback_text = self._template_synthesis(evidence_package)
        return {
            "text": fallback_text,
            "validation_passed": False,
            "llm_fallback": True,
            "word_count": _word_count(fallback_text),
            "llm_call_id": llm_call_id,
            "contradiction_ids": sorted(
                {
                    contradiction_id
                    for item in evidence_package["contradictions"]
                    if item["severity"] in {"HIGH", "MEDIUM"}
                    for contradiction_id in item.get("contradiction_ids", [])
                }
            ),
        }

    def _build_llm_prompt(self, payload: Dict[str, Any], paragraphs_needed: int, attempt: int) -> str:
        stricter = (
            "Return exactly one plain-text synthesis with paragraph breaks only. "
            "Do not use bullets, numbers, headings, citations, or author names.\n"
            if attempt == 1
            else ""
        )
        return (
            "Write a scientific evidence synthesis for a research monitoring system.\n"
            "A synthesis is not a paper summary. It is a summary of what the evidence collectively supports, "
            "where it conflicts, and how confident the system is.\n"
            f"{stricter}"
            f"Use the confidence tier literally: {payload['confidence_tier']}.\n"
            f"Write {paragraphs_needed} connected prose paragraphs.\n"
            "Paragraph 1: main conclusion.\n"
            "Paragraph 2: evidence basis anchored on Tier 1 claims, using study types and findings rather than citations.\n"
            "Paragraph 3: contradictions and qualifications. HIGH contradictions must be explicitly included.\n"
            "Paragraph 4: confidence and limitations.\n"
            "If trigger_type is belief_reversed, paragraph 5 must explain what changed.\n\n"
            f"{json.dumps(payload, default=str)}"
        )

    def _validate_synthesis_text(
        self,
        text: str,
        confidence_tier: str,
        contradictions: Sequence[Dict[str, Any]],
        paragraphs_needed: int,
    ) -> Dict[str, Any]:
        word_count = _word_count(text)
        paragraphs = [chunk.strip() for chunk in re.split(r"\n\s*\n", text or "") if chunk.strip()]
        if not text or word_count < 80 or word_count > 400:
            return {"valid": False, "reason": "word_count", "word_count": word_count}
        if len(paragraphs) < paragraphs_needed:
            return {"valid": False, "reason": "paragraph_count", "word_count": word_count}
        if re.search(r"\bet al\.\b|\(\d{4}\)", text):
            return {"valid": False, "reason": "citation_style", "word_count": word_count}
        lowered = text.lower()
        for banned in CONFIDENCE_LANGUAGE_BANS.get(confidence_tier, []):
            if banned in lowered:
                return {"valid": False, "reason": "confidence_tier_mismatch", "word_count": word_count}
        high_contradictions = [item for item in contradictions if item["severity"] == "HIGH"]
        if high_contradictions and not any(token in lowered for token in ["however", "though", "conflict", "contradict", "uncertain", "mixed"]):
            return {"valid": False, "reason": "missing_contradiction_language", "word_count": word_count}
        required_topic_terms = {
            str(term).lower()
            for item in high_contradictions[:3]
            for term in (item.get("intervention_canonical"), item.get("outcome_canonical"))
            if term and len(str(term).strip()) >= 4
        }
        if required_topic_terms and not any(term in lowered for term in required_topic_terms):
            return {"valid": False, "reason": "missing_high_contradiction_reference", "word_count": word_count}
        return {"valid": True, "word_count": word_count}

    def _template_synthesis(self, evidence_package: Dict[str, Any]) -> str:
        claim_count = len(evidence_package["claim_ids_used"])
        paper_count = evidence_package["paper_count"]
        direction = evidence_package["dominant_direction"]
        confidence_pct = round(evidence_package["current_confidence"] * 100)
        contradictions = [item for item in evidence_package["contradictions"] if item["severity"] == "HIGH"]
        limitation = self._primary_limitation(evidence_package)
        confidence_lead = {
            "STRONG": "strongly supports the current conclusion",
            "MODERATE": "generally supports the current conclusion",
            "MIXED": "is currently mixed and does not support a single clean conclusion",
            "WEAK": "is insufficient to support a firm conclusion",
        }[evidence_package["confidence_tier"]]
        contradiction_note = (
            f" Note: {len(contradictions)} high-severity contradiction topic(s) remain unresolved in the evidence base."
            if contradictions
            else ""
        )
        return (
            f"Based on {claim_count} claims from {paper_count} papers, the current evidence {confidence_lead} "
            f"for the research question: {evidence_package['mission_question']}. "
            f"The dominant evidence direction is {direction}, and the current confidence score is {confidence_pct}%.{contradiction_note}\n\n"
            f"The highest-weighted evidence cluster centers on {evidence_package['primary_pair']['intervention']} and "
            f"{evidence_package['primary_pair']['outcome']}, with Tier 1 findings carrying the most influence on the current synthesis. "
            f"Supporting and peripheral claims were considered but weighted less heavily according to study design, recency, and mission relevance.\n\n"
            f"Uncertainty remains because {limitation}. "
            f"Subgroup and refinement evidence was retained as qualification context rather than treated as a separate conclusion.\n\n"
            "This synthesis was generated from structured evidence directly because the narrative generation path did not pass validation."
        )

    def _primary_limitation(self, evidence_package: Dict[str, Any]) -> str:
        high_contradictions = [item for item in evidence_package["contradictions"] if item["severity"] == "HIGH"]
        if high_contradictions:
            return "high-severity contradictions remain unresolved"
        if evidence_package["tier3"]:
            return "a meaningful portion of the available evidence is weak or peripheral"
        if not evidence_package["subgroups_and_refinements"]:
            return "subgroup-specific qualification evidence is still limited"
        return "the current evidence base still has study-design and generalizability limits"

    def _detect_change(
        self,
        prior: Optional[SynthesisHistory],
        evidence_package: Dict[str, Any],
        current_contradiction_ids: Sequence[str],
    ) -> Dict[str, Any]:
        current_confidence = evidence_package["current_confidence"]
        current_direction = evidence_package["dominant_direction"]
        if not prior:
            return {
                "confidence_delta": current_confidence,
                "direction_changed": False,
                "new_contradictions_surfaced": len(current_contradiction_ids),
                "contradictions_resolved": 0,
                "change_magnitude": "MINOR",
            }

        prior_confidence = float(prior.confidence_at_time or 0.0)
        prior_direction = prior.dominant_direction or "mixed"
        prior_contradictions = set((prior.contradictions_included or prior.contradictions_acknowledged or []))
        current_contradictions = set(current_contradiction_ids)
        confidence_delta = round(current_confidence - prior_confidence, 4)
        direction_changed = prior_direction != current_direction
        new_contradictions = len(current_contradictions - prior_contradictions)
        resolved_contradictions = len(prior_contradictions - current_contradictions)
        if direction_changed or abs(confidence_delta) > 0.20:
            magnitude = "MAJOR"
        elif abs(confidence_delta) >= 0.10 or new_contradictions > 1:
            magnitude = "MODERATE"
        else:
            magnitude = "MINOR"
        return {
            "confidence_delta": confidence_delta,
            "direction_changed": direction_changed,
            "new_contradictions_surfaced": new_contradictions,
            "contradictions_resolved": resolved_contradictions,
            "change_magnitude": magnitude,
        }

    async def _sync_compatibility_answer(
        self,
        mission_id: str,
        record: SynthesisHistory,
        evidence_package: Dict[str, Any],
    ) -> None:
        answer = (
            await self.db.execute(select(SynthesisAnswer).where(SynthesisAnswer.mission_id == mission_id))
        ).scalar_one_or_none()
        if not answer:
            answer = SynthesisAnswer(mission_id=mission_id)
            self.db.add(answer)

        tier_claims = evidence_package["tier1"] + evidence_package["tier2"] + evidence_package["tier3"]
        answer.answer_text = record.full_text
        answer.answer_confidence = record.confidence_at_time
        answer.key_findings = [item["statement"] for item in evidence_package["tier1"][:3]]
        answer.uncertainty_statement = self._primary_limitation(evidence_package)
        answer.limitations = [self._primary_limitation(evidence_package)]
        answer.knowledge_gaps = [item["summary"] for item in evidence_package["subgroups_and_refinements"][:3]]
        answer.supporting_claims_count = sum(1 for item in tier_claims if item["direction"] == "positive")
        answer.contradicting_claims_count = sum(1 for item in tier_claims if item["direction"] == "negative")
        answer.neutral_claims_count = sum(1 for item in tier_claims if item["direction"] in {"null", "unclear"})
        answer.confidence_at_creation = record.confidence_at_time
        answer.confidence_current = record.confidence_at_time
        answer.generated_by = "template_fallback" if record.llm_fallback else "llm"
        answer.generation_cycle = evidence_package["cycle_number"]
        answer.last_reviewed_at = datetime.utcnow()

    async def _latest_history(self, mission_id: str) -> Optional[SynthesisHistory]:
        return (
            await self.db.execute(
                select(SynthesisHistory)
                .where(SynthesisHistory.mission_id == mission_id)
                .order_by(SynthesisHistory.version_number.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    def _history_response(self, row: SynthesisHistory) -> Dict[str, Any]:
        evidence_package = row.evidence_package or {}
        contradictions = row.contradictions_included or row.contradictions_acknowledged or []
        contradiction_details = evidence_package.get("contradictions") or []
        return {
            "id": str(row.id),
            "mission_id": row.mission_id,
            "version_number": row.version_number,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "trigger_type": row.trigger.value if row.trigger else None,
            "synthesis_text": row.full_text,
            "confidence_tier": row.confidence_tier,
            "confidence_score": float(row.confidence_at_time or 0.0),
            "dominant_direction": row.dominant_direction,
            "claim_ids_tier1": row.claim_ids_tier1 or [],
            "claim_ids_tier2": row.claim_ids_tier2 or [],
            "claim_ids_tier3": row.claim_ids_tier3 or [],
            "contradictions_included": contradictions,
            "change_magnitude": row.change_magnitude,
            "confidence_delta": float(row.confidence_delta or 0.0),
            "direction_changed": bool(row.direction_changed),
            "prior_synthesis_id": str(row.prior_synthesis_id) if row.prior_synthesis_id else None,
            "validation_passed": bool(row.validation_passed),
            "word_count": int(row.word_count or 0),
            "llm_fallback": bool(row.llm_fallback),
            "change_summary": {
                "confidence_delta": float(row.confidence_delta or 0.0),
                "direction_changed": bool(row.direction_changed),
                "new_contradictions_surfaced": len(contradictions),
                "contradictions_resolved": 0,
            },
            "summary_metrics": {
                "tier1_count": len(row.claim_ids_tier1 or []),
                "tier2_count": len(row.claim_ids_tier2 or []),
                "tier3_count": len(row.claim_ids_tier3 or []),
                "high_contradictions": sum(1 for item in contradiction_details if item.get("severity") == "HIGH"),
                "medium_contradictions": sum(1 for item in contradiction_details if item.get("severity") == "MEDIUM"),
                "high_contradiction_pairs": sum(len(item.get("contradiction_ids") or []) for item in contradiction_details if item.get("severity") == "HIGH"),
                "medium_contradiction_pairs": sum(len(item.get("contradiction_ids") or []) for item in contradiction_details if item.get("severity") == "MEDIUM"),
            },
        }

    def _timeline_description(
        self,
        record: SynthesisHistory,
        evidence_package: Dict[str, Any],
        change: Dict[str, Any],
    ) -> str:
        return (
            f"Synthesis v{record.version_number} generated with {record.confidence_tier} confidence "
            f"and {record.change_magnitude} change magnitude. "
            f"Primary cluster: {evidence_package['primary_pair']['intervention']} -> {evidence_package['primary_pair']['outcome']}."
        )

    def _major_change_description(self, change: Dict[str, Any], evidence_package: Dict[str, Any]) -> str:
        if change["direction_changed"]:
            return f"Dominant evidence direction changed to {evidence_package['dominant_direction']}."
        return f"Confidence shifted by {change['confidence_delta']:+.2f}."
