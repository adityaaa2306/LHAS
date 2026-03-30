"""NEXT-GENERATION CLAIM EXTRACTION — INTEGRATION GUIDE

Complete specification for integrating 5 new capabilities into the 
existing extraction pipeline. Shows data flow, event emission, 
component orchestration, and updated schemas.
"""


PIPELINE_FLOW_DIAGRAM = """
================================================================================
                    NEXT-GENERATION EXTRACTION PIPELINE
================================================================================

Paper + Mission Input
    ↓
═══════════════════════════════════════════════════════════════════════════════
1. RetrievalLayer: Get semantically relevant chunks
═══════════════════════════════════════════════════════════════════════════════
    ↓
═══════════════════════════════════════════════════════════════════════════════
2. Pass 1: Evidence-grounded LLM extraction (with chunk citations)
   → Outputs: raw_claims with source_chunk_ids, evidence_span
═══════════════════════════════════════════════════════════════════════════════
    ↓ [NEW]
───────────────────────────────────────────────────────────────────────────────
✓ FailureLogger: Track Pass 1 prompt version (for A/B testing)
───────────────────────────────────────────────────────────────────────────────
    ↓
═══════════════════════════════════════════════════════════════════════════════
3. Grounding Validation: Check evidence_span in chunks
═══════════════════════════════════════════════════════════════════════════════
    ↓
═══════════════════════════════════════════════════════════════════════════════
4. Pass 2A: Causal Classification (LLM)
═══════════════════════════════════════════════════════════════════════════════
    ↓
═══════════════════════════════════════════════════════════════════════════════
5. Pass 2B: Entity Normalization (LLM + EntityEvolutionManager boost index)
═══════════════════════════════════════════════════════════════════════════════
    ↓ [PARALLEL]
    ├─────────────────────────────────────────────────────────────────────
    │ QuantitativeExtractor: Extract from tables/figures
    │ (runs in parallel, non-blocking)
    │
    └─ VerificationEngine Tier 1: NLI batch verification (runs in parallel)
       → Output: is_supported, verification_confidence, error_type
    ↓
═══════════════════════════════════════════════════════════════════════════════
6. ArgumentCoherenceChecker: Check paper internal consistency
   → Output: internal_conflict, coherence_flags, confidence_adjustment
═══════════════════════════════════════════════════════════════════════════════
    ↓
═══════════════════════════════════════════════════════════════════════════════
7. UncertaintyDecomposer: Compute 4 uncertainty components
   → Output: extraction_uncertainty, study_uncertainty, 
              generalizability_uncertainty, replication_uncertainty(default 0.5)
   → Compute composite_confidence = sqrt(E × S × G × R)
═══════════════════════════════════════════════════════════════════════════════
    ↓ [ASYNC, NON-BLOCKING]
    ├─────────────────────────────────────────────────────────────────────
    │ VerificationEngine Tier 2: LLM batch verification (escalated)
    │ (runs async, may complete after persistence)
    │
    └─ Validation & Deduplication
    ↓
═══════════════════════════════════════════════════════════════════════════════
8. Persistence: Save claims with all new fields to DB
═══════════════════════════════════════════════════════════════════════════════
    ↓ [ASYNC, AFTER PERSISTENCE]
───────────────────────────────────────────────────────────────────────────────
✓ ClaimGraphManager: Build graph, detect contradictions, update replication_uncertainty
✓ EvidenceGapDetector: Analyze clusters, emit gap suggestions (< 500ms)
✓ FailureLogger: Log verification results, track prompt performance
✓ EntityEvolutionManager: Emit entity.merge_candidate, entity.new_candidate events
───────────────────────────────────────────────────────────────────────────────
    ↓
═══════════════════════════════════════════════════════════════════════════════
9. Event Emission: claims.extracted, gaps detected, graph updated, etc.
═══════════════════════════════════════════════════════════════════════════════
    ↓
Output: Extracted claims with full provenance, 4-component uncertainty, 
        verification status, quantitative evidence, coherence flags
================================================================================

Total Latency: ~16-20 seconds per paper (same as before, non-blocking adds <1%)
"""


