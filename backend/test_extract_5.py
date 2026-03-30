#!/usr/bin/env python
"""Quick test extraction - just 5 papers"""
import asyncio
import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.config import settings
from app.models.paper import ResearchPaper
from app.models.mission import Mission
from app.services.claim_extraction import ClaimExtractionService
from app.services.llm.llm_provider import NIMProvider

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as db:
        # Get mission
        mission_id = "2ee30391-f6bf-4b48-be12-f9660c70a897"
        stmt = select(Mission).where(Mission.id == mission_id)
        mission = (await db.execute(stmt)).scalars().first()
        logger.info(f"Mission: {mission.name}")
        
        # Get first 5 papers
        stmt = select(ResearchPaper).where(ResearchPaper.mission_id == mission_id).limit(5)
        papers = (await db.execute(stmt)).scalars().all()
        logger.info(f"Papers: {len(papers)}")
        
        # LLM
        llm_provider = NIMProvider()
        logger.info("✓ LLM initialized")
        
        # Extract from first 5
        extraction_service = ClaimExtractionService(db=db, llm_provider=llm_provider, embedding_service=None)
        for idx, paper in enumerate(papers, 1):
            logger.info(f"\n[{idx}/5] {paper.title[:50]}...")
            result = await extraction_service.extract_claims_from_paper(
                paper_id=str(paper.id),
                mission_id=mission_id,
                mission_question=mission.normalized_query,
                mission_domain=mission.name,
                pdf_url=paper.pdf_url,
                abstract=paper.abstract
            )
            logger.info(f"Result: {result}")
    
    await engine.dispose()

asyncio.run(main())
