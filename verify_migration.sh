#!/bin/bash
# Quick verification of migration

echo "================================================================================"
echo "MIGRATION VERIFICATION REPORT"
echo "================================================================================"
echo

echo "[1] Columns added to research_claims table:"
docker-compose exec -T postgres psql -U postgres -d LHAS -c \
  "SELECT COUNT(*) as new_columns FROM information_schema.columns 
   WHERE table_name='research_claims' 
   AND column_name IN ('pass1_prompt_version', 'verification_failure_logged', 'internal_conflict', 
                        'coherence_flags', 'extraction_uncertainty', 'glossary_version')" 2>&1 | tail -2

echo
echo "[2] New tables created:"
docker-compose exec -T postgres psql -U postgres -d LHAS -c \
  "SELECT COUNT(*) as new_tables FROM information_schema.tables 
   WHERE table_schema='public' 
   AND table_name IN ('evidence_gaps', 'extraction_failures', 'extraction_successes',
                      'prompt_performance', 'section_quality', 'entity_nodes', 'glossary_versions')" 2>&1 | tail -2

echo
echo "[3] Sample from evidence_gaps table:"
docker-compose exec -T postgres psql -U postgres -d LHAS -c \
  "SELECT * FROM evidence_gaps LIMIT 1;" 2>&1 | tail -5

echo
echo "================================================================================"
echo "MIGRATION VERIFICATION COMPLETE ✓"
echo "================================================================================"