COMPONENT_RESPONSIBILITIES = """
================================================================================
                        COMPONENT RESPONSIBILITIES
================================================================================

1. EVIDENCE_GAP_DETECTOR (runs after ClaimGraphManager)
   ─────────────────────────────────────────────────
   Input: Mission clusters from graph
   Processing: Deterministic gap analysis (no LLM)
   Output: List[EvidenceGap] with gap_type and suggestion_query
   Events: evidence_gap.detected
   Latency: < 500ms
   Async: YES (non-blocking)
   
   Gap Types Detected:
   • NULL_RESULT_UNDERREPRESENTED: 3+ claims but no null results
   • MECHANISM_ABSENT: Outcome claims but no mechanistic
   • HIGH_QUALITY_STUDY_ABSENT: No RCT/meta-analysis level claims
   • CONTRADICTING_EVIDENCE_ABSENT: 90%+ one direction (retrieval bias)
   • SUBGROUP_EVIDENCE_ABSENT: All claims identical population


2. FAILURE_LOGGER (runs throughout & post-verification)
   ─────────────────────────────────────────────────
   Input: Claims after Pass 1, verification results
   Processing:
     • Tag Pass 1 with prompt_version (hash of template)
     • Log successes to extraction_successes table
     • Log failures to extraction_failures table
     • Compute pass_rate per prompt_version (every 20 papers)
     • Track section-level quality
   Output: Tables with labeled data
   Events: domain_adaptation.ready (100+ failures), section_weight_adjusted
   Latency: < 50ms writes
   Database: extraction_successes, extraction_failures, 
             prompt_performance, section_quality
   
   Pass Rate Computation:
   • After 20 papers: compute pass_rate per prompt_version
   • If newer prompt_version.pass_rate > current: auto-promote
   • Emit prompt.promoted event


3. ARGUMENT_COHERENCE_CHECKER (runs after verification, before Pass 3)
   ──────────────────────────────────────────────────────────────────
   Input: All claims from one paper + verification results
   Processing: 4 deterministic coherence checks
   Output: CoherenceResult per claim with flags and confidence_adjustment
   
   Checks:
   1. Internal direction conflict: Same relationship, opposite direction
      → Mark internal_conflict=true, emit paper.internal_conflict_detected
      
   2. Scope escalation: Narrow mechanistic + broad causal claim
      → confidence_adjustment *= 0.85 for causal claim
      
   3. Extraction inconsistency: Same finding, vastly different certainty
      → Keep higher, mark lower as replicated=true
      
   4. Null result inconsistency: Null + directional for same population
      → If populations match: INTERNAL_DIRECTION_CONFLICT
      → If populations differ: population_specific=true
   
   Latency: < 100ms
   Async: NO (synchronous in main pipeline)


4. ENTITY_EVOLUTION_MANAGER (integrated into Pass 2B)
   ──────────────────────────────────────────────────
   Input: Entity names from Pass 1, existing glossary
   Processing:
     • Try exact match in confirmed entities
     • Try fuzzy match (similarity 0.88+)
     • Try merge candidate (similarity 0.65-0.88)
     • Create provisional entity (new)
   Output: (canonical_form, status) for each entity
   Events: entity.merge_candidate, entity.new_candidate, entity.auto_promoted
   Database: entity_nodes, glossary_versions, entity_merge_decisions
   
   Operator Review Queue:
   • entity.merge_candidate: Operator confirms merge or rejects
   • entity.new_candidate: Operator confirms new or rejects
   • Auto-promotion: 3+ papers + consistent low confidence → promote
   
   Retrospective Pass:
   • After glossary update, re-normalize uncertain claims
   • Emit normalization.retrospective_update


5. UNCERTAINTY_DECOMPOSER (replaces simple confidence assembly)
   ─────────────────────────────────────────────────────────
   Input: All claim fields (study design, grounding, verification, coherence)
   Processing: Compute 4 components independently
   
   Components:
   
   extraction_uncertainty = extraction_certainty 
                          × verification_confidence 
                          × grounding_factor 
                          × coherence_adjustment
   
   study_uncertainty = (study_design_score - hedging_penalty)
                      × (0.80 if causal_downgrade else 1.0)
                      × (0.70 if not study_design_consistent else 1.0)
   
   generalizability_uncertainty starts at 1.0, deduct:
     - Very narrow population: -0.15
     - internal_conflict: -0.20
     - population_specific: -0.10
     - SCOPE_ESCALATION_SUSPECTED: -0.25
     - animal_model/in_vitro: -0.40
   
   replication_uncertainty = 0.50 (default for new claims)
     → Updated by GraphManager after edges created:
     + 0.15 per REPLICATES edge (max +0.40)
     - 0.20 per CONTRADICTS edge (max -0.45)
     - 0.10 if isolated after 5+ papers
   
   composite_confidence = sqrt(E × S × G × R)
   
   Latency: < 10ms
   Async: NO (synchronous)
   Output: All 5 values stored on claim


VERIFICATION ENGINE TIER 2 ESCALATION
──────────────────────────────────────
While UncertaintyDecomposer works, VerificationEngine Tier 2 runs in parallel:
   • Claims that failed NLI (uncertain/null)
   • Table/figure claims (skip NLI, go to LLM)
   • Batch up to 6 claims per LLM call
   • Run multiple batches in parallel async
   • Update verification results after LLM completes
   • Emit claim.confidence_updated events
"""


