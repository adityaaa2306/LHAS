from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.memory_system import MemorySystemService
from app.models.memory import SynthesisTrigger

router = APIRouter(prefix="/api/memory", tags=["memory"])


@router.get("/missions/{mission_id}/overview")
async def get_memory_overview(
    mission_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        service = MemorySystemService(db)
        return await service.get_memory_overview(mission_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load memory overview: {exc}")


@router.get("/missions/{mission_id}/snapshots")
async def get_snapshot_history(
    mission_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        service = MemorySystemService(db)
        snapshots = await service.get_snapshot_history(mission_id)
        return {
            "mission_id": mission_id,
            "snapshots": snapshots,
            "count": len(snapshots),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load snapshot history: {exc}")


@router.get("/missions/{mission_id}/drift")
async def get_drift_history(
    mission_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        service = MemorySystemService(db)
        drift = await service.get_drift_history(mission_id)
        return {
            "mission_id": mission_id,
            "drift": drift,
            "count": len(drift),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load drift history: {exc}")


@router.get("/missions/{mission_id}/provenance")
async def get_provenance_log(
    mission_id: str,
    claim_id: str | None = Query(None),
    paper_id: str | None = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        service = MemorySystemService(db)
        events = await service.get_provenance_log(
            mission_id=mission_id,
            claim_id=claim_id,
            paper_id=paper_id,
            limit=limit,
        )
        return {
            "mission_id": mission_id,
            "events": events,
            "count": len(events),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load provenance log: {exc}")


@router.get("/missions/{mission_id}/contradictions")
async def get_active_contradictions(
    mission_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        service = MemorySystemService(db)
        contradictions = await service.get_active_contradictions(mission_id)
        return {
            "mission_id": mission_id,
            "contradictions": contradictions,
            "count": len(contradictions),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load contradictions: {exc}")


@router.get("/missions/{mission_id}/graph")
async def get_memory_graph(
    mission_id: str,
    max_nodes: int = Query(48, ge=8, le=120),
    max_edges: int = Query(120, ge=8, le=240),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        service = MemorySystemService(db)
        return await service.get_graph_visualization(
            mission_id=mission_id,
            max_nodes=max_nodes,
            max_edges=max_edges,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load memory graph: {exc}")


@router.get("/missions/{mission_id}/checkpoint/latest")
async def get_latest_checkpoint(
    mission_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        service = MemorySystemService(db)
        checkpoint = await service.get_latest_checkpoint(mission_id)
        return {
            "mission_id": mission_id,
            "checkpoint": checkpoint,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load latest checkpoint: {exc}")


@router.get("/claims/{claim_id}")
async def get_claim_memory_detail(
    claim_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        service = MemorySystemService(db)
        return await service.get_claim_memory_detail(claim_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load claim memory detail: {exc}")


@router.post("/missions/{mission_id}/cluster-pass")
async def run_cluster_pass(
    mission_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        service = MemorySystemService(db)
        result = await service.run_cluster_pass(mission_id)
        await db.commit()
        return {
            "mission_id": mission_id,
            **result,
        }
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to run cluster pass: {exc}")


@router.post("/missions/{mission_id}/backfill")
async def backfill_mission_memory(
    mission_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        service = MemorySystemService(db)
        result = await service.backfill_mission_memory(mission_id)
        await db.commit()
        return result
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to backfill mission memory: {exc}")


@router.post("/missions/{mission_id}/finalize-cycle")
async def finalize_memory_cycle(
    mission_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        service = MemorySystemService(db)
        result = await service.finalize_cycle(
            mission_id=mission_id,
            trigger=SynthesisTrigger.OPERATOR_REQUEST,
            actor="memory_api",
        )
        await db.commit()
        return {
            "mission_id": mission_id,
            **result,
        }
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to finalize memory cycle: {exc}")
