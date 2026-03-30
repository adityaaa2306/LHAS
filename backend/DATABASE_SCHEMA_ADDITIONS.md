"""Database Schema Migrations for Next-Generation Claim Extraction

Alembic migrations for 5 new capabilities:
1. Evidence gap tracking
2. Failure logging with prompt tracking
3. Coherence checking
4. Entity evolution and glossary versioning
5. Four-component uncertainty decomposition

Run with: alembic upgrade head
"""

# Migration pseudo-code (convert to actual Alembic files as needed)

DATABASE_SCHEMA_ADDITIONS = {
    
    # CAPABILITY 1: Evidence Gap Detection
    "evidence_gaps": """
    CREATE TABLE evidence_gaps (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        mission_id VARCHAR NOT NULL,
        cluster_id VARCHAR NOT NULL,
        paper_id_just_processed VARCHAR NOT NULL,
        gap_type VARCHAR NOT NULL,  -- NULL_RESULT, MECHANISM_ABSENT, HIGH_QUALITY, CONTRADICTING, SUBGROUP
        cluster_claim_count INT NOT NULL,
        supporting_claims INT,
        contradicting_claims INT,
        null_claims INT,
        high_quality_claims INT,
        mechanistic_claims INT,
        suggestion TEXT,  -- Retrieval query suggestion
        detected_at TIMESTAMP DEFAULT NOW(),
        created_at TIMESTAMP DEFAULT NOW(),
        
        FOREIGN KEY (mission_id) REFERENCES missions(id),
        INDEX(mission_id, gap_type),
        INDEX(cluster_id, detected_at)
    );
    """,
    
    # CAPABILITY 2: Failure Logging & Prompt Tracking
    "extraction_failures": """
    CREATE TABLE extraction_failures (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        claim_id UUID NOT NULL,
        paper_id VARCHAR NOT NULL,
        mission_id VARCHAR NOT NULL,
        claim_statement TEXT NOT NULL,
        evidence_span TEXT,
        error_type VARCHAR NOT NULL,  -- hallucination, overgeneralization, scope_drift, unsupported
        source_chunk_id VARCHAR,
        section_source VARCHAR,  -- abstract, results, discussion, conclusion, unknown
        extraction_certainty FLOAT,
        pass1_prompt_version VARCHAR NOT NULL,
        recorded_at TIMESTAMP DEFAULT NOW(),
        
        INDEX(mission_id, pass1_prompt_version),
        INDEX(section_source, mission_id),
        INDEX(error_type)
    );
    """,
    
    "extraction_successes": """
    CREATE TABLE extraction_successes (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        claim_id UUID NOT NULL,
        paper_id VARCHAR NOT NULL,
        mission_id VARCHAR NOT NULL,
        claim_statement TEXT NOT NULL,
        evidence_span TEXT,
        verification_confidence FLOAT,
        source_chunk_id VARCHAR,
        section_source VARCHAR,
        extraction_certainty FLOAT,
        pass1_prompt_version VARCHAR NOT NULL,
        recorded_at TIMESTAMP DEFAULT NOW(),
        
        INDEX(mission_id, pass1_prompt_version),
        INDEX(section_source, mission_id)
    );
    """,
    
    "prompt_performance": """
    CREATE TABLE prompt_performance (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        mission_id VARCHAR NOT NULL,
        prompt_version VARCHAR NOT NULL,
        total_attempts INT,
        successful_verifications INT,
        failed_verifications INT,
        pass_rate FLOAT,
        computed_at TIMESTAMP DEFAULT NOW(),
        
        UNIQUE(mission_id, prompt_version),
        INDEX(mission_id, pass_rate DESC)
    );
    """,
    
    "section_quality": """
    CREATE TABLE section_quality (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        mission_id VARCHAR NOT NULL,
        section_name VARCHAR NOT NULL,
        pass_rate FLOAT,
        claim_count INT,
        weight_multiplier FLOAT DEFAULT 1.0,
        tracked_at TIMESTAMP DEFAULT NOW(),
        
        UNIQUE(mission_id, section_name),
        INDEX(mission_id, pass_rate)
    );
    """,
    
    # CAPABILITY 3: Argument Coherence Checking
    # (Extended columns in research_claims table — see below)
    
    # CAPABILITY 4: Entity Evolution & Vocabulary
    "entity_nodes": """
    CREATE TABLE entity_nodes (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        entity_id VARCHAR NOT NULL UNIQUE,
        mission_id VARCHAR NOT NULL,
        canonical_form VARCHAR NOT NULL,
        status VARCHAR NOT NULL,  -- confirmed, provisional, merge_candidate, rejected
        context TEXT,
        surface_forms TEXT[],  -- ARRAY of surface forms
        paper_ids TEXT[],  -- ARRAY of paper IDs where entity appears
        normalization_confidence FLOAT,
        glossary_version INT,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        
        INDEX(mission_id, canonical_form),
        INDEX(status),
        INDEX(glossary_version)
    );
    """,
    
    "glossary_versions": """
    CREATE TABLE glossary_versions (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        mission_id VARCHAR NOT NULL,
        version INT NOT NULL,
        description TEXT,
        changed_at TIMESTAMP DEFAULT NOW(),
        
        UNIQUE(mission_id, version),
        INDEX(mission_id, version DESC)
    );
    """,
    
    "entity_merge_decisions": """
    CREATE TABLE entity_merge_decisions (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        mission_id VARCHAR NOT NULL,
        new_surface_form VARCHAR NOT NULL,
        canonical_form VARCHAR NOT NULL,
        operator_id VARCHAR,  -- Who made decision
        decision_type VARCHAR,  -- confirmed_merge, confirmed_new, rejected
        decided_at TIMESTAMP DEFAULT NOW(),
        
        INDEX(mission_id, decided_at)
    );
    """,
    
    # CAPABILITY 5: Four-Component Uncertainty
    # (Extended columns in research_claims table — see below)
}


