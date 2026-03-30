#!/usr/bin/env python3
"""Test claim extraction on all 50 papers"""

import asyncio
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Import services and models
from app.models import ResearchPaper, Mission
from app.services.claim_extraction import ClaimExtractionService
from app.database import DATABASE_URL
import time

async def test_all():
    """Extract claims from all 50 papers"""
    
    # Create engine and session
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    start_time = time.time()
    
    async with async_session() as db:
        try:
            print("🔍 Testing claim extraction on all 50 papers...")
            
            # Get mission
            mission_stmt = select(Mission)
            mission_result = await db.execute(mission_stmt)
            mission = mission_result.scalar_one_or_none()
            
            if not mission:
                print("❌ No mission found")
                return
            
            mission_id = mission.id
            mission_question = mission.normalized_query or "test"
            
            print(f"📋 Mission: {mission_id}")
            print(f"   Question: {mission_question[:60]}...")
            
            # Get all papers
            papers_stmt = select(ResearchPaper).where(
                ResearchPaper.mission_id == mission_id
            )
            papers_result = await db.execute(papers_stmt)
            papers = papers_result.scalars().all()
            
            print(f"\n📄 Found {len(papers)} papers to extract from")
            
            if not papers:
                print("❌ No papers found")
                return
            
            # Initialize claim service
            claim_service = ClaimExtractionService(db=db)
            
            # Extract from all papers sequentially (batches of 3 expected by paper_ingestion)
            total_claims = 0
            batch_size = 5
            
            for batch_idx in range(0, len(papers), batch_size):
                batch = papers[batch_idx:batch_idx + batch_size]
                print(f"\n[Batch {batch_idx // batch_size + 1}] Processing {len(batch)} papers...")
                
                for paper_idx, paper in enumerate(batch):
                    result = await claim_service.extract_claims_from_paper(
                        paper_id=paper.id,
                        mission_id=mission_id,
                        mission_question=mission_question,
                        mission_domain="general",
                    )
                    
                    if result.get('success'):
                        claim_count = result.get('claims_extracted', 0)
                        total_claims += claim_count
                        print(f"  [{batch_idx + paper_idx + 1}/50] {paper.title[:45]:45} → {claim_count} claims")
                    else:
                        print(f"  [{batch_idx + paper_idx + 1}/50] {paper.title[:45]:45} ❌")
                
                # Commit after each batch
                print(f"  💾 Committing batch...")
                await db.commit()
                print(f"  ✅ Batch committed")
            
            elapsed = time.time() - start_time
            
            # Query final count
            from app.models import ResearchClaim
            claims_stmt = select(ResearchClaim).where(
                ResearchClaim.mission_id == str(mission_id)
            )
            claims_result = await db.execute(claims_stmt)
            persisted_claims = claims_result.scalars().all()
            
            print(f"\n{'='*60}")
            print(f"✅ EXTRACTION COMPLETE")
            print(f"{'='*60}")
            print(f"Total elapsed: {elapsed:.1f} seconds ({elapsed/60:.1f} minutes)")
            print(f"Papers extracted: 50")
            print(f"Claims extracted (in memory): {total_claims}")
            print(f"Claims persisted (in DB): {len(persisted_claims)}")
            print(f"Average claims/paper: {len(persisted_claims) / 50:.1f}")
            print(f"Throughput: {50 / elapsed * 60:.1f} papers/minute")
            
        except Exception as e:
            import traceback
            print(f"❌ Test failed: {str(e)}")
            traceback.print_exc()
        finally:
            await engine.dispose()

if __name__ == '__main__':
    asyncio.run(test_all())
