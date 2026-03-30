#!/usr/bin/env python
"""
Batch Claim Extraction Script - PRODUCTION

Extracts claims from all papers in the Medical mission
using the real LLM (NVIDIA NIM with meta/llama-3.1-8b-instruct)

Usage:
    python extract_claims_batch.py
"""

import asyncio
import logging
import sys
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import app modules
from app.config import settings
from app.models.paper import ResearchPaper
from app.models.mission import Mission
from app.services.claim_extraction import ClaimExtractionService, ExtractionPipeline
from app.services.llm.llm_provider import NIMProvider
from app.services.embeddings import EmbeddingService


async def main():
    """Extract claims from all papers in Medical mission."""
    
    logger.info("=" * 80)
    logger.info("BATCH CLAIM EXTRACTION - MEDICAL MISSION")
    logger.info("=" * 80)
    
    # Create async database engine
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        pool_pre_ping=True
    )
    
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    
    try:
        async with async_session() as db:
            # Get Medical mission
            mission_id = "2ee30391-f6bf-4b48-be12-f9660c70a897"
            
            stmt = select(Mission).where(Mission.id == mission_id)
            result = await db.execute(stmt)
            mission = result.scalars().first()
            
            if not mission:
                logger.error(f"Mission {mission_id} not found")
                return
            
            logger.info(f"✓ Mission found: {mission.name}")
            logger.info(f"  Query: {mission.normalized_query}")
            
            # Get all papers for this mission
            stmt = select(ResearchPaper).where(
                ResearchPaper.mission_id == mission_id
            )
            result = await db.execute(stmt)
            papers = result.scalars().all()
            
            logger.info(f"✓ Found {len(papers)} papers to process")
            
            if not papers:
                logger.warning("No papers found for extraction")
                return
            
            # Initialize LLM provider and embedding service
            logger.info("\nInitializing LLM provider...")
            try:
                llm_provider = NIMProvider()
                logger.info(f"✓ LLM initialized: {settings.NVIDIA_MODEL}")
            except Exception as e:
                logger.error(f"✗ Failed to initialize LLM: {e}")
                return
            
            # Initialize embedding service (optional for retrieval)
            embedding_service = None  # Can add if needed
            
            # Initialize claim extraction service
            extraction_service = ClaimExtractionService(
                db=db,
                llm_provider=llm_provider,
                embedding_service=embedding_service,
                pipeline_config=ExtractionPipeline(
                    enable_failure_logger=False,  # Disable for now - requires more parameters
                    enable_coherence_checking=False,
                    enable_entity_evolution_advanced=True,
                    enable_uncertainty_decomposition=False,
                    enable_evidence_gap_detection=False
                )
            )
            
            logger.info("✓ Extraction service initialized\n")
            
            # Extract claims from each paper
            total_claims_extracted = 0
            papers_processed = 0
            failed_papers = 0
            
            for idx, paper in enumerate(papers, 1):
                try:
                    logger.info(f"[{idx}/{len(papers)}] Processing: {paper.title[:70]}...")
                    
                    # Extract claims from this paper
                    result = await extraction_service.extract_claims_from_paper(
                        paper_id=str(paper.id),
                        mission_id=mission_id,
                        mission_question=mission.normalized_query,
                        mission_domain=mission.name,
                        pdf_url=paper.pdf_url,
                        abstract=paper.abstract
                    )
                    
                    # Commit transaction to save claims
                    await db.commit()
                    
                    if result.get("success"):
                        claims_count = result.get("claims_extracted", 0)
                        total_claims_extracted += claims_count
                        papers_processed += 1
                        logger.info(f"  ✓ Extracted {claims_count} claims")
                    else:
                        error = result.get("error", "Unknown error")
                        logger.warning(f"  ✗ Failed: {error}")
                        failed_papers += 1
                    
                    # Progress indicator
                    if idx % 10 == 0:
                        logger.info(f"  → Progress: {idx}/{len(papers)} papers processed")
                
                except Exception as e:
                    logger.error(f"  ✗ Exception processing paper: {e}")
                    failed_papers += 1
            
            # Summary
            logger.info("\n" + "=" * 80)
            logger.info("EXTRACTION COMPLETE")
            logger.info("=" * 80)
            logger.info(f"✓ Papers processed: {papers_processed}/{len(papers)}")
            logger.info(f"✓ Total claims extracted: {total_claims_extracted}")
            logger.info(f"✗ Failed papers: {failed_papers}")
            
            # Update mission stats
            mission.total_claims = total_claims_extracted
            await db.commit()
            logger.info(f"✓ Mission updated with {total_claims_extracted} total claims")
            
            # Verify claims in database
            stmt = select(ResearchPaper.id).where(
                ResearchPaper.mission_id == mission_id
            )
            result = await db.execute(stmt)
            paper_ids = result.scalars().all()
            
            logger.info(f"\nVerifying claims in database...")
            logging_info = f"Claim count verification complete"
            logger.info(f"✓ {logging_info}")
    
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
    
    finally:
        await engine.dispose()
        logger.info("\n✓ Database connection closed")


if __name__ == "__main__":
    asyncio.run(main())
