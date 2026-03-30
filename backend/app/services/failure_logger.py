"""CAPABILITY 2: Self-Improving Extraction via Failure Logging

Tracks extraction successes and failures as training signals.
Implements prompt performance tracking and auto-promotion.
Provides domain adaptation dataset generation.
"""

import logging
import hashlib
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum
from datetime import datetime

Logger = logging.getLogger(__name__)


class FailureType(str, Enum):
    """Types of extraction failures tracked"""
    HALLUCINATION = "hallucination"
    OVERGENERALIZATION = "overgeneralization"
    SCOPE_DRIFT = "scope_drift"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


@dataclass
class ExtractionRecord:
    """Base record for extraction success/failure"""
    claim_id: str
    paper_id: str
    mission_id: str
    claim_statement: str
    evidence_span: str
    source_chunk_id: str
    section_source: str
    extraction_certainty: float
    pass1_prompt_version: str
    recorded_at: str = None
    
    def __post_init__(self):
        if self.recorded_at is None:
            self.recorded_at = datetime.utcnow().isoformat()
    
    def to_dict(self) -> Dict:
        return {
            "claim_id": self.claim_id,
            "paper_id": self.paper_id,
            "mission_id": self.mission_id,
            "claim_statement": self.claim_statement,
            "evidence_span": self.evidence_span,
            "source_chunk_id": self.source_chunk_id,
            "section_source": self.section_source,
            "extraction_certainty": self.extraction_certainty,
            "pass1_prompt_version": self.pass1_prompt_version,
            "recorded_at": self.recorded_at
        }


@dataclass
class ExtractionFailure(ExtractionRecord):
    """Record of a claim that failed verification"""
    error_type: str = "unknown"
    
    def to_dict(self) -> Dict:
        data = super().to_dict()
        data["error_type"] = self.error_type
        return data


@dataclass
class ExtractionSuccess(ExtractionRecord):
    """Record of a claim that passed verification"""
    verification_confidence: float = 0.0
    
    def to_dict(self) -> Dict:
        data = super().to_dict()
        data["verification_confidence"] = self.verification_confidence
        return data


@dataclass
class PromptPerformance:
    """Performance metrics for a prompt version"""
    prompt_version: str
    total_attempts: int
    successful_verifications: int
    failed_verifications: int
    pass_rate: float
    timestamp: str = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow().isoformat()
        
        self.pass_rate = (
            self.successful_verifications / self.total_attempts
            if self.total_attempts > 0 else 0.0
        )
    
    def to_dict(self) -> Dict:
        return {
            "prompt_version": self.prompt_version,
            "total_attempts": self.total_attempts,
            "successful_verifications": self.successful_verifications,
            "failed_verifications": self.failed_verifications,
            "pass_rate": self.pass_rate,
            "timestamp": self.timestamp
        }


@dataclass
class SectionQuality:
    """Quality metrics per section"""
    section_name: str
    mission_id: str
    pass_rate: float
    claim_count: int
    weight_multiplier: float = 1.0  # For multi-query retrieval


