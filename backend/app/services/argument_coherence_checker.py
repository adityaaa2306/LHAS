"""CAPABILITY 3: Argument Coherence Checking

Checks if claims from a single paper form a logically consistent set.
Runs after verification, before confidence assembly in main pipeline.
Deterministic checks only (no LLM).
"""

import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

Logger = logging.getLogger(__name__)


class CoherenceFlag(str, Enum):
    """Coherence-related flags"""
    INTERNAL_DIRECTION_CONFLICT = "INTERNAL_DIRECTION_CONFLICT"
    SCOPE_ESCALATION_SUSPECTED = "SCOPE_ESCALATION_SUSPECTED"
    EXTRACTION_INCONSISTENCY = "EXTRACTION_INCONSISTENCY"
    POPULATION_SPECIFIC_MATCH = "POPULATION_SPECIFIC_MATCH"


@dataclass
class CoherenceResult:
    """Result of coherence check for a claim"""
    claim_id: str
    internal_conflict: bool
    coherence_flags: List[str]
    coherence_confidence_adjustment: float  # Multiplicative factor
    conflicting_claims: List[str]  # IDs of conflicting claims in same paper
    reason: str


class ArgumentCoherenceChecker:
    """Checks internal consistency of claims from one paper"""
    
    def __init__(self):
        self.results: Dict[str, CoherenceResult] = {}
        self.conflicts_detected: List[Tuple[str, str]] = []  # (claim_id1, claim_id2)
    
    async def check_paper_coherence(
        self,
        paper_id: str,
        claims: List[Dict]
    ) -> List[CoherenceResult]:
        """
        Check coherence of all claims from a paper.
        
        Args:
            paper_id: Paper identifier
            claims: List of claim dicts with fields:
                id, statement_raw, intervention_canonical, outcome_canonical,
                direction, claim_type, study_design_score, population,
                extraction_certainty, embeddings (if available)
        
        Returns:
            List of CoherenceResult for each claim
        """
        
        results = []
        self.conflicts_detected = []
        
        if not claims:
            return results
        
        Logger.info(f"[COHERENCE] Checking {len(claims)} claims from paper {paper_id}")
        
        # Check 1: Internal direction conflicts
        direction_conflicts = self._check_internal_direction_conflicts(claims)
        
        # Check 2: Scope escalation
        scope_escalations = self._check_scope_escalation(claims)
        
        # Check 3: Extraction inconsistency
        extraction_inconsistencies = self._check_extraction_inconsistency(claims)
        
        # Check 4: Null result consistency
        null_result_conflicts = self._check_null_result_consistency(claims)
        
        # Merge results
        flags_by_claim = {}
        for claim_id in [c.get("id") for c in claims]:
            flags_by_claim[claim_id] = {
                "flags": [],
                "adjustment": 1.0,
                "conflicts": []
            }
        
        # Apply direction conflicts
        for claim_id, conflict_ids in direction_conflicts.items():
            flags_by_claim[claim_id]["flags"].append(CoherenceFlag.INTERNAL_DIRECTION_CONFLICT.value)
            flags_by_claim[claim_id]["adjustment"] *= 1.0  # No adjustment for informational flag
            flags_by_claim[claim_id]["conflicts"].extend(conflict_ids)
        
        # Apply scope escalations
        for claim_id, adjustment in scope_escalations.items():
            flags_by_claim[claim_id]["flags"].append(CoherenceFlag.SCOPE_ESCALATION_SUSPECTED.value)
            flags_by_claim[claim_id]["adjustment"] *= adjustment
        
        # Apply extraction inconsistencies
        for claim_id, replicated_id in extraction_inconsistencies.items():
            flags_by_claim[claim_id]["flags"].append(CoherenceFlag.EXTRACTION_INCONSISTENCY.value)
            flags_by_claim[claim_id]["adjustment"] *= 1.0  # Keep higher-certainty version
        
        # Apply null result conflicts (if identical population)
        for claim_id, (is_conflict, is_subgroup) in null_result_conflicts.items():
            if is_conflict:
                flags_by_claim[claim_id]["flags"].append(CoherenceFlag.INTERNAL_DIRECTION_CONFLICT.value)
            if is_subgroup:
                flags_by_claim[claim_id]["flags"].append(CoherenceFlag.POPULATION_SPECIFIC_MATCH.value)
        
        # Create result objects
        for claim in claims:
            claim_id = claim.get("id")
            info = flags_by_claim.get(claim_id, {})
            
            result = CoherenceResult(
                claim_id=claim_id,
                internal_conflict=CoherenceFlag.INTERNAL_DIRECTION_CONFLICT.value in info.get("flags", []),
                coherence_flags=info.get("flags", []),
                coherence_confidence_adjustment=info.get("adjustment", 1.0),
                conflicting_claims=info.get("conflicts", []),
                reason=self._generate_reason(info.get("flags", []))
            )
            
            results.append(result)
            self.results[claim_id] = result
        
        Logger.info(f"[COHERENCE] Found {len(self.conflicts_detected)} conflicts in paper")
        
        return results
    
    def _check_internal_direction_conflicts(self, claims: List[Dict]) -> Dict[str, List[str]]:
        """
        Check 1: Find pairs with same intervention/outcome but opposite direction.
        Returns dict mapping claim_id → list of conflicting claim_ids
        """
        
        conflicts = {}
        
        for i, claim1 in enumerate(claims):
            for claim2 in claims[i+1:]:
                if self._claims_have_conflict(claim1, claim2):
                    id1 = claim1.get("id")
                    id2 = claim2.get("id")
                    
                    if id1 not in conflicts:
                        conflicts[id1] = []
                    if id2 not in conflicts:
                        conflicts[id2] = []
                    
                    conflicts[id1].append(id2)
                    conflicts[id2].append(id1)
                    
                    self.conflicts_detected.append((id1, id2))
                    Logger.debug(f"[COHERENCE] Direction conflict: {id1} vs {id2}")
        
        return conflicts
    
    def _claims_have_conflict(self, claim1: Dict, claim2: Dict) -> bool:
        """Check if two claims conflict"""
        
        # Same intervention and outcome?
        if (claim1.get("intervention_canonical") != claim2.get("intervention_canonical") or
            claim1.get("outcome_canonical") != claim2.get("outcome_canonical")):
            return False
        
        # Opposite direction?
        dir1 = claim1.get("direction", "")
        dir2 = claim2.get("direction", "")
        
        opposite_pairs = [
            ("positive", "negative"),
            ("negative", "positive")
        ]
        
        return (dir1, dir2) in opposite_pairs or (dir2, dir1) in opposite_pairs
    
    def _check_scope_escalation(self, claims: List[Dict]) -> Dict[str, float]:
        """
        Check 2: Narrow mechanism + broad causal claim pattern.
        Returns dict mapping claim_id → confidence adjustment factor
        """
        
        adjustments = {}
        
        mechanistic = [c for c in claims if c.get("claim_type") == "mechanistic"]
        causal = [c for c in claims if c.get("claim_type") == "causal"]
        
        for mech_claim in mechanistic:
            for causal_claim in causal:
                # Same intervention/outcome?
                if (mech_claim.get("intervention_canonical") == causal_claim.get("intervention_canonical") and
                    mech_claim.get("outcome_canonical") == causal_claim.get("outcome_canonical")):
                    
                    # Mechanistic population narrower?
                    mech_pop = len(mech_claim.get("population", "").split(","))
                    causal_pop = len(causal_claim.get("population", "").split(","))
                    
                    if mech_pop < causal_pop:
                        Logger.warning(f"[COHERENCE] Scope escalation suspected: narrow mechanism, broad causal")
                        
                        if causal_claim.get("id") not in adjustments:
                            adjustments[causal_claim.get("id")] = 1.0
                        
                        adjustments[causal_claim.get("id")] *= 0.85
        
        return adjustments
    
    def _check_extraction_inconsistency(self, claims: List[Dict]) -> Dict[str, str]:
        """
        Check 3: Semantically similar claims with very different extraction certainty.
        Returns dict mapping low-certainty_claim_id → high-certainty_claim_id
        """
        
        # Group by statement similarity (if embeddings available)
        similarities = {}
        
        for i, claim1 in enumerate(claims):
            for claim2 in claims[i+1:]:
                # Simple string similarity as fallback
                if self._claims_semantically_similar(claim1, claim2):
                    certainty1 = claim1.get("extraction_certainty", 0.5)
                    certainty2 = claim2.get("extraction_certainty", 0.5)
                    
                    # Very different certainty?
                    if abs(certainty1 - certainty2) > 0.45:
                        if certainty1 < 0.40 and certainty2 > 0.85:
                            # Keep higher, mark lower as replicated
                            Logger.warning(f"[COHERENCE] Extraction inconsistency: same finding, vastly different certainty")
                            similarities[claim1.get("id")] = claim2.get("id")
                        elif certainty2 < 0.40 and certainty1 > 0.85:
                            similarities[claim2.get("id")] = claim1.get("id")
        
        return similarities
    
    def _claims_semantically_similar(self, claim1: Dict, claim2: Dict) -> bool:
        """Check if two claims are semantically similar"""
        
        # Same intervention/outcome is a proxy
        return (claim1.get("intervention_canonical") == claim2.get("intervention_canonical") and
                claim1.get("outcome_canonical") == claim2.get("outcome_canonical"))
    
    def _check_null_result_consistency(self, claims: List[Dict]) -> Dict[str, Tuple[bool, bool]]:
        """
        Check 4: Null result claimed alongside positive/negative for same pair.
        Returns dict mapping claim_id → (is_conflict, is_subgroup)
        """
        
        results = {}
        
        # Group by intervention/outcome
        by_pair = {}
        for claim in claims:
            key = (claim.get("intervention_canonical"), claim.get("outcome_canonical"))
            if key not in by_pair:
                by_pair[key] = []
            by_pair[key].append(claim)
        
        for pair, group_claims in by_pair.items():
            if len(group_claims) < 2:
                continue
            
            null_claims = [c for c in group_claims if c.get("direction") == "null"]
            directional = [c for c in group_claims if c.get("direction") in ["positive", "negative"]]
            
            if null_claims and directional:
                # Check if populations differ
                for null_c in null_claims:
                    null_pop = null_c.get("population", "")
                    is_subgroup = False
                    
                    for dir_c in directional:
                        dir_pop = dir_c.get("population", "")
                        
                        if null_pop != dir_pop:
                            is_subgroup = True
                            results[null_c.get("id")] = (False, True)
                        else:
                            # Same population, mark as conflict
                            results[null_c.get("id")] = (True, False)
        
        return results
    
    def _generate_reason(self, flags: List[str]) -> str:
        """Generate human-readable reason for adjustments"""
        
        if not flags:
            return "No coherence issues detected"
        
        reasons = []
        for flag in flags:
            if flag == CoherenceFlag.INTERNAL_DIRECTION_CONFLICT.value:
                reasons.append("Paper reports conflicting directions for same relationship")
            elif flag == CoherenceFlag.SCOPE_ESCALATION_SUSPECTED.value:
                reasons.append("Mechanistic evidence narrower than causal claim")
            elif flag == CoherenceFlag.EXTRACTION_INCONSISTENCY.value:
                reasons.append("Same finding extracted with vastly different certainty")
            elif flag == CoherenceFlag.POPULATION_SPECIFIC_MATCH.value:
                reasons.append("Finding is population-specific subgroup analysis")
        
        return "; ".join(reasons)
    
    def get_stats(self) -> Dict:
        """Return summary statistics"""
        
        papers_with_conflict = sum(
            1 for r in self.results.values()
            if r.internal_conflict
        )
        
        adjustments = [r.coherence_confidence_adjustment for r in self.results.values()]
        reduced = sum(1 for a in adjustments if a < 1.0)
        
        return {
            "claims_checked": len(self.results),
            "conflicts_detected": len(self.conflicts_detected),
            "claims_with_adjustments": reduced,
            "average_adjustment": sum(adjustments) / len(adjustments) if adjustments else 1.0
        }
