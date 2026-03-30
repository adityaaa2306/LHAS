"""Add next-generation capability columns to research_claims table

Revision ID: 002_nextgen_capabilities
Revises: 001_initial  
Create Date: 2026-03-29

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic
revision = '002_nextgen_capabilities'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add next-generation capability columns"""
    
    # Add FAILURE LOGGING columns
    op.add_column('research_claims', sa.Column(
        'pass1_prompt_version', sa.String(255),
        nullable=True,
        comment='Hash of Pass 1 prompt template for A/B testing'
    ))
    op.add_column('research_claims', sa.Column(
        'verification_failure_logged', sa.Boolean,
        default=False, nullable=False,
        comment='Flag: verification failure has been logged'
    ))
    op.add_column('research_claims', sa.Column(
        'verification_success_logged', sa.Boolean,
        default=False, nullable=False,
        comment='Flag: verification success has been logged'
    ))
    
    # Add ARGUMENT COHERENCE columns
    op.add_column('research_claims', sa.Column(
        'internal_conflict', sa.Boolean,
        default=False, nullable=False,
        comment='Flag: paper has internal direction conflict for this claim'
    ))
    op.add_column('research_claims', sa.Column(
        'coherence_flags', sa.JSON,
        nullable=True,
        comment='Array of coherence issues detected: [INTERNAL_DIRECTION_CONFLICT, SCOPE_ESCALATION, etc.]'
    ))
    op.add_column('research_claims', sa.Column(
        'coherence_confidence_adjustment', sa.Float,
        default=1.0, nullable=False,
        comment='Multiplicative factor for composite_confidence due to coherence issues'
    ))
    
    # Add UNCERTAINTY DECOMPOSITION columns (4-component model)
    op.add_column('research_claims', sa.Column(
        'extraction_uncertainty', sa.Float,
        default=0.5, nullable=False,
        comment='Extraction certainty × verification × grounding × coherence adjustment (0.05-0.95)'
    ))
    op.add_column('research_claims', sa.Column(
        'study_uncertainty', sa.Float,
        default=0.5, nullable=False,
        comment='Study design score × causal factor × consistency factor (0.05-0.95)'
    ))
    op.add_column('research_claims', sa.Column(
        'generalizability_uncertainty', sa.Float,
        default=0.5, nullable=False,
        comment='1.0 minus deductions for population/conflict/scope/animal (0.05-1.0)'
    ))
    op.add_column('research_claims', sa.Column(
        'replication_uncertainty', sa.Float,
        default=0.5, nullable=False,
        comment='Graph-based: 0.5 base, updated by replications/contradictions (+0.15/-0.20 per edge)'
    ))
    op.add_column('research_claims', sa.Column(
        'confidence_components', sa.JSON,
        nullable=True,
        comment='Full breakdown: {extraction, study, generalizability, replication} for auditability'
    ))
    
    # Add ENTITY EVOLUTION columns
    op.add_column('research_claims', sa.Column(
        'intervention_canonical', sa.String(255),
        nullable=True,
        comment='Normalized intervention entity name from dynamic glossary'
    ))
    op.add_column('research_claims', sa.Column(
        'outcome_canonical', sa.String(255),
        nullable=True,
        comment='Normalized outcome entity name from dynamic glossary'
    ))
    op.add_column('research_claims', sa.Column(
        'intervention_normalization_status', sa.String(50),
        nullable=True,
        comment='Status: confirmed, merge_candidate, new_entity_pending, rejected'
    ))
    op.add_column('research_claims', sa.Column(
        'outcome_normalization_status', sa.String(50),
        nullable=True,
        comment='Status: confirmed, merge_candidate, new_entity_pending, rejected'
    ))
    op.add_column('research_claims', sa.Column(
        'glossary_version', sa.Integer,
        default=1, nullable=False,
        comment='Version of glossary used for normalization (for re-normalization tracking)'
    ))
    
    # Create new tables for FAILURE LOGGING
    op.create_table(
        'evidence_gaps',
        sa.Column('id', sa.String(255), primary_key=True),
        sa.Column('mission_id', sa.UUID(), nullable=False, index=True),
        sa.Column('cluster_id', sa.String(255), nullable=False),
        sa.Column('gap_type', sa.String(100), nullable=False),
        sa.Column('cluster_claim_count', sa.Integer, nullable=False),
        sa.Column('suggestion_query', sa.Text(), nullable=True),
        sa.Column('detected_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['mission_id'], ['missions.id'], ondelete='CASCADE'),
        sa.Index('ix_evidence_gaps_mission', 'mission_id'),
        sa.Index('ix_evidence_gaps_cluster', 'cluster_id')
    )
    
    op.create_table(
        'extraction_failures',
        sa.Column('id', sa.String(255), primary_key=True),
        sa.Column('mission_id', sa.UUID(), nullable=False, index=True),
        sa.Column('paper_id', sa.UUID(), nullable=False),
        sa.Column('claim_id', sa.String(255), nullable=False),
        sa.Column('error_type', sa.String(100), nullable=False),
        sa.Column('section_source', sa.String(50), nullable=True),
        sa.Column('pass1_prompt_version', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Index('ix_extraction_failures_mission', 'mission_id'),
        sa.Index('ix_extraction_failures_error_type', 'error_type')
    )
    
    op.create_table(
        'extraction_successes',
        sa.Column('id', sa.String(255), primary_key=True),
        sa.Column('mission_id', sa.UUID(), nullable=False, index=True),
        sa.Column('paper_id', sa.UUID(), nullable=False),
        sa.Column('claim_id', sa.String(255), nullable=False),
        sa.Column('verification_confidence', sa.Float(), nullable=False),
        sa.Column('pass1_prompt_version', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Index('ix_extraction_successes_mission', 'mission_id')
    )
    
    op.create_table(
        'prompt_performance',
        sa.Column('id', sa.String(255), primary_key=True),
        sa.Column('mission_id', sa.UUID(), nullable=False, index=True),
        sa.Column('prompt_version', sa.String(255), nullable=False),
        sa.Column('pass_count', sa.Integer, default=0),
        sa.Column('fail_count', sa.Integer, default=0),
        sa.Column('pass_rate', sa.Float, nullable=False),
        sa.Column('computed_at', sa.DateTime(), nullable=False),
        sa.Index('ix_prompt_performance_mission_version', 'mission_id', 'prompt_version')
    )
    
    op.create_table(
        'section_quality',
        sa.Column('id', sa.String(255), primary_key=True),
        sa.Column('mission_id', sa.UUID(), nullable=False, index=True),
        sa.Column('section_name', sa.String(50), nullable=False),
        sa.Column('pass_count', sa.Integer, default=0),
        sa.Column('fail_count', sa.Integer, default=0),
        sa.Column('pass_rate', sa.Float, nullable=False),
        sa.Column('weight_multiplier', sa.Float, default=1.0),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Index('ix_section_quality_mission_section', 'mission_id', 'section_name')
    )
    
    op.create_table(
        'entity_nodes',
        sa.Column('id', sa.String(255), primary_key=True),
        sa.Column('mission_id', sa.UUID(), nullable=False, index=True),
        sa.Column('canonical_form', sa.String(255), nullable=False),
        sa.Column('entity_type', sa.String(50), nullable=False),
        sa.Column('status', sa.String(50), nullable=False),  # confirmed, provisional, merge_candidate, rejected
        sa.Column('surface_forms', sa.JSON(), nullable=False),
        sa.Column('paper_ids', sa.JSON(), nullable=False),
        sa.Column('confidence', sa.Float(), default=0.5),
        sa.Column('glossary_version', sa.Integer, default=1),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Index('ix_entity_nodes_mission', 'mission_id'),
        sa.Index('ix_entity_nodes_canonical', 'canonical_form')
    )
    
    op.create_table(
        'glossary_versions',
        sa.Column('id', sa.String(255), primary_key=True),
        sa.Column('mission_id', sa.UUID(), nullable=False, index=True),
        sa.Column('version', sa.Integer, nullable=False),
        sa.Column('description', sa.String(500), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Index('ix_glossary_versions_mission_version', 'mission_id', 'version')
    )
    
    op.create_table(
        'entity_merge_decisions',
        sa.Column('id', sa.String(255), primary_key=True),
        sa.Column('mission_id', sa.UUID(), nullable=False, index=True),
        sa.Column('from_entity_id', sa.String(255), nullable=False),
        sa.Column('to_entity_id', sa.String(255), nullable=False),
        sa.Column('decision_type', sa.String(50), nullable=False),  # confirmed_merge, confirmed_new, rejected
        sa.Column('decided_by', sa.String(255), nullable=True),
        sa.Column('decided_at', sa.DateTime(), nullable=False),
        sa.Index('ix_entity_merge_decisions_mission', 'mission_id')
    )


def downgrade() -> None:
    """Remove next-generation capability columns if needed"""
    
    # Drop new tables
    op.drop_table('entity_merge_decisions')
    op.drop_table('glossary_versions')
    op.drop_table('entity_nodes')
    op.drop_table('section_quality')
    op.drop_table('prompt_performance')
    op.drop_table('extraction_successes')
    op.drop_table('extraction_failures')
    op.drop_table('evidence_gaps')
    
    # Drop new columns (nullable, so safe)
    op.drop_column('research_claims', 'glossary_version')
    op.drop_column('research_claims', 'outcome_normalization_status')
    op.drop_column('research_claims', 'intervention_normalization_status')
    op.drop_column('research_claims', 'outcome_canonical')
    op.drop_column('research_claims', 'intervention_canonical')
    op.drop_column('research_claims', 'confidence_components')
    op.drop_column('research_claims', 'replication_uncertainty')
    op.drop_column('research_claims', 'generalizability_uncertainty')
    op.drop_column('research_claims', 'study_uncertainty')
    op.drop_column('research_claims', 'extraction_uncertainty')
    op.drop_column('research_claims', 'coherence_confidence_adjustment')
    op.drop_column('research_claims', 'coherence_flags')
    op.drop_column('research_claims', 'internal_conflict')
    op.drop_column('research_claims', 'verification_success_logged')
    op.drop_column('research_claims', 'verification_failure_logged')
    op.drop_column('research_claims', 'pass1_prompt_version')