RESEARCH_CLAIMS_EXTENDED_SCHEMA = """
-- Add to existing research_claims table:

ALTER TABLE research_claims ADD COLUMN (
    
    -- COHERENCE CHECKING
    internal_conflict BOOLEAN DEFAULT FALSE,
    coherence_flags TEXT[],  -- ARRAY of flag types
    coherence_confidence_adjustment FLOAT DEFAULT 1.0,
    
    -- UNCERTAINTY DECOMPOSITION (replaces old composite_confidence logic)
    extraction_uncertainty FLOAT,
    study_uncertainty FLOAT,
    generalizability_uncertainty FLOAT,
    replication_uncertainty FLOAT,
    
    -- Keep for backward compatibility
    composite_confidence FLOAT,  -- Now computed as geometric mean
    confidence_components JSONB,  -- Full breakdown for auditability
    
    -- ENTITY EVOLUTION
    normalization_status VARCHAR,  -- confirmed, merge_candidate, new_entity_pending
    glossary_version INT,  -- Which glossary version used
    
    -- VERIFICATION TRACKING (from FailureLogger)
    verification_failure_logged BOOLEAN DEFAULT FALSE,
    verification_success_logged BOOLEAN DEFAULT FALSE,
    pass1_prompt_version VARCHAR,
    
    -- Graph generation tracking
    claim_confidence_updated_at TIMESTAMP
);

CREATE INDEX research_claims_uncertainties ON research_claims(
    extraction_uncertainty, study_uncertainty, 
    generalizability_uncertainty, replication_uncertainty
);

CREATE INDEX research_claims_mission_confidence ON research_claims(
    mission_id, composite_confidence DESC
);

CREATE INDEX research_claims_evidence_gaps ON research_claims(
    mission_id, intervention_canonical, outcome_canonical, direction
);
"""


EVENTS_TABLE_EXTENSION = """
-- New event types to add to existing events table:

INSERT INTO event_types (name, description) VALUES
('evidence_gap.detected', 'Evidence gap detected in cluster'),
('domain_adaptation.ready', 'Domain adaptation dataset ready \(100+ failures\)'),
('section_weight_adjusted', 'Retrieval weight adjusted for section'),
('entity.merge_candidate', 'Entity merge operator review pending'),
('entity.new_candidate', 'New entity operator review pending'),
('entity.auto_promoted', 'Provisional entity auto-promoted to confirmed'),
('claim.confidence_updated', 'Claim confidence updated from graph'),
('paper.internal_conflict_detected', 'Paper with internal direction conflict'),
('paper.coherence_checked', 'Paper coherence analysis complete'),
('prompt.performance_computed', 'Prompt version pass rate computed'),
('prompt.promoted', 'Prompt version auto-promoted as best performer');
"""


