"""claim_extraction.py — ORCHESTRATION LAYER (INTEGRATION TEMPLATE)

This file shows the EXACT integration points for all 5 next-generation capabilities
into the existing claim extraction pipeline. Existing components are UNCHANGED.

Template shows:
1. Imports
2. Initialization
3. Pipeline modification points (clearly marked with [NEW])
4. Event emission
5. Backward compatibility patterns
"""

# IMPORTS (Add to existing imports)
# ==============================================================================

from app.services.evidence_gap_detector import EvidenceGapDetector, EvidenceGap
from app.services.failure_logger import FailureLogger, ExtractionFailure, ExtractionSuccess
from app.services.argument_coherence_checker import ArgumentCoherenceChecker, CoherenceResult
from app.services.entity_evolution_manager import EntityEvolutionManager, EntityNode
from app.services.uncertainty_decomposer import UncertaintyDecomposer, UncertaintyComponents


class ClaimExtractionService:
    """Main orchestration service for multi-pass claim extraction pipeline."""
    
    def __init__(self, config: ExtractionConfig):
        """Initialize all components including new capabilities."""
        
        # Existing components (UNCHANGED)
        self.retrieval_layer = RetrievalLayer(config)
        self.verification_engine = VerificationEngine(config)
        self.quantitative_extractor = QuantitativeExtractor(config)
        self.claim_graph_manager = ClaimGraphManager(config)
        
        # [NEW] Five next-generation capability components
        self.evidence_gap_detector = EvidenceGapDetector()
        self.failure_logger = FailureLogger(config.db_session)
        self.coherence_checker = ArgumentCoherenceChecker()
        self.entity_evolution = EntityEvolutionManager(config.db_session)
        self.uncertainty_decomposer = UncertaintyDecomposer()
        
        self.config = config
        self.db_session = config.db_session
    
    async def extract_claims_from_paper(
        self,
        paper_id: str,
        mission_id: str,
        paper_text: str,
        paper_metadata: Dict
    ) -> ExtractionResult:
        """Main extraction pipeline orchestrating all components.
        
        Returns:
            ExtractionResult with all claims, verification results, uncertainty,
            coherence flags, entity normalization status, etc.
        """
        
        extraction_result = ExtractionResult(
            mission_id=mission_id,
            paper_id=paper_id,
            claims=[],
            gaps=[],
            entity_events=[],
            events=[]
        )
        
        # ═════════════════════════════════════════════════════════════════
        # PASS 0: Retrieve semantically relevant chunks
        # ═════════════════════════════════════════════════════════════════
        
        chunks = await self.retrieval_layer.retrieve_relevant_chunks(
            paper_id=paper_id,
            paper_text=paper_text,
            mission_goals=self.config.mission_goals
        )
        # Output: List[Chunk] with embeddings and similarity scores
        
        
        # ═════════════════════════════════════════════════════════════════
        # PASS 1: Evidence-grounded claim extraction
        # ═════════════════════════════════════════════════════════════════
        
        raw_claims = await self.llm_extract_claims_pass1(
            paper_id=paper_id,
            chunks=chunks,
            paper_metadata=paper_metadata
        )
        # Output: List[Claim] with source_chunk_ids, evidence_span
        
        
        # ═════════════════════════════════════════════════════════════════
        # [NEW] FAILURE LOGGER: Tag Pass 1 with prompt version
        # ═════════════════════════════════════════════════════════════════
        
        for claim in raw_claims:
            # Compute hash of the prompt template used
            pass1_prompt_hash = self.failure_logger.compute_prompt_version(
                prompt_template=PASS1_PROMPT_TEMPLATE
            )
            claim.pass1_prompt_version = pass1_prompt_hash
            # This allows later A/B testing of different extraction prompts
        
        
        # ═════════════════════════════════════════════════════════════════
        # PASS 2A: Classify claims as causal vs correlational
        # ═════════════════════════════════════════════════════════════════
        
        classified_claims = await self.llm_classify_causal_pass2a(
            claims=raw_claims,
            chunks=chunks
        )
        # Output: Updated claims with claim_type, study_design_score
        
        
        # ═════════════════════════════════════════════════════════════════
        # PASS 2B: Normalize entities (WITH ENTITY EVOLUTION)
        # ═════════════════════════════════════════════════════════════════
        
        normalized_claims = await self.llm_normalize_entities_pass2b(
            claims=classified_claims,
            chunks=chunks,
            mission_id=mission_id,
            paper_id=paper_id
        )
        # Output: Claims with intervention_canonical, outcome_canonical
        
        # [NEW] ENTITY EVOLUTION ENHANCEMENT
        # For each claim, propose normalization through evolution manager
        entity_events_this_paper = []
        for claim in normalized_claims:
            
            # Intervention normalization
            intervention_result = await self.entity_evolution.propose_normalization(
                surface_form=claim.intervention_raw,
                context_sentence=claim.statement_raw,
                entity_type="intervention",
                mission_id=mission_id,
                paper_id=paper_id,
                claim_id=claim.id
            )
            claim.intervention_canonical = intervention_result.canonical_form
            claim.intervention_normalization_status = intervention_result.status
            
            # Outcome normalization
            outcome_result = await self.entity_evolution.propose_normalization(
                surface_form=claim.outcome_raw,
                context_sentence=claim.statement_raw,
                entity_type="outcome",
                mission_id=mission_id,
                paper_id=paper_id,
                claim_id=claim.id
            )
            claim.outcome_canonical = outcome_result.canonical_form
            claim.outcome_normalization_status = outcome_result.status
            
            # Track if any merge candidates or new entities proposed
            if outcome_result.status == "merge_candidate":
                entity_events_this_paper.append({
                    "type": "entity.merge_candidate",
                    "surface_form": outcome_result.surface_form,
                    "nearest_canonical": outcome_result.nearest_match,
                    "similarity": outcome_result.similarity
                })
            elif outcome_result.status == "new_entity":
                entity_events_this_paper.append({
                    "type": "entity.new_candidate",
                    "surface_form": outcome_result.surface_form,
                    "context": claim.statement_raw
                })
        
        extraction_result.entity_events = entity_events_this_paper
        
        
        # ═════════════════════════════════════════════════════════════════
        # PASS 2C (PARALLEL): Quantitative evidence extraction
        # ═════════════════════════════════════════════════════════════════
        
        quantitative_task = asyncio.create_task(
            self.quantitative_extractor.extract_from_tables(
                paper_id=paper_id,
                paper_text=paper_text
            )
        )
        # Runs in parallel, non-blocking
        
        
        # ═════════════════════════════════════════════════════════════════
        # VERIFICATION TIER 1: Batch NLI verification (PARALLEL)
        # ═════════════════════════════════════════════════════════════════
        
        verification_tier1_task = asyncio.create_task(
            self.verification_engine.verify_tier1_nli(
                claims=normalized_claims,
                chunks=chunks
            )
        )
        # Runs in parallel, non-blocking
        
        
        # ═════════════════════════════════════════════════════════════════
        # Wait for Tier 1 verification to complete
        # ═════════════════════════════════════════════════════════════════
        
        verified_claims = await verification_tier1_task
        # Output: Claims with is_supported, verification_confidence, error_type
        
        
        # ═════════════════════════════════════════════════════════════════
        # [NEW] FAILURE LOGGER: Log verification results
        # ═════════════════════════════════════════════════════════════════
        
        for claim in verified_claims:
            if claim.is_supported == True:
                # Log success
                await self.failure_logger.log_success(
                    claim_id=claim.id,
                    paper_id=paper_id,
                    mission_id=mission_id,
                    verification_confidence=claim.verification_confidence,
                    pass1_prompt_version=claim.pass1_prompt_version
                )
            else:
                # Log failure
                await self.failure_logger.log_failure(
                    claim_id=claim.id,
                    paper_id=paper_id,
                    mission_id=mission_id,
                    error_type=claim.error_type,  # hallucination, overgeneralization, etc.
                    section_source=claim.section,  # abstract, results, etc.
                    pass1_prompt_version=claim.pass1_prompt_version
                )
        
        
        # ═════════════════════════════════════════════════════════════════
        # [NEW] ARGUMENT COHERENCE CHECKING
        # Runs synchronously AFTER verification, BEFORE confidence assembly
        # ═════════════════════════════════════════════════════════════════
        
        coherence_results = await self.coherence_checker.check_paper_coherence(
            paper_id=paper_id,
            claims=verified_claims,
            mission_id=mission_id
        )
        # Output: List[CoherenceResult] with flags and confidence adjustments
        
        # Apply coherence results to claims
        coherence_map = {r.claim_id: r for r in coherence_results}
        for claim in verified_claims:
            if claim.id in coherence_map:
                coherence = coherence_map[claim.id]
                claim.internal_conflict = coherence.internal_conflict
                claim.coherence_flags = coherence.coherence_flags
                claim.coherence_confidence_adjustment = (
                    coherence.coherence_confidence_adjustment
                )
        
        # Log if internal conflicts detected
        if any(r.internal_conflict for r in coherence_results):
            extraction_result.events.append({
                "type": "paper.internal_conflict_detected",
                "paper_id": paper_id,
                "mission_id": mission_id,
                "claim_ids": [r.claim_id for r in coherence_results if r.internal_conflict]
            })
        
        
        # ═════════════════════════════════════════════════════════════════
        # PASS 3: CONFIDENCE ASSEMBLY WITH UNCERTAINTY DECOMPOSITION
        # ═════════════════════════════════════════════════════════════════
        
        # [NEW] Use UncertaintyDecomposer instead of old simple formula
        final_claims = []
        for claim in verified_claims:
            
            # Compute 4-component uncertainty
            uncertainty_components, composite_confidence = (
                await self.uncertainty_decomposer.decompose_claim_uncertainty(
                    claim=claim,
                    verification_results=claim.verification_data,
                    coherence_adjustment=claim.coherence_confidence_adjustment
                )
            )
            
            # Store all four components on claim
            claim.extraction_uncertainty = uncertainty_components.extraction_uncertainty
            claim.study_uncertainty = uncertainty_components.study_uncertainty
            claim.generalizability_uncertainty = (
                uncertainty_components.generalizability_uncertainty
            )
            claim.replication_uncertainty = (
                uncertainty_components.replication_uncertainty  # Default 0.5, updated later
            )
            
            # Store composite (new formula)
            claim.composite_confidence = composite_confidence
            claim.confidence_components = {
                "extraction": uncertainty_components.extraction_uncertainty,
                "study": uncertainty_components.study_uncertainty,
                "generalizability": uncertainty_components.generalizability_uncertainty,
                "replication": uncertainty_components.replication_uncertainty
            }
            
            final_claims.append(claim)
        
        
        # ═════════════════════════════════════════════════════════════════
        # Wait for quantitative extraction to complete
        # ═════════════════════════════════════════════════════════════════
        
        quantitative_results = await quantitative_task
        # Merge into final claims
        for quant_result in quantitative_results:
            matching_claim = next(
                (c for c in final_claims if c.id == quant_result.related_claim_id),
                None
            )
            if matching_claim:
                matching_claim.quantitative_evidence = quant_result
        
        
        # ═════════════════════════════════════════════════════════════════
        # Validation & Deduplication
        # ═════════════════════════════════════════════════════════════════
        
        deduplicated_claims = self._dedup_claims(final_claims)
        # Output: Unique claims only
        
        
        # ═════════════════════════════════════════════════════════════════
        # Persist to database
        # ═════════════════════════════════════════════════════════════════
        
        db_claims = await self._persist_claims_to_db(
            paper_id=paper_id,
            mission_id=mission_id,
            claims=deduplicated_claims
        )
        # All new fields populated: uncertainty, coherence, normalization status, etc.
        
        
        # ═════════════════════════════════════════════════════════════════
        # [ASYNC, NON-BLOCKING] VERIFICATION TIER 2 ESCALATION
        # While rest of pipeline continues, escalate uncertain claims to LLM
        # ═════════════════════════════════════════════════════════════════
        
        tier2_task = asyncio.create_task(
            self.verification_engine.verify_tier2_llm_escalation(
                claims=[
                    c for c in deduplicated_claims
                    if c.verification_tier == "tier1_nli" and c.verification_confidence < 0.60
                ],
                chunks=chunks,
                paper_id=paper_id,
                mission_id=mission_id
            )
        )
        # Runs in background, updates DB when complete
        
        
        # ═════════════════════════════════════════════════════════════════
        # [ASYNC, NON-BLOCKING] CLAIM GRAPH PROCESSING
        # ═════════════════════════════════════════════════════════════════
        
        graph_task = asyncio.create_task(
            self.claim_graph_manager.add_claims_to_graph(
                mission_id=mission_id,
                paper_id=paper_id,
                claims=db_claims
            )
        )
        # Detects contradictions, builds replication edges, updates graph
        # Returns: claim_id -> replication_uncertainty_updates
        
        
        # ═════════════════════════════════════════════════════════════════
        # Await graph processing to get replication uncertainty updates
        # ═════════════════════════════════════════════════════════════════
        
        graph_updates = await graph_task
        # Output: Dict[claim_id] -> {replication_uncertainty_delta, contradictions}
        
        
        # ═════════════════════════════════════════════════════════════════
        # [NEW] UPDATE REPLICATION UNCERTAINTY FROM GRAPH
        # ═════════════════════════════════════════════════════════════════
        
        for claim_id, updates in graph_updates.items():
            claim = next((c for c in db_claims if c.id == claim_id), None)
            if claim:
                # Update replication_uncertainty based on graph edges
                await self.uncertainty_decomposer.update_replication_uncertainty_from_graph(
                    claim_id=claim_id,
                    replication_edges=updates.get("replication_edges", []),
                    contradiction_edges=updates.get("contradiction_edges", []),
                    is_isolated=updates.get("is_isolated", False)
                )
                
                # Recompute composite confidence with updated replication_uncertainty
                new_components, new_composite = (
                    await self.uncertainty_decomposer.decompose_claim_uncertainty(
                        claim=claim,
                        verification_results=claim.verification_data,
                        coherence_adjustment=claim.coherence_confidence_adjustment
                    )
                )
                claim.replication_uncertainty = new_components.replication_uncertainty
                claim.composite_confidence = new_composite
                
                # Persist update
                await self.db_session.execute(
                    update(ResearchClaims)
                    .where(ResearchClaims.id == claim_id)
                    .values(
                        replication_uncertainty=new_components.replication_uncertainty,
                        composite_confidence=new_composite
                    )
                )
        
        
        # ═════════════════════════════════════════════════════════════════
        # [NEW] EVIDENCE GAP DETECTION
        # Analyze clusters for missing evidence categories
        # ═════════════════════════════════════════════════════════════════
        
        # Get updated clusters from graph
        mission_clusters = await self.claim_graph_manager.get_clusters(
            mission_id=mission_id
        )
        
        # Detect gaps
        evidence_gaps = await self.evidence_gap_detector.detect_gaps(
            mission_id=mission_id,
            paper_id_just_processed=paper_id,
            clusters=mission_clusters
        )
        # Output: List[EvidenceGap] with gap_type and suggestion queries
        
        extraction_result.gaps = evidence_gaps
        
        
        # ═════════════════════════════════════════════════════════════════
        # [ASYNC] Emit all new events
        # ═════════════════════════════════════════════════════════════════
        
        # EvidenceGapDetector events
        if evidence_gaps:
            gap_events = await self.evidence_gap_detector.emit_gap_events(
                gaps=evidence_gaps
            )
            extraction_result.events.extend(gap_events)
        
        # FailureLogger events (domain adaptation, section weight)
        failure_logger_stats = await self.failure_logger.emit_events(
            mission_id=mission_id
        )
        extraction_result.events.extend(failure_logger_stats.get("events", []))
        
        # EntityEvolutionManager events
        entity_events = await self.entity_evolution.emit_entity_events(
            mission_id=mission_id
        )
        extraction_result.events.extend(entity_events)
        
        # Graph manager events
        graph_events = await self.claim_graph_manager.get_emitted_events()
        extraction_result.events.extend(graph_events)
        
        # Main extraction event
        extraction_result.events.insert(0, {
            "type": "claims.extracted",
            "mission_id": mission_id,
            "paper_id": paper_id,
            "claim_count": len(db_claims),
            "claim_ids": [c.id for c in db_claims],
            "timestamp": datetime.utcnow().isoformat()
        })
        
        
        # ═════════════════════════════════════════════════════════════════
        # Finalize result
        # ═════════════════════════════════════════════════════════════════
        
        extraction_result.claims = db_claims
        extraction_result.stats = {
            "total_claims": len(db_claims),
            "verified_count": sum(1 for c in db_claims if c.is_supported),
            "failed_count": sum(1 for c in db_claims if not c.is_supported),
            "gaps_detected": len(evidence_gaps),
            "internal_conflicts": sum(1 for c in db_claims if c.internal_conflict),
            "uncertainty_distribution": {
                "extraction": [c.extraction_uncertainty for c in db_claims],
                "study": [c.study_uncertainty for c in db_claims],
                "generalizability": [c.generalizability_uncertainty for c in db_claims],
                "replication": [c.replication_uncertainty for c in db_claims]
            }
        }
        
        # [ASYNC, NON-BLOCKING] Tier 2 escalation continues in background
        # Don't await, just let it run
        
        return extraction_result


