#!/usr/bin/env python3
"""Populate CEGC scores for existing papers in the database"""

import asyncio
import logging
import sys
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

sys.path.insert(0, '/app')

from app.models import ResearchPaper, Mission
from app.services.cegc_scoring import CEGCScoringService
from app.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def populate_cegc_scores():
    """Populate CEGC scores for all papers missing score_breakdown"""
    
    # Create async engine
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        future=True,
    )
    
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    
    try:
        async with async_session() as db:
            # Get all papers without scores
            stmt = select(ResearchPaper).where(
                ResearchPaper.score_breakdown == None
            )
            result = await db.execute(stmt)
            papers_db = result.scalars().all()
            
            logger.info(f"Found {len(papers_db)} papers without CEGC scores")
            
            if not papers_db:
                logger.info("✅ All papers already have CEGC scores")
                return
            
            # Get missions with their queries
            missions = {}
            for paper in papers_db:
                if paper.mission_id not in missions:
                    mission_stmt = select(Mission).where(
                        Mission.id == paper.mission_id
                    )
                    mission_result = await db.execute(mission_stmt)
                    mission = mission_result.scalar_one_or_none()
                    if mission:
                        missions[paper.mission_id] = mission
            
            logger.info(f"Found {len(missions)} missions")
            
            # Initialize CEGC service (without LLM for speed)
            cegc_service = CEGCScoringService(
                llm_provider=None,  # No LLM for batch population
                embedding_service=None,
            )
            
            # Score papers in batches by mission
            total_updated = 0
            for mission_id, mission in missions.items():
                mission_papers = [p for p in papers_db if p.mission_id == mission_id]
                logger.info(f"\n🔄 Processing {len(mission_papers)} papers for mission: {mission.name}")
                
                # Create structured query from mission
                structured_query = {
                    'normalized_query': mission.normalized_query or mission.query or '',
                    'pico': mission.pico or {},
                    'key_concepts': mission.key_concepts or [],
                }
                
                # Convert DB papers to dict-like objects for CEGC service
                class PaperObj:
                    def __init__(self, paper):
                        self.title = paper.title
                        self.abstract = paper.abstract
                        self.authors = paper.authors
                        self.year = paper.year
                        self.source = paper.source
                        self.url = paper.arxiv_url or paper.semantic_scholar_url or paper.pubmed_url
                        self.pdf_url = paper.pdf_url
                        self.keywords = paper.keywords
                        self.pico_population_match = paper.pico_population_match
                        self.pico_intervention_match = paper.pico_intervention_match
                        self.pico_outcome_match = paper.pico_outcome_match
                        self.id = paper.id
                        self.final_score = 0.0
                        self.pico_match_score = None
                        self.evidence_strength_score = None
                        self.mechanism_agreement_score = None
                        self.assumption_alignment_score = None
                        self.llm_verification_score = None
                        self.score_breakdown = None
                        self.reasoning_graph = None
                        self.mechanism_description = None
                
                paper_objs = [PaperObj(p) for p in mission_papers]
                
                # Score through CEGC (no LLM)
                scored_papers, _, _ = await cegc_service.score_papers(
                    papers=paper_objs,
                    structured_query=structured_query,
                    use_llm=False,  # No LLM for batch processing
                )
                
                # Update database
                for scored_paper in scored_papers:
                    # Find the original DB paper
                    db_paper = next((p for p in mission_papers if str(p.id) == str(scored_paper.id)), None)
                    if db_paper:
                        db_paper.pico_match_score = scored_paper.pico_match_score
                        db_paper.evidence_strength_score = scored_paper.evidence_strength_score
                        db_paper.mechanism_agreement_score = scored_paper.mechanism_agreement_score
                        db_paper.assumption_alignment_score = scored_paper.assumption_alignment_score
                        db_paper.llm_verification_score = scored_paper.llm_verification_score or 0.0
                        db_paper.final_score = scored_paper.final_score
                        db_paper.score_breakdown = scored_paper.score_breakdown
                        db_paper.mechanism_description = scored_paper.mechanism_description
                        total_updated += 1
                
                # Batch commit
                await db.commit()
                logger.info(f"✅ Updated {len(scored_papers)} papers for mission")
            
            logger.info(f"\n✅ CEGC population complete! Updated {total_updated} papers")
    
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(populate_cegc_scores())
