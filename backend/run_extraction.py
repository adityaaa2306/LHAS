#!/usr/bin/env python3
"""Extract claims from all Medical mission papers using NVIDIA NIM LLM"""

import asyncio
import logging
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.models.mission import Mission
from app.models.paper import ResearchPaper
from app.services.claim_extraction import ClaimExtractionService
from app.services.llm.llm_provider import NIMProvider
from app.services.embeddings import EmbeddingService
from app.database import DATABASE_URL

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

async def extract_all():
    """Extract claims from all papers in Medical mission"""
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as db:
        try:
            # Get Medical mission
            result = await db.execute(select(Mission).where(Mission.name == "Medical"))
            mission = result.scalars().first()
            
            if not mission:
                logger.error("❌ Medical mission not found!")
                return
            
            mission_id = mission.id
            logger.info(f"✅ Found Medical mission: {mission_id}")
            
            # Get all papers
            result = await db.execute(
                select(ResearchPaper).where(ResearchPaper.mission_id == mission_id)
            )
            papers = result.scalars().all()
            logger.info(f"✅ Found {len(papers)} papers to extract claims from\n")
            logger.info("=" * 80)
            logger.info("Starting real claim extraction with NVIDIA NIM LLM...")
            logger.info("=" * 80 + "\n")
            
            # Initialize extraction service
            llm_provider = NIMProvider()
            embedding_service = EmbeddingService()
            extraction_service = ClaimExtractionService(
                db=db,
                llm_provider=llm_provider,
                embedding_service=embedding_service
            )
            
            total_claims = 0
            successful = 0
            failed = 0
            
            for idx, paper in enumerate(papers, 1):
                try:
                    logger.info(f"[{idx}/{len(papers)}] {paper.title[:70]}")
                    
                    result = await extraction_service.extract_claims_from_paper(
                        paper_id=str(paper.id),
                        mission_id=str(mission_id),
                        mission_question=mission.normalized_query,
                        mission_domain="Medical Research",
                        pdf_url=paper.pdf_url,
                        abstract=paper.abstract
                    )
                    
                    if result.get("success"):
                        claims_count = result.get("claims_extracted", 0)
                        total_claims += claims_count
                        successful += 1
                        if claims_count > 0:
                            logger.info(f"  ✅ {claims_count} claims extracted")
                        else:
                            logger.info(f"  ℹ️ No claims relevant to mission")
                    else:
                        failed += 1
                        logger.warning(f"  ❌ {result.get('error', 'Unknown error')}")
                except Exception as e:
                    failed += 1
                    logger.error(f"  ❌ {str(e)[:100]}")
            
            logger.info("\n" + "=" * 80)
            logger.info("EXTRACTION COMPLETE")
            logger.info("=" * 80)
            logger.info(f"Total papers: {len(papers)}")
            logger.info(f"Successful: {successful}")
            logger.info(f"Failed: {failed}")
            logger.info(f"Total claims extracted: {total_claims}")
            logger.info("=" * 80)
            
        except Exception as e:
            logger.error(f"❌ Error: {str(e)}", exc_info=True)
        finally:
            await engine.dispose()

if __name__ == "__main__":
    asyncio.run(extract_all())
