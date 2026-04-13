from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.memory import SynthesisTrigger
from app.services.alignment_monitoring import AlignmentMonitoringService
from app.services.belief_revision import BeliefRevisionService
from app.services.contradiction_handling import ContradictionHandlingService
from app.services.memory_system import MemorySystemService
from app.services.synthesis_generation import SynthesisGenerationService

router = APIRouter(prefix="/api/belief", tags=["belief"])


class ApproveReversalRequest(BaseModel):
    operator_notes: str | None = None


@router.get("/missions/{mission_id}/overview")
async def get_belief_overview(
    mission_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        service = BeliefRevisionService(db)
        return await service.get_belief_overview(mission_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load belief overview: {exc}")


@router.get("/missions/{mission_id}/revisions")
async def get_belief_revisions(
    mission_id: str,
    limit: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        service = BeliefRevisionService(db)
        revisions = await service.get_revision_history(mission_id, limit=limit)
        return {
            "mission_id": mission_id,
            "revisions": revisions,
            "count": len(revisions),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load belief revisions: {exc}")


@router.post("/missions/{mission_id}/run-cycle")
async def run_belief_cycle(
    mission_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        contradiction_service = ContradictionHandlingService(db)
        belief_service = BeliefRevisionService(db)
        memory_service = MemorySystemService(db)
        synthesis_service = SynthesisGenerationService(db)
        monitoring_service = AlignmentMonitoringService(db)
        contradiction_result = await contradiction_service.run_cycle(
            mission_id=mission_id,
            actor="belief_api",
            evaluate_all=False,
        )
        await db.commit()
        revision_result = await belief_service.run_revision_cycle(mission_id, actor="belief_api")
        if revision_result.get("success") is False:
            await db.rollback()
            raise HTTPException(status_code=500, detail=revision_result.get("error") or "Belief revision failed")
        await db.commit()

        synthesis_trigger = SynthesisGenerationService.trigger_from_revision(
            revision_result.get("revision_type"),
            revision_result.get("cycle_number"),
        )
        synthesis_result = None
        if synthesis_trigger:
            try:
                synthesis_result = await synthesis_service.generate_synthesis(
                    mission_id=mission_id,
                    trigger=synthesis_trigger,
                    actor="belief_api",
                )
                await db.commit()
            except Exception:
                await db.rollback()
                synthesis_result = {"error": "Synthesis generation failed; cycle continued without blocking."}

        cycle_result = await memory_service.finalize_cycle(
            mission_id=mission_id,
            trigger=synthesis_trigger or SynthesisTrigger.OPERATOR_REQUEST,
            actor="belief_api",
        )
        await db.commit()
        monitoring_result = await monitoring_service.run_monitoring_cycle(
            mission_id=mission_id,
            actor="belief_api",
        )
        await db.commit()
        return {
            "mission_id": mission_id,
            "contradictions": contradiction_result,
            "revision": revision_result,
            "synthesis": synthesis_result,
            "cycle": cycle_result,
            "monitoring": monitoring_result,
        }
    except HTTPException:
        raise
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to run belief cycle: {exc}")


@router.post("/missions/{mission_id}/approve-reversal")
async def approve_reversal(
    mission_id: str,
    request: ApproveReversalRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        belief_service = BeliefRevisionService(db)
        memory_service = MemorySystemService(db)
        synthesis_service = SynthesisGenerationService(db)
        monitoring_service = AlignmentMonitoringService(db)
        approval = await belief_service.approve_pending_reversal(
            mission_id=mission_id,
            actor="belief_api",
            operator_notes=request.operator_notes,
        )
        if approval.get("success") is False:
            await db.rollback()
            raise HTTPException(status_code=500, detail=approval.get("error") or "Belief reversal approval failed")
        await db.commit()

        synthesis_result = None
        try:
            synthesis_result = await synthesis_service.generate_synthesis(
                mission_id=mission_id,
                trigger=SynthesisTrigger.BELIEF_REVERSED,
                actor="belief_api",
            )
            await db.commit()
        except Exception:
            await db.rollback()
            synthesis_result = {"error": "Synthesis generation failed; reversal was still applied."}

        cycle_result = await memory_service.finalize_cycle(
            mission_id=mission_id,
            trigger=SynthesisTrigger.BELIEF_REVERSED,
            actor="belief_api",
        )
        await db.commit()
        monitoring_result = await monitoring_service.run_monitoring_cycle(
            mission_id=mission_id,
            actor="belief_api",
        )
        await db.commit()
        return {
            "mission_id": mission_id,
            "approval": approval,
            "synthesis": synthesis_result,
            "cycle": cycle_result,
            "monitoring": monitoring_result,
        }
    except HTTPException:
        raise
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to approve belief reversal: {exc}")
