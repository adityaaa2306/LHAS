#!/usr/bin/env python3
"""Clear all data from database for fresh testing"""

import asyncio
import sys
from sqlalchemy import select, delete, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Import models
from app.models import (
    Mission, ResearchPaper, ResearchClaim, SynthesisAnswer, 
    ReasoningStep, MissionTimeline, Alert, IngestionEvent
)
from app.database import DATABASE_URL

async def cleanup_claims_only():
    """Delete only claims, keep papers and missions (for fast iteration)"""
    
    # Create async engine
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        try:
            print("🗑️  Clearing claims only...")
            
            # Delete claims and dependent tables
            tables_to_clean = [
                (SynthesisAnswer, 'synthesis_answers'),
                (ReasoningStep, 'reasoning_steps'),
                (ResearchClaim, 'research_claims'),
            ]
            
            for model, table_name in tables_to_clean:
                await session.execute(delete(model))
                await session.commit()
                print(f"  ✅ Cleared {table_name}")
            
            # Verify
            print("\n📊 Verification:")
            print(f"  ✅ Papers retained")
            print(f"  ✅ Missions retained")
            result = await session.execute(select(ResearchClaim))
            claim_count = len(result.scalars().all())
            print(f"  {'✅' if claim_count == 0 else '❌'} research_claims: {claim_count} rows")
            
            print("\n✅ Claims purged - ready for fresh extraction!")
            
        except Exception as e:
            print(f"❌ Cleanup failed: {str(e)}")
            raise
        finally:
            await engine.dispose()

async def cleanup_database():
    """Delete all data from all tables"""
    
    # Create async engine
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        try:
            print("🗑️  Cleaning up database...")
            
            # Delete in order of dependencies (reverse of creation)
            tables_to_clean = [
                (ResearchClaim, 'research_claims'),
                (SynthesisAnswer, 'synthesis_answers'),
                (ReasoningStep, 'reasoning_steps'),
                (MissionTimeline, 'mission_timelines'),
                (Alert, 'alerts'),
                (IngestionEvent, 'ingestion_events'),
                (ResearchPaper, 'research_papers'),
                (Mission, 'missions'),
            ]
            
            for model, table_name in tables_to_clean:
                await session.execute(delete(model))
                await session.commit()
                print(f"  ✅ Cleared {table_name}")
            
            # Verify cleanup
            print("\n📊 Verification:")
            for model, table_name in tables_to_clean:
                result = await session.execute(select(model))
                count = len(result.scalars().all())
                status = "✅" if count == 0 else "❌"
                print(f"  {status} {table_name}: {count} rows")
            
            print("\n✅ Database cleanup complete!")
            
        except Exception as e:
            print(f"❌ Cleanup failed: {str(e)}")
            raise
        finally:
            await engine.dispose()

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == '--claims-only':
        asyncio.run(cleanup_claims_only())
    else:
        asyncio.run(cleanup_database())
