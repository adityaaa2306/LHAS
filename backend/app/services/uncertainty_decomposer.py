"""CAPABILITY 5: Four-Component Uncertainty Decomposition

Replaces single composite_confidence with four named uncertainty components.
Preserves composite for backward compatibility.
Updates dynamically as graph evidence arrives.
"""

import logging
import math
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

Logger = logging.getLogger(__name__)


@dataclass
class UncertaintyComponents:
    """Four uncertainty components for a claim"""
    extraction_uncertainty: float  # 0-1, confidence in correct extraction
    study_uncertainty: float       # 0-1, confidence in study quality
    generalizability_uncertainty: float  # 0-1, confidence finding applies broadly
    replication_uncertainty: float # 0-1, confidence finding would replicate
    
    def to_dict(self) -> Dict:
        return {
            "extraction_uncertainty": round(self.extraction_uncertainty, 3),
            "study_uncertainty": round(self.study_uncertainty, 3),
            "generalizability_uncertainty": round(self.generalizability_uncertainty, 3),
            "replication_uncertainty": round(self.replication_uncertainty, 3)
        }


class UncertaintyDecomposer:
    """Computes and manages four-component uncertainty model"""
    
    def __init__(self):
        self.claims_uncertainty: Dict[str, UncertaintyComponents] = {}
    
    async def decompose_claim_uncertainty(
        self,
        claim: Dict,
        verification_results: Optional[Dict] = None
    ) -> Tuple[UncertaintyComponents, float]:
        """
        Compute 4-component uncertainty for a claim.
        
        Args:
            claim: Claim dict with fields:
                extraction_certainty, study_design_score, hedging_penalty,
                grounding_valid, verification_confidence, internal_conflict,
                coherence_confidence_adjustment, population, study_type,
                causal_downgrade_applied, study_design_consistent
            verification_results: Optional verification result dict
        
        Returns:
            (UncertaintyComponents, composite_confidence)
        """
        
        # 1. EXTRACTION UNCERTAINTY
        # How confident are we that the claim was correctly read?
        extraction_uncertainty = self._compute_extraction_uncertainty(claim)
        
        # 2. STUDY UNCERTAINTY
        # How confident are we in the study quality?
        study_uncertainty = self._compute_study_uncertainty(claim)
        
        # 3. GENERALIZABILITY UNCERTAINTY
        # How confident it applies beyond specific context?
        generalizability_uncertainty = self._compute_generalizability_uncertainty(claim)
        
        # 4. REPLICATION UNCERTAINTY
        # How confident finding would replicate?
        # For new claims, default to 0.50 (unknown)
        replication_uncertainty = 0.50
        
        components = UncertaintyComponents(
            extraction_uncertainty=extraction_uncertainty,
            study_uncertainty=study_uncertainty,
            generalizability_uncertainty=generalizability_uncertainty,
            replication_uncertainty=replication_uncertainty
        )
        
        # Compute composite using geometric mean with square root
        composite = self._compute_composite_confidence(components)
        
        claim_id = claim.get("id")
        self.claims_uncertainty[claim_id] = components
        
        Logger.debug(f"[UNCERTAINTY] Claim {claim_id}: E={extraction_uncertainty:.2f}, S={study_uncertainty:.2f}, G={generalizability_uncertainty:.2f}, R={replication_uncertainty:.2f}, Composite={composite:.2f}")
        
        return components, composite
    
    def _compute_extraction_uncertainty(self, claim: Dict) -> float:
        """
        Extraction uncertainty: how confident in correct extraction?
        
        Sources:
        - extraction_certainty from Pass 1
        - grounding_valid flag
        - verification_confidence from verification
        - coherence_confidence_adjustment
        """
        
        extraction_certainty = claim.get("extraction_certainty", 0.5)
        grounding_valid = claim.get("grounding_valid", False)
        verification_confidence = claim.get("verification_confidence", 1.0)
        coherence_adjustment = claim.get("coherence_confidence_adjustment", 1.0)
        
        # Grounding factor
        grounding_factor = 1.0 if grounding_valid else 0.80
        
        extraction_uncertainty = (
            extraction_certainty
            * verification_confidence
            * grounding_factor
            * coherence_adjustment
        )
        
        # Clamp
        extraction_uncertainty = max(0.05, min(0.95, extraction_uncertainty))
        
        return extraction_uncertainty
    
    def _compute_study_uncertainty(self, claim: Dict) -> float:
        """
        Study uncertainty: how confident in study quality?
        
        Sources:
        - study_design_score
        - hedging_penalty
        - study_design_consistent flag
        - causal_downgrade_applied flag
        """
        
        study_design_score = claim.get("study_design_score", 0.5)
        hedging_penalty = claim.get("hedging_penalty", 0.0)
        study_design_consistent = claim.get("study_design_consistent", True)
        causal_downgrade = claim.get("causal_downgrade_applied", False)
        
        # Base study quality
        base = study_design_score - hedging_penalty
        
        # Apply design consistency deduction
        design_factor = 0.70 if not study_design_consistent else 1.0
        
        # Apply causal downgrade if applicable
        causal_factor = 0.80 if causal_downgrade else 1.0
        
        study_uncertainty = base * design_factor * causal_factor
        
        # Clamp
        study_uncertainty = max(0.05, min(0.95, study_uncertainty))
        
        return study_uncertainty
    
    def _compute_generalizability_uncertainty(self, claim: Dict) -> float:
        """
        Generalizability uncertainty: applies beyond specific population?
        
        Start at 1.0 and deduct for limiting factors:
        - Very narrow population: -0.15
        - Internal conflict: -0.20
        - Population-specific subgroup: -0.10
        - Scope escalation: -0.25
        - Animal/in vitro study: -0.40
        """
        
        generalizability = 1.0
        
        # Population specificity
        population = claim.get("population", "")
        if population and self._is_narrow_population(population):
            generalizability -= 0.15
        
        # Internal conflicts
        if claim.get("internal_conflict", False):
            generalizability -= 0.20
        
        # Population-specific finding (subgroup)
        if claim.get("population_specific", False):
            generalizability -= 0.10
        
        # Scope escalation
        if "SCOPE_ESCALATION_SUSPECTED" in claim.get("coherence_flags", []):
            generalizability -= 0.25
        
        # Study type
        study_type = claim.get("study_type", "")
        if study_type in ["in_vitro", "animal_model"]:
            generalizability -= 0.40
        
        # Floor at 0.05
        generalizability = max(0.05, generalizability)
        
        return generalizability
    
    def _is_narrow_population(self, population_desc: str) -> bool:
        """Check if population description indicates narrow focus"""
        
        narrow_indicators = [
            "single site",
            "specific hospital",
            "highly specific",
            "exclusion criteria",
            "restricted"
        ]
        
        pop_lower = population_desc.lower()
        return any(indicator in pop_lower for indicator in narrow_indicators)
    
    def _compute_composite_confidence(self, components: UncertaintyComponents) -> float:
        """
        Compute composite using geometric mean with square root.
        
        Formula: ((E × S × G × R) ^ 0.5
        
        Square root prevents aggressive collapsing.
        Four values of 0.7 produces ~0.70, not 0.24.
        """
        
        product = (
            components.extraction_uncertainty
            * components.study_uncertainty
            * components.generalizability_uncertainty
            * components.replication_uncertainty
        )
        
        # Take square root for geometric mean
        composite = math.sqrt(product) if product > 0 else 0.0
        
        # Clamp
        composite = max(0.05, min(0.95, composite))
        
        return composite
    
    async def update_replication_uncertainty_from_graph(
        self,
        claim_id: str,
        replicating_claim_count: int,
        contradicting_claim_count: int,
        is_isolated: bool,
        papers_in_mission: int
    ):
        """
        Update replication_uncertainty based on graph evidence.
        Called by ClaimGraphManager when edges are established.
        
        Args:
            claim_id: Claim to update
            replicating_claim_count: How many REPLICATES edges
            contradicting_claim_count: How many CONTRADICTS edges
            is_isolated: True if no edges after 5+ papers
            papers_in_mission: Total papers processed
        """
        
        if claim_id not in self.claims_uncertainty:
            Logger.warning(f"[UNCERTAINTY] Claim {claim_id} not found in uncertainty cache")
            return None
        
        components = self.claims_uncertainty[claim_id]
        
        # Start from default
        replication_uncertainty = 0.50
        
        # Add for replicating claims (cap at +0.40 total)
        if replicating_claim_count > 0:
            replication_boost = min(0.40, replicating_claim_count * 0.15)
            replication_uncertainty += replication_boost
        
        # Subtract for contradicting claims (cap at -0.45 total)
        if contradicting_claim_count > 0:
            replication_penalty = max(-0.45, contradicting_claim_count * -0.20)
            replication_uncertainty += replication_penalty
        
        # Penalty for isolation in mature graph
        if is_isolated and papers_in_mission >= 5:
            replication_uncertainty -= 0.10
        
        # Clamp
        replication_uncertainty = max(0.05, min(0.95, replication_uncertainty))
        
        # Update components
        components.replication_uncertainty = replication_uncertainty
        
        Logger.info(f"[UNCERTAINTY] Updated replication_uncertainty for {claim_id}: {replication_uncertainty:.2f} (reps={replicating_claim_count}, contrad={contradicting_claim_count})")
        
        # Return updated composite for reference
        new_composite = self._compute_composite_confidence(components)
        return new_composite
    
    def get_uncertainty_components(self, claim_id: str) -> Optional[UncertaintyComponents]:
        """Retrieve uncertainty components for a claim"""
        return self.claims_uncertainty.get(claim_id)
    
    def get_uncertainty_interpretation(
        self,
        components: UncertaintyComponents
    ) -> Dict[str, str]:
        """
        Generate human-readable interpretation of uncertainty components.
        Used for documentation and synthesis generation guidance.
        """
        
        interpretations = {}
        
        # Extraction interpretation
        if components.extraction_uncertainty < 0.40:
            interpretations["extraction"] = "⚠️ Consider re-extraction — low confidence in correct reading"
        elif components.extraction_uncertainty < 0.60:
            interpretations["extraction"] = "⚠️ Verify grounding and evidence span alignment"
        else:
            interpretations["extraction"] = "✓ Good extraction confidence"
        
        # Study interpretation
        if components.study_uncertainty < 0.40:
            interpretations["study"] = "⚠️ Qualify language — study design limitation present"
        elif components.study_uncertainty < 0.60:
            interpretations["study"] = "⚠️ Note methodological constraints in synthesis"
        else:
            interpretations["study"] = "✓ Sound study quality"
        
        # Generalizability interpretation
        if components.generalizability_uncertainty < 0.40:
            interpretations["generalizability"] = "⚠️ Add population qualifier to synthesis language"
        elif components.generalizability_uncertainty < 0.70:
            interpretations["generalizability"] = "⚠️ Scope findings to specific populations"
        else:
            interpretations["generalizability"] = "✓ Good generalizability"
        
        # Replication interpretation
        if components.replication_uncertainty < 0.40:
            interpretations["replication"] = "⚠️ Flag as needing more evidence — do not treat as established"
        elif components.replication_uncertainty < 0.60:
            interpretations["replication"] = "⚠️ Tentative findings — corroborate with other evidence"
        else:
            interpretations["replication"] = "✓ Good replication signal"
        
        return interpretations
    
    def get_stats(self) -> Dict:
        """Return summary statistics"""
        
        if not self.claims_uncertainty:
            return {"claims_tracked": 0}
        
        all_extraction = [c.extraction_uncertainty for c in self.claims_uncertainty.values()]
        all_study = [c.study_uncertainty for c in self.claims_uncertainty.values()]
        all_generalizability = [c.generalizability_uncertainty for c in self.claims_uncertainty.values()]
        all_replication = [c.replication_uncertainty for c in self.claims_uncertainty.values()]
        
        return {
            "claims_tracked": len(self.claims_uncertainty),
            "avg_extraction_uncertainty": sum(all_extraction) / len(all_extraction),
            "avg_study_uncertainty": sum(all_study) / len(all_study),
            "avg_generalizability_uncertainty": sum(all_generalizability) / len(all_generalizability),
            "avg_replication_uncertainty": sum(all_replication) / len(all_replication),
            "low_extraction_uncertainty": sum(1 for u in all_extraction if u < 0.40),
            "low_study_uncertainty": sum(1 for u in all_study if u < 0.40),
            "low_generalizability_uncertainty": sum(1 for u in all_generalizability if u < 0.40),
            "low_replication_uncertainty": sum(1 for u in all_replication if u < 0.40)
        }