UPDATED_CLAIM_SCHEMA = """
================================================================================
                    RESEARCH_CLAIMS TABLE — UPDATED SCHEMA
================================================================================

-- Core extraction (original)
id UUID PRIMARY KEY
statement_raw TEXT
intervention VARCHAR
outcome VARCHAR
direction VARCHAR
claim_type VARCHAR
study_design_score FLOAT
hedging_penalty FLOAT

-- Evidence grounding (Capability 2)
source_chunk_ids INTEGER[]
evidence_span TEXT
grounding_valid BOOLEAN
grounding_confidence FLOAT

-- Verification (Capability 3)
is_supported VARCHAR  -- true, false, partial, uncertain
error_type VARCHAR    -- hallucination, overgeneralization, scope_drift, unsupported
verification_tier VARCHAR  -- tier1_nli, tier2_llm, none
verification_confidence FLOAT

-- Argument coherence (Capability 3)
internal_conflict BOOLEAN
coherence_flags VARCHAR[]  -- INTERNAL_DIRECTION_CONFLICT, SCOPE_ESCALATION, etc.
coherence_confidence_adjustment FLOAT  -- Multiplicative factor

-- Four-component uncertainty (Capability 5)
extraction_uncertainty FLOAT [0-1]
study_uncertainty FLOAT [0-1]
generalizability_uncertainty FLOAT [0-1]
replication_uncertainty FLOAT [0-1]

-- Composite confidence (backward compatible)
composite_confidence FLOAT [0.05-0.95]
confidence_components JSONB  -- Full breakdown for auditability

-- Entity evolution (Capability 4)
intervention_canonical VARCHAR
outcome_canonical VARCHAR
normalization_status VARCHAR  -- confirmed, merge_candidate, new_entity_pending
normalization_confidence FLOAT
glossary_version INTEGER

-- Failure logging (Capability 2)
pass1_prompt_version VARCHAR  -- Hash of prompt template
verification_failure_logged BOOLEAN
verification_success_logged BOOLEAN

-- Other
quantitative_evidence JSONB
population VARCHAR
study_type VARCHAR
created_at TIMESTAMP
updated_at TIMESTAMP

INDEXES:
- PRIMARY (id)
- (mission_id, composite_confidence DESC)
- (mission_id, intervention_canonical, outcome_canonical, direction)
- (extraction_uncertainty, study_uncertainty, generalizability_uncertainty, replication_uncertainty)
- (normalization_status, glossary_version)
- (pass1_prompt_version, mission_id)
"""


