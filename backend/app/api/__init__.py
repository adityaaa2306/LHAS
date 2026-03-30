from fastapi import APIRouter
from .dashboard import router as dashboard_router
from .query import router as query_router
from .papers import router as papers_router
from .claims import router as claims_router

api_router = APIRouter()
api_router.include_router(dashboard_router)
api_router.include_router(query_router)
api_router.include_router(papers_router)
api_router.include_router(claims_router)

__all__ = ["api_router"]
