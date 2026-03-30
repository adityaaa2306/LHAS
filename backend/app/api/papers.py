"""Paper Ingestion API Endpoints"""

import logging
import asyncio
from datetime import datetime
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from typing import Dict, Any, List, Optional
from app.database import get_db, async_session_maker
from app.services.paper_ingestion import PaperIngestionService, IngestionConfig
from app.models import ResearchPaper, IngestionEvent, Mission
from app.config import settings
from pydantic import BaseModel
import statistics

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/papers", tags=["papers"])


class IngestionConfigRequest(BaseModel):
    """Configuration for paper ingestion"""
    max_candidates: int = 200
    prefilter_k: int = 100  # Increased from 60: more candidates through prefilter stage
    final_k: int = 50  # Increased from 20: get 50 papers instead of 20
    relevance_threshold: float = 0.5
    sources: List[str] = ["arxiv", "semantic_scholar", "pubmed"]
    mmr_lambda: float = 0.8  # Increased from 0.6: prioritize relevance (80%) over diversity (20%)
    min_abstract_length: int = 100


class StructuredQueryRequest(BaseModel):
    """Structured query from Module 1"""
    normalized_query: str
    key_concepts: List[str] = []
    search_queries: List[str] = []
    intent_type: str = "Exploratory"
    pico: Dict[str, Any] = {}


