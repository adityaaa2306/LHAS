import asyncio
from app.services.paper_ingestion import ArxivConnector, SemanticScholarConnector, PubMedConnector

async def test():
    query = 'machine learning'
    
    print('Testing all three sources for:', query)
    print('='*60)
    
    print('\n1. ArXiv:')
    arxiv = ArxivConnector()
    papers = await arxiv.search(query, 2)
    print(f'   Retrieved: {len(papers)} papers')
    for p in papers[:2]:
        print(f'   - {p.title[:50]}... ({p.source})')
    
    print('\n2. Semantic Scholar:')
    ss = SemanticScholarConnector(api_key='f1ZigXCjmh9OrVN8nmQpi4wQgDNR5xXjaTu9iZH8')
    papers = await ss.search(query, 2)
    print(f'   Retrieved: {len(papers)} papers')
    for p in papers[:2]:
        print(f'   - {p.title[:50]}... ({p.source})')
    
    print('\n3. PubMed:')
    pubmed = PubMedConnector(api_key='9659faaa79740b57807d7f35d5104dd3e008')
    papers = await pubmed.search(query, 2)
    print(f'   Retrieved: {len(papers)} papers')
    for p in papers[:2]:
        print(f'   - {p.title[:50]}... ({p.source})')
    
    print('\n' + '='*60)

asyncio.run(test())
