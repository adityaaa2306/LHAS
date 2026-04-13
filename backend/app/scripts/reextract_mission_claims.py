"""Rebuild all claims for a mission using the current extraction pipeline."""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select

from app.database import async_session_maker
from app.models import Mission, ResearchPaper
from app.services.claim_extraction import ClaimExtractionService
from app.services.embeddings import get_embedding_service
from app.services.llm import get_llm_provider


async def main(mission_id: str) -> int:
    async with async_session_maker() as db:
        mission = await db.get(Mission, mission_id)
        if not mission:
            print(f"Mission not found: {mission_id}", flush=True)
            return 1

        papers = (
            await db.execute(
                select(ResearchPaper)
                .where(ResearchPaper.mission_id == mission_id)
                .order_by(ResearchPaper.final_score.desc())
            )
        ).scalars().all()

        service = ClaimExtractionService(
            db=db,
            llm_provider=get_llm_provider(),
            embedding_service=get_embedding_service(),
        )

        print(f"Mission: {mission_id}", flush=True)
        print(f"Query: {mission.normalized_query}", flush=True)
        print(f"Papers to process: {len(papers)}", flush=True)

        total_claims = 0
        successes = 0
        failures = 0

        for index, paper in enumerate(papers, 1):
            try:
                result = await service.extract_claims_from_paper(
                    paper_id=paper.id,
                    mission_id=mission_id,
                    mission_question=mission.normalized_query,
                    mission_domain=mission.intent_type.value if mission.intent_type else "general",
                    pdf_url=paper.pdf_url,
                    abstract=paper.abstract or "",
                )

                if result.get("success"):
                    count = result.get("claims_extracted", 0)
                    total_claims += count
                    successes += 1
                    print(
                        f"{index:03d}/{len(papers)} OK   {count:02d} claims | {paper.title[:100]}",
                        flush=True,
                    )
                else:
                    failures += 1
                    print(
                        f"{index:03d}/{len(papers)} FAIL 00 claims | "
                        f"{paper.title[:100]} | {result.get('error')}",
                        flush=True,
                    )

                await db.commit()
            except Exception as exc:
                failures += 1
                await db.rollback()
                print(
                    f"{index:03d}/{len(papers)} FAIL 00 claims | "
                    f"{paper.title[:100]} | exception: {exc}",
                    flush=True,
                )

        print(
            f"Done. successes={successes} failures={failures} total_claims={total_claims}",
            flush=True,
        )
        return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m app.scripts.reextract_mission_claims <mission_id>", flush=True)
        raise SystemExit(2)

    raise SystemExit(asyncio.run(main(sys.argv[1])))