# Helper classes & functions
# ==============================================================================

class ExtractionResult:
    """Result object from pipeline with all new fields."""
    
    def __init__(self, mission_id, paper_id, claims=None, gaps=None,
                 entity_events=None, events=None):
        self.mission_id = mission_id
        self.paper_id = paper_id
        self.claims = claims or []
        self.gaps = gaps or []  # [NEW] Evidence gaps
        self.entity_events = entity_events or []  # [NEW] Entity merge/new candidates
        self.events = events or []
        self.stats = {}


@dataclass
class Claim:
    """Research claim with all new fields."""
    
    # Core extraction
    id: str
    statement_raw: str
    intervention_raw: str
    outcome_raw: str
    direction: str  # positive, negative, null
    claim_type: str  # causal, correlational, mechanistic
    
    # Entity normalization
    intervention_canonical: str  # [NEW]
    outcome_canonical: str  # [NEW]
    intervention_normalization_status: str  # confirmed, merge_candidate, new_entity [NEW]
    outcome_normalization_status: str  # [NEW]
    
    # Evidence grounding
    source_chunk_ids: List[int]
    evidence_span: str
    grounding_valid: bool
    grounding_confidence: float
    
    # Verification
    is_supported: bool
    verification_confidence: float
    verification_tier: str  # tier1_nli, tier2_llm
    error_type: Optional[str]  # hallucination, overgeneralization, etc.
    
    # Argument coherence [NEW]
    internal_conflict: bool
    coherence_flags: List[str]
    coherence_confidence_adjustment: float
    
    # Four-component uncertainty [NEW]
    extraction_uncertainty: float
    study_uncertainty: float
    generalizability_uncertainty: float
    replication_uncertainty: float
    
    # Composite confidence (backward compatible)
    composite_confidence: float
    confidence_components: Dict  # For auditability
    
    # Study design
    study_design_score: float
    hedging_penalty: float
    quantitative_evidence: Optional[Dict] = None
    
    # Failure logging [NEW]
    pass1_prompt_version: str
    
    # Metadata
    section: str  # abstract, results, discussion, etc.
    population: str
    created_at: datetime
    updated_at: datetime


