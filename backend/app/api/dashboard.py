from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Dict, Any, List
from pydantic import BaseModel
from app.database import get_db
from app.services import DashboardService
from app.models import ResearchPaper, PaperSource, ResearchClaim, SynthesisAnswer, ReasoningStep, MissionTimeline, ClaimTypeEnum
from app.services.claim_curation import build_mission_findings
from app.services.synthesis_generation import SynthesisGenerationService

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


# Request/Response Models
class CreateMissionRequest(BaseModel):
    name: str
    query: str
    intent_type: str
    pico_population: str | None = None
    pico_intervention: str | None = None
    pico_comparator: str | None = None
    pico_outcome: str | None = None
    key_concepts: List[str] | None = None


@router.get("/overview")
async def get_dashboard_overview(
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Get complete dashboard overview with mission stats, alerts, and mission list.
    
    This endpoint aggregates data from multiple tables efficiently:
    - Mission statistics (counts by status/health)
    - Recent active alerts with mission context
    - Complete mission list with all dashboard metrics
    
    Returns:
        {
            "stats": {
                "total_missions": int,
                "active_missions": int,
                "missions_needing_attention": int,
                "total_alerts": int
            },
            "alerts": [
                {
                    "id": str,
                    "mission_id": str,
                    "mission_name": str,
                    "alert_type": str,
                    "severity": str,
                    "cycle_number": int,
                    "lifecycle_status": str,
                    "message": str | null,
                    "created_at": str (ISO 8601)
                }
            ],
            "missions": [
                {
                    "id": str,
                    "name": str,
                    "query": str,
                    "intent_type": str,
                    "status": str,
                    "health": str,
                    "last_run": str (ISO 8601) | null,
                    "papers": int,
                    "claims": int,
                    "confidence": float,
                    "sessions": int,
                    "active_alerts": int,
                    "created_at": str (ISO 8601),
                    "updated_at": str (ISO 8601)
                }
            ]
        }
    """
    try:
        service = DashboardService(db)

        # Fetch all data in parallel using async
        stats = await service.get_dashboard_stats()
        alerts = await service.get_recent_alerts(limit=15)
        missions = await service.get_all_missions()

        return {
            "stats": stats,
            "alerts": alerts,
            "missions": missions,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/missions/{mission_id}")
async def get_mission_detail(
    mission_id: str,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Get detailed information about a specific mission.
    
    Args:
        mission_id: The UUID of the mission to retrieve
        
    Returns:
        Mission object with full details including PICO breakdown, decision, etc.
    """
    try:
        service = DashboardService(db)
        mission = await service.get_mission_by_id(mission_id)

        if not mission:
            raise HTTPException(status_code=404, detail=f"Mission {mission_id} not found")

        return mission
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/missions/{mission_id}/alerts")
async def get_mission_alerts(
    mission_id: str,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Get all alerts for a specific mission.
    
    Args:
        mission_id: The UUID of the mission to get alerts for
        
    Returns:
        List of alerts with resolution records if available
    """
    try:
        service = DashboardService(db)
        alerts = await service.get_mission_alerts(mission_id)

        return {
            "mission_id": mission_id,
            "alerts": alerts,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/missions/{mission_id}/papers")
async def get_mission_papers(
    mission_id: str,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Get all papers for a specific mission.
    
    Args:
        mission_id: The UUID of the mission to get papers for
        
    Returns:
        List of papers with scores and metadata
    """
    try:
        stmt = (
            select(ResearchPaper)
            .where(ResearchPaper.mission_id == mission_id)
            .order_by(ResearchPaper.final_score.desc())
        )
        
        result = await db.execute(stmt)
        papers = result.scalars().all()
        
        papers_data = [
            {
                "id": str(paper.id),
                "title": paper.title,
                "authors": paper.authors or [],
                "abstract": paper.abstract,
                "source": paper.source.value if paper.source else "unknown",
                "year": paper.year,
                "final_score": float(paper.final_score) if paper.final_score else 0.0,
                "score_breakdown": paper.score_breakdown,  # CEGC component scores
                "cegc_components": {
                    "pico_match": float(paper.pico_match_score) if paper.pico_match_score else None,
                    "evidence_strength": float(paper.evidence_strength_score) if paper.evidence_strength_score else None,
                    "mechanism_agreement": float(paper.mechanism_agreement_score) if paper.mechanism_agreement_score else None,
                    "assumption_alignment": float(paper.assumption_alignment_score) if paper.assumption_alignment_score else None,
                    "llm_verification": float(paper.llm_verification_score) if paper.llm_verification_score else None,
                },
                "mechanism_description": paper.mechanism_description,
                "arxiv_url": paper.arxiv_url,
                "semantic_scholar_url": paper.semantic_scholar_url,
                "pubmed_url": paper.pubmed_url,
                "pdf_url": paper.pdf_url,
                "rank_in_ingestion": paper.rank_in_ingestion,
                "doi": paper.doi,
            }
            for paper in papers
        ]
        
        return {
            "mission_id": mission_id,
            "papers": papers_data,
            "count": len(papers_data),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/missions/{mission_id}/synthesis")
async def get_mission_synthesis(
    mission_id: str,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Get synthesized answer and key findings for a mission.
    
    Args:
        mission_id: Mission ID
        db: Database session
        
    Returns:
        Current synthesis including answer, findings, uncertainty
    """
    try:
        service = SynthesisGenerationService(db)
        synthesis = await service.get_latest_synthesis(mission_id)
        if not synthesis:
            return {
                "mission_id": mission_id,
                "synthesis": None,
                "message": "No synthesis available yet"
            }
        return {
            "mission_id": mission_id,
            "synthesis": synthesis,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/missions/{mission_id}/claims")
async def get_mission_claims(
    mission_id: str,
    claim_type: str = Query(None),  # supporting, contradicting, neutral, related
    view: str = Query("findings", pattern="^(findings|raw)$"),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Get all claims for a mission with optional filtering.
    
    Args:
        mission_id: Mission ID
        claim_type: Optional filter (supporting, contradicting, neutral, related)
        db: Database session
        
    Returns:
        List of claims matching filters
    """
    try:
        stmt = select(ResearchClaim).where(ResearchClaim.mission_id == mission_id)
        
        if claim_type:
            stmt = stmt.where(ResearchClaim.claim_type == claim_type)
        
        stmt = stmt.order_by(ResearchClaim.composite_confidence.desc())
        
        result = await db.execute(stmt)
        claims = result.scalars().all()

        if view == "raw":
            claims_data = [
                {
                    "id": str(claim.id),
                    "claim_text": claim.statement_raw or claim.statement_normalized or "N/A",
                    "claim_type": claim.claim_type.value,
                    "confidence_score": float(claim.composite_confidence),
                    "paper_title": claim.paper_title or "Unknown",
                    "direction": claim.direction.value if claim.direction else "NULL",
                    "validation_status": claim.validation_status.value if claim.validation_status else "UNKNOWN",
                    "extracted_at": claim.extraction_timestamp.isoformat() if claim.extraction_timestamp else None,
                    "aggregation_scope": "raw_claim",
                }
                for claim in claims
            ]
            return {
                "mission_id": mission_id,
                "claims": claims_data,
                "count": len(claims_data),
                "filter": claim_type or "all",
                "view": "raw",
            }

        findings = build_mission_findings(claims, max_findings=200)
        return {
            "mission_id": mission_id,
            "claims": findings,
            "count": len(findings),
            "filter": claim_type or "all",
            "view": "findings",
            "raw_claim_count": len(claims),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/missions/{mission_id}/reasoning")
async def get_mission_reasoning(
    mission_id: str,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Get structured reasoning steps for a mission.
    
    Args:
        mission_id: Mission ID
        db: Database session
        
    Returns:
        List of reasoning steps in order
    """
    try:
        stmt = (
            select(ReasoningStep)
            .where(ReasoningStep.mission_id == mission_id)
            .order_by(ReasoningStep.step_number)
        )
        
        result = await db.execute(stmt)
        steps = result.scalars().all()
        
        reasoning_data = [
            {
                "id": str(step.id),
                "step_number": step.step_number,
                "reasoning_type": step.reasoning_type,
                "premise": step.premise,
                "logic": step.logic,
                "conclusion": step.conclusion,
                "supporting_paper_ids": step.supporting_paper_ids or [],
                "supporting_claims": step.supporting_claims or [],
                "confidence_score": float(step.confidence_score) if step.confidence_score else None,
                "generated_at": step.generated_at.isoformat() if step.generated_at else None,
            }
            for step in steps
        ]
        
        return {
            "mission_id": mission_id,
            "reasoning_steps": reasoning_data,
            "count": len(reasoning_data),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/missions/{mission_id}/timeline")
async def get_mission_timeline(
    mission_id: str,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Get mission timeline events.
    
    Args:
        mission_id: Mission ID
        db: Database session
        
    Returns:
        List of timeline events in chronological order
    """
    try:
        stmt = (
            select(MissionTimeline)
            .where(MissionTimeline.mission_id == mission_id)
            .order_by(MissionTimeline.occurred_at.desc())
        )
        
        result = await db.execute(stmt)
        events = result.scalars().all()
        
        timeline_data = [
            {
                "id": str(event.id),
                "event_type": event.event_type,
                "event_title": event.event_title,
                "event_description": event.event_description,
                "cycle_number": event.cycle_number,
                "metrics_change": event.metrics_change or {},
                "occurred_at": event.occurred_at.isoformat() if event.occurred_at else None,
            }
            for event in events
        ]
        
        return {
            "mission_id": mission_id,
            "timeline": timeline_data,
            "count": len(timeline_data),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/missions")
async def create_mission(
    request: CreateMissionRequest,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Create a new research mission.
    
    This endpoint creates a new mission with initial metadata and questions.
    The mission starts in IDLE status with HEALTHY health status.
    
    Args:
        request: Mission creation details including name, query, PICO breakdown
        db: Database session
        
    Returns:
        Created mission with all details
    """
    try:
        service = DashboardService(db)
        mission = await service.create_mission(
            name=request.name,
            query=request.query,
            intent_type=request.intent_type,
            pico_population=request.pico_population,
            pico_intervention=request.pico_intervention,
            pico_comparator=request.pico_comparator,
            pico_outcome=request.pico_outcome,
            key_concepts=request.key_concepts,
        )
        return mission
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/missions/{mission_id}")
async def delete_mission(
    mission_id: str,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Delete a mission and all its associated alerts and data.
    
    Args:
        mission_id: ID of the mission to delete
        db: Database session
        
    Returns:
        Confirmation of deletion
    """
    try:
        service = DashboardService(db)
        success = await service.delete_mission(mission_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Mission not found")
        
        return {
            "success": True,
            "message": f"Mission {mission_id} deleted successfully",
            "mission_id": mission_id,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
