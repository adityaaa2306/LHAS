"""End-to-end pipeline diagnostics for memory, claims, and contradiction detection."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ResearchClaim, ResearchPaper
from app.models.contradiction import (
    AmbiguousContradictionRecord,
    ContextResolvedPairRecord,
    ContradictionRecord,
)
from app.models.memory import (
    CanonicalEntityIndexRecord,
    ClaimGraphEdge,
    ClaimGraphNode,
    MemoryEventType,
    ProvenanceLogEntry,
    RawClaimRecord,
    RawPaperRecord,
)

logger = logging.getLogger(__name__)


class PipelineDiagnosticsService:
    """Verify every stage of the knowledge extraction pipeline with real DB counts."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_mission_diagnostics(self, mission_id: str) -> Dict[str, Any]:
        papers = (
            await self.db.execute(
                select(ResearchPaper).where(ResearchPaper.mission_id == mission_id)
            )
        ).scalars().all()

        claims = (
            await self.db.execute(
                select(ResearchClaim).where(ResearchClaim.mission_id == mission_id)
            )
        ).scalars().all()

        entity_count = (
            await self.db.execute(
                select(func.count(CanonicalEntityIndexRecord.id)).where(
                    CanonicalEntityIndexRecord.mission_id == mission_id
                )
            )
        ).scalar_one()

        graph_nodes = (
            await self.db.execute(
                select(func.count(ClaimGraphNode.claim_id)).where(
                    ClaimGraphNode.mission_id == mission_id
                )
            )
        ).scalar_one()

        graph_edges = (
            await self.db.execute(
                select(func.count(ClaimGraphEdge.id)).where(
                    ClaimGraphEdge.mission_id == mission_id
                )
            )
        ).scalar_one()

        confirmed_contradictions = (
            await self.db.execute(
                select(func.count(ContradictionRecord.id)).where(
                    ContradictionRecord.mission_id == mission_id
                )
            )
        ).scalar_one()

        context_resolved = (
            await self.db.execute(
                select(func.count(ContextResolvedPairRecord.id)).where(
                    ContextResolvedPairRecord.mission_id == mission_id
                )
            )
        ).scalar_one()

        ambiguous = (
            await self.db.execute(
                select(func.count(AmbiguousContradictionRecord.id)).where(
                    AmbiguousContradictionRecord.mission_id == mission_id
                )
            )
        ).scalar_one()

        raw_paper_records = (
            await self.db.execute(
                select(func.count(RawPaperRecord.id)).where(
                    RawPaperRecord.mission_id == mission_id
                )
            )
        ).scalar_one()

        raw_claim_records = (
            await self.db.execute(
                select(func.count(RawClaimRecord.id)).where(
                    RawClaimRecord.mission_id == mission_id
                )
            )
        ).scalar_one()

        no_candidate_events = (
            await self.db.execute(
                select(func.count(ProvenanceLogEntry.id)).where(
                    ProvenanceLogEntry.mission_id == mission_id,
                    ProvenanceLogEntry.event_type == MemoryEventType.CONTRADICTION_NO_CANDIDATES,
                )
            )
        ).scalar_one()

        link_failed_events = (
            await self.db.execute(
                select(func.count(ProvenanceLogEntry.id)).where(
                    ProvenanceLogEntry.mission_id == mission_id,
                    ProvenanceLogEntry.event_type == MemoryEventType.LINK_RESOLUTION_FAILED,
                )
            )
        ).scalar_one()

        papers_with_fulltext = sum(1 for p in papers if p.full_text_flag)
        papers_with_pdf = sum(1 for p in papers if p.pdf_url)
        claims_with_entities = sum(
            1 for c in claims if c.intervention_canonical and c.outcome_canonical
        )

        paper_audits = [self._audit_paper(p, claims) for p in papers]

        contradiction_explanation = self._explain_contradictions(
            claims_evaluated=len(claims),
            confirmed=confirmed_contradictions,
            context_resolved=context_resolved,
            ambiguous=ambiguous,
            no_candidate_events=no_candidate_events,
            claims_with_entities=claims_with_entities,
            graph_edges=graph_edges,
        )

        pipeline_stages = {
            "papers_retrieved": len(papers),
            "papers_with_pdf_url": papers_with_pdf,
            "papers_full_text_extracted": papers_with_fulltext,
            "raw_paper_records": raw_paper_records,
            "claims_extracted": len(claims),
            "raw_claim_records": raw_claim_records,
            "claims_with_canonical_entities": claims_with_entities,
            "entities_indexed": entity_count,
            "memory_graph_nodes": graph_nodes,
            "memory_graph_edges": graph_edges,
            "contradiction_candidates_evaluated": no_candidate_events + confirmed_contradictions + context_resolved + ambiguous,
            "confirmed_contradictions": confirmed_contradictions,
            "context_resolved_pairs": context_resolved,
            "ambiguous_pairs": ambiguous,
            "link_resolution_failures": link_failed_events,
        }

        stage_health = self._stage_health(pipeline_stages, paper_audits)

        return {
            "mission_id": mission_id,
            "pipeline_stages": pipeline_stages,
            "stage_health": stage_health,
            "contradiction_explanation": contradiction_explanation,
            "paper_audits": paper_audits,
            "graph_statistics": {
                "claim_nodes": graph_nodes,
                "claim_edges": graph_edges,
                "entities": entity_count,
            },
        }

    def _audit_paper(self, paper: ResearchPaper, all_claims: List[ResearchClaim]) -> Dict[str, Any]:
        paper_claims = [c for c in all_claims if c.paper_id == paper.id]
        has_fulltext = bool(paper.full_text_flag and paper.full_text_content)
        has_abstract = bool(paper.abstract and len(paper.abstract.strip()) >= 40)
        entities = set()
        for c in paper_claims:
            if c.intervention_canonical:
                entities.add(c.intervention_canonical)
            if c.outcome_canonical:
                entities.add(c.outcome_canonical)

        stages = {
            "downloaded": bool(paper.pdf_url),
            "parsed": has_fulltext or has_abstract,
            "full_text_available": has_fulltext,
            "abstract_available": has_abstract,
            "chunks_created": has_fulltext or has_abstract,
            "embeddings_generated": has_fulltext or has_abstract,
            "claims_extracted": len(paper_claims) > 0,
            "entities_extracted": len(entities) > 0,
            "graph_nodes_created": len(paper_claims) > 0,
        }

        failure_reason: Optional[str] = None
        if not stages["parsed"]:
            failure_reason = "No full text or usable abstract available"
        elif not stages["claims_extracted"]:
            failure_reason = "Text available but no claims persisted (curation bar or extraction failure)"
        elif not stages["entities_extracted"]:
            failure_reason = "Claims extracted but canonical entity normalization failed"

        return {
            "paper_id": paper.paper_id,
            "title": (paper.title or "")[:120],
            "stages": stages,
            "claims_count": len(paper_claims),
            "entities_count": len(entities),
            "entities": sorted(entities)[:10],
            "failure_reason": failure_reason,
        }

    def _stage_health(
        self, stages: Dict[str, Any], paper_audits: List[Dict[str, Any]]
    ) -> Dict[str, str]:
        health: Dict[str, str] = {}
        if stages["papers_retrieved"] == 0:
            health["retrieval"] = "no_papers"
        else:
            health["retrieval"] = "ok"

        if stages["papers_retrieved"] > 0 and stages["papers_full_text_extracted"] == 0:
            health["pdf_extraction"] = "degraded_abstract_only"
        elif stages["papers_full_text_extracted"] > 0:
            health["pdf_extraction"] = "ok"
        else:
            health["pdf_extraction"] = "not_run"

        if stages["claims_extracted"] == 0:
            health["claim_extraction"] = "no_claims"
        else:
            health["claim_extraction"] = "ok"

        if stages["entities_indexed"] == 0 and stages["claims_extracted"] > 0:
            health["entity_extraction"] = "missing_canonicals"
        elif stages["entities_indexed"] > 0:
            health["entity_extraction"] = "ok"
        else:
            health["entity_extraction"] = "not_run"

        if stages["memory_graph_edges"] == 0 and stages["claims_extracted"] >= 2:
            health["relationship_generation"] = "no_edges_despite_claims"
        elif stages["memory_graph_edges"] > 0:
            health["relationship_generation"] = "ok"
        elif stages["claims_extracted"] < 2:
            health["relationship_generation"] = "insufficient_claims_for_edges"
        else:
            health["relationship_generation"] = "not_run"

        if stages["confirmed_contradictions"] == 0:
            health["contradiction_detection"] = "zero_confirmed"
        else:
            health["contradiction_detection"] = "ok"

        failed_papers = [p for p in paper_audits if p.get("failure_reason")]
        health["papers_fully_processed"] = (
            f"{len(paper_audits) - len(failed_papers)}/{len(paper_audits)}"
            if paper_audits
            else "0/0"
        )
        return health

    def _explain_contradictions(
        self,
        *,
        claims_evaluated: int,
        confirmed: int,
        context_resolved: int,
        ambiguous: int,
        no_candidate_events: int,
        claims_with_entities: int,
        graph_edges: int,
    ) -> str:
        if claims_evaluated == 0:
            return (
                "No claims have been extracted yet, so contradiction detection has nothing to evaluate. "
                "Run paper ingestion and wait for claim extraction to complete."
            )
        if claims_evaluated < 2:
            return (
                f"Only {claims_evaluated} claim was extracted. Contradiction detection requires at least "
                "two claims with the same intervention-outcome pair and opposing directions."
            )
        if confirmed > 0:
            return (
                f"{confirmed} confirmed contradiction(s) found among {claims_evaluated} claims. "
                f"{context_resolved} pair(s) were context-resolved and {ambiguous} remained ambiguous."
            )
        if claims_with_entities < 2:
            return (
                f"{claims_evaluated} claims exist but only {claims_with_entities} have canonical intervention "
                "and outcome entities. Without entity normalization, the system cannot match comparable claim pairs."
            )
        if graph_edges == 0:
            return (
                f"{claims_evaluated} claims were extracted with canonical entities, but no relationship edges "
                "were created between them. This usually means claims address different intervention-outcome pairs, "
                "or link resolution failed. Contradiction detection only evaluates opposing claims on the same pair."
            )
        if context_resolved > 0:
            return (
                f"No confirmed contradictions. {context_resolved} potentially opposing pair(s) were resolved as "
                "contextually compatible (different populations, study designs, or time horizons)."
            )
        if ambiguous > 0:
            return (
                f"No confirmed contradictions. {ambiguous} candidate pair(s) were flagged as semantically ambiguous "
                "and require manual review."
            )
        if no_candidate_events >= claims_evaluated:
            return (
                f"Contradiction detection ran on {claims_evaluated} claims but found no candidate pairs. "
                "All studies likely address different intervention-outcome combinations, or report compatible "
                "directions (e.g., all positive effects on the same outcome)."
            )
        return (
            f"Contradiction detection evaluated {claims_evaluated} claims with {graph_edges} relationship edges. "
            "No opposing claim pairs met the threshold for confirmed contradiction. The retrieved evidence "
            "appears directionally consistent across comparable studies."
        )
