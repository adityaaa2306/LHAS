from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.memory import SynthesisTrigger
from app.services.synthesis_generation import SynthesisGenerationService

router = APIRouter(prefix="/api/synthesis", tags=["synthesis"])


class GenerateSynthesisRequest(BaseModel):
    trigger_type: str | None = None


@router.get("/missions/{mission_id}/latest")
async def get_latest_synthesis(
    mission_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        service = SynthesisGenerationService(db)
        synthesis = await service.get_latest_synthesis(mission_id)
        return {
            "mission_id": mission_id,
            "synthesis": synthesis,
            "message": None if synthesis else "No synthesis available yet",
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load synthesis: {exc}")


@router.get("/missions/{mission_id}/history")
async def get_synthesis_history(
    mission_id: str,
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        service = SynthesisGenerationService(db)
        rows = await service.get_synthesis_history(mission_id, limit=limit)
        return {
            "mission_id": mission_id,
            "history": rows,
            "count": len(rows),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load synthesis history: {exc}")


@router.post("/missions/{mission_id}/generate")
async def generate_synthesis(
    mission_id: str,
    request: GenerateSynthesisRequest | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        service = SynthesisGenerationService(db)
        trigger = SynthesisTrigger.OPERATOR_REQUEST
        if request and request.trigger_type:
            try:
                trigger = SynthesisTrigger(request.trigger_type)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Unsupported trigger_type: {request.trigger_type}")
        result = await service.generate_synthesis(
            mission_id=mission_id,
            trigger=trigger,
            actor="synthesis_api",
        )
        await db.commit()
        return result
    except HTTPException:
        raise
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to generate synthesis: {exc}")
