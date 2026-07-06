"""Lightweight ingestion progress tracking with in-memory cache for instant status reads."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select, update

from app.database import async_session_maker
from app.models.mission import Mission

logger = logging.getLogger(__name__)

MAX_ACTIVITY_ENTRIES = 50
MAX_FINALIZED_PAPERS = 100
DB_FLUSH_INTERVAL_SEC = 2.0

# Instant status reads — never blocked by ingestion DB writes
_live_cache: Dict[str, Dict[str, Any]] = {}
_flush_tasks: Dict[str, asyncio.Task] = {}

INGESTION_STAGES: List[Dict[str, Any]] = [
    {"id": "mission_created", "label": "Mission created", "progress_min": 0, "progress_max": 2},
    {"id": "query_expansion", "label": "Processing clarification", "progress_min": 2, "progress_max": 8},
    {"id": "searching_papers", "label": "Searching papers", "progress_min": 8, "progress_max": 18},
    {"id": "deduplicating", "label": "Deduplicating results", "progress_min": 18, "progress_max": 22},
    {"id": "creating_embeddings", "label": "Creating embeddings", "progress_min": 22, "progress_max": 35},
    {"id": "downloading_pdfs", "label": "Downloading PDFs", "progress_min": 35, "progress_max": 48},
    {"id": "extracting_text", "label": "Extracting text", "progress_min": 48, "progress_max": 58},
    {"id": "scoring_papers", "label": "Scoring papers", "progress_min": 58, "progress_max": 65},
    {"id": "storing_papers", "label": "Storing papers", "progress_min": 65, "progress_max": 72},
    {"id": "storing_vectors", "label": "Storing vectors", "progress_min": 72, "progress_max": 78},
    {"id": "creating_claims", "label": "Creating claims", "progress_min": 78, "progress_max": 88},
    {"id": "detecting_contradictions", "label": "Detecting contradictions", "progress_min": 88, "progress_max": 92},
    {"id": "generating_synthesis", "label": "Generating synthesis", "progress_min": 92, "progress_max": 95},
    {"id": "building_memory", "label": "Building memory", "progress_min": 95, "progress_max": 98},
    {"id": "finalizing", "label": "Finalizing mission", "progress_min": 98, "progress_max": 100},
]

BACKGROUND_TASK_IDS = [
    "claims", "contradictions", "synthesis", "memory", "monitoring", "timeline", "reasoning",
]


def default_background_tasks() -> Dict[str, Dict[str, Any]]:
    return {task_id: {"status": "waiting", "progress": 0, "detail": None} for task_id in BACKGROUND_TASK_IDS}


def default_stats() -> Dict[str, Any]:
    return {
        "candidates_retrieved": 0,
        "after_dedup": 0,
        "after_prefilter": 0,
        "selected": 0,
        "stored": 0,
        "source_counts": {},
        "finalized_papers": [],
        "retrieval_plan": None,
    }


def init_live_cache(mission_id: str) -> None:
    now = datetime.utcnow().isoformat() + "Z"
    _live_cache[mission_id] = {
        "mission_id": mission_id,
        "status": "pending",
        "progress": 0,
        "error": None,
        "current_stage": "mission_created",
        "stage_detail": "Queued for processing",
        "activities": [{"timestamp": now, "message": "Ingestion queued", "level": "info"}],
        "background_tasks": default_background_tasks(),
        "stats": default_stats(),
        "started_at": now,
        "completed_at": None,
        "_updated_at": time.monotonic(),
    }


def get_live_cache(mission_id: str) -> Optional[Dict[str, Any]]:
    cached = _live_cache.get(mission_id)
    return deepcopy(cached) if cached else None


def clear_live_cache(mission_id: str) -> None:
    _live_cache.pop(mission_id, None)
    task = _flush_tasks.pop(mission_id, None)
    if task and not task.done():
        task.cancel()


class IngestionProgressTracker:
    """In-memory first, debounced DB flush — status polls never wait on ingestion."""

    def __init__(self, mission_id: str) -> None:
        self.mission_id = mission_id
        self._stage_started_at: Dict[str, float] = {}
        self._queue_entered_at = time.monotonic()
        self._dirty = False
        self._last_flush = 0.0
        if mission_id not in _live_cache:
            init_live_cache(mission_id)

    def _cache(self) -> Dict[str, Any]:
        return _live_cache.setdefault(self.mission_id, {})

    def _touch(self) -> None:
        self._cache()["_updated_at"] = time.monotonic()
        self._dirty = True
        self._schedule_flush()

    def _schedule_flush(self) -> None:
        now = time.monotonic()
        if now - self._last_flush < DB_FLUSH_INTERVAL_SEC:
            if self.mission_id not in _flush_tasks or _flush_tasks[self.mission_id].done():
                delay = DB_FLUSH_INTERVAL_SEC - (now - self._last_flush)

                async def _delayed_flush() -> None:
                    await asyncio.sleep(max(0.1, delay))
                    await self.flush_to_db()

                try:
                    loop = asyncio.get_running_loop()
                    _flush_tasks[self.mission_id] = loop.create_task(_delayed_flush())
                except RuntimeError:
                    pass
            return
        try:
            loop = asyncio.get_running_loop()
            _flush_tasks[self.mission_id] = loop.create_task(self.flush_to_db())
        except RuntimeError:
            pass

    async def flush_to_db(self) -> None:
        if not self._dirty:
            return
        cache = self._cache()
        values: Dict[str, Any] = {
            "ingestion_status": cache.get("status", "processing"),
            "ingestion_progress": cache.get("progress", 0),
            "ingestion_current_stage": cache.get("current_stage"),
            "ingestion_stage_detail": cache.get("stage_detail"),
            "ingestion_activity_log": json.dumps(cache.get("activities", [])),
            "ingestion_background_tasks": json.dumps(cache.get("background_tasks", {})),
            "ingestion_stats": json.dumps(cache.get("stats", default_stats())),
        }
        if cache.get("error"):
            values["ingestion_error"] = cache["error"]
        t0 = time.monotonic()
        try:
            async with async_session_maker() as db:
                await db.execute(update(Mission).where(Mission.id == self.mission_id).values(**values))
                await db.commit()
            self._dirty = False
            self._last_flush = time.monotonic()
            db_ms = (time.monotonic() - t0) * 1000
            if db_ms > 100:
                logger.warning("[ingestion:%s] slow DB flush %.0fms", self.mission_id[:8], db_ms)
        except Exception as exc:
            logger.warning("[ingestion:%s] DB flush failed: %s", self.mission_id[:8], exc)

    def _apply_stage(
        self,
        stage_id: str,
        *,
        detail: Optional[str] = None,
        progress: Optional[int] = None,
        activity: Optional[str] = None,
    ) -> None:
        stage = next((s for s in INGESTION_STAGES if s["id"] == stage_id), None)
        if stage and stage_id not in self._stage_started_at:
            self._stage_started_at[stage_id] = time.monotonic()

        if progress is None and stage:
            progress = stage["progress_min"]

        cache = self._cache()
        cache["current_stage"] = stage_id
        cache["stage_detail"] = detail
        cache["status"] = "processing"
        if progress is not None:
            cache["progress"] = max(0, min(100, progress))
        self._touch()

        if activity:
            self._log_activity_sync(activity)

    async def set_stage(
        self,
        stage_id: str,
        *,
        detail: Optional[str] = None,
        progress: Optional[int] = None,
        activity: Optional[str] = None,
    ) -> None:
        self._apply_stage(stage_id, detail=detail, progress=progress, activity=activity)
        await asyncio.sleep(0)

    def _apply_background_task(self, task_id: str, *, status: str, progress: int = 0, detail: Optional[str] = None) -> None:
        tasks = self._cache().setdefault("background_tasks", default_background_tasks())
        tasks[task_id] = {"status": status, "progress": progress, "detail": detail}
        self._touch()
        if detail and status in ("running", "completed", "failed"):
            self._log_activity_sync(detail)

    async def set_background_task(self, task_id: str, *, status: str, progress: int = 0, detail: Optional[str] = None) -> None:
        self._apply_background_task(task_id, status=status, progress=progress, detail=detail)
        await asyncio.sleep(0)

    def _apply_progress(self, progress: int, *, detail: Optional[str] = None) -> None:
        cache = self._cache()
        cache["progress"] = max(0, min(100, progress))
        if detail is not None:
            cache["stage_detail"] = detail
        self._touch()

    async def set_progress(self, progress: int, *, detail: Optional[str] = None) -> None:
        self._apply_progress(progress, detail=detail)
        await asyncio.sleep(0)

    async def log_activity(self, message: str, *, level: str = "info") -> None:
        self._log_activity_sync(message, level=level)
        await asyncio.sleep(0)

    def _log_activity_sync(self, message: str, *, level: str = "info") -> None:
        entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "message": message,
            "level": level,
        }
        activities = self._cache().setdefault("activities", [])
        activities.append(entry)
        self._cache()["activities"] = activities[-MAX_ACTIVITY_ENTRIES:]
        self._touch()
        logger.info("[ingestion:%s] %s", self.mission_id[:8], message)

    def mark_completed(self, *, error: Optional[str] = None) -> None:
        cache = self._cache()
        cache["status"] = "failed" if error else "completed"
        cache["progress"] = 100
        cache["error"] = error
        cache["completed_at"] = datetime.utcnow().isoformat() + "Z"
        self._touch()

    def update_stats(self, **kwargs: Any) -> None:
        stats = self._cache().setdefault("stats", default_stats())
        for key, value in kwargs.items():
            if key == "source_counts" and isinstance(value, dict):
                merged = dict(stats.get("source_counts", {}))
                merged.update(value)
                stats["source_counts"] = merged
            else:
                stats[key] = value
        self._cache()["stats"] = stats
        self._touch()

    def add_finalized_paper(self, *, title: str, source: str, score: float, paper_id: str) -> None:
        stats = self._cache().setdefault("stats", default_stats())
        papers: List[Dict[str, Any]] = stats.setdefault("finalized_papers", [])
        papers.append({
            "id": paper_id,
            "title": title[:200],
            "source": source,
            "score": round(score, 3),
            "timestamp": datetime.utcnow().isoformat() + "Z",
        })
        stats["finalized_papers"] = papers[-MAX_FINALIZED_PAPERS:]
        stats["stored"] = len(stats["finalized_papers"])
        self._cache()["stats"] = stats
        self._touch()

    async def finalize(self) -> None:
        await self.flush_to_db()
