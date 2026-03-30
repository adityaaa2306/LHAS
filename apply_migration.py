#!/usr/bin/env python3
"""
Apply next-generation capability database migration.
This script directly adds new columns and creates new tables for next-gen features.
"""

import asyncio
import os
import sys
from datetime import datetime
from sqlalchemy import inspect, Column, String, Float, Integer, Boolean, DateTime, ForeignKey, JSON, create_engine, UUID, text
from sqlalchemy.orm import Session
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Parse database URL for sync engine (alembic needs sync)
database_url = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:aditya@localhost:5432/LHAS"
)

# Convert async URL to sync URL
database_url_sync = database_url.replace('postgresql+asyncpg://', 'postgresql://')

print("=" * 80)
print("LHAS NEXT-GENERATION MIGRATION")
print("=" * 80)
print(f"\nDatabase: {database_url_sync.split('@')[1]}")
print(f"Timestamp: {datetime.now().isoformat()}\n")

def column_exists(connection, table_name, column_name):
    """Check if column exists in table"""
    inspector = inspect(connection)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns

def add_column_if_missing(connection, table_name, column_name, column_definition):
    """Add column if it doesn't exist"""
    if column_exists(connection, table_name, column_name):
        print(f"  ✓ Column '{column_name}' already exists")
        return False
    
    # Construct ALTER TABLE statement
    alter_sql = f"ALTER TABLE {table_name} ADD COLUMN {column_definition};"
    try:
        connection.execute(text(alter_sql))
        connection.commit()
        print(f"  ✓ Added column '{column_name}'")
        return True
    except Exception as e:
        print(f"  ✗ Error adding column '{column_name}': {e}")
        connection.rollback()
        return False

def migrate_research_claims_table():
    """Add new columns to research_claims table"""
    engine = create_engine(database_url_sync)
    
    with engine.connect() as connection:
        print("\n[1/2] Migrating 'research_claims' table...")
        
        columns_to_add = [
            # Failure logging columns
            ('pass1_prompt_version', 'pass1_prompt_version VARCHAR(255)'),
            ('verification_failure_logged', 'verification_failure_logged BOOLEAN DEFAULT FALSE'),
            ('verification_success_logged', 'verification_success_logged BOOLEAN DEFAULT FALSE'),
            
            # Argument coherence columns
            ('internal_conflict', 'internal_conflict BOOLEAN DEFAULT FALSE'),
            ('coherence_flags', 'coherence_flags JSONB'),
            ('coherence_confidence_adjustment', 'coherence_confidence_adjustment FLOAT DEFAULT 1.0'),
            
            # Uncertainty decomposition columns
            ('extraction_uncertainty', 'extraction_uncertainty FLOAT DEFAULT 0.5'),
            ('study_uncertainty', 'study_uncertainty FLOAT DEFAULT 0.5'),
            ('generalizability_uncertainty', 'generalizability_uncertainty FLOAT DEFAULT 0.5'),
            ('replication_uncertainty', 'replication_uncertainty FLOAT DEFAULT 0.5'),
            ('confidence_components', 'confidence_components JSONB'),
            
            # Entity evolution columns
            ('intervention_normalization_status', 'intervention_normalization_status VARCHAR(50)'),
            ('outcome_normalization_status', 'outcome_normalization_status VARCHAR(50)'),
            ('glossary_version', 'glossary_version INTEGER DEFAULT 1'),
        ]
        
        added_count = 0
        for col_name, col_def in columns_to_add:
            if add_column_if_missing(connection, 'research_claims', col_name, col_def):
                added_count += 1
        
        print(f"\n  Summary: {added_count}/{len(columns_to_add)} new columns added to research_claims")

