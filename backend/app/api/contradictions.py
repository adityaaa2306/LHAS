from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Mission
from app.services.contradiction_handling import ContradictionHandlingService

router = APIRouter(prefix="/api/contradictions", tags=["contradictions"])


class ContradictionSettingsRequest(BaseModel):
    contradiction_asymmetry_threshold: float


@router.get("/missions/{mission_id}/overview")
async def get_contradiction_overview(
    mission_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        service = ContradictionHandlingService(db)
        return await service.get_overview(mission_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load contradiction overview: {exc}")


@router.get("/missions/{mission_id}/confirmed")
async def get_confirmed_contradictions(
    mission_id: str,
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        service = ContradictionHandlingService(db)
        items = await service.get_confirmed(mission_id, limit=limit)
        return {"mission_id": mission_id, "contradictions": items, "count": len(items)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load confirmed contradictions: {exc}")


@router.get("/missions/{mission_id}/resolved")
async def get_context_resolved_pairs(
    mission_id: str,
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        service = ContradictionHandlingService(db)
        items = await service.get_context_resolved(mission_id, limit=limit)
        return {"mission_id": mission_id, "resolved_pairs": items, "count": len(items)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load context-resolved pairs: {exc}")


@router.get("/missions/{mission_id}/ambiguous")
async def get_ambiguous_pairs(
    mission_id: str,
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        service = ContradictionHandlingService(db)
        items = await service.get_ambiguous(mission_id, limit=limit)
        return {"mission_id": mission_id, "ambiguous_pairs": items, "count": len(items)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load ambiguous contradiction pairs: {exc}")


@router.post("/missions/{mission_id}/run-cycle")
async def run_contradiction_cycle(
    mission_id: str,
    evaluate_all: bool = Query(False),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        service = ContradictionHandlingService(db)
        result = await service.run_cycle(mission_id=mission_id, actor="contradiction_api", evaluate_all=evaluate_all)
        await db.commit()
        return result
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to run contradiction cycle: {exc}")


@router.patch("/missions/{mission_id}/settings")
async def update_contradiction_settings(
    mission_id: str,
    request: ContradictionSettingsRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        mission = await db.get(Mission, mission_id)
        if not mission:
            raise HTTPException(status_code=404, detail=f"Mission not found: {mission_id}")
        mission.contradiction_asymmetry_threshold = max(0.05, min(float(request.contradiction_asymmetry_threshold), 1.0))
        await db.commit()
        return {
            "mission_id": mission_id,
            "contradiction_asymmetry_threshold": mission.contradiction_asymmetry_threshold,
        }
    except HTTPException:
        raise
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update contradiction settings: {exc}")
