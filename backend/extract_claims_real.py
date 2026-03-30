"""
Real Claim Extraction Script

1. Remove mock test claims
2. Extract claims from all 100 papers in Medical mission
3. Verify extraction worked
"""

import asyncio
import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, delete, and_

from app.models.claims import ResearchClaim
from app.models.paper import Paper
from app.models.mission import Mission
from app.services.claim_extraction import ClaimExtractionService
from app.services.llm.llm_provider import NIMProvider
from app.services.embeddings import EmbeddingService
from app.config import settings
import os

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Database setup
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:aditya@postgres:5432/LHAS"
)

async def main():
    # Create engine
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as db:
        try:
            # ===== STEP 1: DELETE MOCK CLAIMS =====
            logger.info("=" * 80)
            logger.info("STEP 1: Deleting mock test claims...")
            logger.info("=" * 80)
            
            # Get the Medical mission
            result = await db.execute(
                select(Mission).where(Mission.name == "Medical")
            )
            medical_mission = result.scalars().first()
            
            if not medical_mission:
                logger.error("Medical mission not found!")
                return
            
            mission_id = medical_mission.id
            logger.info(f"Found Medical mission: {mission_id}")
            
            # Delete all claims for this mission (these are the mock ones)
            result = await db.execute(
                delete(ResearchClaim).where(ResearchClaim.mission_id == mission_id)
            )
            await db.commit()
            logger.info(f"✓ Deleted {result.rowcount} mock claims")
            
            # ===== STEP 2: GET MEDICAL MISSION PAPERS =====
            logger.info("=" * 80)
            logger.info("STEP 2: Finding papers in Medical mission...")
            logger.info("=" * 80)
            
            result = await db.execute(
                select(Paper).where(Paper.mission_id == mission_id)
            )
            papers = result.scalars().all()
            logger.info(f"Found {len(papers)} papers to extract claims from")
            
            if not papers:
                logger.warning("No papers found!")
                return
            
            # ===== STEP 3: INITIALIZE EXTRACTION SERVICE =====
            logger.info("=" * 80)
            logger.info("STEP 3: Initializing extraction service with LLM...")
            logger.info("=" * 80)
            
            # Initialize LLM provider
            llm_provider = NIMProvider()
            embedding_service = EmbeddingService()
            
            # Initialize extraction service
            extraction_service = ClaimExtractionService(
                db=db,
                llm_provider=llm_provider,
                embedding_service=embedding_service
            )
            logger.info("✓ Extraction service initialized")
            
            # ===== STEP 4: EXTRACT CLAIMS =====
            logger.info("=" * 80)
            logger.info("STEP 4: Extracting claims from papers...")
            logger.info("=" * 80)
            
            total_claims_extracted = 0
            failed_papers = 0
            
            for idx, paper in enumerate(papers, 1):
                try:
                    logger.info(f"\n[{idx}/{len(papers)}] Processing: {paper.title[:60]}...")
                    
                    result = await extraction_service.extract_claims_from_paper(
                        paper_id=str(paper.id),
                        mission_id=str(mission_id),
                        mission_question=medical_mission.research_question,
                        mission_domain=medical_mission.domain,
                        pdf_url=paper.pdf_url,
                        abstract=paper.abstract
                    )
                    
                    if result.get("success"):
                        claims_count = result.get("claims_extracted", 0)
                        total_claims_extracted += claims_count
                        logger.info(f"  ✓ Extracted {claims_count} claims")
                    else:
                        failed_papers += 1
                        logger.warning(f"  ✗ Failed: {result.get('error', 'Unknown error')}")
                
                except Exception as e:
                    failed_papers += 1
                    logger.error(f"  ✗ Error: {str(e)}")
                    continue
            
            # ===== STEP 5: VERIFY EXTRACTION =====
            logger.info("=" * 80)
            logger.info("STEP 5: Verifying extraction results...")
            logger.info("=" * 80)
            
            result = await db.execute(
                select(ResearchClaim).where(ResearchClaim.mission_id == mission_id)
            )
            all_claims = result.scalars().all()
            
            logger.info(f"\n{'=' * 80}")
            logger.info("EXTRACTION COMPLETE")
            logger.info(f"{'=' * 80}")
            logger.info(f"Total papers processed: {len(papers)}")
            logger.info(f"Failed papers: {failed_papers}")
            logger.info(f"Total claims extracted: {total_claims_extracted}")
            logger.info(f"Total claims in DB: {len(all_claims)}")
            
            # Show sample claims
            if all_claims:
                logger.info(f"\nSample of extracted claims (first 3):")
                for claim in all_claims[:3]:
                    logger.info(f"  - {claim.statement_raw[:80]}")
            
            logger.info(f"{'=' * 80}\n")
            
        except Exception as e:
            logger.error(f"Fatal error: {str(e)}", exc_info=True)
        finally:
            await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