EVENT_EMISSION_SEQUENCE = """
================================================================================
                        EVENT EMISSION SEQUENCE
================================================================================

After persistence (async, non-blocking):

1. claims.extracted
   {mission_id, paper_id, claim_count, claim_ids[], timestamp}

2. ClaimGraphManager processes:
   → contradiction.detected {cluster_id, claim_a_id, claim_b_id, severity}
   → cluster.updated {cluster_id, replication_uncertainty_updates}
   → claim.confidence_updated {claim_id, new_composite_confidence, deltas}

3. EvidenceGapDetector processes:
   → evidence_gap.detected {cluster_id, gap_type, suggestion, mission_id}
   → (Ingestion module subscribes, adds suggestions to next retrieval)

4. FailureLogger processes:
   → (If failures >= 100)
   → domain_adaptation.ready {mission_id, failure_count, dataset_path}
   
   → (If section pass_rate < 0.50)
   → section_weight_adjusted {mission_id, section_name, weight_multiplier}

5. EntityEvolutionManager processes:
   → (For each merge candidate)
   → entity.merge_candidate {new_surface_form, nearest_canonical, similarity}
   
   → (For each new candidate)
   → entity.new_candidate {surface_form, context_sentence}
   
   → (For auto-promotions after 3+ papers)
   → entity.auto_promoted {surface_form, paper_count}

6. VerificationEngine Tier 2 (if still running):
   → (When verification complete)
   → claim.verification_tier2_complete {claim_ids[], results}
"""


INTEGRATION_CHECKLIST = """
================================================================================
                        INTEGRATION CHECKLIST
================================================================================

STEP 1: Create Database Tables
─────────────────────────────
☐ evidence_gaps
☐ extraction_failures
☐ extraction_successes
☐ prompt_performance
☐ section_quality
☐ entity_nodes
☐ glossary_versions
☐ entity_merge_decisions
☐ Extend research_claims with new columns (see DATABASE_SCHEMA_ADDITIONS.md)

STEP 2: Import New Components
──────────────────────────────
☐ from app.services.evidence_gap_detector import EvidenceGapDetector
☐ from app.services.failure_logger import FailureLogger
☐ from app.services.argument_coherence_checker import ArgumentCoherenceChecker
☐ from app.services.entity_evolution_manager import EntityEvolutionManager
☐ from app.services.uncertainty_decomposer import UncertaintyDecomposer

STEP 3: Update ClaimExtractionService.__init__
───────────────────────────────────────────────
☐ Initialize: self.evidence_gap_detector = EvidenceGapDetector()
☐ Initialize: self.failure_logger = FailureLogger()
☐ Initialize: self.coherence_checker = ArgumentCoherenceChecker()
☐ Initialize: self.entity_evolution = EntityEvolutionManager()
☐ Initialize: self.uncertainty_decomposer = UncertaintyDecomposer()

STEP 4: Update Pipeline Orchestration
──────────────────────────────────────
After Pass 1:
☐ Call: self.failure_logger.compute_prompt_version(pass1_prompt_template)
☐ Tag: claims with pass1_prompt_version

After Verification:
☐ For each failure: await self.failure_logger.log_failure(...)
☐ For each success: await self.failure_logger.log_success(...)

After Pass 2B (Entity Normalization):
☐ Replace static LLM normalization with:
   canonical, status = await self.entity_evolution.propose_normalization(...)

After Verification, Before Pass 3:
☐ Call: await self.coherence_checker.check_paper_coherence(paper_id, claims)
☐ Update claims with coherence_flags and confidence_adjustment

Before Assertion to DB:
☐ For each claim:
   components, composite = await self.uncertainty_decomposer.decompose_claim_uncertainty(claim)
☐ Update claim with: extraction_uncertainty, study_uncertainty, etc.
☐ Update composite_confidence with new formula

After Persistence:
☐ Call: await self.graph_manager.add_claims_to_graph(...)
☐ Get claim_updates from graph (replication_uncertainty changes)
☐ Call: await self.uncertainty_decomposer.update_replication_uncertainty_from_graph(...)
☐ Call: await self.evidence_gap_detector.detect_gaps(mission_id, clusters)
☐ Call: await self.evidence_gap_detector.emit_gap_events(gaps, event_emitter)
☐ Call: await self.failure_logger.emit_events(event_emitter, mission_id)
☐ Call: await self.entity_evolution.emit_entity_events(event_emitter)

STEP 5: Update Frontend
───────────────────────
☐ Implement ClaimsExplorerCard component (see CLAIMS_EXPLORER_UI_SPEC.md)
☐ Create entity review queue for entity.merge_candidate/entity.new_candidate
☐ Create gap details view in cluster expansion
☐ Show uncertainty dots (E S G R) on claims
☐ Implement contradiction map view
☐ Create uncertainty interpretation modal

STEP 6: Testing
───────────────
☐ Unit test: Each component independently
☐ Integration test: Run sample paper through pipeline
☐ Verify all new fields populated
☐ Verify events emitted correctly
☐ Check database tables populated
☐ Test entity merge/new candidate workflows
☐ Test prompt version tracking
☐ Test coherence detection

STEP 7: Monitoring
──────────────────
☐ Create database views (see DATABASE_SCHEMA_ADDITIONS.md)
☐ Monitor: evidence_gap detection rates
☐ Monitor: failure_logger pass rates by section
☐ Monitor: prompt_version pass rates (for auto-promotion)
☐ Monitor: entity_nodes status distribution
☐ Monitor: uncertainty component distributions
☐ Alert: If any section pass_rate < 0.50
☐ Alert: If contradictions detected in cluster
"""


