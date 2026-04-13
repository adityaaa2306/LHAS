"""Claims API endpoints - MODULE 3 CLAIM EXTRACTION

Routes:
- GET /api/claims/mission/{mission_id} - List all claims for mission
- GET /api/claims/{claim_id} - Get single claim with full provenance
- GET /api/claims/mission/{mission_id}/stats - Claim statistics
- GET /api/claims/mission/{mission_id}/clusters - Evidence clusters (EVIDENCE NETWORK VIEW)
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from typing import Optional, List
from uuid import UUID

from app.database import get_db
from app.models import ContradictionRecord, ResearchClaim, ResearchPaper
from app.models.claims import ClaimTypeEnum, DirectionEnum, ValidationStatusEnum
from app.services.claim_curation import (
    build_mission_findings,
    claim_confidence,
    claim_direction_value,
    claim_section,
    claim_type_value,
    summarize_findings,
)

router = APIRouter(prefix="/api/claims", tags=["claims"])


async def _load_mission_claims(
    db: AsyncSession,
    mission_id: str,
    claim_type: Optional[str] = None,
    direction: Optional[str] = None,
    min_confidence: Optional[float] = None,
    max_confidence: Optional[float] = None,
    validation_status: Optional[str] = None,
) -> List[ResearchClaim]:
    query = select(ResearchClaim).where(ResearchClaim.mission_id == mission_id)

    if claim_type:
        query = query.where(ResearchClaim.claim_type == claim_type)
    if direction:
        query = query.where(ResearchClaim.direction == direction)
    if min_confidence is not None:
        query = query.where(ResearchClaim.composite_confidence >= min_confidence)
    if max_confidence is not None:
        query = query.where(ResearchClaim.composite_confidence <= max_confidence)
    if validation_status:
        query = query.where(ResearchClaim.validation_status == validation_status)

    query = query.order_by(ResearchClaim.composite_confidence.desc())
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/mission/{mission_id}", response_model=dict)
async def list_claims_for_mission(
    mission_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    view: str = Query("findings", pattern="^(findings|raw)$"),
    claim_type: Optional[str] = None,
    direction: Optional[str] = None,
    min_confidence: Optional[float] = Query(None, ge=0.05, le=0.95),
    max_confidence: Optional[float] = Query(None, ge=0.05, le=0.95),
    validation_status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    List mission findings by default, with optional raw-claim access for debugging.
    
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
        claims = await _load_mission_claims(
            db=db,
            mission_id=mission_id,
            claim_type=claim_type,
            direction=direction,
            min_confidence=min_confidence,
            max_confidence=max_confidence,
            validation_status=validation_status,
        )

        if view == "raw":
            total = len(claims)
            page = claims[skip:skip + limit]
            return {
                "view": "raw",
                "total": total,
                "claims": [_format_claim(c) for c in page],
                "has_more": (skip + len(page)) < total,
                "skip": skip,
                "limit": limit,
            }

        findings = build_mission_findings(claims, max_findings=200)
        total = len(findings)
        page = findings[skip:skip + limit]
        return {
            "view": "findings",
            "total": total,
            "claims": page,
            "has_more": (skip + len(page)) < total,
            "skip": skip,
            "limit": limit,
            "raw_claim_count": len(claims),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve claims: {str(e)}")


@router.get("/mission/{mission_id}/findings", response_model=dict)
async def list_findings_for_mission(
    mission_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        claims = await _load_mission_claims(db=db, mission_id=mission_id)
        findings = build_mission_findings(claims, max_findings=200)
        page = findings[skip:skip + limit]
        return {
            "mission_id": mission_id,
            "view": "findings",
            "total": len(findings),
            "findings": page,
            "has_more": (skip + len(page)) < len(findings),
            "skip": skip,
            "limit": limit,
            "raw_claim_count": len(claims),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve mission findings: {str(e)}")


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
    mission_id: str,
    view: str = Query("findings", pattern="^(findings|raw)$"),
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
        claims = await _load_mission_claims(db=db, mission_id=mission_id)
        raw_total = len(claims)

        if raw_total == 0:
            return {
                "total_claims": 0,
                "message": "No claims extracted for this mission"
            }

        if view == "findings":
            findings = build_mission_findings(claims, max_findings=200)
            summary = summarize_findings(findings)
            return {
                "view": "findings",
                "total_claims": summary["total_findings"],
                "valid_claims": summary["valid_findings"],
                "degraded_claims": 0,
                "percentage_valid": summary["percentage_valid"],
                "by_type": summary["by_type"],
                "by_direction": summary["by_direction"],
                "by_section": summary["by_section"],
                "confidence_statistics": summary["confidence_statistics"],
                "normalization_quality_percentage": round(
                    (
                        sum(
                            1
                            for finding in findings
                            if finding.get("intervention_canonical") and finding.get("outcome_canonical")
                        ) / len(findings) * 100
                    ) if findings else 0.0,
                    1,
                ),
                "raw_claim_count": raw_total,
            }

        valid = sum(
            1 for claim in claims
            if getattr(claim.validation_status, "value", claim.validation_status) == ValidationStatusEnum.VALID.value
        )
        degraded = sum(
            1 for claim in claims
            if getattr(claim.validation_status, "value", claim.validation_status) == ValidationStatusEnum.EXTRACTION_DEGRADED.value
        )
        by_type = {}
        by_direction = {}
        by_section = {}
        confidences = []
        canonical_count = 0
        for claim in claims:
            by_type[claim_type_value(claim)] = by_type.get(claim_type_value(claim), 0) + 1
            by_direction[claim_direction_value(claim)] = by_direction.get(claim_direction_value(claim), 0) + 1
            by_section[claim_section(claim)] = by_section.get(claim_section(claim), 0) + 1
            confidences.append(claim_confidence(claim))
            if claim.intervention_canonical and claim.outcome_canonical:
                canonical_count += 1

        sorted_conf = sorted(confidences)
        p25_idx = len(sorted_conf) // 4
        p50_idx = len(sorted_conf) // 2
        p75_idx = (3 * len(sorted_conf)) // 4
        confidence_stats = {
            "mean": round(sum(confidences) / len(confidences), 3),
            "min": round(min(confidences), 3),
            "max": round(max(confidences), 3),
            "p25": round(sorted_conf[p25_idx], 3),
            "median": round(sorted_conf[p50_idx], 3),
            "p75": round(sorted_conf[p75_idx], 3),
        }

        return {
            "view": "raw",
            "total_claims": raw_total,
            "valid_claims": valid,
            "degraded_claims": degraded,
            "percentage_valid": round(valid / raw_total * 100, 1) if raw_total > 0 else 0,
            "by_type": by_type,
            "by_direction": by_direction,
            "by_section": by_section,
            "confidence_statistics": confidence_stats,
            "normalization_quality_percentage": round((canonical_count / raw_total) * 100, 1) if raw_total > 0 else 0,
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


@router.get("/mission/{mission_id}/clusters", response_model=dict)
async def get_mission_clusters(
    mission_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Get evidence clusters for a mission.
    
    Clusters are groups of claims addressing the same (intervention_canonical, outcome_canonical) pair.
    
    Returns:
    - clusters: List of evidence clusters with:
        - cluster_key: (intervention_canonical, outcome_canonical)
        - claims: List of claims in cluster
        - statistics: Confidence, direction distribution, evidence bar
        - contradictions: List of contradicting claim pairs
        - evidence_gaps: Detected gaps for this cluster
        - timeline: Chronological progression
    - total_clusters: Count of evidence clusters
    - cluster_statistics: Overall cluster metrics
    """
    try:
        # Get all claims with canonical entities
        query = select(ResearchClaim).where(
            and_(
                ResearchClaim.mission_id == mission_id,
                ResearchClaim.intervention_canonical.isnot(None),
                ResearchClaim.outcome_canonical.isnot(None),
            )
        )
        result = await db.execute(query)
        all_claims = result.scalars().all()
        
        if not all_claims:
            return {
                "clusters": [],
                "total_clusters": 0,
                "total_claims_clustered": 0,
                "message": "No claims with canonical entities for clustering"
            }
        
        # Group claims by (intervention_canonical, outcome_canonical)
        clusters_dict = {}
        for claim in all_claims:
            key = (claim.intervention_canonical, claim.outcome_canonical)
            if key not in clusters_dict:
                clusters_dict[key] = []
            clusters_dict[key].append(claim)
        
        contradiction_rows = (
            await db.execute(
                select(ContradictionRecord).where(ContradictionRecord.mission_id == mission_id)
            )
        ).scalars().all()
        contradiction_map = {}
        for row in contradiction_rows:
            key = (row.intervention_canonical or "", row.outcome_canonical or "")
            contradiction_map.setdefault(key, []).append(row)

        # Build cluster responses
        clusters = []
        for (intervention_canonical, outcome_canonical), claims in clusters_dict.items():
            cluster = _build_evidence_cluster(
                intervention_canonical,
                outcome_canonical,
                claims,
                contradiction_map.get((intervention_canonical or "", outcome_canonical or ""), []),
            )
            clusters.append(cluster)
        
        # Sort clusters by average confidence (descending)
        clusters.sort(
            key=lambda c: c['statistics']['avg_confidence'],
            reverse=True
        )
        
        # Compute overall statistics
        total_supporting = sum(
            c['statistics']['supporting_count'] for c in clusters
        )
        total_contradicting = sum(
            c['statistics']['contradicting_count'] for c in clusters
        )
        total_null = sum(
            c['statistics']['null_count'] for c in clusters
        )
        
        return {
            "clusters": clusters,
            "total_clusters": len(clusters),
            "total_claims_clustered": len(all_claims),
            "cluster_statistics": {
                "total_supporting": total_supporting,
                "total_contradicting": total_contradicting,
                "total_null": total_null,
                "average_cluster_confidence": round(
                    sum(c['statistics']['avg_confidence'] for c in clusters) / len(clusters), 3
                ) if clusters else 0.0,
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to build clusters: {str(e)}")


def _build_evidence_cluster(
    intervention_canonical: str,
    outcome_canonical: str,
    claims: List[ResearchClaim],
    contradiction_records: List[ContradictionRecord],
) -> dict:
    """Build a single evidence cluster from grouped claims."""
    
    # Direction distribution
    direction_counts = {
        'positive': 0,
        'negative': 0,
        'null': 0,
        'unclear': 0,
    }
    
    confidence_scores = []
    contradictions = []
    
    for claim in claims:
        direction_str = claim_direction_value(claim)
        if direction_str not in direction_counts:
            direction_str = "unclear"
        direction_counts[direction_str] += 1
        confidence_scores.append(claim.composite_confidence)
    
    # Calculate average confidence
    avg_confidence = (
        sum(confidence_scores) / len(confidence_scores)
        if confidence_scores
        else 0.0
    )
    
    contradiction_severity = "NONE"
    if contradiction_records:
        severity_order = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}
        contradiction_severity = max(
            (getattr(row.severity, "value", row.severity) for row in contradiction_records),
            key=lambda item: severity_order.get(str(item), 0),
            default="LOW",
        )
        claim_lookup = {str(claim.id): claim for claim in claims}
        for row in contradiction_records[:3]:
            claim_a = claim_lookup.get(str(row.claim_a_id))
            claim_b = claim_lookup.get(str(row.claim_b_id))
            contradictions.append({
                "claim1_id": str(row.claim_a_id),
                "claim1_direction": row.direction_a,
                "claim1_paper": (claim_a.paper_title if claim_a else "Unknown"),
                "claim2_id": str(row.claim_b_id),
                "claim2_direction": row.direction_b,
                "claim2_paper": (claim_b.paper_title if claim_b else "Unknown"),
                "severity": getattr(row.severity, "value", row.severity),
            })
    
    return {
        "cluster_key": {
            "intervention_canonical": intervention_canonical,
            "outcome_canonical": outcome_canonical,
        },
        "claim_count": len(claims),
        "statistics": {
            "supporting_count": direction_counts['positive'],
            "contradicting_count": direction_counts['negative'],
            "null_count": direction_counts['null'],
            "unclear_count": direction_counts['unclear'],
            "avg_confidence": round(avg_confidence, 3),
            "min_confidence": round(min(confidence_scores), 3) if confidence_scores else 0.0,
            "max_confidence": round(max(confidence_scores), 3) if confidence_scores else 0.0,
        },
        "evidence_bar": {
            "supporting": direction_counts['positive'],
            "contradicting": direction_counts['negative'],
            "null": direction_counts['null'] + direction_counts['unclear'],
        },
        "contradiction_signal": {
            "has_conflict": bool(contradiction_records),
            "severity": contradiction_severity,
            "pairs": contradictions[:3],  # Top 3 contradictions
        },
        "best_evidence_type": _get_best_evidence_type(claims),
        "evidence_gaps": _extract_evidence_gaps(claims, intervention_canonical, outcome_canonical),
        "claims_summary": [
            {
                "id": str(claim.id),
                "statement": claim.statement_raw,
                "direction": claim_direction_value(claim),
                "confidence": round(claim.composite_confidence, 3),
                "paper_title": claim.paper_title or "Unknown",
                "claim_type": claim_type_value(claim),
            }
            for claim in claims
        ]
    }


def _get_best_evidence_type(claims: List[ResearchClaim]) -> str:
    """Get the most common/highest-confidence evidence type."""
    if not claims:
        return "unknown"
    
    type_scores = {}
    for claim in claims:
        claim_type = claim_type_value(claim)
        if claim_type not in type_scores:
            type_scores[claim_type] = []
        type_scores[claim_type].append(claim.composite_confidence)
    
    # Calculate average confidence per type
    best_type = max(
        type_scores.items(),
        key=lambda x: sum(x[1]) / len(x[1])
    )[0]
    
    return best_type


def _extract_evidence_gaps(
    claims: List[ResearchClaim],
    intervention_canonical: str,
    outcome_canonical: str
) -> List[dict]:
    """Extract evidence gaps for a cluster."""
    gaps = []
    
    # Gap 1: Limited evidence
    if len(claims) < 3:
        gaps.append({
            "type": "limited_evidence",
            "description": f"Only {len(claims)} claim(s) found for this intervention/outcome pair",
            "severity": "medium",
        })
    
    # Gap 2: Study design diversity
    study_designs = set(claim.study_design for claim in claims if claim.study_design)
    if len(study_designs) <= 1:
        gaps.append({
            "type": "study_design_homogeneity",
            "description": "Limited diversity in study designs",
            "severity": "low",
        })
    
    # Gap 3: Population coverage
    populations = set(claim.population for claim in claims if claim.population)
    if len(populations) < len(claims) / 2:
        gaps.append({
            "type": "population_coverage",
            "description": "Limited population diversity",
            "severity": "low",
        })
    
    # Gap 4: Contradictory evidence
    directions = set(claim_direction_value(c) for c in claims)
    if len(directions) > 1 and 'positive' in directions and 'negative' in directions:
        gaps.append({
            "type": "conflicting_evidence",
            "description": "Contradictory findings exist",
            "severity": "high",
        })
    
    return gaps


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
