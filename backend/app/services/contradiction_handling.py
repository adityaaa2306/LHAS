from __future__ import annotations

import json
import logging
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Alert, AlertSeverity, Mission, ResearchClaim
from app.models.belief_revision import ContradictionSeverityEnum
from app.models.contradiction import (
    AmbiguousContradictionRecord,
    ContextResolutionResultEnum,
    ContextResolvedPairRecord,
    ContradictionRecord,
    ContradictionVerificationCall,
    PopulationOverlapEnum,
    SemanticVerificationResultEnum,
    VerificationStageEnum,
)
from app.models.memory import ClaimGraphEdge, GraphEdgeType, MemoryEventType
from app.services.claim_curation import claim_direction_value
from app.services.embeddings import get_embedding_service
from app.services.llm import get_llm_provider
from app.services.memory_system import MemorySystemService, _claim_statement, _confidence_product, _edge_weight

logger = logging.getLogger(__name__)


@dataclass
class CandidatePair:
    new_claim: ResearchClaim
    existing_claim: ResearchClaim
    source: str
    similarity: Optional[float] = None


def _normalized_text(value: Any) -> str:
    return " ".join(str(value or "").lower().split())


def _pair_key(claim_a_id: UUID | str, claim_b_id: UUID | str) -> str:
    left, right = sorted([str(claim_a_id), str(claim_b_id)])
    return f"{left}::{right}"


def _topic_key(intervention: Any, outcome: Any) -> str:
    left = _normalized_text(intervention) or "unknown intervention"
    right = _normalized_text(outcome) or "unknown outcome"
    return f"{left}::{right}"