BACKWARD_COMPATIBILITY = """
================================================================================
                        BACKWARD COMPATIBILITY
================================================================================

All changes are ADDITIVE and OPTIONAL:

1. New columns in research_claims are NULLABLE
   → Existing code continues to work
   → New fields populated only if components run

2. composite_confidence is still computed
   → Old formula: (study_design - hedging) × extraction_certainty
   → New formula: sqrt(E × S × G × R)
   → Both available, recommended to use new

3. Event system is extended, not replaced
   → Old events (claims.extracted) still emitted
   → New events (evidence_gap.detected) added

4. Pipeline stages are hooks, not replacements
   → ArgumentCoherenceChecker can be disabled
   → EntityEvolutionManager can use fixed glossary only
   → All components gracefully degrade

5. Database migrations are one-way forward
   → Old extraction code cannot read new fields
   → But new code can read old claims (treats new fields as None)

To run with legacy only:
   Set ExtractionPipeline flags to False:
   - enable_coherence_checking = False
   - enable_uncertainty_decomposition = False (uses old formula)
   - enable_entity_evolution_advanced = False (uses simple LLM normalization)
"""


PERFORMANCE_CHARACTERISTICS = """
================================================================================
                    PERFORMANCE CHARACTERISTICS
================================================================================

Latency per paper (with all capabilities enabled):

Blocking path:
┌─ Retrieval: 3s
├─ Pass 1: 8s
├─ Pass 2A/2B: 5s
├─ Coherence check: 0.1s
├─ Uncertainty decomposition: 0.01s
└─ Persistence: 0.5s
= ~16.6s blocking

Non-blocking (parallel/async):
├─ QuantitativeExtractor: 2s (parallel with Pass 2B)
├─ VerificationEngine Tier 1: 0.5s (during Pass 3)
├─ VerificationEngine Tier 2: 5s (async, after persistence)
├─ ClaimGraphManager: 0.3s (async after persistence)
├─ EvidenceGapDetector: 0.4s (async after persistence)
└─ FailureLogger: 0.05s (async logging)
= ~0.2s user-perceived overhead

**Total user-perceived: ~16.6s (non-blocking adds <1% perceived latency)**

Memory usage per paper:
- Chunks + embeddings: ~100MB (FAISS cached by paper)
- Claims in memory: ~5MB
- Verification results: ~2MB
- Total peak: ~150MB per concurrent paper

Database writes:
- research_claims: 1 write per paper (50-200 claims)
- extraction_failures: 0-20 writes per paper
- extraction_successes: 30-150 writes per paper
- evidence_gaps: 0-5 writes per paper
- entity_nodes: 0-3 writes per paper (if new entities)

Throughput:
- 50-100 papers/hour on single-executor setup
- Scales linearly with LLM executor concurrency
"""


if __name__ == "__main__":
    print(PIPELINE_FLOW_DIAGRAM)
    print("\n\n")
    print(COMPONENT_RESPONSIBILITIES)
    print("\n\n")
    print(UPDATED_CLAIM_SCHEMA)
    print("\n\n")
    print(EVENT_EMISSION_SEQUENCE)
    print("\n\n")
    print(INTEGRATION_CHECKLIST)
    print("\n\n")
    print(BACKWARD_COMPATIBILITY)
    print("\n\n")
    print(PERFORMANCE_CHARACTERISTICS)