@router.post("/ingest")
async def ingest_papers(
    background_tasks: BackgroundTasks,
    mission_id: str = Query(..., description="UUID of the mission"),
    structured_query: Optional[StructuredQueryRequest] = None,
    config: IngestionConfigRequest = IngestionConfigRequest(),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Trigger paper ingestion for a mission (non-blocking background job).

    Returns immediately with {"status": "started"} and runs the full
    11-stage pipeline in the background.  Poll GET /ingest/status/{mission_id}
    to track progress.
    """
    try:
        # Validate mission exists
        stmt = select(Mission).where(Mission.id == mission_id)
        result = await db.execute(stmt)
        mission = result.scalar_one_or_none()

        if not mission:
            raise HTTPException(status_code=404, detail=f"Mission {mission_id} not found")

        # Prevent double-start if already running
        if mission.ingestion_status == "processing":
            return {"status": "already_running", "mission_id": mission_id}

        # Build structured_query from mission if not provided
        if not structured_query:
            pico_dict = {}
            if mission.pico_population:
                pico_dict["population"] = mission.pico_population
            if mission.pico_intervention:
                pico_dict["intervention"] = mission.pico_intervention
            if mission.pico_comparator:
                pico_dict["comparator"] = mission.pico_comparator
            if mission.pico_outcome:
                pico_dict["outcome"] = mission.pico_outcome

            key_concepts_list = [c.strip() for c in mission.key_concepts.split(",") if c.strip()] if mission.key_concepts else []
            structured_query = StructuredQueryRequest(
                normalized_query=mission.normalized_query,
                key_concepts=key_concepts_list,
                intent_type=mission.intent_type.value if mission.intent_type else "Exploratory",
                pico=pico_dict,
                search_queries=[],
            )

        # Mark as pending immediately (still within this request's session)
        await db.execute(
            update(Mission)
            .where(Mission.id == mission_id)
            .values(
                ingestion_status="pending",
                ingestion_progress=0,
                ingestion_error=None,
                ingestion_started_at=datetime.utcnow(),
                ingestion_completed_at=None,
            )
        )
        await db.commit()

        # Queue to run after response is sent — uses its own DB session
        background_tasks.add_task(
            _run_ingestion_background,
            mission_id,
            structured_query.dict(),
            config,
        )

        return {"status": "started", "mission_id": mission_id}

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


async def _update_ingestion_status(
    db: AsyncSession,
    mission_id: str,
    status: str,
    progress: int = 0,
    error: Optional[str] = None,
    completed: bool = False,
) -> None:
    """Update ingestion tracking columns in its own commit."""
    values: Dict[str, Any] = {
        "ingestion_status": status,
        "ingestion_progress": progress,
        "ingestion_error": error,
    }
    if completed:
        values["ingestion_completed_at"] = datetime.utcnow()
    await db.execute(update(Mission).where(Mission.id == mission_id).values(**values))
    await db.commit()


async def _run_ingestion_background(
    mission_id: str,
    structured_query_dict: Dict[str, Any],
    config: IngestionConfigRequest,
) -> None:
    """
    Background task: runs the full ingestion pipeline with its own DB session.
    Never throws — all exceptions are caught and written to ingestion_error.
    """
    async with async_session_maker() as db:
        try:
            await _update_ingestion_status(db, mission_id, "processing", progress=5)

            structured_query = StructuredQueryRequest(**structured_query_dict)
            service = PaperIngestionService(
                db,
                semantic_scholar_api_key=settings.SEMANTIC_SCHOLAR_API_KEY,
                pubmed_api_key=settings.PUBMED_API_KEY,
            )

            await service.ingest_papers(
                mission_id=mission_id,
                structured_query=structured_query.dict(),
                config=IngestionConfig(
                    max_candidates=config.max_candidates,
                    prefilter_k=config.prefilter_k,
                    final_k=config.final_k,
                    relevance_threshold=config.relevance_threshold,
                    sources=config.sources,
                    mmr_lambda=config.mmr_lambda,
                    min_abstract_length=config.min_abstract_length,
                ),
            )

            # Check if any papers were actually stored
            from sqlalchemy import func as sqlfunc
            paper_count_result = await db.execute(
                select(sqlfunc.count()).select_from(ResearchPaper).where(ResearchPaper.mission_id == mission_id)
            )
            paper_count = paper_count_result.scalar() or 0

            if paper_count == 0:
                await _update_ingestion_status(
                    db, mission_id, "failed", progress=100,
                    error="All API sources returned 0 results (rate limits or no matching papers). Try again in a few minutes.",
                    completed=True,
                )
                logger.warning("Background ingestion completed with 0 papers for mission %s", mission_id)
            else:
                await _update_ingestion_status(db, mission_id, "completed", progress=100, completed=True)
                logger.info("Background ingestion completed (%d papers) for mission %s", paper_count, mission_id)

        except Exception as e:
            import traceback
            err_msg = str(e)
            logger.error("Background ingestion FAILED for mission %s: %s", mission_id, err_msg)
            traceback.print_exc()
            try:
                await _update_ingestion_status(db, mission_id, "failed", error=err_msg, completed=True)
            except Exception:
                pass  # DB might be gone — nothing we can do


@router.get("/ingest/status/{mission_id}")
async def get_ingestion_status(
    mission_id: str,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Poll the current ingestion status for a mission.

    Returns:
        status: idle | pending | processing | completed | failed
        progress: 0-100
        error: error message if failed, else null
    """
    stmt = select(Mission).where(Mission.id == mission_id)
    result = await db.execute(stmt)
    mission = result.scalar_one_or_none()

    if not mission:
        raise HTTPException(status_code=404, detail=f"Mission {mission_id} not found")

    return {
        "mission_id": mission_id,
        "status": mission.ingestion_status or "idle",
        "progress": mission.ingestion_progress or 0,
        "error": mission.ingestion_error,
        "started_at": mission.ingestion_started_at.isoformat() if mission.ingestion_started_at else None,
        "completed_at": mission.ingestion_completed_at.isoformat() if mission.ingestion_completed_at else None,
    }


@router.get("/mission/{mission_id}")
async def get_mission_papers(
    mission_id: str,
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Get all papers for a mission.
    
    Args:
        mission_id: UUID of the mission
        db: Database session
        limit: Max papers to return
        offset: Pagination offset
        
    Returns:
        List of papers with scores
    """
    try:
        stmt = (
            select(ResearchPaper)
            .where(ResearchPaper.mission_id == mission_id)
            .where(ResearchPaper.selected == 1)
            .order_by(ResearchPaper.final_score.desc())
            .limit(limit)
            .offset(offset)
        )
        
        result = await db.execute(stmt)
        papers = result.scalars().all()
        
        return {
            "mission_id": mission_id,
            "count": len(papers),
            "papers": [
                {
                    "id": str(paper.id),
                    "title": paper.title,
                    "authors": paper.authors,
                    "abstract": paper.abstract[:300] + "..." if paper.abstract and len(paper.abstract) > 300 else paper.abstract,
                    "year": paper.year,
                    "source": paper.source.value,
                    "final_score": paper.final_score,
                    "relevance_score": paper.relevance_score,
                    "url": paper.arxiv_url or paper.semantic_scholar_url or paper.pubmed_url,
                    "pdf_url": paper.pdf_url,
                    "score_breakdown": paper.score_breakdown,  # CEGC component scores
                    "mechanism_description": paper.mechanism_description,
                }
                for paper in papers
            ]
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/mission/{mission_id}/graph-stats")
async def get_mission_graph_stats(
    mission_id: str,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Get mission-level graph statistics for visualization.
    
    Args:
        mission_id: UUID of the mission
        db: Database session
        
    Returns:
        Graph statistics including total papers, average score, median score
    """
    try:
        # Get all papers for the mission
        stmt = (
            select(ResearchPaper)
            .where(ResearchPaper.mission_id == mission_id)
            .where(ResearchPaper.selected == 1)
        )
        
        result = await db.execute(stmt)
        papers = result.scalars().all()
        
        # Extract scores
        scores = []
        for paper in papers:
            # Try to get final_score from score_breakdown if available
            if paper.score_breakdown and isinstance(paper.score_breakdown, dict):
                final_score = paper.score_breakdown.get("final", paper.final_score or 0.0)
            else:
                final_score = paper.final_score or 0.0
            
            if final_score > 0:
                scores.append(final_score)
        
        # Calculate statistics
        total_papers = len(papers)
        
        if scores:
            avg_score = sum(scores) / len(scores)
            median_score = statistics.median(scores)
        else:
            avg_score = 0.0
            median_score = 0.0
        
        return {
            "mission_id": mission_id,
            "total_papers": total_papers,
            "papers_with_scores": len(scores),
            "avg_score": avg_score,
            "median_score": median_score,
            "min_score": min(scores) if scores else 0.0,
            "max_score": max(scores) if scores else 0.0,
            "timestamp": datetime.utcnow().isoformat(),
        }
    
    except Exception as e:
        logger.error(f"Error getting mission graph stats: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/paper/{paper_id}")
async def get_paper_detail(
    paper_id: str,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Get detailed information about a paper.
    
    Args:
        paper_id: UUID of the paper
        db: Database session
        
    Returns:
        Full paper details
    """
    try:
        stmt = select(ResearchPaper).where(ResearchPaper.id == paper_id)
        result = await db.execute(stmt)
        paper = result.scalar_one_or_none()
        
        if not paper:
            raise HTTPException(status_code=404, detail="Paper not found")
        
        return {
            "id": str(paper.id),
            "title": paper.title,
            "authors": paper.authors,
            "abstract": paper.abstract,
            "year": paper.year,
            "source": paper.source.value,
            "final_score": paper.final_score,
            "relevance_score": paper.relevance_score,
            "usefulness_score": paper.usefulness_score,
            "keywords": paper.keywords,
            "citations_count": paper.citations_count,
            "influence_score": paper.influence_score,
            "urls": {
                "arxiv": paper.arxiv_url,
                "semantic_scholar": paper.semantic_scholar_url,
                "pubmed": paper.pubmed_url,
                "pdf": paper.pdf_url,
            },
            "pico_matches": {
                "population": paper.pico_population_match,
                "intervention": paper.pico_intervention_match,
                "comparator": paper.pico_comparator_match,
                "outcome": paper.pico_outcome_match,
            },
            "cegc_scores": {
                "pico_match_score": paper.pico_match_score,
                "evidence_strength_score": paper.evidence_strength_score,
                "mechanism_agreement_score": paper.mechanism_agreement_score,
                "assumption_alignment_score": paper.assumption_alignment_score,
                "llm_verification_score": paper.llm_verification_score,
                "score_breakdown": paper.score_breakdown,
            },
            "mechanism_description": paper.mechanism_description,
            "reasoning_graph": paper.reasoning_graph,
            "full_text_available": bool(paper.full_text_content),
            "retrieved_at": paper.retrieved_at.isoformat() if paper.retrieved_at else None,
            "processed_at": paper.processed_at.isoformat() if paper.processed_at else None,
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/mission/{mission_id}/events")
async def get_ingestion_events(
    mission_id: str,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Get ingestion event history for a mission.
    
    Args:
        mission_id: UUID of the mission
        db: Database session
        
    Returns:
        List of ingestion events with statistics
    """
    try:
        stmt = (
            select(IngestionEvent)
            .where(IngestionEvent.mission_id == mission_id)
            .order_by(IngestionEvent.started_at.desc())
        )
        
        result = await db.execute(stmt)
        events = result.scalars().all()
        
        return {
            "mission_id": mission_id,
            "total_events": len(events),
            "events": [
                {
                    "batch_id": event.batch_id,
                    "started_at": event.started_at.isoformat(),
                    "completed_at": event.completed_at.isoformat() if event.completed_at else None,
                    "status": event.status,
                    "total_retrieved": event.total_retrieved,
                    "after_dedup": event.after_dedup,
                    "after_prefilter": event.after_prefilter,
                    "after_rerank": event.after_rerank,
                    "final_selected": event.final_selected,
                    "avg_scores": {
                        "relevance": event.avg_relevance_score,
                        "usefulness": event.avg_usefulness_score,
                        "final": event.avg_final_score,
                    },
                    "processing_time_seconds": event.processing_time_seconds,
                    "llm_calls": event.total_llm_calls,
                    "llm_tokens": event.total_llm_tokens,
                    "sources_used": event.sources_used,
                    "error": event.error_message,
                }
                for event in events
            ]
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/similar/{paper_id}")
async def get_similar_papers(
    paper_id: str,
    mission_id: str = Query(..., description="UUID of the mission"),
    limit: int = Query(5, ge=1, le=20, description="Number of similar papers to return"),
    threshold: float = Query(0.0, ge=0.0, le=1.0, description="Minimum similarity score (0-1)"),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Find papers semantically similar to a given paper using FAISS vector search.
    
    This uses embeddings (768-dimensional vectors) to find papers with similar content.
    The search compares abstract embeddings and returns results ranked by similarity.
    
    Args:
        paper_id: UUID of the query paper
        mission_id: UUID of the mission (to identify which FAISS index to use)
        limit: Maximum number of similar papers to return (1-20)
        threshold: Minimum similarity score to include (0.0-1.0)
        db: Database session
        
    Returns:
        List of similar papers with similarity scores
        
    Example:
        GET /api/papers/similar/abc123?mission_id=xyz&limit=5&threshold=0.7
        Returns top 5 papers with similarity ≥ 0.7
    """
    try:
        # 1. Get the query paper
        stmt = select(ResearchPaper).where(ResearchPaper.id == paper_id)
        result = await db.execute(stmt)
        query_paper = result.scalar_one_or_none()
        
        if not query_paper:
            raise HTTPException(status_code=404, detail=f"Paper {paper_id} not found")
        
        if not query_paper.embedding:
            raise HTTPException(
                status_code=400, 
                detail="Paper has no embedding - cannot search for similar papers"
            )
        
        # 2. Get all papers for this mission
        stmt = (
            select(ResearchPaper)
            .where(ResearchPaper.mission_id == mission_id)
            .where(ResearchPaper.selected == 1)
            .order_by(ResearchPaper.final_score.desc())
        )
        result = await db.execute(stmt)
        all_papers = result.scalars().all()
        
        if not all_papers:
            raise HTTPException(status_code=404, detail=f"No papers found for mission {mission_id}")
        
        # 3. Use FAISS or fallback to manual search
        similar_papers = await search_similar_papers_service(
            query_paper=query_paper,
            all_papers=all_papers,
            limit=limit + 1,  # +1 to exclude the query paper itself
            mission_id=mission_id,
        )
        
        # 4. Filter by threshold and exclude query paper itself
        similar_papers = [
            p for p in similar_papers 
            if p["id"] != paper_id and p["similarity_score"] >= threshold
        ][:limit]
        
        return {
            "query_paper": {
                "id": str(query_paper.id),
                "title": query_paper.title,
            },
            "similar_papers_count": len(similar_papers),
            "similar_papers": similar_papers,
        }
    
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        logger.error(f"Error searching similar papers: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


async def search_similar_papers_service(
    query_paper: ResearchPaper,
    all_papers: List[ResearchPaper],
    limit: int,
    mission_id: str,
) -> List[Dict[str, Any]]:
    """
    Search for similar papers using FAISS index if available, fallback to manual search.
    
    Args:
        query_paper: The paper to find similarities for
        all_papers: All papers in the mission
        limit: Number of results to return
        mission_id: Mission ID (for FAISS index path)
        
    Returns:
        List of similar papers with scores, sorted by similarity
    """
    try:
        import faiss
        import numpy as np
        import json
        import os
        
        index_path = f"storage/faiss_indices/{mission_id}.index"
        mapping_path = f"storage/faiss_indices/{mission_id}_mapping.json"
        
        # Try FAISS if index exists
        if os.path.exists(index_path) and os.path.exists(mapping_path):
            try:
                # Load FAISS index
                index = faiss.read_index(index_path)
                
                # Load mapping (index position → paper ID)
                with open(mapping_path, 'r') as f:
                    mapping = json.load(f)
                
                # Prepare query embedding
                query_embedding = np.array(query_paper.embedding).reshape(1, -1).astype('float32')
                
                # Search FAISS index
                distances, indices = index.search(query_embedding, min(limit, index.ntotal))
                
                # Build reverse mapping (paper ID → index position)
                id_to_index = {v: int(k) for k, v in mapping.items()}
                
                # Convert results to paper details
                results = []
                for dist, idx in zip(distances[0], indices[0]):
                    if idx == -1:  # Invalid index
                        continue
                    
                    # Find paper by index
                    matching_paper = None
                    for paper in all_papers:
                        if str(paper.id) in mapping.values():
                            position = int([k for k, v in mapping.items() if v == str(paper.id)][0])
                            if position == idx:
                                matching_paper = paper
                                break
                    
                    if matching_paper:
                        # Convert L2 distance to similarity score (0-1)
                        # Normalize distance to similarity: sim = 1 / (1 + distance)
                        similarity = 1.0 / (1.0 + float(dist))
                        
                        results.append({
                            "id": str(matching_paper.id),
                            "title": matching_paper.title,
                            "authors": matching_paper.authors,
                            "abstract": matching_paper.abstract[:300] + "..." if matching_paper.abstract and len(matching_paper.abstract) > 300 else matching_paper.abstract,
                            "year": matching_paper.year,
                            "source": matching_paper.source.value,
                            "final_score": matching_paper.final_score,
                            "relevance_score": matching_paper.relevance_score,
                            "url": matching_paper.arxiv_url or matching_paper.semantic_scholar_url or matching_paper.pubmed_url,
                            "pdf_url": matching_paper.pdf_url,
                            "similarity_score": similarity,
                            "distance": float(dist),
                        })
                
                return results
            
            except Exception as e:
                logger.warning(f"FAISS search failed, falling back to manual: {str(e)}")
                # Fall through to manual search
        
    except ImportError:
        logger.warning("FAISS not available, using manual search")
    
    # Fallback: Manual similarity search using stored embeddings
    logger.debug("Using manual paper-to-paper similarity search")
    all_similarities = []
    
    for paper in all_papers:
        if not paper.embedding:
            continue
        
        try:
            # Compute cosine similarity manually
            from app.services.embeddings import EmbeddingService
            
            similarity = EmbeddingService.cosine_similarity(
                query_paper.embedding,
                paper.embedding
            )
            
            all_similarities.append({
                "id": str(paper.id),
                "title": paper.title,
                "authors": paper.authors,
                "abstract": paper.abstract[:300] + "..." if paper.abstract and len(paper.abstract) > 300 else paper.abstract,
                "year": paper.year,
                "source": paper.source.value,
                "final_score": paper.final_score,
                "relevance_score": paper.relevance_score,
                "url": paper.arxiv_url or paper.semantic_scholar_url or paper.pubmed_url,
                "pdf_url": paper.pdf_url,
                "similarity_score": similarity,
                "distance": 1.0 - similarity,  # Inverse relationship
            })
        except Exception as e:
            logger.debug(f"Error computing similarity for paper {paper.id}: {str(e)}")
            continue
    
    # Sort by similarity (descending)
    all_similarities.sort(key=lambda x: x["similarity_score"], reverse=True)
    
    return all_similarities[:limit]


@router.get("/batch/{batch_id}/papers")
async def get_batch_papers(
    batch_id: str,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Get all papers from a specific ingestion batch.
    
    Args:
        batch_id: Batch UUID
        db: Database session
        
    Returns:
        Papers from this batch
    """
    try:
        stmt = (
            select(ResearchPaper)
            .where(ResearchPaper.ingestion_batch_id == batch_id)
            .order_by(ResearchPaper.rank_in_ingestion)
        )
        
        result = await db.execute(stmt)
        papers = result.scalars().all()
        
        return {
            "batch_id": batch_id,
            "count": len(papers),
            "papers": [
                {
                    "rank": paper.rank_in_ingestion,
                    "id": str(paper.id),
                    "title": paper.title,
                    "final_score": paper.final_score,
                    "source": paper.source.value,
                }
                for paper in papers
            ]
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats/source-distribution")
async def get_source_distribution(
    mission_id: str = None,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Get distribution of papers by source.
    
    Args:
        mission_id: Optional mission filter
        db: Database session
        
    Returns:
        Source distribution statistics
    """
    try:
        stmt = select(ResearchPaper.source, func.count(ResearchPaper.id).label("count"))
        
        if mission_id:
            stmt = stmt.where(ResearchPaper.mission_id == mission_id)
        
        stmt = stmt.where(ResearchPaper.selected == 1).group_by(ResearchPaper.source)
        
        result = await db.execute(stmt)
        rows = result.all()
        
        return {
            "mission_id": mission_id,
            "distributions": [
                {"source": row[0].value, "count": row[1]}
                for row in rows
            ]
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