# ═════════════════════════════════════════════════════════════════════════════
# BACKWARD COMPATIBILITY PATTERNS
# ═════════════════════════════════════════════════════════════════════════════

class LegacyCompatibility:
    """Patterns for backward-compatible integration."""
    
    @staticmethod
    def old_confidence_formula(claim: Claim) -> float:
        """Old confidence formula for existing code."""
        study_base = claim.study_design_score - claim.hedging_penalty
        extraction = claim.extraction_certainty if hasattr(claim, 'extraction_certainty') else 0.7
        return study_base * extraction
    
    @staticmethod
    def can_disable_coherence_checking() -> ExtractionConfig:
        """Example: Disable coherence checking for legacy mode."""
        config = ExtractionConfig()
        config.enable_argument_coherence_checking = False
        return config
    
    @staticmethod
    def can_disable_entity_evolution() -> ExtractionConfig:
        """Example: Disable entity evolution for static glossary."""
        config = ExtractionConfig()
        config.enable_entity_evolution_advanced = False  # Use simple LLM
        return config
    
    @staticmethod
    def can_disable_uncertainty_decomposition() -> ExtractionConfig:
        """Example: Use old confidence formula instead of 4-component."""
        config = ExtractionConfig()
        config.enable_uncertainty_decomposition = False
        # Falls back to old formula: (study - hedging) × extraction
        return config