MONITORING_VIEWS = """
-- Create views for monitoring

CREATE VIEW v_evidence_gap_summary AS
SELECT 
    eg.mission_id,
    eg.gap_type,
    COUNT(*) as gap_count,
    AVG(eg.cluster_claim_count) as avg_cluster_size,
    MAX(eg.detected_at) as most_recent
FROM evidence_gaps eg
GROUP BY eg.mission_id, eg.gap_type
ORDER BY eg.mission_id, gap_count DESC;

CREATE VIEW v_prompt_performance_summary AS
SELECT 
    pp.mission_id,
    pp.prompt_version,
    pp.pass_rate,
    pp.total_attempts,
    RANK() OVER (PARTITION BY pp.mission_id ORDER BY pp.pass_rate DESC) as rank
FROM prompt_performance pp;

CREATE VIEW v_extraction_quality_by_section AS
SELECT 
    sq.mission_id,
    sq.section_name,
    sq.pass_rate,
    sq.claim_count,
    sq.weight_multiplier,
    CASE 
        WHEN sq.pass_rate < 0.50 AND sq.claim_count >= 5 THEN 'DEGRADED'
        WHEN sq.pass_rate < 0.70 THEN 'WATCH'
        ELSE 'NORMAL'
    END as status
FROM section_quality sq;

CREATE VIEW v_entity_glossary_status AS
SELECT 
    mission_id,
    status,
    COUNT(*) as entity_count,
    glossary_version
FROM entity_nodes
GROUP BY mission_id, status, glossary_version;

CREATE VIEW v_uncertainty_distribution AS
SELECT 
    mission_id,
    ROUND(AVG(CAST(extraction_uncertainty AS NUMERIC)), 3) as avg_extraction,
    ROUND(AVG(CAST(study_uncertainty AS NUMERIC)), 3) as avg_study,
    ROUND(AVG(CAST(generalizability_uncertainty AS NUMERIC)), 3) as avg_generalizability,
    ROUND(AVG(CAST(replication_uncertainty AS NUMERIC)), 3) as avg_replication,
    COUNT(*) as claim_count
FROM research_claims
WHERE mission_id IS NOT NULL
GROUP BY mission_id;
"""


MIGRATION_INSTRUCTIONS = """
# Database Migration Instructions

## Step 1: Create new tables
Run migrations in this order:
1. evidence_gaps
2. extraction_failures, extraction_successes
3. prompt_performance, section_quality
4. entity_nodes, glossary_versions, entity_merge_decisions

## Step 2: Extend existing tables
ALTER research_claims table with new columns:
- Coherence: internal_conflict, coherence_flags, coherence_confidence_adjustment
- Uncertainty: extraction_uncertainty, study_uncertainty, generalizability_uncertainty, replication_uncertainty
- Entity evolution: normalization_status, glossary_version
- Verification tracking: verification_failure_logged, verification_success_logged, pass1_prompt_version

## Step 3: Create indexes
Create indexes on frequently-queried columns (see schema above).

## Step 4: Create views
Create monitoring views for observability.

## Step 5: Backfill (optional)
For existing missions, backfill uncertainty components:
- SET extraction_uncertainty = old composite_confidence * 0.8 for legacy data
- This preserves approximate confidence while distinguishing components

## Rollback
If needed, the new columns are all NULLABLE/optional, so old code continues to work.
The new components are initialized to sensible defaults if missing.

## Performance notes
- evidence_gaps table grows ~0.5KB per gap (typically 1-3 per paper)
- extraction_failures/successes grow ~1KB per entry (significant after 1000+ papers)
- entity_nodes grows slowly unless high entity variance
- Index creation on large tables may take minutes — run during low-traffic window
"""

print(__doc__)
print("\n" + "="*80 + "\n")
print("SCHEMA ADDITIONS:")
for table_name, schema_sql in DATABASE_SCHEMA_ADDITIONS.items():
    print(f"\n{table_name}:\n{schema_sql}")

print("\n" + "="*80 + "\n")
print("RESEARCH_CLAIMS EXTENSIONS:")
print(RESEARCH_CLAIMS_EXTENDED_SCHEMA)

print("\n" + "="*80 + "\n")
print("MONITORING VIEWS:")
print(MONITORING_VIEWS)

print("\n" + "="*80 + "\n")
print("MIGRATION INSTRUCTIONS:")
print(MIGRATION_INSTRUCTIONS)
