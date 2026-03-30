"""Claims API endpoints - MODULE 3 CLAIM EXTRACTION

Routes:
- GET /api/claims/mission/{mission_id} - List all claims for mission
- GET /api/claims/{claim_id} - Get single claim with full provenance
- GET /api/claims/mission/{mission_id}/stats - Claim statistics
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from typing import Optional, List
from uuid import UUID

from app.database import get_db
from app.models import ResearchClaim, ResearchPaper
from app.models.claims import ClaimTypeEnum, DirectionEnum, ValidationStatusEnum

router = APIRouter(prefix="/api/claims", tags=["claims"])


@router.get("/mission/{mission_id}", response_model=dict)
async def list_claims_for_mission(
    mission_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    claim_type: Optional[str] = None,
    direction: Optional[str] = None,
    min_confidence: Optional[float] = Query(None, ge=0.05, le=0.95),
    max_confidence: Optional[float] = Query(None, ge=0.05, le=0.95),
    validation_status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    List all claims for a mission with optional filtering.
    
    Query Parameters:
    - skip: Number of results to skip (pagination)
    - limit: Max results per page (default 50, max 500)
    - claim_type: Filter by epistemic type (causal, correlational, etc.)
    - direction: Filter by effect direction (positive, negative, null, unclear)
    - min_confidence: Filter by minimum composite confidence
    - max_confidence: Filter by maximum composite confidence
    - validation_status: Filter by validation status (VALID, EXTRACTION_DEGRADED, UNKNOWN_TYPE)
    
    Returns: { total, claims, has_more, confidence_stats }
    """
    try:
        # Build query
        query = select(ResearchClaim).where(ResearchClaim.mission_id == mission_id)
        
        # Apply filters
        if claim_type:
            query = query.where(ResearchClaim.claim_type == claim_type)
        if direction:
            query = query.where(ResearchClaim.direction == direction)
        if min_confidence:
            query = query.where(ResearchClaim.composite_confidence >= min_confidence)
        if max_confidence:
            query = query.where(ResearchClaim.composite_confidence <= max_confidence)
        if validation_status:
            query = query.where(ResearchClaim.validation_status == validation_status)
        
        # Get total count
        count_query = select(func.count(ResearchClaim.id)).where(
            ResearchClaim.mission_id == mission_id
        )
        total_result = await db.execute(count_query)
        total = total_result.scalar()
        
        # Apply pagination
        query = query.offset(skip).limit(limit)
        
        # Execute query
        result = await db.execute(query)
        claims = result.scalars().all()
        
        # Format response
        return {
            "total": total,
            "claims": [_format_claim(c) for c in claims],
            "has_more": (skip + len(claims)) < total,
            "skip": skip,
            "limit": limit
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve claims: {str(e)}")


@router.get("/{claim_id}", response_model=dict)
async def get_claim(
    claim_id: UUID,
    db: AsyncSession = Depends(get_db)
) -> dict:
    """
    Get a single claim by ID with full provenance and metadata.
    
    Returns: Complete claim object with:
    - All pass outputs (Pass 1-3 fields)
    - Full provenance record
    - Paper metadata
    - Confidence component breakdown
    """
    try:
        query = select(ResearchClaim).where(ResearchClaim.id == claim_id)
        result = await db.execute(query)
        claim = result.scalar_one_or_none()
        
        if not claim:
            raise HTTPException(status_code=404, detail=f"Claim {claim_id} not found")
        
        return _format_claim_detailed(claim)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve claim: {str(e)}")


@router.get("/mission/{mission_id}/stats", response_model=dict)
async def get_claim_statistics(
    mission_id: UUID,
    db: AsyncSession = Depends(get_db)
) -> dict:
    """
    Get statistics about claims extracted for a mission.
    
    Returns:
    - total_claims: Count of all claims
    - valid_claims: Only VALID validation status
    - degraded_claims: EXTRACTION_DEGRADED status
    - by_type: Count breakdown by epistemic type
    - by_direction: Count breakdown by effect direction
    - by_section: Count breakdown by section source
    - confidence_distribution: Percentiles & quartiles
    - average_confidence: Mean composite_confidence
    - normalization_quality: % of claims with canonical entities
    """
    try:
        # Total counts
        total_result = await db.execute(
            select(func.count(ResearchClaim.id)).where(
                ResearchClaim.mission_id == mission_id
            )
        )
        total = total_result.scalar() or 0
        
        if total == 0:
            return {
                "total_claims": 0,
                "message": "No claims extracted for this mission"
            }
        
        # By validation status
        valid_result = await db.execute(
            select(func.count(ResearchClaim.id)).where(
                and_(
                    ResearchClaim.mission_id == mission_id,
                    ResearchClaim.validation_status == ValidationStatusEnum.VALID.value
                )
            )
        )
        valid = valid_result.scalar() or 0
        
        degraded_result = await db.execute(
            select(func.count(ResearchClaim.id)).where(
                and_(
                    ResearchClaim.mission_id == mission_id,
                    ResearchClaim.validation_status == ValidationStatusEnum.EXTRACTION_DEGRADED.value
                )
            )
        )
        degraded = degraded_result.scalar() or 0
        
        # By claim type
        type_result = await db.execute(
            select(ResearchClaim.claim_type, func.count(ResearchClaim.id)).where(
                ResearchClaim.mission_id == mission_id
            ).group_by(ResearchClaim.claim_type)
        )
        by_type = {str(row[0]): row[1] for row in type_result.all() if row[0]}
        
        # By direction
        direction_result = await db.execute(
            select(ResearchClaim.direction, func.count(ResearchClaim.id)).where(
                ResearchClaim.mission_id == mission_id
            ).group_by(ResearchClaim.direction)
        )
        by_direction = {str(row[0]): row[1] for row in direction_result.all()}
        
        # Get all confidence values for distribution
        confidence_result = await db.execute(
            select(ResearchClaim.composite_confidence).where(
                ResearchClaim.mission_id == mission_id
            )
        )
        confidences = [row[0] for row in confidence_result.all()]
        
        # Calculate statistics
        if confidences:
            avg_confidence = sum(confidences) / len(confidences)
            sorted_conf = sorted(confidences)
            p25_idx = len(sorted_conf) // 4
            p50_idx = len(sorted_conf) // 2
            p75_idx = (3 * len(sorted_conf)) // 4
            
            confidence_stats = {
                "mean": round(avg_confidence, 3),
                "min": round(min(confidences), 3),
                "max": round(max(confidences), 3),
                "p25": round(sorted_conf[p25_idx], 3),
                "median": round(sorted_conf[p50_idx], 3),
                "p75": round(sorted_conf[p75_idx], 3),
            }
        else:
            confidence_stats = {}
        
        # Normalization quality
        canonical_result = await db.execute(
            select(func.count(ResearchClaim.id)).where(
                and_(
                    ResearchClaim.mission_id == mission_id,
                    ResearchClaim.intervention_canonical.isnot(None),
                    ResearchClaim.outcome_canonical.isnot(None)
                )
            )
        )
        canonical_count = canonical_result.scalar() or 0
        normalization_quality = (canonical_count / total * 100) if total > 0 else 0
        
        return {
            "total_claims": total,
            "valid_claims": valid,
            "degraded_claims": degraded,
            "percentage_valid": round(valid / total * 100, 1) if total > 0 else 0,
            "by_type": by_type,
            "by_direction": by_direction,
            "confidence_statistics": confidence_stats,
            "normalization_quality_percentage": round(normalization_quality, 1),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to compute statistics: {str(e)}")


def _format_claim(claim: ResearchClaim) -> dict:
    """Format claim for list view (minimal fields)"""
    return {
        "id": str(claim.id),
        "paper_id": str(claim.paper_id),
        "statement_raw": claim.statement_raw,
        "statement_normalized": claim.statement_normalized,
        "intervention": claim.intervention,
        "intervention_canonical": claim.intervention_canonical,
        "outcome": claim.outcome,
        "outcome_canonical": claim.outcome_canonical,
        "direction": claim.direction,
        "claim_type": claim.claim_type,
        "composite_confidence": round(claim.composite_confidence, 3),
        "validation_status": claim.validation_status,
        "mission_relevance": claim.mission_relevance,
        "section_source": claim.section_source,
    }


def _format_claim_detailed(claim: ResearchClaim) -> dict:
    """Format claim for detail view (all fields + provenance)"""
    confidence_components = claim.provenance.get('confidence_components', {}) if claim.provenance else {}
    
    return {
        # Identity
        "id": str(claim.id),
        "mission_id": str(claim.mission_id),
        "paper_id": str(claim.paper_id),
        
        # Pass 1 fields
        "statement_raw": claim.statement_raw,
        "statement_normalized": claim.statement_normalized,
        "intervention": claim.intervention,
        "outcome": claim.outcome,
        "population": claim.population,
        "direction": claim.direction,
        "hedging_text": claim.hedging_text,
        "section_source": claim.section_source,
        "extraction_certainty": round(claim.extraction_certainty, 3),
        
        # Pass 2a fields
        "claim_type": claim.claim_type,
        "causal_justification": claim.causal_justification,
        "study_design_consistent": claim.study_design_consistent,
        "causal_downgrade_applied": claim.causal_downgrade_applied,
        
        # Pass 2b fields
        "intervention_canonical": claim.intervention_canonical,
        "outcome_canonical": claim.outcome_canonical,
        "normalization_confidence": round(claim.normalization_confidence, 3),
        "normalization_uncertain": claim.normalization_uncertain,
        
        # Pass 3 fields
        "composite_confidence": round(claim.composite_confidence, 3),
        "study_design_score": round(claim.study_design_score, 3),
        "hedging_penalty": round(claim.hedging_penalty, 3),
        
        # Confidence components breakdown
        "confidence_components": {
            "study_design_score": round(confidence_components.get('study_design_score', 0.0), 3),
            "hedging_penalty": round(confidence_components.get('hedging_penalty', 0.0), 3),
            "extraction_certainty": round(confidence_components.get('extraction_certainty', 0.5), 3),
        },
        
        # Metadata
        "validation_status": claim.validation_status,
        "mission_relevance": claim.mission_relevance,
        "paper_title": claim.paper_title,
        "doi_or_url": claim.doi_or_url,
        "study_design": claim.study_design,
        
        # Full provenance
        "provenance": claim.provenance or {},
    }
