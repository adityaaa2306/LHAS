import asyncio
from app.database import AsyncSessionLocal, init_db
from app.services.paper_ingestion import PaperIngestionService, IngestionConfig
from app.config import settings
import uuid

async def test_ingest():
    await init_db()
    
    async with AsyncSessionLocal() as db:
        service = PaperIngestionService(
            db,
            semantic_scholar_api_key=settings.SEMANTIC_SCHOLAR_API_KEY,
            pubmed_api_key=settings.PUBMED_API_KEY,
        )
        
        mission_id = str(uuid.uuid4())
        query = {
            'normalized_query': 'cancer immunotherapy',
            'key_concepts': ['cancer', 'immunotherapy'],
            'search_queries': ['cancer immunotherapy'],
        }
        
        config = IngestionConfig(
            max_candidates=60,
            sources=['arxiv', 'semantic_scholar', 'pubmed']
        )
        
        print('Running ingestion...')
        result = await service.ingest_papers(mission_id, query, config)
        
        print('Ingestion complete!')
        print(f"Total retrieved: {result.get('total_retrieved', 0)}")
        print(f"Final selected: {result.get('final_selected', 0)}")
        print(f"Processing time: {result.get('processing_time_seconds', 0):.1f}s")

asyncio.run(test_ingest())
