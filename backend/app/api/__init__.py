from fastapi import APIRouter
from .dashboard import router as dashboard_router
from .query import router as query_router
from .papers import router as papers_router
from .claims import router as claims_router
from .memory import router as memory_router
from .belief import router as belief_router
from .contradictions import router as contradictions_router
from .synthesis import router as synthesis_router
from .monitoring import router as monitoring_router

api_router = APIRouter()
api_router.include_router(dashboard_router)
api_router.include_router(query_router)
api_router.include_router(papers_router)
api_router.include_router(claims_router)
api_router.include_router(memory_router)
api_router.include_router(belief_router)
api_router.include_router(contradictions_router)
api_router.include_router(synthesis_router)
api_router.include_router(monitoring_router)

__all__ = ["api_router"]
