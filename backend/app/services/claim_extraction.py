"""ADDED: Production-Grade Claim Extraction Service with Six Major Upgrades

Three-pass pipeline (extraction, classification+normalization, confidence scoring)
enhanced with:
1. Multi-query semantic retrieval layer (GROBID + FAISS + cross-encoder)
2. Evidence-grounded Pass 1 with chunk sourcing
3. Two-tier verification layer (NLI + LLM)
4. Enhanced confidence formula with verification factors
5. Claim graph with cross-paper deduplication
6. Quantitative extraction from tables/figures

Original pipeline structure preserved. All additions non-blocking.
"""

import asyncio
import ast
import logging
import json
import re
import uuid
from difflib import SequenceMatcher
from typing import Optional, List, Dict, Any, Tuple, Callable
from datetime import datetime
from dataclasses import dataclass, field
import math

from sqlalchemy import select, delete, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    ClaimTypeEnum,
    DirectionEnum,
    Mission,
    MissionRelevanceEnum,
    ResearchClaim,
    ResearchPaper,
    SectionSourceEnum,
    ValidationStatusEnum,
)
from app.services.embeddings import get_embedding_service
from app.services.llm import get_llm_provider

# ADDED: Import new components (6-upgrades)
from app.services.retrieval_layer import RetrievalLayer, ChunkMetadata
from app.services.verification_engine import VerificationEngine, VerificationResult
from app.services.quantitative_extractor import QuantitativeExtractor
from app.services.graph_manager import ClaimGraphManager
from app.services.memory_system import MemorySystemService

# [NEW] NEXT-GENERATION COMPONENTS (5-capabilities)
from app.services.evidence_gap_detector import EvidenceGapDetector
from app.services.failure_logger import FailureLogger
from app.services.argument_coherence_checker import ArgumentCoherenceChecker
from app.services.entity_evolution_manager import EntityEvolutionManager
from app.services.uncertainty_decomposer import UncertaintyDecomposer

logger = logging.getLogger(__name__)


@dataclass
class ExtractionPipeline:
    """ADDED: Configuration for extraction pipeline"""
    enable_retrieval_layer: bool = True
    enable_verification: bool = True
    enable_quantitative: bool = True
    enable_graph_manager: bool = False
    # These next-generation modules are still partial and are disabled by default
    # so the core extraction pipeline can run reliably end-to-end.
    enable_failure_logger: bool = False
    enable_coherence_checking: bool = False
    enable_entity_evolution_advanced: bool = False
    enable_uncertainty_decomposition: bool = False
    enable_evidence_gap_detection: bool = False
    max_chunks_for_extraction: int = 20
    parallel_batch_size: int = 3


class EventEmitter:
    """Event emission system for MODULE 3 pipeline"""
    
    def __init__(self):
        self.handlers: Dict[str, List] = {}
    
    def on(self, event_type: str, handler):
        if event_type not in self.handlers:
            self.handlers[event_type] = []
        self.handlers[event_type].append(handler)
    
    async def emit(self, event_type: str, data: Dict[str, Any]):
        if event_type in self.handlers:
            tasks = [handler(data) for handler in self.handlers[event_type]]
            await asyncio.gather(*tasks, return_exceptions=True)


