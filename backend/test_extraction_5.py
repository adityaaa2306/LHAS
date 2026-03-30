#!/usr/bin/env python3
"""Test claim extraction on 5 papers"""

import asyncio
import sys
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Import services and models
from app.models import ResearchPaper, Mission
from app.services.claim_extraction import ClaimExtractionService
from app.database import DATABASE_URL

async def test_extraction():
    """Test claim extraction on 5 papers"""
    
    # Create engine and session
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as db:
        try:
            print("🔍 Testing claim extraction on 5 papers...")
            
            # Get mission
            mission_stmt = select(Mission)
            mission_result = await db.execute(mission_stmt)
            mission = mission_result.scalar_one_or_none()
            
            if not mission:
                print("❌ No mission found")
                return
            
            mission_id = mission.id
            mission_question = mission.normalized_query or "test"
            mission_domain = "general"  # Mission doesn't have a domain attribute
            
            print(f"📋 Mission: {mission_id}")
            print(f"   Question: {mission_question}")
            print(f"   Domain: {mission_domain}")
            
            # Get 5 papers
            papers_stmt = select(ResearchPaper).where(
                ResearchPaper.mission_id == mission_id
            ).limit(5)
            papers_result = await db.execute(papers_stmt)
            papers = papers_result.scalars().all()
            
            print(f"\n📄 Found {len(papers)} papers to test")
            
            if not papers:
                print("❌ No papers found")
                return
            
            # Initialize service
            claim_service = ClaimExtractionService(db=db)
            
            # Extract claims from each paper
            total_claims = 0
            for idx, paper in enumerate(papers):
                print(f"\n[{idx+1}/5] Extracting from: {paper.title[:50]}...")
                
                result = await claim_service.extract_claims_from_paper(
                    paper_id=paper.id,
                    mission_id=mission_id,
                    mission_question=mission_question,
                    mission_domain=mission_domain,
                )
                
                if result.get('success'):
                    claim_count = result.get('claims_extracted', 0)
                    total_claims += claim_count
                    print(f"     ✅ {claim_count} claims extracted")
                else:
                    print(f"     ❌ Extraction failed: {result.get('error')}")
            
            # Commit all claims
            print(f"\n💾 Committing {total_claims} claims to database...")
            await db.commit()
            print("✅ Committed!")
            
            # Verify
            from app.models import ResearchClaim
            claims_stmt = select(ResearchClaim).where(
                ResearchClaim.mission_id == mission_id
            )
            claims_result = await db.execute(claims_stmt)
            persisted_claims = claims_result.scalars().all()
            
            print(f"\n📊 Final verification:")
            print(f"   Claims in database: {len(persisted_claims)}")
            print(f"   Expected: {total_claims}")
            
            if len(persisted_claims) == total_claims:
                print("   ✅ SUCCESS - All claims persisted!")
            else:
                print(f"   ❌ MISMATCH - Missing {total_claims - len(persisted_claims)} claims")
            
        except Exception as e:
            import traceback
            print(f"❌ Test failed: {str(e)}")
            traceback.print_exc()
        finally:
            await engine.dispose()

if __name__ == '__main__':
    asyncio.run(test_extraction())
