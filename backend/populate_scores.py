#!/usr/bin/env python3
import asyncio
import sys
sys.path.insert(0, '/app')

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

from app.models import ResearchPaper, Mission
from app.services.cegc_scoring import CEGCScoringService
from app.config import settings

async def main():
    engine = create_async_engine(settings.DATABASE_URL, echo=False, future=True)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    updated_count = 0
    
    try:
        async with async_session() as db:
            # Get all missions
            missions_result = await db.execute(select(Mission))
            missions = missions_result.scalars().all()
            
            print(f"Found {len(missions)} missions")
            
            for mission in missions:
                print(f"\n📌 Processing mission: {mission.name}")
                
                # Get papers for this mission
                stmt = select(ResearchPaper).where(
                    ResearchPaper.mission_id == mission.id
                )
                result = await db.execute(stmt)
                papers = result.scalars().all()
                
                print(f"  Papers: {len(papers)}")
                if not papers:
                    continue
                
                # Initialize CEGC service
                cegc = CEGCScoringService(llm_provider=None, embedding_service=None)
                
                # Build query
                query = {
                    'normalized_query': mission.normalized_query or mission.query or '',
                    'pico': getattr(mission, 'pico', {}) or {},
                    'key_concepts': getattr(mission, 'key_concepts', []) or [],
                }
                
                # Create paper objects for CEGC scoring
                class PaperObj:
                    def __init__(self, p):
                        self.title = p.title or ""
                        self.abstract = p.abstract or ""
                        self.authors = p.authors or []
                        self.year = p.year
                        self.source = p.source
                        self.url = p.arxiv_url or p.semantic_scholar_url or p.pubmed_url
                        self.pdf_url = p.pdf_url
                        self.keywords = p.keywords or []
                        self.id = str(p.id)
                        self.pico_population_match = p.pico_population_match
                        self.pico_intervention_match = p.pico_intervention_match
                        self.pico_outcome_match = p.pico_outcome_match
                        self.pico_comparator_match = p.pico_comparator_match
                        self.final_score = 0.0
                        self.pico_match_score = None
                        self.evidence_strength_score = None
                        self.mechanism_agreement_score = None
                        self.assumption_alignment_score = None
                        self.llm_verification_score = None
                        self.score_breakdown = None
                        self.mechanism_description = None
                
                paper_objs = [PaperObj(p) for p in papers]
                
                # Score all papers
                print(f"  Scoring {len(paper_objs)} papers...")
                scored, llm_calls, llm_tokens = await cegc.score_papers(
                    paper_objs, query, use_llm=False
                )
                
                # Update database
                for scored_paper in scored:
                    for db_paper in papers:
                        if str(db_paper.id) == scored_paper.id:
                            db_paper.pico_match_score = float(scored_paper.pico_match_score or 0)
                            db_paper.evidence_strength_score = float(scored_paper.evidence_strength_score or 0)
                            db_paper.mechanism_agreement_score = float(scored_paper.mechanism_agreement_score or 0)
                            db_paper.assumption_alignment_score = float(scored_paper.assumption_alignment_score or 0)
                            db_paper.llm_verification_score = float(scored_paper.llm_verification_score or 0)
                            db_paper.final_score = float(scored_paper.final_score or 0)
                            db_paper.score_breakdown = scored_paper.score_breakdown
                            db_paper.mechanism_description = scored_paper.mechanism_description
                            updated_count += 1
                            break
                
                await db.commit()
                print(f"  ✅ Updated {len(scored)} papers")
            
            print(f"\n✅ COMPLETED: {updated_count} papers updated with CEGC scores")
    
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