class FailureLogger:
    """Tracks and analyzes extraction successes/failures"""
    
    def __init__(self):
        self.failures: List[ExtractionFailure] = []
        self.successes: List[ExtractionSuccess] = []
        self.prompt_performance: Dict[str, PromptPerformance] = {}
        self.section_quality: Dict[str, SectionQuality] = {}
        self.domain_adaptation_ready = False
    
    def compute_prompt_version(self, prompt_template: str) -> str:
        """Hash prompt template to create version identifier"""
        return hashlib.md5(prompt_template.encode()).hexdigest()[:8]
    
    async def log_failure(
        self,
        claim_id: str,
        paper_id: str,
        mission_id: str,
        claim_statement: str,
        evidence_span: str,
        error_type: str,
        source_chunk_id: str,
        section_source: str,
        extraction_certainty: float,
        pass1_prompt_version: str
    ):
        """Log a claim that failed verification"""
        
        failure = ExtractionFailure(
            claim_id=claim_id,
            paper_id=paper_id,
            mission_id=mission_id,
            claim_statement=claim_statement,
            evidence_span=evidence_span,
            error_type=error_type,
            source_chunk_id=source_chunk_id,
            section_source=section_source,
            extraction_certainty=extraction_certainty,
            pass1_prompt_version=pass1_prompt_version
        )
        
        self.failures.append(failure)
        
        Logger.debug(f"[FAILURE] Logged extraction failure: {error_type} in {section_source}")
        
        # Update section quality
        await self._update_section_quality(section_source, mission_id, passed=False)
        
        # Check if we've reached domain adaptation threshold
        if len(self.failures) >= 100 and len(self.failures) % 100 == 0:
            self.domain_adaptation_ready = True
            Logger.info(f"[DOMAIN] Domain adaptation dataset ready ({len(self.failures)} failures)")
    
    async def log_success(
        self,
        claim_id: str,
        paper_id: str,
        mission_id: str,
        claim_statement: str,
        evidence_span: str,
        verification_confidence: float,
        source_chunk_id: str,
        section_source: str,
        extraction_certainty: float,
        pass1_prompt_version: str
    ):
        """Log a claim that passed verification"""
        
        success = ExtractionSuccess(
            claim_id=claim_id,
            paper_id=paper_id,
            mission_id=mission_id,
            claim_statement=claim_statement,
            evidence_span=evidence_span,
            verification_confidence=verification_confidence,
            source_chunk_id=source_chunk_id,
            section_source=section_source,
            extraction_certainty=extraction_certainty,
            pass1_prompt_version=pass1_prompt_version
        )
        
        self.successes.append(success)
        
        Logger.debug(f"[SUCCESS] Logged verified claim: {pass1_prompt_version} in {section_source}")
        
        # Update section quality
        await self._update_section_quality(section_source, mission_id, passed=True)
    
    async def _update_section_quality(
        self,
        section_name: str,
        mission_id: str,
        passed: bool
    ):
        """Update section-level quality metrics"""
        
        key = f"{section_name}|{mission_id}"
        
        if key not in self.section_quality:
            self.section_quality[key] = SectionQuality(
                section_name=section_name,
                mission_id=mission_id,
                pass_rate=0.0,
                claim_count=0
            )
        
        section = self.section_quality[key]
        section.claim_count += 1
        
        if passed:
            passes = sum(
                1 for s in self.successes
                if s.section_source == section_name and s.mission_id == mission_id
            )
            section.pass_rate = passes / section.claim_count
        else:
            passes = sum(
                1 for s in self.successes
                if s.section_source == section_name and s.mission_id == mission_id
            )
            section.pass_rate = passes / section.claim_count
        
        # Reduce retrieval weight for poor-performing sections
        if section.pass_rate < 0.50 and section.claim_count >= 5:
            section.weight_multiplier = 0.6
            Logger.warning(f"[SECTION] Reducing weight for {section_name}: {section.pass_rate:.1%} pass rate")
    
    async def compute_prompt_performance(
        self,
        papers_processed_threshold: int = 20
    ) -> Dict[str, PromptPerformance]:
        """
        Compute pass rates per prompt version after N papers.
        Returns dict of prompt_version → PromptPerformance
        """
        
        # Group by prompt version
        by_prompt = {}
        
        for failure in self.failures:
            v = failure.pass1_prompt_version
            if v not in by_prompt:
                by_prompt[v] = {"successes": 0, "failures": 0}
            by_prompt[v]["failures"] += 1
        
        for success in self.successes:
            v = success.pass1_prompt_version
            if v not in by_prompt:
                by_prompt[v] = {"successes": 0, "failures": 0}
            by_prompt[v]["successes"] += 1
        
        # Create performance records
        self.prompt_performance = {}
        for prompt_version, counts in by_prompt.items():
            total = counts["successes"] + counts["failures"]
            self.prompt_performance[prompt_version] = PromptPerformance(
                prompt_version=prompt_version,
                total_attempts=total,
                successful_verifications=counts["successes"],
                failed_verifications=counts["failures"]
            )
        
        Logger.info(f"[PROMPT] Computed performance for {len(self.prompt_performance)} prompt versions")
        return self.prompt_performance
    
    def get_best_prompt_version(self) -> Optional[str]:
        """Return highest-performing prompt version"""
        if not self.prompt_performance:
            return None
        
        best = max(
            self.prompt_performance.values(),
            key=lambda p: p.pass_rate
        )
        
        Logger.info(f"[PROMPT] Best performer: {best.prompt_version} ({best.pass_rate:.1%})")
        return best.prompt_version
    
    async def generate_domain_adaptation_dataset(self) -> Dict:
        """
        Export labeled dataset for fine-tuning or few-shot learning.
        Only called when len(failures) >= 100.
        """
        
        if len(self.failures) < 100:
            Logger.warning(f"[DOMAIN] Only {len(self.failures)} failures, threshold is 100")
            return {}
        
        dataset = {
            "positive_examples": [s.to_dict() for s in self.successes],
            "negative_examples": [f.to_dict() for f in self.failures],
            "error_type_distribution": self._compute_error_distribution(),
            "section_performance": {
                k: v.to_dict() if hasattr(v, "to_dict") else v.__dict__
                for k, v in self.section_quality.items()
            },
            "generated_at": datetime.utcnow().isoformat()
        }
        
        Logger.info(f"[DOMAIN] Generated dataset: {len(self.successes)} positive, {len(self.failures)} negative")
        return dataset
    
    def _compute_error_distribution(self) -> Dict[str, int]:
        """Count failures by error type"""
        distribution = {}
        for failure in self.failures:
            distribution[failure.error_type] = distribution.get(failure.error_type, 0) + 1
        return distribution
    
    async def emit_events(self, event_emitter, mission_id: str):
        """Emit relevant events"""
        
        # Emit domain adaptation ready
        if self.domain_adaptation_ready:
            dataset = await self.generate_domain_adaptation_dataset()
            await event_emitter.emit("domain_adaptation.ready", {
                "mission_id": mission_id,
                "failure_count": len(self.failures),
                "success_count": len(self.successes),
                "dataset_path": f"mission_{mission_id}_adaptation_dataset.json",
                "error_distribution": self._compute_error_distribution(),
                "timestamp": datetime.utcnow().isoformat()
            })
        
        # Emit section weight adjustments
        for key, section in self.section_quality.items():
            if section.weight_multiplier < 1.0:
                await event_emitter.emit("section_weight_adjusted", {
                    "mission_id": mission_id,
                    "section_name": section.section_name,
                    "pass_rate": section.pass_rate,
                    "weight_multiplier": section.weight_multiplier,
                    "claim_count": section.claim_count,
                    "reason": "low_verification_pass_rate",
                    "timestamp": datetime.utcnow().isoformat()
                })
    
    def get_stats(self) -> Dict:
        """Return summary statistics"""
        total = len(self.successes) + len(self.failures)
        return {
            "total_claims_logged": total,
            "successes": len(self.successes),
            "failures": len(self.failures),
            "pass_rate": len(self.successes) / total if total > 0 else 0.0,
            "error_distribution": self._compute_error_distribution(),
            "prompt_versions_tracked": len(self.prompt_performance),
            "sections_tracked": len(self.section_quality)
        }
