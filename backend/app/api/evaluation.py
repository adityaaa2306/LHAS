from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Mission, RawPaperRecord, ResearchClaim, ResearchPaper
from app.services.alignment_monitoring import AlignmentMonitoringService
from app.services.belief_revision import BeliefRevisionService
from app.services.claim_curation import (
    build_mission_findings,
    claim_metadata_completeness,
    summarize_findings,
)
from app.services.contradiction_handling import ContradictionHandlingService
from app.services.memory_system import MemorySystemService
from app.services.synthesis_generation import SynthesisGenerationService

router = APIRouter(prefix="/api/evaluation", tags=["evaluation"])


def _paper_metadata_completeness(paper: ResearchPaper, raw_lookup: dict[str, RawPaperRecord]) -> float:
    raw = raw_lookup.get(str(paper.id))
    score = 0.0
    if paper.title:
        score += 0.18
    if paper.year:
        score += 0.16
    if (paper.score_breakdown or {}).get("study_type") or paper.mechanism_description:
        score += 0.14
    if paper.doi or paper.arxiv_url or paper.semantic_scholar_url or paper.pubmed_url:
        score += 0.12
    if paper.abstract:
        score += 0.16
    if (paper.full_text_content or "").strip():
        score += 0.12
    if paper.authors:
        score += 0.12
    if raw and raw.payload:
        score = max(score, min(1.0, score + 0.04))
    return round(min(score, 1.0), 3)


@router.get("/missions/{mission_id}/bundle", response_model=dict)
async def export_mission_evaluation_bundle(
    mission_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    mission = await db.get(Mission, mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail=f"Mission {mission_id} not found")

    claims = (
        await db.execute(
            select(ResearchClaim)
            .where(ResearchClaim.mission_id == mission_id)
            .order_by(ResearchClaim.composite_confidence.desc())
        )
    ).scalars().all()
    papers = (
        await db.execute(
            select(ResearchPaper)
            .where(ResearchPaper.mission_id == mission_id)
            .order_by(ResearchPaper.final_score.desc())
        )
    ).scalars().all()
    raw_papers = (
        await db.execute(
            select(RawPaperRecord).where(RawPaperRecord.mission_id == mission_id)
        )
    ).scalars().all()
    raw_lookup = {str(row.research_paper_id): row for row in raw_papers if row.research_paper_id}

    findings = build_mission_findings(claims, max_findings=250)
    contradiction_service = ContradictionHandlingService(db)
    synthesis_service = SynthesisGenerationService(db)
    memory_service = MemorySystemService(db)
    monitoring_service = AlignmentMonitoringService(db)
    belief_service = BeliefRevisionService(db)

    contradictions_overview = await contradiction_service.get_overview(mission_id)
    confirmed = await contradiction_service.get_confirmed(mission_id, limit=250)
    context_resolved = await contradiction_service.get_context_resolved(mission_id, limit=250)
    ambiguous = await contradiction_service.get_ambiguous(mission_id, limit=250)
    latest_synthesis = await synthesis_service.get_latest_synthesis(mission_id)
    synthesis_history = await synthesis_service.get_synthesis_history(mission_id, limit=25)
    monitoring = await monitoring_service.get_monitoring_overview(mission_id)
    memory = await memory_service.get_memory_overview(mission_id)
    belief = await belief_service.get_belief_overview(mission_id)

    claim_completeness = [claim_metadata_completeness(claim) for claim in claims]
    paper_completeness = [_paper_metadata_completeness(paper, raw_lookup) for paper in papers]

    return {
        "mission": {
            "id": mission.id,
            "query": mission.normalized_query,
            "normalized_query": mission.normalized_query,
            "name": mission.name,
            "status": getattr(mission.status, "value", mission.status),
            "session_count": mission.session_count,
            "pico": {
                "population": mission.pico_population,
                "intervention": mission.pico_intervention,
                "comparator": mission.pico_comparator,
                "outcome": mission.pico_outcome,
            },
        },
        "summary": {
            "paper_count": len(papers),
            "raw_claim_count": len(claims),
            "finding_count": len(findings),
            "claim_metadata_completeness_mean": round(sum(claim_completeness) / len(claim_completeness), 3) if claim_completeness else None,
            "paper_metadata_completeness_mean": round(sum(paper_completeness) / len(paper_completeness), 3) if paper_completeness else None,
            "findings_summary": summarize_findings(findings),
            "contradiction_overview": contradictions_overview,
            "contradictions": contradictions_overview,
        },
        "belief": belief,
        "memory": memory,
        "monitoring": monitoring,
        "latest_synthesis": latest_synthesis,
        "synthesis_history": synthesis_history,
        "annotation_candidates": {
            "top_findings": findings[:25],
            "confirmed_contradictions": confirmed[:100],
            "context_resolved_pairs": context_resolved[:50],
            "ambiguous_pairs": ambiguous[:50],
        },
        "raw_support": {
            "claims": [
                {
                    "id": str(claim.id),
                    "statement": claim.statement_normalized or claim.statement_raw,
                    "direction": getattr(claim.direction, "value", claim.direction),
                    "claim_type": getattr(claim.claim_type, "value", claim.claim_type),
                    "intervention_canonical": claim.intervention_canonical,
                    "outcome_canonical": claim.outcome_canonical,
                    "population": claim.population,
                    "confidence": round(float(claim.composite_confidence or 0.0), 3),
                    "study_design_score": round(float(claim.study_design_score or 0.0), 3),
                    "metadata_completeness": claim_metadata_completeness(claim),
                    "paper_title": claim.paper_title,
                }
                for claim in claims[:250]
            ],
            "papers": [
                {
                    "id": str(paper.id),
                    "title": paper.title,
                    "year": paper.year,
                    "final_score": round(float(paper.final_score or 0.0), 3),
                    "source": getattr(paper.source, "value", paper.source),
                    "metadata_completeness": _paper_metadata_completeness(paper, raw_lookup),
                }
                for paper in papers[:250]
            ],
        },
    }