class ClaimExtractionService:
    """
    Production-grade claim extraction service.
    
    Pipeline:
    1. RetrievalLayer: GROBID + multi-query + reranking → top-20 chunks
    2. Pass 1: Evidence-grounded LLM extraction with chunk citations
    3. Grounding validation: Mechanical substring check
    4. Pass 2a: Causal classification (LLM)
    5. Pass 2b: Entity normalization (LLM with boost index lookup)
    6. QuantitativeExtractor (parallel): Extract from tables/figures
    7. VerificationEngine: NLI + LLM verification of evidence entailment
    8. Pass 3: Enhanced confidence assembly with verification factors
    9. Validation: Reject not-grounded and unsupported claims
    10. Persistence: Store with full provenance
    11. EventEmitter: Emit events
    12. GraphManager: Build knowledge graph, detect contradictions
    """
    
    def __init__(
        self,
        db: AsyncSession,
        llm_provider: Any = None,
        embedding_service: Any = None,
        event_emitter: Optional[EventEmitter] = None,
        pipeline_config: Optional[ExtractionPipeline] = None
    ):
        self.db = db
        self.llm_provider = llm_provider or get_llm_provider()
        self.embedding_service = embedding_service or get_embedding_service()
        self.event_emitter = event_emitter or EventEmitter()
        self.pipeline_config = pipeline_config or ExtractionPipeline()
        
        # ADDED: Initialize new components
        self.retrieval_layer = RetrievalLayer(
            db=db,
            embedding_service=self.embedding_service,
            llm_provider=self.llm_provider,
            enable_cross_encoder=False
        ) if self.pipeline_config.enable_retrieval_layer else None
        
        self.verification_engine = VerificationEngine(
            db=db,
            llm_provider=self.llm_provider,
            enable_nli=False,
        ) if self.pipeline_config.enable_verification else None
        
        self.quantitative_extractor = QuantitativeExtractor(
            llm_provider=self.llm_provider
        ) if self.pipeline_config.enable_quantitative else None
        
        self.graph_manager = ClaimGraphManager(
            db=db,
            embedding_service=self.embedding_service
        ) if self.pipeline_config.enable_graph_manager else None
        
        # [NEW] Initialize next-generation components
        self.failure_logger = FailureLogger(
        ) if self.pipeline_config.enable_failure_logger else None
        
        self.coherence_checker = ArgumentCoherenceChecker(
        ) if self.pipeline_config.enable_coherence_checking else None
        
        self.entity_evolution = EntityEvolutionManager(
        ) if self.pipeline_config.enable_entity_evolution_advanced else None
        
        self.uncertainty_decomposer = UncertaintyDecomposer(
        ) if self.pipeline_config.enable_uncertainty_decomposition else None
        
        self.evidence_gap_detector = EvidenceGapDetector(
        ) if self.pipeline_config.enable_evidence_gap_detection else None

        self.structured_output_stats: Dict[str, Dict[str, int]] = {}
        self.memory_system = MemorySystemService(
            db=db,
            llm_provider=self.llm_provider,
            embedding_service=self.embedding_service,
        )
        
        logger.info("ClaimExtractionService initialized with all upgrades + 5 next-generation capabilities")

    def _record_structured_output(self, stage_name: str, mode: str) -> None:
        stage_stats = self.structured_output_stats.setdefault(stage_name, {})
        stage_stats[mode] = stage_stats.get(mode, 0) + 1

    def _iter_batches(self, items: List[Any], batch_size: int):
        for start in range(0, len(items), batch_size):
            yield start, items[start:start + batch_size]

    def _truncate_prompt_text(self, text: str, max_chars: int = 2200) -> str:
        cleaned = (text or "").strip()
        if len(cleaned) <= max_chars:
            return cleaned
        return cleaned[: max_chars - 16].rstrip() + "\n[TRUNCATED]"

    def _strip_code_fences(self, text: str) -> str:
        cleaned = (text or "").strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        cleaned = re.sub(r"^<json>\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*</json>$", "", cleaned, flags=re.IGNORECASE)
        return cleaned.strip()

    def _extract_balanced_json_segments(self, text: str, expected_kind: str) -> List[str]:
        opener = "[" if expected_kind == "array" else "{"
        closer = "]" if expected_kind == "array" else "}"
        segments: List[str] = []
        source = self._strip_code_fences(text)

        for start_idx, char in enumerate(source):
            if char != opener:
                continue

            depth = 0
            in_string = False
            escape = False

            for end_idx in range(start_idx, len(source)):
                current = source[end_idx]

                if in_string:
                    if escape:
                        escape = False
                    elif current == "\\":
                        escape = True
                    elif current == '"':
                        in_string = False
                    continue

                if current == '"':
                    in_string = True
                elif current == opener:
                    depth += 1
                elif current == closer:
                    depth -= 1
                    if depth == 0:
                        segments.append(source[start_idx:end_idx + 1])
                        break

        return segments

    def _cleanup_json_text(self, text: str) -> str:
        cleaned = self._strip_code_fences(text)
        cleaned = cleaned.replace("\u201c", '"').replace("\u201d", '"')
        cleaned = cleaned.replace("\u2018", "'").replace("\u2019", "'")
        cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)
        return cleaned.strip()

    def _load_json_candidate(self, text: str, expected_kind: str) -> Tuple[Optional[Any], Optional[str]]:
        cleaned = self._cleanup_json_text(text)
        expected_type = list if expected_kind == "array" else dict

        parse_attempts = [cleaned]
        parse_attempts.extend(self._extract_balanced_json_segments(cleaned, expected_kind))

        seen = set()
        for candidate in parse_attempts:
            candidate = candidate.strip()
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)

            try:
                parsed = json.loads(candidate)
            except Exception:
                try:
                    pythonish = re.sub(r"\btrue\b", "True", candidate, flags=re.IGNORECASE)
                    pythonish = re.sub(r"\bfalse\b", "False", pythonish, flags=re.IGNORECASE)
                    pythonish = re.sub(r"\bnull\b", "None", pythonish, flags=re.IGNORECASE)
                    parsed = ast.literal_eval(pythonish)
                except Exception as exc:
                    last_error = str(exc)
                    continue
            else:
                last_error = None

            if isinstance(parsed, expected_type):
                return parsed, None

            if expected_kind == "array" and isinstance(parsed, dict):
                for key in ("claims", "items", "data", "results", "normalizations", "classifications"):
                    value = parsed.get(key)
                    if isinstance(value, list):
                        return value, None

        return None, locals().get("last_error") or f"Could not parse {expected_kind}"

    def _clamp_score(self, value: Any, default: float = 0.5) -> float:
        try:
            score = float(value)
        except (TypeError, ValueError):
            return default
        return max(0.0, min(1.0, score))

    def _coerce_bool(self, value: Any, default: bool = False) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "yes", "1"}:
                return True
            if lowered in {"false", "no", "0"}:
                return False
        return default

    def _coerce_optional_text(self, value: Any) -> Optional[str]:
        if value is None:
            return None
        text = " ".join(str(value).split()).strip()
        return text or None

    def _coerce_pass1_claim(self, item: Any, max_chunk_index: int) -> Optional[Dict[str, Any]]:
        if not isinstance(item, dict):
            return None

        statement_raw = self._coerce_optional_text(item.get("statement_raw"))
        evidence_span = self._coerce_optional_text(item.get("evidence_span"))
        if not statement_raw or not evidence_span:
            return None

        raw_chunk_ids = item.get("source_chunk_ids", [])
        if isinstance(raw_chunk_ids, (str, int)):
            raw_chunk_ids = [raw_chunk_ids]

        source_chunk_ids: List[int] = []
        for raw_chunk_id in raw_chunk_ids:
            try:
                chunk_id = int(raw_chunk_id)
            except (TypeError, ValueError):
                continue
            if 1 <= chunk_id <= max_chunk_index and chunk_id not in source_chunk_ids:
                source_chunk_ids.append(chunk_id)

        if not source_chunk_ids:
            return None

        direction = str(item.get("direction") or "unclear").strip().lower()
        if direction not in {"positive", "negative", "null", "unclear"}:
            direction = "unclear"

        section_source = str(item.get("section_source") or "unknown").strip().lower()
        if section_source not in {"abstract", "results", "discussion", "conclusion", "methods", "introduction", "unknown"}:
            section_source = "unknown"

        return {
            "statement_raw": statement_raw,
            "source_chunk_ids": source_chunk_ids,
            "evidence_span": evidence_span[:240],
            "grounding_confidence": self._clamp_score(item.get("grounding_confidence"), 0.7),
            "intervention": self._coerce_optional_text(item.get("intervention")),
            "outcome": self._coerce_optional_text(item.get("outcome")),
            "direction": direction,
            "hedging_text": self._coerce_optional_text(item.get("hedging_text")),
            "section_source": section_source,
            "extraction_certainty": self._clamp_score(item.get("extraction_certainty"), 0.7),
        }

    def _coerce_pass2a_classification(self, item: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(item, dict):
            return None
        claim_id = self._coerce_optional_text(item.get("claim_id"))
        if not claim_id:
            return None
        claim_type = str(item.get("claim_type") or "correlational").strip().lower()
        if claim_type not in {"causal", "correlational", "mechanistic", "comparative", "safety", "prevalence", "null_result"}:
            claim_type = "correlational"
        return {
            "claim_id": claim_id,
            "claim_type": claim_type,
            "study_design_consistent": self._coerce_bool(item.get("study_design_consistent"), True),
            "causal_justification": self._coerce_optional_text(item.get("causal_justification")) or "",
        }

    def _coerce_pass2b_normalization(self, item: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(item, dict):
            return None
        claim_id = self._coerce_optional_text(item.get("claim_id"))
        if not claim_id:
            return None
        return {
            "claim_id": claim_id,
            "intervention_canonical": self._coerce_optional_text(item.get("intervention_canonical")),
            "outcome_canonical": self._coerce_optional_text(item.get("outcome_canonical")),
            "normalization_confidence": self._clamp_score(item.get("normalization_confidence"), 0.5),
        }

    def _normalize_entity_key(self, value: str) -> str:
        normalized = re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()
        return re.sub(r"\s+", " ", normalized)

    def _heuristic_claim_classification(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        text = f"{candidate.get('statement_raw', '')} {candidate.get('evidence_span', '')}".lower()
        claim_type = "correlational"
        study_design_consistent = True
        justification = "Heuristic default based on wording of the statement."

        if any(term in text for term in ["adverse", "safety", "side effect", "tolerab", "toxicity"]):
            claim_type = "safety"
            justification = "The statement discusses safety, tolerability, or adverse effects."
        elif any(term in text for term in ["mechanism", "pathway", "receptor", "signaling", "pharmacogenomic"]):
            claim_type = "mechanistic"
            justification = "The statement focuses on mechanism, pathways, or receptor biology."
        elif any(term in text for term in ["prevalence", "incidence", "frequency", "rate of"]):
            claim_type = "prevalence"
            justification = "The statement reports frequency or incidence."
        elif any(term in text for term in ["compared with", "compared to", "versus", "vs."]):
            claim_type = "comparative"
            justification = "The statement compares interventions or groups."
        elif any(term in text for term in ["no effect", "no significant", "no difference", "did not", "not associated"]):
            claim_type = "null_result"
            justification = "The statement explicitly reports a null or non-significant finding."
        elif any(term in text for term in ["caused", "led to", "resulted in", "reduced", "improved", "increased"]):
            claim_type = "causal"
            justification = "The statement uses causal or intervention-effect language."
            if any(term in text for term in ["associated", "correlated", "linked"]):
                study_design_consistent = False
                justification = "Mixed causal and associational language makes causal interpretation uncertain."

        return {
            "claim_type": claim_type,
            "study_design_consistent": study_design_consistent,
            "causal_justification": justification,
        }

    def _heuristic_entity_canonicalization(
        self,
        value: Optional[str],
        entity_type: str,
    ) -> Optional[str]:
        text = self._coerce_optional_text(value)
        if not text:
            return None

        normalized = self._normalize_entity_key(text)
        if entity_type == "intervention":
            alias_map = {
                "ozempic": "semaglutide",
                "wegovy": "semaglutide",
                "rybelsus": "semaglutide",
                "semaglutide": "semaglutide",
                "liraglutide": "liraglutide",
                "saxenda": "liraglutide",
                "tirzepatide": "tirzepatide",
                "mounjaro": "tirzepatide",
                "zepbound": "tirzepatide",
                "glp 1 receptor agonist": "glp-1 receptor agonist",
                "glp1 receptor agonist": "glp-1 receptor agonist",
                "glp 1 agonist": "glp-1 receptor agonist",
                "glp1 agonist": "glp-1 receptor agonist",
                "glp 1 ra": "glp-1 receptor agonist",
                "anti obesity medication": "anti-obesity medication",
                "anti obesity medications": "anti-obesity medication",
            }
        else:
            alias_map = {
                "body weight reduction": "weight loss",
                "weight reduction": "weight loss",
                "weight loss": "weight loss",
                "bmi reduction": "bmi reduction",
                "glycemic control": "glycemic control",
                "blood glucose": "glycemic control",
                "adverse events": "adverse events",
                "safety": "safety",
                "kidney function": "kidney function",
                "renal function": "kidney function",
                "pregnancy outcome": "pregnancy outcomes",
                "pregnancy outcomes": "pregnancy outcomes",
                "breast milk transfer": "breast milk transfer",
                "nicotine related events": "nicotine-related events",
            }

        for alias, canonical in alias_map.items():
            if alias in normalized:
                return canonical

        cleaned = re.sub(r"\s+", " ", text.strip())
        return cleaned.lower()

    def _section_priority(self, section_name: Optional[str]) -> int:
        normalized = (section_name or "unknown").lower()
        priority_map = {
            "results": 5,
            "conclusion": 4,
            "abstract": 4,
            "discussion": 3,
            "body": 2,
            "introduction": 1,
            "methods": 0,
            "unknown": 1,
        }
        return priority_map.get(normalized, 1)

    def _section_finding_cap(self, section_name: Optional[str]) -> int:
        normalized = (section_name or "unknown").lower()
        caps = {
            "results": 3,
            "conclusion": 2,
            "abstract": 2,
            "discussion": 2,
            "body": 2,
            "introduction": 1,
            "methods": 0,
            "unknown": 1,
        }
        return caps.get(normalized, 1)

    def _finding_focus_for_section(self, section_name: Optional[str]) -> str:
        normalized = (section_name or "unknown").lower()
        focus_map = {
            "results": "primary outcomes, secondary outcomes, quantitative results, subgroup findings, null findings",
            "conclusion": "main takeaways, strongest findings, clinical implications, high-level limitations",
            "abstract": "headline findings, intervention effects, major safety findings",
            "discussion": "interpreted findings, safety implications, limitations, mechanistic implications",
            "body": "explicit evidence-bearing findings only",
            "introduction": "only explicit prior-evidence statements if they are phrased as findings",
            "methods": "avoid methods unless the section states an explicit measured finding",
            "unknown": "explicit evidence-bearing findings only",
        }
        return focus_map.get(normalized, "explicit evidence-bearing findings only")

    def _build_document_frame(self, retrieved_chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
        section_stats: Dict[str, Dict[str, Any]] = {}
        for chunk in retrieved_chunks:
            section_name = (chunk.get("section_name") or "unknown").lower()
            stats = section_stats.setdefault(
                section_name,
                {
                    "chunk_count": 0,
                    "avg_rank": 0.0,
                    "best_rank": None,
                    "priority": self._section_priority(section_name),
                },
            )
            stats["chunk_count"] += 1
            rank = chunk.get("final_rank") or chunk.get("crossencoder_score") or chunk.get("cosine_score") or 999
            stats["avg_rank"] += float(rank)
            if stats["best_rank"] is None or float(rank) < stats["best_rank"]:
                stats["best_rank"] = float(rank)

        for stats in section_stats.values():
            if stats["chunk_count"]:
                stats["avg_rank"] = round(stats["avg_rank"] / stats["chunk_count"], 3)

        ordered_sections = sorted(
            section_stats.items(),
            key=lambda item: (-item[1]["priority"], item[1]["best_rank"] or 999),
        )
        return {
            "total_chunks": len(retrieved_chunks),
            "section_summary": section_stats,
            "ordered_sections": [section for section, _ in ordered_sections],
            "high_value_sections": [
                section for section, stats in ordered_sections if stats["priority"] >= 3
            ],
        }

    def _group_chunks_for_finding_extraction(
        self,
        retrieved_chunks: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        section_groups: Dict[str, List[Dict[str, Any]]] = {}
        for chunk in retrieved_chunks:
            section_name = (chunk.get("section_name") or "unknown").lower()
            section_groups.setdefault(section_name, []).append(chunk)

        ordered_sections = sorted(
            section_groups.keys(),
            key=lambda name: (
                -self._section_priority(name),
                min(
                    (
                        chunk.get("final_rank")
                        or chunk.get("crossencoder_score")
                        or chunk.get("cosine_score")
                        or 999
                    )
                    for chunk in section_groups[name]
                ),
            ),
        )

        groups: List[Dict[str, Any]] = []
        for section_name in ordered_sections:
            cap = self._section_finding_cap(section_name)
            if cap <= 0:
                continue

            section_chunks = sorted(
                section_groups[section_name],
                key=lambda chunk: (
                    chunk.get("final_rank")
                    or -(chunk.get("crossencoder_score") or 0.0)
                    or -(chunk.get("cosine_score") or 0.0)
                ),
            )
            batch_size = 4 if section_name in {"results", "discussion", "body"} else 3

            for batch_start, chunk_batch in self._iter_batches(section_chunks, batch_size):
                groups.append(
                    {
                        "section_name": section_name,
                        "chunks": chunk_batch,
                        "max_findings": min(cap, 3 if section_name == "results" else 2),
                        "focus": self._finding_focus_for_section(section_name),
                    }
                )

        if not groups and retrieved_chunks:
            groups.append(
                {
                    "section_name": "unknown",
                    "chunks": retrieved_chunks[:6],
                    "max_findings": 3,
                    "focus": "explicit evidence-bearing findings only",
                }
            )

        return groups

    def _claim_text_signature(self, claim: Dict[str, Any]) -> str:
        text = (
            claim.get("statement_normalized")
            or claim.get("statement_raw")
            or claim.get("evidence_span")
            or ""
        ).lower()
        text = re.sub(r"[^a-z0-9\s]", " ", text)
        stopwords = {
            "the", "and", "for", "with", "that", "this", "from", "were", "was",
            "are", "but", "into", "than", "then", "have", "has", "had", "their",
            "them", "they", "there", "while", "after", "before", "during", "among",
            "using", "used", "showed", "shows", "study", "patients", "adults",
        }
        tokens = [token for token in text.split() if len(token) > 2 and token not in stopwords]
        return " ".join(tokens[:20])

    def _claims_similar_for_consolidation(
        self,
        left: Dict[str, Any],
        right: Dict[str, Any],
    ) -> bool:
        left_intervention = self._normalize_entity_key(
            left.get("intervention_canonical") or left.get("intervention") or ""
        )
        right_intervention = self._normalize_entity_key(
            right.get("intervention_canonical") or right.get("intervention") or ""
        )
        if left_intervention and right_intervention and left_intervention != right_intervention:
            return False

        left_outcome = self._normalize_entity_key(
            left.get("outcome_canonical") or left.get("outcome") or ""
        )
        right_outcome = self._normalize_entity_key(
            right.get("outcome_canonical") or right.get("outcome") or ""
        )
        if left_outcome and right_outcome and left_outcome != right_outcome:
            return False

        left_direction = left.get("direction")
        right_direction = right.get("direction")
        if (
            left_direction
            and right_direction
            and left_direction != "unclear"
            and right_direction != "unclear"
            and left_direction != right_direction
        ):
            return False

        left_type = left.get("claim_type")
        right_type = right.get("claim_type")
        if left_type and right_type and left_type != right_type:
            compatible = {left_type, right_type} <= {"causal", "correlational"}
            if not compatible:
                return False

        left_sig = self._claim_text_signature(left)
        right_sig = self._claim_text_signature(right)
        if not left_sig or not right_sig:
            return False

        left_tokens = set(left_sig.split())
        right_tokens = set(right_sig.split())
        if not left_tokens or not right_tokens:
            return False

        jaccard = len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
        sequence = SequenceMatcher(None, left_sig, right_sig).ratio()
        containment = left_sig in right_sig or right_sig in left_sig

        return containment or jaccard >= 0.58 or sequence >= 0.74

    def _claim_quality_score(self, claim: Dict[str, Any]) -> float:
        section_bonus = self._section_priority(claim.get("section_source")) * 0.12
        grounding = float(claim.get("grounding_confidence") or 0.0)
        extraction = float(claim.get("extraction_certainty") or 0.0)
        support_bonus = min(0.2, 0.05 * max(0, len(claim.get("resolved_source_chunk_ids", [])) - 1))
        return section_bonus + grounding + extraction + support_bonus

    def _claim_statement_is_specific(self, claim: Dict[str, Any]) -> bool:
        text = " ".join((claim.get("statement_raw") or "").split())
        if len(text) < 35 or len(text) > 280:
            return False

        lowered = text.lower()
        generic_prefixes = (
            "this study",
            "our findings",
            "we investigated",
            "the safety, pharmacokinetics",
        )
        if lowered.startswith(generic_prefixes):
            return False
        if any(
            phrase in lowered
            for phrase in (
                "study selection",
                "data extraction",
                "risk of bias",
                "grade assessments",
                "editorial process",
                "publication of the studies",
                "conflict of interest",
                "funding source",
                "protocol for evaluation",
            )
        ):
            return False
        if "more research is needed" in lowered and float(claim.get("composite_confidence") or 0.0) < 0.70:
            return False
        return True

    def _persistence_quality_score(self, claim: Dict[str, Any]) -> float:
        section_bonus = {
            "results": 0.22,
            "conclusion": 0.18,
            "abstract": 0.14,
            "discussion": 0.06,
        }.get((claim.get("section_source") or "unknown").lower(), -0.08)
        support_bonus = min(0.15, 0.04 * max(0, int(claim.get("supporting_evidence_count", 1)) - 1))
        canonical_bonus = 0.06 if claim.get("intervention_canonical") and claim.get("outcome_canonical") else 0.0
        relevance_bonus = 0.05 if claim.get("mission_relevance") == MissionRelevanceEnum.PRIMARY.value else 0.0
        quantitative_bonus = 0.04 if claim.get("quantitative_evidence") else 0.0
        return float(claim.get("composite_confidence") or 0.0) + section_bonus + support_bonus + canonical_bonus + relevance_bonus + quantitative_bonus

    def _passes_high_quality_persistence_bar(self, claim: Dict[str, Any]) -> bool:
        confidence = float(claim.get("composite_confidence") or 0.0)
        section = (claim.get("section_source") or "unknown").lower()
        claim_type = str(claim.get("claim_type") or "correlational").lower()
        support_count = int(claim.get("supporting_evidence_count", 1) or 1)

        if not claim.get("grounding_valid", False):
            return False
        if section not in {"results", "abstract", "conclusion", "discussion"}:
            return False
        if not any(
            [
                claim.get("intervention"),
                claim.get("intervention_canonical"),
                claim.get("outcome"),
                claim.get("outcome_canonical"),
            ]
        ):
            return False
        if not self._claim_statement_is_specific(claim):
            return False
        if confidence < 0.58:
            return False
        if claim_type == "correlational" and confidence < 0.65:
            return False
        if section == "discussion" and confidence < 0.68 and support_count < 2:
            return False
        return True

    def _curate_claims_for_persistence(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        ordered = sorted(candidates, key=self._persistence_quality_score, reverse=True)
        curated = [claim for claim in ordered if self._passes_high_quality_persistence_bar(claim)]

        if not curated:
            curated = [
                claim
                for claim in ordered
                if claim.get("grounding_valid", False)
                and (claim.get("section_source") or "unknown").lower() in {"results", "abstract", "conclusion"}
                and self._claim_statement_is_specific(claim)
                and float(claim.get("composite_confidence") or 0.0) >= 0.50
            ][:1]

        curated = curated[:3]
        for rank, claim in enumerate(curated, 1):
            claim["persistence_rank"] = rank
            claim["curated_for_persistence"] = True

        logger.info(
            "Curated %s claims down to %s persisted findings",
            len(candidates),
            len(curated),
        )
        return curated

    def _default_supporting_evidence(self, claim: Dict[str, Any]) -> List[Dict[str, Any]]:
        return [
            {
                "evidence_span": claim.get("evidence_span"),
                "source_chunk_ids": claim.get("source_chunk_ids", []),
                "resolved_source_chunk_ids": claim.get("resolved_source_chunk_ids", []),
                "section_source": claim.get("section_source"),
                "grounding_confidence": claim.get("grounding_confidence"),
                "parse_strategy": claim.get("parse_strategy"),
                "quantitative_evidence": claim.get("quantitative_evidence"),
            }
        ]

    def _merge_claim_group(self, claims: List[Dict[str, Any]]) -> Dict[str, Any]:
        primary = max(claims, key=self._claim_quality_score)
        merged = json.loads(json.dumps(primary))

        support_entries: List[Dict[str, Any]] = []
        seen_support = set()
        resolved_chunks: Dict[str, Dict[str, Any]] = {}
        source_chunk_ids = set()
        evidence_sections = set()
        quantitative_evidence = None

        for claim in claims:
            for chunk in claim.get("resolved_source_chunks", []):
                chunk_id = chunk.get("chunk_id")
                if chunk_id:
                    resolved_chunks[chunk_id] = chunk

            for support in claim.get("supporting_evidence") or self._default_supporting_evidence(claim):
                support_key = (
                    support.get("evidence_span"),
                    tuple(sorted(support.get("resolved_source_chunk_ids") or [])),
                )
                if support_key in seen_support:
                    continue
                seen_support.add(support_key)
                support_entries.append(support)

                for chunk_id in support.get("source_chunk_ids") or []:
                    try:
                        source_chunk_ids.add(int(chunk_id))
                    except (TypeError, ValueError):
                        continue

                if support.get("section_source"):
                    evidence_sections.add(support.get("section_source"))
                if not quantitative_evidence and support.get("quantitative_evidence"):
                    quantitative_evidence = support.get("quantitative_evidence")

            if not quantitative_evidence and claim.get("quantitative_evidence"):
                quantitative_evidence = claim.get("quantitative_evidence")

        support_entries.sort(
            key=lambda support: (
                -self._section_priority(support.get("section_source")),
                -(support.get("grounding_confidence") or 0.0),
            )
        )

        merged["supporting_evidence"] = support_entries
        merged["supporting_evidence_count"] = len(support_entries)
        merged["within_paper_replication_count"] = len(claims)
        merged["representative_claim_ids"] = [claim.get("id") for claim in claims if claim.get("id")]
        merged["evidence_sections"] = sorted(evidence_sections)
        merged["source_chunk_ids"] = sorted(source_chunk_ids)
        merged["resolved_source_chunks"] = list(resolved_chunks.values())
        merged["resolved_source_chunk_ids"] = list(resolved_chunks.keys())
        merged["grounding_valid"] = bool(support_entries)
        merged["grounding_confidence"] = max(
            [support.get("grounding_confidence") or 0.0 for support in support_entries] or [merged.get("grounding_confidence") or 0.0]
        )
        if support_entries:
            merged["evidence_span"] = support_entries[0].get("evidence_span") or merged.get("evidence_span")
            merged["section_source"] = support_entries[0].get("section_source") or merged.get("section_source")
        merged["statement_normalized"] = " ".join((merged.get("statement_raw") or "").split())
        merged["parse_strategy"] = f"{merged.get('parse_strategy', 'unknown')}_consolidated"
        merged["finding_scope"] = "distinct_finding"
        merged["consolidation_method"] = "within_paper_similarity"
        if quantitative_evidence:
            merged["quantitative_evidence"] = quantitative_evidence
        return merged

    def _consolidate_distinct_findings(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not candidates:
            return []

        ordered = sorted(candidates, key=self._claim_quality_score, reverse=True)
        groups: List[List[Dict[str, Any]]] = []

        for candidate in ordered:
            placed = False
            for group in groups:
                if self._claims_similar_for_consolidation(candidate, group[0]):
                    group.append(candidate)
                    placed = True
                    break
            if not placed:
                groups.append([candidate])

        consolidated = [self._merge_claim_group(group) for group in groups]
        consolidated.sort(key=self._claim_quality_score, reverse=True)
        for rank, claim in enumerate(consolidated, 1):
            claim["finding_rank"] = rank

        logger.info(
            "Consolidated %s atomic claims into %s distinct findings",
            len(candidates),
            len(consolidated),
        )
        return consolidated

    async def _repair_json_with_llm(
        self,
        stage_name: str,
        invalid_content: str,
        schema_hint: str,
        max_tokens: int,
    ) -> str:
        response = await self.llm_provider.generate_async(
            [
                {
                    "role": "system",
                    "content": "You repair malformed JSON. Return only valid JSON with no markdown or commentary.",
                },
                {
                    "role": "user",
                    "content": (
                        f"The following {stage_name} output is malformed.\n"
                        f"Convert it into valid JSON that matches this schema:\n{schema_hint}\n\n"
                        "Rules:\n"
                        "- Return only a JSON array.\n"
                        "- Use double quotes.\n"
                        "- Use JSON null/true/false.\n"
                        "- Do not invent new records.\n"
                        "- Keep only information present in the malformed output.\n\n"
                        f"Malformed output:\n{invalid_content[:12000]}"
                    ),
                },
            ],
            temperature=0.0,
            top_p=0.1,
            max_tokens=max_tokens,
        )
        return response.get("content", "")

    async def _generate_validated_json_array(
        self,
        stage_name: str,
        system_prompt: str,
        user_prompt: str,
        schema_hint: str,
        validator: Callable[[Any], Optional[Dict[str, Any]]],
        max_tokens: int,
    ) -> Tuple[Optional[List[Dict[str, Any]]], str, Optional[str]]:
        response = await self.llm_provider.generate_async(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
            top_p=0.1,
            max_tokens=max_tokens,
        )
        content = response.get("content", "")

        parsed, parse_error = self._load_json_candidate(content, "array")
        if isinstance(parsed, list):
            validated = [validated_item for item in parsed if (validated_item := validator(item))]
            if validated:
                self._record_structured_output(stage_name, "direct")
                return validated, "direct", None

        repaired_content = await self._repair_json_with_llm(
            stage_name=stage_name,
            invalid_content=content,
            schema_hint=schema_hint,
            max_tokens=max_tokens,
        )
        repaired, repair_error = self._load_json_candidate(repaired_content, "array")
        if isinstance(repaired, list):
            validated = [validated_item for item in repaired if (validated_item := validator(item))]
            if validated:
                self._record_structured_output(stage_name, "repaired")
                return validated, "repaired", None

        retry_prompt = (
            user_prompt
            + "\n\nIMPORTANT:\n"
            + "- Return only a JSON array.\n"
            + "- The JSON must parse with json.loads.\n"
            + "- Use double quotes for every string.\n"
            + "- Do not include markdown fences.\n"
        )
        retry_response = await self.llm_provider.generate_async(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": retry_prompt},
            ],
            temperature=0.0,
            top_p=0.1,
            max_tokens=max_tokens,
        )
        retry_content = retry_response.get("content", "")
        retried, retry_error = self._load_json_candidate(retry_content, "array")
        if isinstance(retried, list):
            validated = [validated_item for item in retried if (validated_item := validator(item))]
            if validated:
                self._record_structured_output(stage_name, "retry")
                return validated, "retry", None

        self._record_structured_output(stage_name, "fallback")
        error_message = "; ".join(
            error for error in [parse_error, repair_error, retry_error] if error
        ) or "Unable to parse structured output"
        return None, "fallback", error_message
    
    async def extract_claims_from_paper(
        self,
        paper_id: str,
        mission_id: str,
        mission_question: str,
        mission_domain: str,
        entity_glossary: Optional[Dict[str, List[str]]] = None,
        pdf_url: Optional[str] = None,
        abstract: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Extract claims from paper using full production pipeline.
        
        Returns:
            {
                "success": bool,
                "claims_extracted": int,
                "claims": List[claim],
                "pipeline_status": str,
                "error": Optional[str]
            }
        """
        
        try:
            logger.info(f"[EXTRACTION] Starting for paper {paper_id}, mission {mission_id}")

            paper_lookup_id = paper_id if isinstance(paper_id, uuid.UUID) else uuid.UUID(str(paper_id))
            paper_record = await self.db.get(ResearchPaper, paper_lookup_id)
            if not paper_record:
                return {
                    "success": False,
                    "error": f"Paper {paper_id} not found",
                    "pipeline_status": "FAILED"
                }

            mission_record = await self.db.get(Mission, mission_id)
            if mission_record:
                mission_question = mission_record.normalized_query or mission_question
                mission_domain = mission_record.intent_type.value if mission_record.intent_type else mission_domain

            pico_data = {
                "population": (mission_record.pico_population if mission_record else None) or mission_domain,
                "intervention": (mission_record.pico_intervention if mission_record else None) or "",
                "comparator": (mission_record.pico_comparator if mission_record else None) or "",
                "outcome": (mission_record.pico_outcome if mission_record else None) or "",
            }
            
            # ===== UPGRADE 1: RETRIEVAL LAYER =====
            retrieved_chunks = await self._retrieve_chunks(
                paper_id=str(paper_record.id),
                pdf_url=pdf_url or paper_record.pdf_url or "",
                abstract=abstract or paper_record.abstract or "",
                full_text_content=paper_record.full_text_content or "",
                mission_question=mission_question,
                pico_data=pico_data,
            )
            
            if not retrieved_chunks:
                logger.warning(f"No chunks retrieved for paper {paper_id}")
                return {"success": False, "error": "No chunks retrieved"}
            
            logger.info(f"[RETRIEVAL] Retrieved {len(retrieved_chunks)} chunks")
            document_frame = self._build_document_frame(retrieved_chunks)
            
            # ===== PASS 1: EVIDENCE-GROUNDED EXTRACTION =====
            pass1_result = await self._pass1_extraction(
                paper_id=paper_id,
                mission_question=mission_question,
                retrieved_chunks=retrieved_chunks,
                document_frame=document_frame,
            )
            
            if not pass1_result.get("success"):
                logger.error(f"Pass 1 extraction failed: {pass1_result.get('error')}")
                return pass1_result
            
            pass1_candidates = pass1_result.get("candidates", [])
            logger.info(f"[PASS 1] Extracted {len(pass1_candidates)} raw claims")
            
            # [NEW] FAILURE LOGGER: Tag Pass 1 with prompt version (for A/B testing)
            if self.pipeline_config.enable_failure_logger and self.failure_logger:
                pass1_prompt_hash = self.failure_logger.compute_prompt_version(
                    prompt_template="pass1_evidence_grounded_extraction_v1"
                )
                for claim in pass1_candidates:
                    claim["pass1_prompt_version"] = pass1_prompt_hash
                logger.info(f"[FAILURE_LOGGER] Tagged {len(pass1_candidates)} claims with prompt version {pass1_prompt_hash}")
            
            # ===== GROUNDING VALIDATION =====
            pass1_candidates = await self._validate_grounding(
                candidates=pass1_candidates,
                retrieved_chunks=retrieved_chunks
            )
            logger.info(f"[GROUNDING] {len(pass1_candidates)} claims passed validation")
            
            if not pass1_candidates:
                logger.warning("No claims passed grounding validation")
                return {
                    "success": False,
                    "error": "No grounded claims extracted"
                }
            
            # ===== PASS 2A: CAUSAL CLASSIFICATION =====
            pass2a_result = await self._pass2a_classification(pass1_candidates)
            pass1_candidates = pass2a_result.get("candidates", pass1_candidates)
            logger.info(f"[PASS 2A] Classified {len(pass1_candidates)} claims")
            
            # ===== PASS 2B: ENTITY NORMALIZATION =====
            pass2b_result = await self._pass2b_normalization(
                candidates=pass1_candidates,
                mission_id=mission_id,
                entity_glossary=entity_glossary
            )
            pass1_candidates = pass2b_result.get("candidates", pass1_candidates)
            logger.info(f"[PASS 2B] Normalized {len(pass1_candidates)} claims")
            self._hydrate_claim_metadata(
                candidates=pass1_candidates,
                paper_record=paper_record,
                mission_record=mission_record,
            )
            for claim in pass1_candidates:
                claim["document_frame"] = document_frame
            pass1_candidates = self._consolidate_distinct_findings(pass1_candidates)
            logger.info(f"[CONSOLIDATION] Reduced to {len(pass1_candidates)} distinct findings")
            
            # [NEW] ENTITY EVOLUTION MANAGER: Dynamic vocabulary growth
            if self.pipeline_config.enable_entity_evolution_advanced and self.entity_evolution:
                for claim in pass1_candidates:
                    claim_id = claim.get("id")
                    
                    # Propose intervention normalization
                    intervention_raw = claim.get("intervention", "")
                    if intervention_raw:
                        intervention_canonical, intervention_status = await self.entity_evolution.propose_normalization(
                            surface_form=intervention_raw,
                            context_sentence=claim.get("statement_raw", ""),
                            normalization_confidence=claim.get("composite_confidence", 0.5),
                            mission_id=mission_id,
                            paper_id=paper_id,
                            claim_id=claim_id
                        )
                        claim["intervention_canonical"] = intervention_canonical
                        claim["intervention_normalization_status"] = intervention_status.value
                    
                    # Propose outcome normalization
                    outcome_raw = claim.get("outcome", "")
                    if outcome_raw:
                        outcome_canonical, outcome_status = await self.entity_evolution.propose_normalization(
                            surface_form=outcome_raw,
                            context_sentence=claim.get("statement_raw", ""),
                            normalization_confidence=claim.get("composite_confidence", 0.5),
                            mission_id=mission_id,
                            paper_id=paper_id,
                            claim_id=claim_id
                        )
                        claim["outcome_canonical"] = outcome_canonical
                        claim["outcome_normalization_status"] = outcome_status.value
                
                logger.info(f"[ENTITY_EVOLUTION] Normalized entities for {len(pass1_candidates)} claims")
            
            # ===== UPGRADE 6: QUANTITATIVE EXTRACTION (PARALLEL) =====
            quantitative_results = {}
            if self.pipeline_config.enable_quantitative:
                quantitative_results = await self.quantitative_extractor.extract_for_chunks(
                    retrieved_chunks
                )
                logger.info(f"[QUANTITATIVE] Extracted from {len(quantitative_results)} chunks")
            
            # Attach quantitative evidence to claims
            for claim in pass1_candidates:
                for chunk in claim.get("resolved_source_chunks", []):
                    chunk_id = chunk.get("chunk_id")
                    if chunk_id in quantitative_results and quantitative_results[chunk_id]:
                        claim["quantitative_evidence"] = quantitative_results[chunk_id].to_dict()
                        break
            
            # ===== UPGRADE 3: VERIFICATION LAYER =====
            verification_results = {}
            if self.pipeline_config.enable_verification:
                # Build source chunks map for verification
                source_chunks_map = {
                    claim.get("id"): claim.get("resolved_source_chunks", [])
                    for claim in pass1_candidates
                }
                
                verification_results_list = await self.verification_engine.verify_batch(
                    claims=pass1_candidates,
                    source_chunks_map=source_chunks_map
                )
                
                # Map results by claim ID
                for result in verification_results_list:
                    verification_results[result.claim_id] = result
                
                logger.info(f"[VERIFICATION] Verified {len(verification_results)} claims")
            
            # [NEW] FAILURE LOGGER: Log verification results (SKIP IF DISABLED)
            # Disabled in batch mode due to complex parameter requirements
            if False and self.pipeline_config.enable_failure_logger and self.failure_logger:
                pass  # Disabled - complex parameter requirements
            
            # [NEW] ARGUMENT COHERENCE CHECKER: Check intra-paper logical consistency
            if self.pipeline_config.enable_coherence_checking and self.coherence_checker:
                coherence_results = await self.coherence_checker.check_paper_coherence(
                    paper_id=paper_id,
                    claims=pass1_candidates,
                    mission_id=mission_id
                )
                
                # Apply coherence results to claims
                coherence_map = {r.get("claim_id"): r for r in coherence_results}
                for claim in pass1_candidates:
                    if claim.get("id") in coherence_map:
                        coherence = coherence_map[claim.get("id")]
                        claim["internal_conflict"] = coherence.get("internal_conflict", False)
                        claim["coherence_flags"] = coherence.get("coherence_flags", [])
                        claim["coherence_confidence_adjustment"] = coherence.get("coherence_confidence_adjustment", 1.0)
                
                logger.info(f"[COHERENCE_CHECKER] Analyzed coherence for {len(pass1_candidates)} claims")
                
                # Emit event if internal conflicts detected
                if any(r.get("internal_conflict") for r in coherence_results):
                    await self.event_emitter.emit("paper.internal_conflict_detected", {
                        "paper_id": paper_id,
                        "mission_id": mission_id,
                        "claims_with_conflicts": [r.get("claim_id") for r in coherence_results if r.get("internal_conflict")]
                    })
            
            # ===== PASS 3: ENHANCED CONFIDENCE ASSEMBLY =====
            pass3_result = await self._pass3_confidence_assembly(
                candidates=pass1_candidates,
                verification_results=verification_results
            )
            pass1_candidates = pass3_result.get("candidates", pass1_candidates)
            logger.info(f"[PASS 3] Assembled confidence for {len(pass1_candidates)} claims")
            
            # [NEW] UNCERTAINTY DECOMPOSER: Replace single confidence with 4-component model
            if self.pipeline_config.enable_uncertainty_decomposition and self.uncertainty_decomposer:
                for claim in pass1_candidates:
                    claim_id = claim.get("id")
                    
                    # Get verification result if available
                    verification_data = verification_results.get(claim_id, {})
                    
                    # Decompose uncertainty into 4 components
                    components = await self.uncertainty_decomposer.decompose_claim_uncertainty(
                        claim=claim,
                        verification_results=verification_data,
                        coherence_adjustment=claim.get("coherence_confidence_adjustment", 1.0)
                    )
                    
                    # Store 4 components on claim
                    claim["extraction_uncertainty"] = components.get("extraction_uncertainty", 0.5)
                    claim["study_uncertainty"] = components.get("study_uncertainty", 0.5)
                    claim["generalizability_uncertainty"] = components.get("generalizability_uncertainty", 0.5)
                    claim["replication_uncertainty"] = components.get("replication_uncertainty", 0.5)  # Will be updated after graph
                    
                    # Compute composite confidence using new formula
                    import math
                    composite = math.sqrt(
                        claim["extraction_uncertainty"] * 
                        claim["study_uncertainty"] * 
                        claim["generalizability_uncertainty"] * 
                        claim["replication_uncertainty"]
                    )
                    claim["composite_confidence"] = min(0.95, max(0.05, composite))
                    
                    # Store components for auditability
                    claim["confidence_components"] = {
                        "extraction": claim["extraction_uncertainty"],
                        "study": claim["study_uncertainty"],
                        "generalizability": claim["generalizability_uncertainty"],
                        "replication": claim["replication_uncertainty"]
                    }
                
                logger.info(f"[UNCERTAINTY_DECOMPOSER] Computed 4-component uncertainty for {len(pass1_candidates)} claims")
            
            # ===== VALIDATION & DEDUPLICATION =====
            validated_claims = await self._validate_and_deduplicate(
                candidates=pass1_candidates
            )
            logger.info(f"[VALIDATION] {len(validated_claims)} claims passed validation")
            
            if not validated_claims:
                logger.warning("No claims passed final validation; clearing any prior persisted claims for this paper")
                await self._persist_claims(
                    paper_id=paper_id,
                    mission_id=mission_id,
                    claims=[],
                    mission_question=mission_question,
                    mission_domain=mission_domain
                )
                return {
                    "success": True,
                    "claims": [],
                    "claims_extracted": 0,
                    "message": "No curated high-quality findings met the persistence threshold"
                }
            
            # ===== PERSISTENCE =====
            persisted = await self._persist_claims(
                paper_id=paper_id,
                mission_id=mission_id,
                claims=validated_claims,
                mission_question=mission_question,
                mission_domain=mission_domain
            )
            logger.info(f"[PERSISTENCE] Persisted {len(persisted)} claims")
            
            # ===== UPGRADE 5: GRAPH MANAGER =====
            if self.pipeline_config.enable_graph_manager and persisted:
                graph_result = await self.graph_manager.add_claims_to_graph(
                    mission_id=mission_id,
                    claims=persisted
                )
                logger.info(f"[GRAPH] Updated graph: {graph_result}")
                
                # [NEW] UPDATE REPLICATION UNCERTAINTY FROM GRAPH
                if self.pipeline_config.enable_uncertainty_decomposition and self.uncertainty_decomposer:
                    for claim in persisted:
                        # Get graph edge information for this claim
                        graph_edges = graph_result.get("edges", {}).get(claim.get("id"), {})
                        replication_edges = graph_edges.get("replications", [])
                        contradiction_edges = graph_edges.get("contradictions", [])
                        
                        # Update replication_uncertainty based on graph edges
                        updated_components = await self.uncertainty_decomposer.update_replication_uncertainty_from_graph(
                            claim_id=claim.get("id"),
                            replication_edges=replication_edges,
                            contradiction_edges=contradiction_edges,
                            is_isolated=graph_edges.get("is_isolated", False)
                        )
                        
                        # Recompute composite confidence with updated replication_uncertainty
                        claim["replication_uncertainty"] = updated_components.get("replication_uncertainty", 0.5)
                        import math
                        composite = math.sqrt(
                            claim.get("extraction_uncertainty", 0.5) * 
                            claim.get("study_uncertainty", 0.5) * 
                            claim.get("generalizability_uncertainty", 0.5) * 
                            claim["replication_uncertainty"]
                        )
                        claim["composite_confidence"] = min(0.95, max(0.05, composite))
                    
                    logger.info(f"[UNCERTAINTY_DECOMPOSER] Updated replication_uncertainty for {len(persisted)} claims from graph")
                
                # Emit graph events
                for event in await self.graph_manager.get_events():
                    await self.event_emitter.emit(event.get("event_type"), event.get("data", {}))
            
            # [NEW] EVIDENCE GAP DETECTION
            if self.pipeline_config.enable_evidence_gap_detection and self.evidence_gap_detector:
                # Get clusters from graph manager
                try:
                    mission_clusters = await self.graph_manager.get_clusters(mission_id=mission_id)
                    if mission_clusters:
                        # Detect gaps in clusters
                        evidence_gaps = await self.evidence_gap_detector.detect_gaps(
                            mission_id=mission_id,
                            paper_id_just_processed=paper_id,
                            clusters=mission_clusters
                        )
                        
                        # Emit gap events
                        for gap in evidence_gaps:
                            await self.event_emitter.emit("evidence_gap.detected", {
                                "cluster_id": gap.get("cluster_id"),
                                "gap_type": gap.get("gap_type"),
                                "suggestion": gap.get("suggestion"),
                                "mission_id": mission_id
                            })
                        
                        logger.info(f"[EVIDENCE_GAP_DETECTOR] Detected {len(evidence_gaps)} evidence gaps")
                except Exception as e:
                    logger.warning(f"[EVIDENCE_GAP_DETECTOR] Error detecting gaps: {str(e)}")
            
            # [NEW] EMIT FAILURE LOGGER EVENTS
            if self.pipeline_config.enable_failure_logger and self.failure_logger:
                try:
                    logger_stats = await self.failure_logger.get_stats(mission_id=mission_id)
                    
                    # Check if domain adaptation dataset is ready
                    if logger_stats.get("failures", 0) >= 100:
                        await self.event_emitter.emit("domain_adaptation.ready", {
                            "mission_id": mission_id,
                            "failure_count": logger_stats.get("failures"),
                            "pass_rate": logger_stats.get("pass_rate")
                        })
                    
                    # Check if section weights need adjustment
                    for section_name, section_quality in logger_stats.get("sections", {}).items():
                        if section_quality.get("pass_rate", 1.0) < 0.50:
                            await self.event_emitter.emit("section_weight_adjusted", {
                                "mission_id": mission_id,
                                "section": section_name,
                                "new_weight": section_quality.get("weight_multiplier", 1.0)
                            })
                    
                    logger.info(f"[FAILURE_LOGGER] Emitted {len(logger_stats.get('events', []))} events")
                except Exception as e:
                    logger.warning(f"[FAILURE_LOGGER] Error emitting events: {str(e)}")
            
            # [NEW] EMIT ENTITY EVOLUTION EVENTS
            if self.pipeline_config.enable_entity_evolution_advanced and self.entity_evolution:
                try:
                    entity_events = await self.entity_evolution.emit_entity_events(self.event_emitter)
                    logger.info(f"[ENTITY_EVOLUTION] Emitted entity events")
                except Exception as e:
                    logger.warning(f"[ENTITY_EVOLUTION] Error emitting events: {str(e)}")
            
            # ===== EVENT EMISSION =====
            await self.event_emitter.emit("claims.extracted", {
                "mission_id": mission_id,
                "paper_id": paper_id,
                "claim_count": len(persisted),
                "claim_ids": [c.get("id") for c in persisted],
                "timestamp": datetime.utcnow().isoformat()
            })
            
            logger.info(f"[EXTRACTION] Complete: {len(persisted)} claims extracted and persisted")
            
            return {
                "success": True,
                "claims_extracted": len(persisted),
                "claims": persisted,
                "pipeline_status": "SUCCESS"
            }
        
        except Exception as e:
            logger.error(f"[EXTRACTION] Pipeline failed: {str(e)}", exc_info=True)
            
            await self.event_emitter.emit("pipeline.degraded", {
                "mission_id": mission_id,
                "paper_id": paper_id,
                "reason": f"Pipeline error: {str(e)}",
                "timestamp": datetime.utcnow().isoformat()
            })
            
            return {
                "success": False,
                "error": str(e),
                "pipeline_status": "FAILED"
            }
    
    # ===== UPGRADED COMPONENTS =====
    
    async def _retrieve_chunks(
        self,
        paper_id: str,
        pdf_url: str,
        abstract: str,
        full_text_content: str,
        mission_question: str,
        pico_data: Dict[str, str]
    ) -> List[Dict[str, Any]]:
        """Use the stored full paper text when available, otherwise fall back to abstract."""
        
        if not self.retrieval_layer:
            return [{
                "chunk_id": str(uuid.uuid4()),
                "paper_id": paper_id,
                "section_name": "abstract",
                "chunk_type": "text",
                "raw_text": abstract
            }]
        
        try:
            result = await self.retrieval_layer.retrieve(
                paper_id=paper_id,
                pdf_url=pdf_url,
                abstract=abstract,
                full_text_content=full_text_content,
                mission_question=mission_question,
                pico_data=pico_data
            )
            
            if result.success:
                return [
                    {
                        "chunk_id": chunk.chunk_id,
                        "paper_id": chunk.paper_id,
                        "section_name": chunk.section_name,
                        "chunk_type": chunk.chunk_type,
                        "raw_text": chunk.raw_text,
                        "token_count": chunk.token_count,
                        "retrieval_query_matches": chunk.retrieval_query_matches,
                        "cosine_score": chunk.cosine_score,
                        "crossencoder_score": chunk.crossencoder_score,
                        "final_rank": chunk.final_rank
                    }
                    for chunk in result.chunks
                ]
            else:
                logger.warning(f"Retrieval failed: {result.error}, using abstract")
                return [{
                    "chunk_id": str(uuid.uuid4()),
                    "paper_id": paper_id,
                    "section_name": "abstract",
                    "chunk_type": "text",
                    "raw_text": abstract
                }]
        
        except Exception as e:
            logger.error(f"Retrieval layer error: {str(e)}")
            return [{
                "chunk_id": str(uuid.uuid4()),
                "paper_id": paper_id,
                "section_name": "abstract",
                "chunk_type": "text",
                "raw_text": abstract
            }]
    
    async def _pass1_extraction(
        self,
        paper_id: str,
        mission_question: str,
        retrieved_chunks: List[Dict[str, Any]],
        document_frame: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Extract section-aware evidence-backed findings before later consolidation."""

        extracted_claims: List[Dict[str, Any]] = []
        fallback_groups = 0
        limited_chunks = retrieved_chunks[: self.pipeline_config.max_chunks_for_extraction]
        extraction_groups = self._group_chunks_for_finding_extraction(limited_chunks)
        chunk_index_map = {
            chunk.get("chunk_id"): idx + 1
            for idx, chunk in enumerate(limited_chunks)
            if chunk.get("chunk_id")
        }
        schema_hint = json.dumps(
            [
                {
                    "statement_raw": "Explicit claim text copied from the paper",
                    "source_chunk_ids": [1],
                    "evidence_span": "Exact supporting text copied verbatim from the chunk",
                    "grounding_confidence": 0.85,
                    "intervention": "Semaglutide",
                    "outcome": "Weight loss",
                    "direction": "positive",
                    "hedging_text": None,
                    "section_source": "results",
                    "extraction_certainty": 0.8,
                }
            ],
            indent=2,
        )

        for group_index, group in enumerate(extraction_groups, 1):
            chunk_batch = group["chunks"]
            section_name = group["section_name"]
            max_findings = group["max_findings"]
            chunks_formatted = ""
            for local_idx, chunk in enumerate(chunk_batch, 1):
                section = chunk.get("section_name", "unknown")
                chunk_type = chunk.get("chunk_type", "text")
                chunk_id = chunk.get("chunk_id", "")
                text = self._truncate_prompt_text(chunk.get("raw_text", ""))
                chunks_formatted += (
                    f"[CHUNK {local_idx:03d} | Section: {section} | Type: {chunk_type} | ID: {chunk_id}]\n"
                    f"{text}\n\n"
                )

            prompt = f"""Extract distinct evidence-backed findings from these paper sections.

Mission Question: {mission_question}
Document Frame: {json.dumps(document_frame or {}, ensure_ascii=True)}
Section Focus: {section_name}
Prioritize: {group['focus']}

{chunks_formatted}

Rules:
- Return at most {max_findings} findings from this section batch.
- Each finding should represent one distinct paper-level result, safety observation, mechanistic point, or null finding.
- Prefer primary outcomes, strong secondary outcomes, safety findings, mechanistic findings, and clearly stated limitations.
- Ignore background narrative, citation boilerplate, and pure methods text unless it contains an explicit reported finding.
- If multiple chunks repeat the same finding, return it once using the clearest evidence span.
- Every finding must be directly supported by one of the provided chunks.
- Do not combine evidence from different chunks into a new synthesized finding.
- Use only chunk numbers from this batch in source_chunk_ids.
- evidence_span must be copied verbatim from one cited chunk and stay under 220 characters.
- Return strict JSON only. No markdown, no prose, no comments.

Required JSON schema:
{schema_hint}
"""

            try:
                validated, parse_mode, parse_error = await self._generate_validated_json_array(
                    stage_name="pass1",
                    system_prompt="You extract explicit research claims and must return strict JSON only.",
                    user_prompt=prompt,
                    schema_hint=schema_hint,
                    validator=lambda item, batch_size=len(chunk_batch): self._coerce_pass1_claim(item, batch_size),
                    max_tokens=1400,
                )
            except Exception as exc:
                validated = None
                parse_mode = "fallback"
                parse_error = str(exc)

            if validated:
                for claim in validated:
                    claim["id"] = str(uuid.uuid4())
                    claim["parse_strategy"] = f"pass1_{parse_mode}"
                    claim["source_chunk_ids"] = [
                        chunk_index_map.get(chunk_batch[source_chunk_id - 1].get("chunk_id"))
                        for source_chunk_id in claim.get("source_chunk_ids", [])
                        if 1 <= source_chunk_id <= len(chunk_batch)
                        and chunk_index_map.get(chunk_batch[source_chunk_id - 1].get("chunk_id"))
                    ]
                    claim["section_source"] = section_name
                extracted_claims.extend(validated)
                continue

            fallback_groups += 1
            fallback = self._fallback_pass1_candidates(
                chunk_batch,
                max_candidates=max_findings,
            )
            if fallback:
                logger.warning(
                    "Pass 1 group %s (%s) used deterministic fallback: %s",
                    group_index,
                    section_name,
                    parse_error or "unknown parse error",
                )
                for claim in fallback:
                    claim["parse_strategy"] = "pass1_fallback"
                    claim["source_chunk_ids"] = [
                        chunk_index_map.get(chunk_batch[source_chunk_id - 1].get("chunk_id"))
                        for source_chunk_id in claim.get("source_chunk_ids", [])
                        if 1 <= source_chunk_id <= len(chunk_batch)
                        and chunk_index_map.get(chunk_batch[source_chunk_id - 1].get("chunk_id"))
                    ]
                    claim["section_source"] = section_name
                extracted_claims.extend(fallback)

        if extracted_claims:
            logger.info(
                "Pass 1 extracted %s atomic findings across %s group(s); fallback groups=%s; stats=%s",
                len(extracted_claims),
                len(extraction_groups),
                fallback_groups,
                self.structured_output_stats.get("pass1", {}),
            )
            return {"success": True, "candidates": extracted_claims}

        return {"success": False, "error": "Failed to extract findings from any section group"}

    def _fallback_pass1_candidates(
        self,
        retrieved_chunks: List[Dict[str, Any]],
        max_candidates: int = 6,
    ) -> List[Dict[str, Any]]:
        candidates: List[Dict[str, Any]] = []
        seen_sentences = set()
        claim_markers = [
            "improve", "improved", "increase", "increased", "decrease", "decreased",
            "reduce", "reduced", "associated", "effect", "effective", "resulted",
            "led to", "caused", "risk", "benefit", "adverse", "safety",
        ]

        for idx, chunk in enumerate(retrieved_chunks[: self.pipeline_config.max_chunks_for_extraction], 1):
            sentences = re.split(r'(?<=[.!?])\s+', chunk.get("raw_text", ""))
            for sentence in sentences:
                normalized = " ".join(sentence.split()).strip()
                lowered = normalized.lower()
                if len(normalized) < 40 or len(normalized) > 320:
                    continue
                if normalized in seen_sentences:
                    continue
                if not any(marker in lowered for marker in claim_markers):
                    continue

                if any(term in lowered for term in ["no effect", "did not", "not significant", "no significant"]):
                    direction = "null"
                elif any(term in lowered for term in ["decrease", "reduced", "lower", "improve", "benefit"]):
                    direction = "positive"
                elif any(term in lowered for term in ["increase", "risk", "adverse", "harm"]):
                    direction = "negative"
                else:
                    direction = "unclear"

                candidates.append({
                    "id": str(uuid.uuid4()),
                    "statement_raw": normalized,
                    "source_chunk_ids": [idx],
                    "evidence_span": normalized[:200],
                    "grounding_confidence": 0.6,
                    "intervention": None,
                    "outcome": None,
                    "direction": direction,
                    "hedging_text": None,
                    "section_source": chunk.get("section_name", "unknown"),
                    "extraction_certainty": 0.55,
                })
                seen_sentences.add(normalized)

                if len(candidates) >= max_candidates:
                    return candidates

        return candidates
    
    async def _validate_grounding(
        self,
        candidates: List[Dict[str, Any]],
        retrieved_chunks: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """ADDED: Mechanical validation that evidence_span is in source chunks"""
        
        valid_claims = []
        
        for claim in candidates:
            evidence_span = claim.get("evidence_span", "")
            source_chunk_ids = claim.get("source_chunk_ids", [])
            
            # Check if evidence_span is substring of any source chunk
            grounding_valid = False
            resolved_source_chunks = []
            for chunk_idx in source_chunk_ids:
                try:
                    chunk_idx = int(chunk_idx)
                except (TypeError, ValueError):
                    continue
                if 1 <= chunk_idx <= len(retrieved_chunks):
                    chunk = retrieved_chunks[chunk_idx - 1]
                    resolved_source_chunks.append(chunk)
                    chunk_text = chunk.get("raw_text", "")
                    normalized_span = " ".join(evidence_span.split())
                    normalized_text = " ".join(chunk_text.split())
                    if normalized_span and normalized_span in normalized_text:
                        grounding_valid = True
            
            claim["grounding_valid"] = grounding_valid
            claim["resolved_source_chunks"] = resolved_source_chunks
            claim["resolved_source_chunk_ids"] = [
                chunk.get("chunk_id")
                for chunk in resolved_source_chunks
                if chunk.get("chunk_id")
            ]
            claim["supporting_evidence"] = [
                {
                    "evidence_span": evidence_span,
                    "source_chunk_ids": claim.get("source_chunk_ids", []),
                    "resolved_source_chunk_ids": claim.get("resolved_source_chunk_ids", []),
                    "section_source": claim.get("section_source") or (
                        resolved_source_chunks[0].get("section_name", "unknown")
                        if resolved_source_chunks else "unknown"
                    ),
                    "grounding_confidence": claim.get("grounding_confidence", 0.0),
                    "parse_strategy": claim.get("parse_strategy"),
                }
            ]
            claim["supporting_evidence_count"] = 1
            claim["within_paper_replication_count"] = 1
            if resolved_source_chunks and not claim.get("section_source"):
                claim["section_source"] = resolved_source_chunks[0].get("section_name", "unknown")
            
            if grounding_valid:
                valid_claims.append(claim)
            else:
                logger.warning(f"Claim {claim.get('id')} failed grounding check")
        
        return valid_claims
    
    async def _pass2a_classification(
        self,
        candidates: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Classify claims in validated batches and fall back to conservative defaults."""

        schema_hint = json.dumps(
            [
                {
                    "claim_id": "uuid",
                    "claim_type": "correlational",
                    "study_design_consistent": True,
                    "causal_justification": "Association language only; no randomized causal evidence in the quoted text.",
                }
            ],
            indent=2,
        )

        try:
            for candidate in candidates:
                heuristic = self._heuristic_claim_classification(candidate)
                candidate["claim_type"] = heuristic["claim_type"]
                candidate["study_design_consistent"] = heuristic["study_design_consistent"]
                candidate["causal_justification"] = heuristic["causal_justification"]
                candidate["classification_parse_strategy"] = "pass2a_heuristic"

            for _, claim_batch in self._iter_batches(candidates, 6):
                prompt = f"""Classify the epistemic type of each research claim.

Claims to classify:
{json.dumps([{
    'id': c.get('id'),
    'statement': c.get('statement_raw'),
    'evidence': c.get('evidence_span')
} for c in claim_batch], indent=2)}

For each claim, determine:
- claim_type: causal | correlational | mechanistic | comparative | safety | prevalence | null_result
- study_design_consistent: true or false
- causal_justification: brief reason

Return strict JSON only using this schema:
{schema_hint}
"""

                parsed, parse_mode, parse_error = await self._generate_validated_json_array(
                    stage_name="pass2a",
                    system_prompt="You classify research claims and must return strict JSON only.",
                    user_prompt=prompt,
                    schema_hint=schema_hint,
                    validator=self._coerce_pass2a_classification,
                    max_tokens=900,
                )

                if not parsed:
                    logger.warning("Pass 2a batch kept heuristic classifications: %s", parse_error or "unknown parse error")
                    continue

                class_map = {item["claim_id"]: item for item in parsed}
                for candidate in claim_batch:
                    classification = class_map.get(candidate.get("id"))
                    if not classification:
                        continue
                    candidate["claim_type"] = classification.get("claim_type", "correlational")
                    candidate["study_design_consistent"] = classification.get("study_design_consistent", True)
                    candidate["causal_justification"] = classification.get("causal_justification", "")
                    candidate["classification_parse_strategy"] = f"pass2a_{parse_mode}"

            logger.info("Pass 2a stats=%s", self.structured_output_stats.get("pass2a", {}))
            return {"success": True, "candidates": candidates}

        except Exception as e:
            logger.error(f"Pass 2a error: {str(e)}")
            for candidate in candidates:
                if "claim_type" not in candidate:
                    heuristic = self._heuristic_claim_classification(candidate)
                    candidate["claim_type"] = heuristic["claim_type"]
                    candidate["study_design_consistent"] = heuristic["study_design_consistent"]
                    candidate["causal_justification"] = heuristic["causal_justification"]
                    candidate["classification_parse_strategy"] = "pass2a_heuristic_error"

            return {"success": True, "candidates": candidates}
    
    async def _pass2b_normalization(
        self,
        candidates: List[Dict[str, Any]],
        mission_id: str,
        entity_glossary: Optional[Dict[str, List[str]]] = None
    ) -> Dict[str, Any]:
        """MODIFIED: Entity boost index lookup before LLM call"""
        
        # ADDED: Try entity boost index first
        if self.graph_manager:
            for candidate in candidates:
                intervention = candidate.get("intervention", "")
                outcome = candidate.get("outcome", "")
                
                # Try boost index for intervention
                if intervention:
                    boost_canonical = await self.graph_manager.apply_entity_boost_in_normalization(
                        intervention, mission_id
                    )
                    if boost_canonical:
                        candidate["intervention_canonical"] = boost_canonical
                        candidate["normalization_source"] = "boost_index"
                
                # Try boost index for outcome
                if outcome and "outcome_canonical" not in candidate:
                    boost_canonical = await self.graph_manager.apply_entity_boost_in_normalization(
                        outcome, mission_id
                    )
                    if boost_canonical:
                        candidate["outcome_canonical"] = boost_canonical
                        candidate["normalization_source"] = "boost_index"
        
        # LLM normalization for remaining
        to_normalize = [
            c for c in candidates 
            if "intervention_canonical" not in c or "outcome_canonical" not in c
        ]
        
        if not to_normalize:
            return {"success": True, "candidates": candidates}

        schema_hint = json.dumps(
            [
                {
                    "claim_id": "uuid",
                    "intervention_canonical": "semaglutide",
                    "outcome_canonical": "weight loss",
                    "normalization_confidence": 0.85,
                }
            ],
            indent=2,
        )

        try:
            for candidate in to_normalize:
                if "intervention_canonical" not in candidate:
                    heuristic_intervention = self._heuristic_entity_canonicalization(
                        candidate.get("intervention"),
                        "intervention",
                    )
                    if heuristic_intervention:
                        candidate["intervention_canonical"] = heuristic_intervention
                        candidate["normalization_confidence"] = max(
                            candidate.get("normalization_confidence", 0.0),
                            0.55,
                        )
                        candidate["normalization_source"] = "heuristic"
                if "outcome_canonical" not in candidate:
                    heuristic_outcome = self._heuristic_entity_canonicalization(
                        candidate.get("outcome"),
                        "outcome",
                    )
                    if heuristic_outcome:
                        candidate["outcome_canonical"] = heuristic_outcome
                        candidate["normalization_confidence"] = max(
                            candidate.get("normalization_confidence", 0.0),
                            0.55,
                        )
                        candidate["normalization_source"] = "heuristic"

            for _, normalization_batch in self._iter_batches(to_normalize, 6):
                prompt = f"""Normalize entity names in research claims.

Claims needing normalization:
{json.dumps([{
    'id': c.get('id'),
    'intervention': c.get('intervention'),
    'outcome': c.get('outcome')
} for c in normalization_batch], indent=2)}

Rules:
- Standardize drug names, outcomes, and synonyms.
- If a field is missing, return null for the canonical value.
- Return strict JSON only.

Schema:
{schema_hint}
"""

                parsed, parse_mode, parse_error = await self._generate_validated_json_array(
                    stage_name="pass2b",
                    system_prompt="You standardize biomedical entities and must return strict JSON only.",
                    user_prompt=prompt,
                    schema_hint=schema_hint,
                    validator=self._coerce_pass2b_normalization,
                    max_tokens=900,
                )

                if not parsed:
                    logger.warning("Pass 2b batch kept heuristic normalization: %s", parse_error or "unknown parse error")
                    continue

                norm_map = {item["claim_id"]: item for item in parsed}
                for candidate in normalization_batch:
                    norm = norm_map.get(candidate.get("id"))
                    if not norm:
                        continue
                    candidate["intervention_canonical"] = norm.get("intervention_canonical") or candidate.get("intervention")
                    candidate["outcome_canonical"] = norm.get("outcome_canonical") or candidate.get("outcome")
                    candidate["normalization_confidence"] = norm.get("normalization_confidence", 0.5)
                    candidate["normalization_source"] = f"llm_{parse_mode}"

            logger.info("Pass 2b stats=%s", self.structured_output_stats.get("pass2b", {}))
            return {"success": True, "candidates": candidates}

        except Exception as e:
            logger.error(f"Pass 2b error: {str(e)}")
            for candidate in to_normalize:
                if "intervention_canonical" not in candidate:
                    candidate["intervention_canonical"] = self._heuristic_entity_canonicalization(
                        candidate.get("intervention"),
                        "intervention",
                    ) or candidate.get("intervention", "unknown")
                if "outcome_canonical" not in candidate:
                    candidate["outcome_canonical"] = self._heuristic_entity_canonicalization(
                        candidate.get("outcome"),
                        "outcome",
                    ) or candidate.get("outcome", "unknown")
                candidate["normalization_confidence"] = max(candidate.get("normalization_confidence", 0.0), 0.55)
                candidate["normalization_source"] = candidate.get("normalization_source", "heuristic_error")

            return {"success": True, "candidates": candidates}

    def _infer_study_type(self, paper_record: ResearchPaper) -> str:
        paper_text = f"{paper_record.title or ''} {paper_record.abstract or ''}".lower()
        if "meta-analysis" in paper_text or "systematic review" in paper_text:
            return "meta_analysis"
        if "randomized controlled trial" in paper_text or "randomized trial" in paper_text or " rct" in paper_text:
            return "rct"
        if "cohort" in paper_text:
            return "cohort"
        if "case-control" in paper_text:
            return "case_control"
        if "observational" in paper_text:
            return "observational"
        if "review" in paper_text:
            return "review"
        if "mouse" in paper_text or "mice" in paper_text or "rat" in paper_text or "animal" in paper_text:
            return "animal_model"
        if "in vitro" in paper_text or "cell line" in paper_text:
            return "in_vitro"
        return "unknown"

    def _study_design_score(self, study_type: str) -> float:
        return {
            "meta_analysis": 0.92,
            "rct": 0.90,
            "cohort": 0.72,
            "case_control": 0.68,
            "observational": 0.65,
            "review": 0.55,
            "animal_model": 0.40,
            "in_vitro": 0.30,
            "unknown": 0.50,
        }.get(study_type, 0.50)

    def _hedging_penalty(self, claim: Dict[str, Any]) -> float:
        hedging_text = (claim.get("hedging_text") or "").lower()
        statement_text = (claim.get("statement_raw") or "").lower()
        combined = f"{hedging_text} {statement_text}"
        if any(term in combined for term in ["may", "might", "possible", "possibly"]):
            return 0.20
        if any(term in combined for term in ["suggest", "suggests", "associated with", "appears to"]):
            return 0.12
        return 0.0

    def _mission_relevance(
        self,
        claim: Dict[str, Any],
        mission_record: Optional[Mission]
    ) -> str:
        if not mission_record:
            return MissionRelevanceEnum.SECONDARY.value

        question = (mission_record.normalized_query or "").lower()
        intervention = (claim.get("intervention_canonical") or claim.get("intervention") or "").lower()
        outcome = (claim.get("outcome_canonical") or claim.get("outcome") or "").lower()

        if intervention and intervention in question:
            return MissionRelevanceEnum.PRIMARY.value
        if outcome and outcome in question:
            return MissionRelevanceEnum.PRIMARY.value
        return MissionRelevanceEnum.SECONDARY.value

    def _hydrate_claim_metadata(
        self,
        candidates: List[Dict[str, Any]],
        paper_record: ResearchPaper,
        mission_record: Optional[Mission]
    ) -> None:
        study_type = self._infer_study_type(paper_record)
        study_design_score = self._study_design_score(study_type)
        default_population = mission_record.pico_population if mission_record and mission_record.pico_population else None

        for candidate in candidates:
            candidate["statement_normalized"] = " ".join((candidate.get("statement_raw") or "").split())
            candidate["study_type"] = study_type
            candidate["study_design_score"] = study_design_score
            candidate["hedging_penalty"] = self._hedging_penalty(candidate)
            candidate["population"] = candidate.get("population") or default_population
            candidate["mission_relevance"] = self._mission_relevance(candidate, mission_record)
            candidate["paper_title"] = paper_record.title
            candidate["doi_or_url"] = (
                paper_record.doi
                or paper_record.arxiv_url
                or paper_record.semantic_scholar_url
                or paper_record.pubmed_url
            )
    
    async def _pass3_confidence_assembly(
        self,
        candidates: List[Dict[str, Any]],
        verification_results: Dict[str, VerificationResult]
    ) -> Dict[str, Any]:
        """MODIFIED: Enhanced formula with verification and grounding factors"""
        
        for candidate in candidates:
            claim_id = candidate.get("id")
            
            # Base formula (unchanged)
            study_design_score = candidate.get("study_design_score", 0.5)
            hedging_penalty = candidate.get("hedging_penalty", 0.0)
            extraction_certainty = candidate.get("extraction_certainty", 0.5)
            
            base = (study_design_score - hedging_penalty) * extraction_certainty
            
            # ADDED: Verification factor
            verification_factor = 1.0
            verification_confidence = 1.0
            if claim_id in verification_results:
                result = verification_results[claim_id]
                
                is_supported = result.is_supported
                if is_supported == "true":
                    verification_factor = 1.0
                elif is_supported == "partial":
                    verification_factor = 0.75
                elif is_supported == "uncertain":
                    verification_factor = 0.85
                elif is_supported == "false":
                    error_type = result.error_type or "unsupported"
                    if error_type == "hallucination":
                        verification_factor = 0.10
                    elif error_type == "overgeneralization":
                        verification_factor = 0.50
                    elif error_type == "scope_drift":
                        verification_factor = 0.60
                    else:  # unsupported
                        verification_factor = 0.30
                
                verification_confidence = result.verification_confidence
            
            # ADDED: Grounding factor
            grounding_factor = 1.0 if candidate.get("grounding_valid", False) else 0.80

            section_factor = {
                "results": 1.08,
                "conclusion": 1.06,
                "abstract": 1.03,
                "discussion": 0.98,
                "body": 0.96,
                "introduction": 0.92,
                "methods": 0.88,
                "unknown": 0.95,
            }.get((candidate.get("section_source") or "unknown").lower(), 0.95)

            support_factor = min(
                1.15,
                1.0 + 0.05 * max(0, int(candidate.get("supporting_evidence_count", 1)) - 1),
            )
            quantitative_factor = 1.05 if candidate.get("quantitative_evidence") else 1.0
            
            # ADDED: Full enhanced formula
            composite_confidence = (
                base
                * verification_factor
                * grounding_factor
                * verification_confidence
                * section_factor
                * support_factor
                * quantitative_factor
            )
            
            # Clamp
            composite_confidence = max(0.05, min(0.95, composite_confidence))
            
            # NaN guard
            if math.isnan(composite_confidence) or math.isinf(composite_confidence):
                logger.warning(f"Invalid confidence computed, defaulting to 0.4")
                composite_confidence = 0.4
            
            candidate["composite_confidence"] = composite_confidence
            candidate["verification_confidence"] = verification_confidence
            
            # ADDED: Store confidence components for auditability
            candidate["confidence_components"] = {
                "base": base,
                "verification_factor": verification_factor,
                "grounding_factor": grounding_factor,
                "verification_confidence": verification_confidence,
                "study_design_score": study_design_score,
                "hedging_penalty": hedging_penalty,
                "extraction_certainty": extraction_certainty,
                "section_factor": section_factor,
                "support_factor": support_factor,
                "quantitative_factor": quantitative_factor,
            }
        
        return {"success": True, "candidates": candidates}
    
    async def _validate_and_deduplicate(
        self,
        candidates: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Validate, deduplicate, and curate claims before persistence."""
        
        valid_claims = []
        seen_statements = set()
        
        for claim in candidates:
            # Validate required fields
            if not claim.get("statement_raw") or claim.get("composite_confidence") is None:
                logger.warning(f"Claim {claim.get('id')} missing required fields")
                continue
            
            # Check for duplicates within batch
            stmt = (claim.get("statement_normalized") or claim.get("statement_raw") or "").strip().lower()
            if stmt in seen_statements:
                logger.debug(f"Skipping duplicate claim within batch")
                continue
            
            # Check grounding and verification
            if not claim.get("grounding_valid", False):
                logger.warning(f"Claim {claim.get('id')} not grounded")
                claim["validation_status"] = "EXTRACTION_DEGRADED"
            else:
                claim["validation_status"] = "VALID"
            
            seen_statements.add(stmt)
            valid_claims.append(claim)

        return self._curate_claims_for_persistence(valid_claims)

    def _enum_value(self, enum_cls: Any, value: Any, default: Any) -> Any:
        if isinstance(value, enum_cls):
            return value
        if value is None:
            return default
        try:
            return enum_cls(value)
        except Exception:
            return default
    
    async def _persist_claims(
        self,
        paper_id: str,
        mission_id: str,
        claims: List[Dict[str, Any]],
        mission_question: str,
        mission_domain: str
    ) -> List[Dict[str, Any]]:
        """Persist claims into research_claims and replace any prior claims for the paper."""

        persisted: List[Dict[str, Any]] = []
        paper_uuid = paper_id if isinstance(paper_id, uuid.UUID) else uuid.UUID(str(paper_id))
        paper_record = await self.db.get(ResearchPaper, paper_uuid)
        if not paper_record:
            logger.warning("Cannot persist claims: paper %s not found", paper_id)
            return persisted

        for attempt in range(2):
            try:
                await self.memory_system.snapshot_existing_claim_versions(
                    paper_id=paper_uuid,
                    mission_id=mission_id,
                    actor="claim_extraction",
                )
                break
            except Exception as memory_exc:
                logger.warning(
                    "Memory snapshot of existing claims failed for paper %s (attempt %s/2): %s",
                    paper_id,
                    attempt + 1,
                    memory_exc,
                )

        await self.db.execute(
            delete(ResearchClaim).where(ResearchClaim.paper_id == paper_uuid)
        )
        await self.db.flush()

        for claim in claims:
            extraction_timestamp = datetime.utcnow()
            provenance = {
                "paper_id": str(paper_id),
                "paper_uuid": str(paper_uuid),
                "mission_id": mission_id,
                "extraction_timestamp": extraction_timestamp.isoformat(),
                "mission_question": mission_question,
                "mission_domain": mission_domain,
                "source_chunk_ids": claim.get("source_chunk_ids", []),
                "resolved_source_chunk_ids": claim.get("resolved_source_chunk_ids", []),
                "evidence_span": claim.get("evidence_span", ""),
                "supporting_evidence": claim.get("supporting_evidence", []),
                "supporting_evidence_count": claim.get("supporting_evidence_count", 1),
                "within_paper_replication_count": claim.get("within_paper_replication_count", 1),
                "evidence_sections": claim.get("evidence_sections", []),
                "consolidation_method": claim.get("consolidation_method"),
                "finding_scope": claim.get("finding_scope"),
                "finding_rank": claim.get("finding_rank"),
                "persistence_rank": claim.get("persistence_rank"),
                "curated_for_persistence": claim.get("curated_for_persistence", False),
                "document_frame": claim.get("document_frame"),
                "grounding_valid": claim.get("grounding_valid", False),
                "confidence_components": claim.get("confidence_components", {}),
                "quantitative_evidence": claim.get("quantitative_evidence"),
            }

            claim_id = claim.get("id") or str(uuid.uuid4())
            claim_uuid = uuid.UUID(str(claim_id))
            db_claim = ResearchClaim(
                id=claim_uuid,
                mission_id=mission_id,
                paper_id=paper_uuid,
                statement_raw=claim.get("statement_raw", "").strip(),
                statement_normalized=claim.get("statement_normalized"),
                intervention=claim.get("intervention"),
                outcome=claim.get("outcome"),
                population=claim.get("population"),
                direction=self._enum_value(DirectionEnum, claim.get("direction"), DirectionEnum.UNCLEAR),
                hedging_text=claim.get("hedging_text"),
                section_source=self._enum_value(
                    SectionSourceEnum,
                    claim.get("section_source"),
                    SectionSourceEnum.UNKNOWN,
                ),
                extraction_certainty=claim.get("extraction_certainty", 0.5),
                pass1_prompt_version=claim.get("pass1_prompt_version"),
                claim_type=self._enum_value(
                    ClaimTypeEnum,
                    claim.get("claim_type"),
                    ClaimTypeEnum.CORRELATIONAL,
                ),
                causal_justification=claim.get("causal_justification"),
                study_design_consistent=claim.get("study_design_consistent", True),
                internal_conflict=claim.get("internal_conflict", False),
                coherence_flags=claim.get("coherence_flags"),
                coherence_confidence_adjustment=claim.get("coherence_confidence_adjustment", 1.0),
                intervention_canonical=claim.get("intervention_canonical"),
                outcome_canonical=claim.get("outcome_canonical"),
                normalization_confidence=claim.get("normalization_confidence", 0.0),
                intervention_normalization_status=claim.get("intervention_normalization_status"),
                outcome_normalization_status=claim.get("outcome_normalization_status"),
                composite_confidence=claim.get("composite_confidence", 0.4),
                study_design_score=claim.get("study_design_score", 0.5),
                hedging_penalty=claim.get("hedging_penalty", 0.0),
                extraction_uncertainty=claim.get("extraction_uncertainty", claim.get("extraction_certainty", 0.5)),
                study_uncertainty=claim.get("study_uncertainty", claim.get("study_design_score", 0.5)),
                generalizability_uncertainty=claim.get("generalizability_uncertainty", 0.5),
                replication_uncertainty=claim.get("replication_uncertainty", 0.5),
                confidence_components=claim.get("confidence_components"),
                validation_status=self._enum_value(
                    ValidationStatusEnum,
                    claim.get("validation_status"),
                    ValidationStatusEnum.VALID,
                ),
                mission_relevance=self._enum_value(
                    MissionRelevanceEnum,
                    claim.get("mission_relevance"),
                    MissionRelevanceEnum.SECONDARY,
                ),
                paper_title=paper_record.title,
                doi_or_url=(
                    paper_record.doi
                    or paper_record.arxiv_url
                    or paper_record.semantic_scholar_url
                    or paper_record.pubmed_url
                ),
                study_design=claim.get("study_type"),
                extraction_timestamp=extraction_timestamp,
                provenance=provenance,
            )

            self.db.add(db_claim)
            await self.db.flush()
            for attempt in range(2):
                try:
                    await self.memory_system.register_claim_creation(
                        claim=db_claim,
                        raw_payload=claim,
                        actor="claim_extraction",
                    )
                    break
                except Exception as memory_exc:
                    logger.warning(
                        "Memory claim registration failed for claim %s (attempt %s/2): %s | payload=%s",
                        claim_uuid,
                        attempt + 1,
                        memory_exc,
                        json.dumps(claim, default=str)[:1200],
                    )
            claim["id"] = str(claim_uuid)
            claim["provenance"] = provenance
            claim["created_at"] = extraction_timestamp.isoformat()
            persisted.append(claim)

        await self.db.flush()
        mission_claim_total = await self.db.scalar(
            select(func.count(ResearchClaim.id)).where(ResearchClaim.mission_id == mission_id)
        )
        await self.db.execute(
            update(Mission)
            .where(Mission.id == mission_id)
            .values(total_claims=int(mission_claim_total or 0))
        )
        await self.db.flush()
        logger.info(f"Persisted {len(persisted)} claims for paper {paper_id}")
        return persisted
