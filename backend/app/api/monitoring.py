from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.alignment_monitoring import AlignmentMonitoringService

router = APIRouter(prefix="/api/monitoring", tags=["monitoring"])


@router.get("/missions/{mission_id}/overview")
async def get_monitoring_overview(
    mission_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        service = AlignmentMonitoringService(db)
        return await service.get_monitoring_overview(mission_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load monitoring overview: {exc}")


@router.get("/missions/{mission_id}/snapshots")
async def get_monitoring_snapshots(
    mission_id: str,
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        service = AlignmentMonitoringService(db)
        snapshots = await service.get_snapshot_history(mission_id, limit=limit)
        return {"mission_id": mission_id, "snapshots": snapshots, "count": len(snapshots)}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load monitoring snapshots: {exc}")


@router.get("/missions/{mission_id}/alerts")
async def get_monitoring_alerts(
    mission_id: str,
    status: str = Query("active", pattern="^(active|history|all)$"),
    limit: int = Query(100, ge=1, le=250),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        service = AlignmentMonitoringService(db)
        statuses = None
        if status == "active":
            statuses = ["firing", "active"]
        elif status == "history":
            statuses = ["resolved", "expired"]
        alerts = await service.get_alert_history(mission_id, statuses=statuses, limit=limit)
        return {"mission_id": mission_id, "alerts": alerts, "count": len(alerts), "status": status}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load monitoring alerts: {exc}")


@router.post("/missions/{mission_id}/run-cycle")
async def run_monitoring_cycle(
    mission_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        service = AlignmentMonitoringService(db)
        result = await service.run_monitoring_cycle(mission_id, actor="monitoring_api")
        await db.commit()
        return result
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to run monitoring cycle: {exc}")