def _study_score(claim: ResearchClaim) -> float:
    try:
        return float(claim.study_design_score or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _coerce_uuid(value: Any) -> Optional[UUID]:
    if not value:
        return None
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


def _token_set(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", _normalized_text(value)) if len(token) > 2}


def _directions_opposed(left: str, right: str) -> bool:
    return (left, right) in {
        ("positive", "negative"),
        ("negative", "positive"),
        ("positive", "null"),
        ("null", "positive"),
        ("negative", "null"),
        ("null", "negative"),
    }


class ContradictionHandlingService:
    def __init__(
        self,
        db: AsyncSession,
        llm_provider: Any = None,
        embedding_service: Any = None,
    ) -> None:
        self.db = db
        self.llm_provider = llm_provider or get_llm_provider()
        self.embedding_service = embedding_service or get_embedding_service()
        self.memory_system = MemorySystemService(
            db=db,
            llm_provider=self.llm_provider,
            embedding_service=self.embedding_service,
        )

    async def run_cycle(
        self,
        mission_id: str,
        new_claim_ids: Optional[Sequence[str]] = None,
        actor: str = "contradiction_handling",
        evaluate_all: bool = False,
    ) -> Dict[str, Any]:
        mission = await self.db.get(Mission, mission_id)
        if not mission:
            raise ValueError(f"Mission not found: {mission_id}")

        claims = await self._load_target_claims(mission_id, new_claim_ids, evaluate_all)
        if not claims:
            return {
                "success": True,
                "mission_id": mission_id,
                "claims_evaluated": 0,
                "confirmed_contradictions": 0,
                "context_resolved": 0,
                "ambiguous": 0,
                "no_candidates": 0,
            }

        summary = {
            "success": True,
            "mission_id": mission_id,
            "claims_evaluated": len(claims),
            "confirmed_contradictions": 0,
            "context_resolved": 0,
            "ambiguous": 0,
            "no_candidates": 0,
            "instability_signal": False,
            "confirmed_ids": [],
        }

        for claim in claims:
            pairs = await self._retrieve_candidate_pairs(mission, claim, actor)
            if not pairs:
                summary["no_candidates"] += 1
                await self.memory_system.log_event(
                    event_type=MemoryEventType.CONTRADICTION_NO_CANDIDATES,
                    mission_id=mission_id,
                    actor=actor,
                    claim_id=claim.id,
                    previous_value=None,
                    new_value={"claim_id": str(claim.id)},
                )
                continue

            for pair in pairs:
                if not await self._passes_direction_check(mission_id, pair, actor):
                    continue
                context_result = await self._contextual_reconciliation(mission, pair, actor)
                if context_result["resolved"]:
                    summary["context_resolved"] += 1
                    continue
                semantic_result = await self._semantic_verification(mission_id, pair, actor)
                if semantic_result["result"] == SemanticVerificationResultEnum.COMPATIBLE:
                    continue
                if semantic_result["result"] == SemanticVerificationResultEnum.AMBIGUOUS:
                    await self._write_ambiguous_record(
                        mission_id,
                        pair,
                        semantic_result.get("call_id"),
                        semantic_result.get("reason") or "semantic_verification_ambiguous",
                        actor,
                    )
                    summary["ambiguous"] += 1
                    continue
                record = await self._write_confirmed_contradiction(mission, pair, semantic_result.get("call_id"), actor)
                if record:
                    summary["confirmed_contradictions"] += 1
                    summary["confirmed_ids"].append(str(record.id))

        if summary["confirmed_contradictions"] >= 3:
            summary["instability_signal"] = True
            await self.memory_system.log_event(
                event_type=MemoryEventType.CONTRADICTION_INSTABILITY_SIGNAL,
                mission_id=mission_id,
                actor=actor,
                previous_value=None,
                new_value={"confirmed_count": summary["confirmed_contradictions"]},
            )
        return summary

    async def get_overview(self, mission_id: str) -> Dict[str, Any]:
        confirmed_rows = (
            await self.db.execute(
                select(ContradictionRecord).where(ContradictionRecord.mission_id == mission_id)
            )
        ).scalars().all()
        confirmed = len(confirmed_rows)
        resolved = (await self.db.execute(select(func.count(ContextResolvedPairRecord.id)).where(ContextResolvedPairRecord.mission_id == mission_id))).scalar_one()
        ambiguous = (await self.db.execute(select(func.count(AmbiguousContradictionRecord.id)).where(AmbiguousContradictionRecord.mission_id == mission_id))).scalar_one()
        high = (
            await self.db.execute(
                select(func.count(ContradictionRecord.id)).where(
                    ContradictionRecord.mission_id == mission_id,
                    ContradictionRecord.severity == ContradictionSeverityEnum.HIGH,
                )
            )
        ).scalar_one()
        mission = await self.db.get(Mission, mission_id)
        return {
            "mission_id": mission_id,
            "confirmed_count": int(confirmed or 0),
            "topic_count": len(self._group_confirmed_rows(confirmed_rows)),
            "context_resolved_count": int(resolved or 0),
            "ambiguous_count": int(ambiguous or 0),
            "high_severity_count": int(high or 0),
            "asymmetry_threshold": float(getattr(mission, "contradiction_asymmetry_threshold", 0.35) or 0.35),
        }

    async def get_confirmed(self, mission_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        records = (
            await self.db.execute(
                select(ContradictionRecord)
                .where(ContradictionRecord.mission_id == mission_id)
                .order_by(ContradictionRecord.timestamp.desc())
                .limit(limit)
            )
        ).scalars().all()
        return [await self._confirmed_record_response(record) for record in records]

    def _group_confirmed_rows(self, rows: Sequence[ContradictionRecord]) -> List[Dict[str, Any]]:
        severity_rank = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}
        groups: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            key = _topic_key(row.intervention_canonical, row.outcome_canonical)
            severity = row.severity.value if row.severity else "LOW"
            if key not in groups:
                groups[key] = {
                    "topic_key": key,
                    "intervention_canonical": row.intervention_canonical,
                    "outcome_canonical": row.outcome_canonical,
                    "pair_count": 0,
                    "claim_ids": set(),
                    "highest_severity": severity,
                    "severity_breakdown": Counter(),
                }
            group = groups[key]
            group["pair_count"] += 1
            group["claim_ids"].add(str(row.claim_a_id))
            group["claim_ids"].add(str(row.claim_b_id))
            group["severity_breakdown"][severity] += 1
            if severity_rank[severity] > severity_rank[group["highest_severity"]]:
                group["highest_severity"] = severity

        ordered = sorted(
            groups.values(),
            key=lambda item: (
                -severity_rank[item["highest_severity"]],
                -item["pair_count"],
                item["topic_key"],
            ),
        )
        for item in ordered:
            item["claim_count"] = len(item["claim_ids"])
            item["claim_ids"] = sorted(item["claim_ids"])
            item["severity_breakdown"] = dict(item["severity_breakdown"])
        return ordered

    async def get_context_resolved(self, mission_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        rows = (
            await self.db.execute(
                select(ContextResolvedPairRecord)
                .where(ContextResolvedPairRecord.mission_id == mission_id)
                .order_by(ContextResolvedPairRecord.timestamp.desc())
                .limit(limit)
            )
        ).scalars().all()
        return [self._context_resolved_response(row) for row in rows]

    async def get_ambiguous(self, mission_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        rows = (
            await self.db.execute(
                select(AmbiguousContradictionRecord)
                .where(AmbiguousContradictionRecord.mission_id == mission_id)
                .order_by(AmbiguousContradictionRecord.timestamp.desc())
                .limit(limit)
            )
        ).scalars().all()
        return [self._ambiguous_response(row) for row in rows]

    async def _load_target_claims(
        self,
        mission_id: str,
        new_claim_ids: Optional[Sequence[str]],
        evaluate_all: bool,
    ) -> List[ResearchClaim]:
        if not evaluate_all and not new_claim_ids:
            return []
        query = select(ResearchClaim).where(ResearchClaim.mission_id == mission_id)
        if new_claim_ids and not evaluate_all:
            query = query.where(ResearchClaim.id.in_([_coerce_uuid(item) for item in new_claim_ids if item]))
        rows = (await self.db.execute(query.order_by(ResearchClaim.extraction_timestamp.asc()))).scalars().all()
        return rows

    async def _retrieve_candidate_pairs(self, mission: Mission, claim: ResearchClaim, actor: str) -> List[CandidatePair]:
        pairs: Dict[str, CandidatePair] = {}
        for candidate in await self._exact_entity_matches(claim):
            pairs[_pair_key(claim.id, candidate.id)] = CandidatePair(claim, candidate, "exact")

        if len(pairs) < 2:
            for candidate, similarity in await self._embedding_matches(claim, limit=5):
                key = _pair_key(claim.id, candidate.id)
                if key not in pairs:
                    pairs[key] = CandidatePair(claim, candidate, "embedding", similarity)

        filtered: List[CandidatePair] = []
        for pair in pairs.values():
            if not await self._is_known_contradiction(mission.id, pair.new_claim.id, pair.existing_claim.id):
                filtered.append(pair)

        if len(filtered) > 20:
            filtered.sort(key=lambda item: _confidence_product(item.new_claim, item.existing_claim), reverse=True)
            await self.memory_system.log_event(
                event_type=MemoryEventType.CONTRADICTION_CANDIDATE_CAPPED,
                mission_id=mission.id,
                actor=actor,
                claim_id=claim.id,
                previous_value=None,
                new_value={"candidate_count": len(filtered), "cap": 20},
            )
            filtered = filtered[:20]
        return filtered

    async def _exact_entity_matches(self, claim: ResearchClaim) -> List[ResearchClaim]:
        if not claim.intervention_canonical or not claim.outcome_canonical:
            return []
        rows = (
            await self.db.execute(
                select(ResearchClaim).where(
                    ResearchClaim.mission_id == claim.mission_id,
                    ResearchClaim.intervention_canonical == claim.intervention_canonical,
                    ResearchClaim.outcome_canonical == claim.outcome_canonical,
                    ResearchClaim.id != claim.id,
                )
            )
        ).scalars().all()
        return rows

    async def _embedding_matches(self, claim: ResearchClaim, limit: int = 5) -> List[Tuple[ResearchClaim, float]]:
        if not self.embedding_service:
            return []
        query_embedding = await self.embedding_service.embed_text(_claim_statement(claim), input_type="query")
        if not query_embedding:
            return []

        candidates = (
            await self.db.execute(
                select(ResearchClaim).where(
                    ResearchClaim.mission_id == claim.mission_id,
                    ResearchClaim.id != claim.id,
                    or_(
                        ResearchClaim.intervention_canonical.isnot(None),
                        ResearchClaim.outcome_canonical.isnot(None),
                    ),
                )
            )
        ).scalars().all()
        if not candidates:
            return []

        embeddings = await self.embedding_service.embed_batch([_claim_statement(item) for item in candidates], input_type="passage")
        scored: List[Tuple[ResearchClaim, float]] = []
        for candidate, embedding in zip(candidates, embeddings):
            if embedding is None:
                continue
            similarity = self.embedding_service.cosine_similarity(query_embedding, embedding)
            if similarity >= 0.82:
                scored.append((candidate, round(float(similarity), 4)))
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:limit]

    async def _is_known_contradiction(self, mission_id: str, claim_a_id: UUID, claim_b_id: UUID) -> bool:
        existing_record = (
            await self.db.execute(
                select(ContradictionRecord.id).where(
                    ContradictionRecord.mission_id == mission_id,
                    or_(
                        and_(ContradictionRecord.claim_a_id == claim_a_id, ContradictionRecord.claim_b_id == claim_b_id),
                        and_(ContradictionRecord.claim_a_id == claim_b_id, ContradictionRecord.claim_b_id == claim_a_id),
                    ),
                )
            )
        ).first()
        if existing_record:
            return True
        existing_edge = (
            await self.db.execute(
                select(ClaimGraphEdge).where(
                    ClaimGraphEdge.mission_id == mission_id,
                    ClaimGraphEdge.edge_type == GraphEdgeType.CONTRADICTS,
                    or_(
                        and_(ClaimGraphEdge.claim_a_id == claim_a_id, ClaimGraphEdge.claim_b_id == claim_b_id),
                        and_(ClaimGraphEdge.claim_a_id == claim_b_id, ClaimGraphEdge.claim_b_id == claim_a_id),
                    ),
                )
            )
        ).scalar_one_or_none()
        if not existing_edge:
            return False
        justification = (existing_edge.justification or "").lower()
        return "confirmed contradiction" in justification

    async def _passes_direction_check(self, mission_id: str, pair: CandidatePair, actor: str) -> bool:
        left = claim_direction_value(pair.new_claim)
        right = claim_direction_value(pair.existing_claim)
        if _directions_opposed(left, right):
            return True
        await self.memory_system.log_event(
            event_type=MemoryEventType.CONTRADICTION_DIRECTION_COMPATIBLE,
            mission_id=mission_id,
            actor=actor,
            claim_id=pair.new_claim.id,
            previous_value=None,
            new_value={
                "other_claim_id": str(pair.existing_claim.id),
                "direction_a": left,
                "direction_b": right,
            },
        )
        return False

    def _population_markers(self, value: str) -> Dict[str, set[str]]:
        tokens = _token_set(value)
        marker_table = {
            "adult": {"adult", "adults"},
            "pediatric": {"child", "children", "pediatric", "paediatric", "adolescent", "adolescents"},
            "elderly": {"elderly", "older", "aged", "geriatric"},
            "female": {"female", "women", "woman", "pregnant", "pregnancy", "breastfeeding"},
            "male": {"male", "men", "man"},
            "severe": {"severe", "advanced", "morbid"},
            "mild": {"mild", "moderate", "early"},
        }
        return {name: tokens.intersection(words) for name, words in marker_table.items()}

    def _condition_signature(self, claim: ResearchClaim) -> Dict[str, set[str]]:
        text = " ".join(filter(None, [claim.statement_raw or "", claim.statement_normalized or "", json.dumps(claim.provenance or {})])).lower()
        return {
            "dosage": set(re.findall(r"\b\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml)\b", text)),
            "duration": set(re.findall(r"\b\d+\s*(?:day|days|week|weeks|month|months|year|years)\b", text)),
            "schedule": {word for word in {"daily", "weekly", "monthly", "oral", "subcutaneous"} if word in text},
            "co_interventions": {word for word in {"diet", "exercise", "lifestyle", "surgery", "placebo", "metformin", "empagliflozin"} if word in text},
        }

    async def _contextual_reconciliation(self, mission: Mission, pair: CandidatePair, actor: str) -> Dict[str, Any]:
        population_check = await self._check_population_difference(mission.id, pair)
        if population_check["resolved"]:
            await self._write_context_resolved_record(
                mission,
                pair,
                ContextResolutionResultEnum.POPULATION_DIFFERENCE,
                None,
                population_check.get("call_id"),
                population_check.get("notes"),
                actor,
            )
            return {"resolved": True, "reason": ContextResolutionResultEnum.POPULATION_DIFFERENCE.value}

        condition_check = await self._check_condition_difference(mission.id, pair)
        if condition_check["resolved"]:
            await self._write_context_resolved_record(
                mission,
                pair,
                ContextResolutionResultEnum.CONDITION_DIFFERENCE,
                None,
                condition_check.get("call_id"),
                condition_check.get("notes"),
                actor,
            )
            return {"resolved": True, "reason": ContextResolutionResultEnum.CONDITION_DIFFERENCE.value}

        threshold = float(getattr(mission, "contradiction_asymmetry_threshold", 0.35) or 0.35)
        score_delta = abs(_study_score(pair.new_claim) - _study_score(pair.existing_claim))
        if score_delta >= threshold:
            stronger = pair.new_claim if _study_score(pair.new_claim) >= _study_score(pair.existing_claim) else pair.existing_claim
            await self._write_context_resolved_record(
                mission,
                pair,
                ContextResolutionResultEnum.STUDY_DESIGN_ASYMMETRY,
                stronger.id,
                None,
                f"Study design score delta {score_delta:.2f} exceeded threshold {threshold:.2f}.",
                actor,
            )
            return {"resolved": True, "reason": ContextResolutionResultEnum.STUDY_DESIGN_ASYMMETRY.value}

        return {"resolved": False, "reason": ContextResolutionResultEnum.NONE_RESOLVED.value}

    async def _check_population_difference(self, mission_id: str, pair: CandidatePair) -> Dict[str, Any]:
        left = _normalized_text(pair.new_claim.population)
        right = _normalized_text(pair.existing_claim.population)
        if left and right and left == right:
            return {"resolved": False}

        left_markers = self._population_markers(left)
        right_markers = self._population_markers(right)
        exclusive_pairs = [("adult", "pediatric"), ("male", "female"), ("elderly", "pediatric"), ("severe", "mild")]
        for first, second in exclusive_pairs:
            if left_markers[first] and right_markers[second]:
                return {"resolved": True, "notes": f"Population differs: {first} vs {second}."}
            if left_markers[second] and right_markers[first]:
                return {"resolved": True, "notes": f"Population differs: {second} vs {first}."}

        if not left or not right:
            return {"resolved": False}

        llm_result = await self._binary_llm_check(
            mission_id=mission_id,
            stage=VerificationStageEnum.POPULATION_COMPARE,
            pair=pair,
            instruction="Return yes if the populations are meaningfully different, no if not, or unclear if insufficient information.",
            prompt_payload={"population_a": left, "population_b": right},
        )
        return {
            "resolved": llm_result["result"] == "yes",
            "call_id": llm_result.get("call_id"),
            "notes": "LLM confirmed meaningful population difference." if llm_result["result"] == "yes" else None,
        }

    async def _check_condition_difference(self, mission_id: str, pair: CandidatePair) -> Dict[str, Any]:
        left = self._condition_signature(pair.new_claim)
        right = self._condition_signature(pair.existing_claim)
        for key in left:
            if left[key] and right[key] and left[key] != right[key] and left[key].isdisjoint(right[key]):
                return {"resolved": True, "notes": f"Condition differs on {key}: {sorted(left[key])} vs {sorted(right[key])}."}

        if not any(left.values()) or not any(right.values()):
            return {"resolved": False}

        llm_result = await self._binary_llm_check(
            mission_id=mission_id,
            stage=VerificationStageEnum.CONDITION_COMPARE,
            pair=pair,
            instruction="Return yes if the claims were measured under clearly different conditions, no if not, or unclear if insufficient information.",
            prompt_payload={
                "claim_a": _claim_statement(pair.new_claim),
                "claim_b": _claim_statement(pair.existing_claim),
                "condition_signature_a": {key: sorted(value) for key, value in left.items()},
                "condition_signature_b": {key: sorted(value) for key, value in right.items()},
            },
        )
        return {
            "resolved": llm_result["result"] == "yes",
            "call_id": llm_result.get("call_id"),
            "notes": "LLM confirmed condition difference." if llm_result["result"] == "yes" else None,
        }

    async def _binary_llm_check(
        self,
        mission_id: str,
        stage: VerificationStageEnum,
        pair: CandidatePair,
        instruction: str,
        prompt_payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        allowed = {"yes", "no", "unclear"}
        prompt_text = f"{instruction}\n{json.dumps(prompt_payload)}"
        response_text = ""
        validated = "unclear"
        try:
            response = await self.llm_provider.generate_async(
                [
                    {"role": "system", "content": "Return one token only."},
                    {"role": "user", "content": prompt_text},
                ],
                temperature=0.0,
                max_tokens=10,
            )
            response_text = (response or {}).get("content", "").strip().lower()
            token = response_text.split()[0].strip(".,;:") if response_text else ""
            if token in allowed:
                validated = token
        except Exception as exc:
            logger.warning("Contradiction helper LLM failed for %s: %s", stage.value, exc)
            response_text = str(exc)

        call = await self._store_verification_call(
            mission_id,
            pair,
            stage,
            prompt_text,
            response_text,
            validated,
            "1",
        )
        return {"result": validated, "call_id": call.id if call else None}

    async def _semantic_verification(self, mission_id: str, pair: CandidatePair, actor: str) -> Dict[str, Any]:
        allowed = {
            SemanticVerificationResultEnum.GENUINE_CONTRADICTION.value,
            SemanticVerificationResultEnum.COMPATIBLE.value,
            SemanticVerificationResultEnum.AMBIGUOUS.value,
        }
        prompt_payload = {
            "claim_a": {
                "statement": _claim_statement(pair.new_claim),
                "intervention": pair.new_claim.intervention_canonical,
                "outcome": pair.new_claim.outcome_canonical,
                "direction": claim_direction_value(pair.new_claim),
                "population": pair.new_claim.population,
            },
            "claim_b": {
                "statement": _claim_statement(pair.existing_claim),
                "intervention": pair.existing_claim.intervention_canonical,
                "outcome": pair.existing_claim.outcome_canonical,
                "direction": claim_direction_value(pair.existing_claim),
                "population": pair.existing_claim.population,
            },
        }

        for attempt in range(1, 3):
            prompt_text = (
                "Two claims are genuinely contradictory if a researcher familiar with both would conclude that both cannot "
                "be true simultaneously for the same population and context.\n"
                "Return exactly one token: GENUINE_CONTRADICTION, COMPATIBLE, or AMBIGUOUS.\n"
                f"{json.dumps(prompt_payload)}"
            )
            response_text = ""
            validated = SemanticVerificationResultEnum.AMBIGUOUS.value
            try:
                response = await self.llm_provider.generate_async(
                    [
                        {"role": "system", "content": "Return one token only."},
                        {"role": "user", "content": prompt_text},
                    ],
                    temperature=0.0,
                    max_tokens=20,
                )
                response_text = (response or {}).get("content", "").strip()
                token = response_text.split()[0].strip() if response_text else ""
                if token in allowed:
                    validated = token
            except Exception as exc:
                logger.warning("Semantic contradiction verification failed: %s", exc)
                response_text = str(exc)
                await self.memory_system.log_event(
                    event_type=MemoryEventType.LLM_VERIFICATION_FAILED,
                    mission_id=mission_id,
                    actor=actor,
                    claim_id=pair.new_claim.id,
                    previous_value=None,
                    new_value={
                        "other_claim_id": str(pair.existing_claim.id),
                        "attempt": attempt,
                        "stage": VerificationStageEnum.SEMANTIC_VERIFICATION.value,
                    },
                )
            call = await self._store_verification_call(
                mission_id,
                pair,
                VerificationStageEnum.SEMANTIC_VERIFICATION,
                prompt_text,
                response_text,
                validated,
                str(attempt),
            )
            return {"result": SemanticVerificationResultEnum(validated), "call_id": call.id if call else None}

        return {"result": SemanticVerificationResultEnum.AMBIGUOUS, "reason": "llm_verification_failed"}

    def _population_overlap(self, pair: CandidatePair) -> PopulationOverlapEnum:
        left = _normalized_text(pair.new_claim.population)
        right = _normalized_text(pair.existing_claim.population)
        if left and right and left == right:
            return PopulationOverlapEnum.IDENTICAL
        left_tokens = _token_set(left)
        right_tokens = _token_set(right)
        if left_tokens and right_tokens and left_tokens.intersection(right_tokens):
            return PopulationOverlapEnum.PARTIAL
        return PopulationOverlapEnum.DIFFERENT

    def _classify_severity(self, pair: CandidatePair) -> ContradictionSeverityEnum:
        quality_parity = abs(_study_score(pair.new_claim) - _study_score(pair.existing_claim))
        confidence_product = _confidence_product(pair.new_claim, pair.existing_claim)
        overlap = self._population_overlap(pair)
        if quality_parity < 0.15 and confidence_product > 0.5 and overlap == PopulationOverlapEnum.IDENTICAL:
            return ContradictionSeverityEnum.HIGH
        if quality_parity >= 0.35 or confidence_product < 0.25:
            return ContradictionSeverityEnum.LOW
        return ContradictionSeverityEnum.MEDIUM

    async def _write_confirmed_contradiction(
        self,
        mission: Mission,
        pair: CandidatePair,
        llm_call_id: Optional[UUID],
        actor: str,
    ) -> Optional[ContradictionRecord]:
        existing = (
            await self.db.execute(
                select(ContradictionRecord).where(
                    ContradictionRecord.mission_id == mission.id,
                    or_(
                        and_(ContradictionRecord.claim_a_id == pair.new_claim.id, ContradictionRecord.claim_b_id == pair.existing_claim.id),
                        and_(ContradictionRecord.claim_a_id == pair.existing_claim.id, ContradictionRecord.claim_b_id == pair.new_claim.id),
                    ),
                )
            )
        ).scalar_one_or_none()
        if existing:
            return existing

        edge = await self.memory_system._create_or_update_edge(
            pair.new_claim,
            pair.existing_claim,
            GraphEdgeType.CONTRADICTS,
            justification="Confirmed contradiction after contextual reconciliation and semantic verification.",
            actor=actor,
        )
        record = ContradictionRecord(
            mission_id=mission.id,
            claim_a_id=pair.new_claim.id,
            claim_b_id=pair.existing_claim.id,
            graph_edge_id=edge.id if edge else None,
            severity=self._classify_severity(pair),
            direction_a=claim_direction_value(pair.new_claim),
            direction_b=claim_direction_value(pair.existing_claim),
            intervention_canonical=pair.new_claim.intervention_canonical or pair.existing_claim.intervention_canonical,
            outcome_canonical=pair.new_claim.outcome_canonical or pair.existing_claim.outcome_canonical,
            quality_parity_delta=round(abs(_study_score(pair.new_claim) - _study_score(pair.existing_claim)), 4),
            confidence_product=round(_confidence_product(pair.new_claim, pair.existing_claim), 6),
            population_overlap=self._population_overlap(pair),
            context_resolution_attempted=True,
            context_resolution_result=ContextResolutionResultEnum.NONE_RESOLVED,
            semantic_verification_result=SemanticVerificationResultEnum.GENUINE_CONTRADICTION,
            llm_verification_call_id=llm_call_id,
            resolution_status="unresolved",
        )
        self.db.add(record)
        await self.db.flush()
        await self.memory_system.log_event(
            event_type=MemoryEventType.CONTRADICTION_DETECTED,
            mission_id=mission.id,
            actor=actor,
            claim_id=pair.new_claim.id,
            previous_value=None,
            new_value={
                "contradiction_id": str(record.id),
                "claim_a_id": str(pair.new_claim.id),
                "claim_b_id": str(pair.existing_claim.id),
                "severity": record.severity.value,
                **_edge_weight(pair.new_claim, pair.existing_claim),
            },
        )
        if record.severity == ContradictionSeverityEnum.HIGH:
            await self.memory_system.log_event(
                event_type=MemoryEventType.CONTRADICTION_HIGH_SEVERITY,
                mission_id=mission.id,
                actor=actor,
                claim_id=pair.new_claim.id,
                previous_value=None,
                new_value={"contradiction_id": str(record.id), "claim_b_id": str(pair.existing_claim.id)},
            )
            self.db.add(
                Alert(
                    id=str(record.id),
                    mission_id=mission.id,
                    alert_type="HIGH_SEVERITY_CONTRADICTION",
                    severity=AlertSeverity.WATCH,
                    cycle_number=int(mission.session_count or 0),
                    lifecycle_status="active",
                    message=f"High-severity contradiction detected for {record.intervention_canonical or 'unknown intervention'} / {record.outcome_canonical or 'unknown outcome'}.",
                )
            )
        return record

    async def _write_context_resolved_record(
        self,
        mission: Mission,
        pair: CandidatePair,
        reason: ContextResolutionResultEnum,
        stronger_claim_id: Optional[UUID],
        llm_call_id: Optional[UUID],
        notes: Optional[str],
        actor: str,
    ) -> ContextResolvedPairRecord:
        existing = (
            await self.db.execute(
                select(ContextResolvedPairRecord).where(
                    ContextResolvedPairRecord.mission_id == mission.id,
                    or_(
                        and_(ContextResolvedPairRecord.claim_a_id == pair.new_claim.id, ContextResolvedPairRecord.claim_b_id == pair.existing_claim.id),
                        and_(ContextResolvedPairRecord.claim_a_id == pair.existing_claim.id, ContextResolvedPairRecord.claim_b_id == pair.new_claim.id),
                    ),
                )
            )
        ).scalar_one_or_none()
        if existing:
            return existing
        row = ContextResolvedPairRecord(
            mission_id=mission.id,
            claim_a_id=pair.new_claim.id,
            claim_b_id=pair.existing_claim.id,
            direction_a=claim_direction_value(pair.new_claim),
            direction_b=claim_direction_value(pair.existing_claim),
            intervention_canonical=pair.new_claim.intervention_canonical or pair.existing_claim.intervention_canonical,
            outcome_canonical=pair.new_claim.outcome_canonical or pair.existing_claim.outcome_canonical,
            resolution_reason=reason,
            stronger_claim_id=stronger_claim_id,
            llm_call_id=llm_call_id,
            notes=notes,
        )
        self.db.add(row)
        await self.db.flush()
        await self.memory_system.log_event(
            event_type=MemoryEventType.CONTRADICTION_CONTEXT_RESOLVED,
            mission_id=mission.id,
            actor=actor,
            claim_id=pair.new_claim.id,
            previous_value=None,
            new_value={"pair_id": str(row.id), "other_claim_id": str(pair.existing_claim.id), "reason": reason.value},
        )
        return row

    async def _write_ambiguous_record(
        self,
        mission_id: str,
        pair: CandidatePair,
        llm_call_id: Optional[UUID],
        reason: str,
        actor: str,
    ) -> AmbiguousContradictionRecord:
        existing = (
            await self.db.execute(
                select(AmbiguousContradictionRecord).where(
                    AmbiguousContradictionRecord.mission_id == mission_id,
                    or_(
                        and_(AmbiguousContradictionRecord.claim_a_id == pair.new_claim.id, AmbiguousContradictionRecord.claim_b_id == pair.existing_claim.id),
                        and_(AmbiguousContradictionRecord.claim_a_id == pair.existing_claim.id, AmbiguousContradictionRecord.claim_b_id == pair.new_claim.id),
                    ),
                )
            )
        ).scalar_one_or_none()
        if existing:
            return existing
        row = AmbiguousContradictionRecord(
            mission_id=mission_id,
            claim_a_id=pair.new_claim.id,
            claim_b_id=pair.existing_claim.id,
            direction_a=claim_direction_value(pair.new_claim),
            direction_b=claim_direction_value(pair.existing_claim),
            intervention_canonical=pair.new_claim.intervention_canonical or pair.existing_claim.intervention_canonical,
            outcome_canonical=pair.new_claim.outcome_canonical or pair.existing_claim.outcome_canonical,
            ambiguity_reason=reason,
            llm_verification_call_id=llm_call_id,
        )
        self.db.add(row)
        await self.db.flush()
        await self.memory_system.log_event(
            event_type=MemoryEventType.CONTRADICTION_AMBIGUOUS,
            mission_id=mission_id,
            actor=actor,
            claim_id=pair.new_claim.id,
            previous_value=None,
            new_value={"pair_id": str(row.id), "other_claim_id": str(pair.existing_claim.id), "reason": reason},
        )
        return row

    async def _store_verification_call(
        self,
        mission_id: str,
        pair: CandidatePair,
        stage: VerificationStageEnum,
        prompt_text: str,
        response_text: str,
        validated_output: str,
        attempt_number: str,
    ) -> ContradictionVerificationCall:
        row = ContradictionVerificationCall(
            mission_id=mission_id,
            pair_key=_pair_key(pair.new_claim.id, pair.existing_claim.id),
            claim_a_id=pair.new_claim.id,
            claim_b_id=pair.existing_claim.id,
            stage=stage,
            prompt_text=prompt_text,
            response_text=response_text,
            validated_output=validated_output,
            attempt_number=attempt_number,
        )
        self.db.add(row)
        await self.db.flush()
        return row

    async def _confirmed_record_response(self, record: ContradictionRecord) -> Dict[str, Any]:
        edge = await self.db.get(ClaimGraphEdge, record.graph_edge_id) if record.graph_edge_id else None
        return {
            "id": str(record.id),
            "mission_id": record.mission_id,
            "timestamp": record.timestamp.isoformat() if record.timestamp else None,
            "claim_a_id": str(record.claim_a_id),
            "claim_b_id": str(record.claim_b_id),
            "graph_edge_id": str(record.graph_edge_id) if record.graph_edge_id else None,
            "severity": record.severity.value,
            "direction_a": record.direction_a,
            "direction_b": record.direction_b,
            "intervention_canonical": record.intervention_canonical,
            "outcome_canonical": record.outcome_canonical,
            "topic_key": _topic_key(record.intervention_canonical, record.outcome_canonical),
            "quality_parity_delta": record.quality_parity_delta,
            "confidence_product": record.confidence_product,
            "population_overlap": record.population_overlap.value,
            "context_resolution_attempted": record.context_resolution_attempted,
            "context_resolution_result": record.context_resolution_result.value,
            "semantic_verification_result": record.semantic_verification_result.value,
            "llm_verification_call_id": str(record.llm_verification_call_id) if record.llm_verification_call_id else None,
            "resolution_status": record.resolution_status,
            "resolution_timestamp": record.resolution_timestamp.isoformat() if record.resolution_timestamp else None,
            "resolved_by": record.resolved_by,
            "edge_weight": edge.edge_weight if edge else None,
            "study_design_delta": edge.study_design_delta if edge else record.quality_parity_delta,
            "recency_weight": edge.recency_weight if edge else None,
            "justification": edge.justification if edge else None,
        }

    def _context_resolved_response(self, row: ContextResolvedPairRecord) -> Dict[str, Any]:
        return {
            "id": str(row.id),
            "mission_id": row.mission_id,
            "timestamp": row.timestamp.isoformat() if row.timestamp else None,
            "claim_a_id": str(row.claim_a_id),
            "claim_b_id": str(row.claim_b_id),
            "direction_a": row.direction_a,
            "direction_b": row.direction_b,
            "intervention_canonical": row.intervention_canonical,
            "outcome_canonical": row.outcome_canonical,
            "resolution_reason": row.resolution_reason.value,
            "stronger_claim_id": str(row.stronger_claim_id) if row.stronger_claim_id else None,
            "llm_call_id": str(row.llm_call_id) if row.llm_call_id else None,
            "notes": row.notes,
        }

    def _ambiguous_response(self, row: AmbiguousContradictionRecord) -> Dict[str, Any]:
        return {
            "id": str(row.id),
            "mission_id": row.mission_id,
            "timestamp": row.timestamp.isoformat() if row.timestamp else None,
            "claim_a_id": str(row.claim_a_id),
            "claim_b_id": str(row.claim_b_id),
            "direction_a": row.direction_a,
            "direction_b": row.direction_b,
            "intervention_canonical": row.intervention_canonical,
            "outcome_canonical": row.outcome_canonical,
            "ambiguity_reason": row.ambiguity_reason,
            "llm_verification_call_id": str(row.llm_verification_call_id) if row.llm_verification_call_id else None,
            "review_status": row.review_status,
        }