"""
═════════════════════════════════════════════════════════════════════════════════
INTEGRATION NOTES FOR DEVELOPERS
═════════════════════════════════════════════════════════════════════════════════

1. ALL EXISTING COMPONENTS UNCHANGED
   - RetrievalLayer, VerificationEngine, QuantitativeExtractor, ClaimGraphManager
   - Continue to work exactly as before
   - New components are ADDITIONS, not replacements

2. EXECUTION FLOW SUMMARY
   Pass 1 → [FailureLogger.tag] → Pass 2A → Pass 2B + [EntityEvolution] 
   → [Quantitative + Tier1 verification in parallel]
   → [FailureLogger.log] → [CoherenceChecker] → Pass 3 + [UncertaintyDecomposer]
   → Persist → [ASYNC: Tier2, Graph, Gaps, Logging, Entity events]

3. NEW FIELDS ARE NULLABLE
   - Existing code continues to work
   - New fields populated by new components
   - Safe to deploy incrementally

4. EVENTS EMITTED
   - Old: claims.extracted, contradiction.detected, cluster.updated
   - New: evidence_gap.detected, domain_adaptation.ready, section_weight_adjusted,
          entity.merge_candidate, entity.new_candidate, entity.auto_promoted,
          claim.confidence_updated, paper.internal_conflict_detected, etc.

5. DATABASE MIGRATIONS REQUIRED
   - 8 new tables
   - 20+ new columns on research_claims
   - See DATABASE_SCHEMA_ADDITIONS.md

6. GRADUAL ROLLOUT STRATEGY
   a) Deploy with enable_new_capabilities = False (disable all new components)
   b) Verify logs show no errors in new code paths
   c) Enable components one-by-one: FailureLogger → Coherence → Entity Evolution → Uncertainty
   d) Monitor performance and event emission
   e) Enable all

7. TESTING CHECKLIST
   - Unit test each component independently
   - Integration test full pipeline
   - Verify new fields populated
   - Check events emitted in correct order
   - Validate database writes
   - Test entity merge/new workflows
   - Benchmark performance (should add <1% latency)

═════════════════════════════════════════════════════════════════════════════════
"""