def create_new_tables():
    """Create new tables for next-gen features"""
    engine = create_engine(database_url_sync)
    
    with engine.connect() as connection:
        print("\n[2/2] Creating new tables for next-gen features...")
        
        tables_to_create = [
            (
                'evidence_gaps',
                """
                CREATE TABLE IF NOT EXISTS evidence_gaps (
                    id VARCHAR(255) PRIMARY KEY,
                    mission_id UUID NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
                    cluster_id VARCHAR(255) NOT NULL,
                    gap_type VARCHAR(100) NOT NULL,
                    cluster_claim_count INTEGER NOT NULL,
                    suggestion_query TEXT,
                    detected_at TIMESTAMP NOT NULL,
                    CONSTRAINT fk_evidence_gaps_mission FOREIGN KEY (mission_id) REFERENCES missions(id)
                );
                CREATE INDEX IF NOT EXISTS ix_evidence_gaps_mission ON evidence_gaps(mission_id);
                CREATE INDEX IF NOT EXISTS ix_evidence_gaps_cluster ON evidence_gaps(cluster_id);
                """
            ),
            (
                'extraction_failures',
                """
                CREATE TABLE IF NOT EXISTS extraction_failures (
                    id VARCHAR(255) PRIMARY KEY,
                    mission_id UUID NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
                    paper_id UUID NOT NULL,
                    claim_id VARCHAR(255) NOT NULL,
                    error_type VARCHAR(100) NOT NULL,
                    section_source VARCHAR(50),
                    pass1_prompt_version VARCHAR(255),
                    created_at TIMESTAMP NOT NULL,
                    CONSTRAINT fk_extraction_failures_mission FOREIGN KEY (mission_id) REFERENCES missions(id)
                );
                CREATE INDEX IF NOT EXISTS ix_extraction_failures_mission ON extraction_failures(mission_id);
                CREATE INDEX IF NOT EXISTS ix_extraction_failures_error_type ON extraction_failures(error_type);
                """
            ),
            (
                'extraction_successes',
                """
                CREATE TABLE IF NOT EXISTS extraction_successes (
                    id VARCHAR(255) PRIMARY KEY,
                    mission_id UUID NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
                    paper_id UUID NOT NULL,
                    claim_id VARCHAR(255) NOT NULL,
                    verification_confidence FLOAT NOT NULL,
                    pass1_prompt_version VARCHAR(255),
                    created_at TIMESTAMP NOT NULL,
                    CONSTRAINT fk_extraction_successes_mission FOREIGN KEY (mission_id) REFERENCES missions(id)
                );
                CREATE INDEX IF NOT EXISTS ix_extraction_successes_mission ON extraction_successes(mission_id);
                """
            ),
            (
                'prompt_performance',
                """
                CREATE TABLE IF NOT EXISTS prompt_performance (
                    id VARCHAR(255) PRIMARY KEY,
                    mission_id UUID NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
                    prompt_version VARCHAR(255) NOT NULL,
                    pass_count INTEGER DEFAULT 0,
                    fail_count INTEGER DEFAULT 0,
                    pass_rate FLOAT NOT NULL,
                    computed_at TIMESTAMP NOT NULL,
                    CONSTRAINT fk_prompt_performance_mission FOREIGN KEY (mission_id) REFERENCES missions(id)
                );
                CREATE INDEX IF NOT EXISTS ix_prompt_performance_mission_version ON prompt_performance(mission_id, prompt_version);
                """
            ),
            (
                'section_quality',
                """
                CREATE TABLE IF NOT EXISTS section_quality (
                    id VARCHAR(255) PRIMARY KEY,
                    mission_id UUID NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
                    section_name VARCHAR(50) NOT NULL,
                    pass_count INTEGER DEFAULT 0,
                    fail_count INTEGER DEFAULT 0,
                    pass_rate FLOAT NOT NULL,
                    weight_multiplier FLOAT DEFAULT 1.0,
                    updated_at TIMESTAMP NOT NULL,
                    CONSTRAINT fk_section_quality_mission FOREIGN KEY (mission_id) REFERENCES missions(id)
                );
                CREATE INDEX IF NOT EXISTS ix_section_quality_mission_section ON section_quality(mission_id, section_name);
                """
            ),
            (
                'entity_nodes',
                """
                CREATE TABLE IF NOT EXISTS entity_nodes (
                    id VARCHAR(255) PRIMARY KEY,
                    mission_id UUID NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
                    canonical_form VARCHAR(255) NOT NULL,
                    entity_type VARCHAR(50) NOT NULL,
                    status VARCHAR(50) NOT NULL,
                    surface_forms JSONB NOT NULL,
                    paper_ids JSONB NOT NULL,
                    confidence FLOAT DEFAULT 0.5,
                    glossary_version INTEGER DEFAULT 1,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL,
                    CONSTRAINT fk_entity_nodes_mission FOREIGN KEY (mission_id) REFERENCES missions(id)
                );
                CREATE INDEX IF NOT EXISTS ix_entity_nodes_mission ON entity_nodes(mission_id);
                CREATE INDEX IF NOT EXISTS ix_entity_nodes_canonical ON entity_nodes(canonical_form);
                """
            ),
            (
                'glossary_versions',
                """
                CREATE TABLE IF NOT EXISTS glossary_versions (
                    id VARCHAR(255) PRIMARY KEY,
                    mission_id UUID NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
                    version INTEGER NOT NULL,
                    description VARCHAR(500),
                    created_at TIMESTAMP NOT NULL,
                    CONSTRAINT fk_glossary_versions_mission FOREIGN KEY (mission_id) REFERENCES missions(id)
                );
                CREATE INDEX IF NOT EXISTS ix_glossary_versions_mission_version ON glossary_versions(mission_id, version);
                """
            ),
        ]
        
        created_count = 0
        for table_name, create_sql in tables_to_create:
            try:
                connection.execute(text(create_sql))
                connection.commit()
                print(f"  ✓ Created table '{table_name}'")
                created_count += 1
            except Exception as e:
                print(f"  ✗ Error creating table '{table_name}': {e}")
                connection.rollback()
        
        print(f"\n  Summary: {created_count}/{len(tables_to_create)} new tables created")

def main():
    try:
        migrate_research_claims_table()
        create_new_tables()
        
        print("\n" + "=" * 80)
        print("MIGRATION COMPLETE ✓")
        print("=" * 80)
        print("\nNext steps:")
        print("  1. Verify data integrity in pgAdmin")
        print("  2. Test extraction pipeline with sample paper")
        print("  3. Update frontend UI to display new fields")
        print("  4. Deploy to production\n")
        
        return 0
    except Exception as e:
        print(f"\nMIGRATION FAILED: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
