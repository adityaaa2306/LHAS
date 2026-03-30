#!/usr/bin/env python3
"""
Test script to verify multi-source paper retrieval
"""
import asyncio
import sys
sys.path.insert(0, '/app')

from app.services.paper_ingestion import ArxivConnector, SemanticScholarConnector, PubMedConnector
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

async def test_sources():
    """Test retrieval from all sources"""
    query = "machine learning"
    max_results = 5
    
    print(f"\n{'='*60}")
    print(f"Testing retrieval for query: '{query}'")
    print(f"{'='*60}\n")
    
    # Test ArXiv
    print("1. Testing ArXiv Connector...")
    arxiv = ArxivConnector()
    try:
        arxiv_papers = await arxiv.search(query, max_results)
        print(f"   ✓ ArXiv: Retrieved {len(arxiv_papers)} papers")
        if arxiv_papers:
            print(f"   First paper: {arxiv_papers[0].title[:60]}...")
    except Exception as e:
        print(f"   ✗ ArXiv Error: {str(e)}")
    
    # Test Semantic Scholar
    print("\n2. Testing Semantic Scholar Connector...")
    ss = SemanticScholarConnector(api_key="f1ZigXCjmh9OrVN8nmQpi4wQgDNR5xXjaTu9iZH8")
    try:
        ss_papers = await ss.search(query, max_results)
        print(f"   ✓ Semantic Scholar: Retrieved {len(ss_papers)} papers")
        if ss_papers:
            print(f"   First paper: {ss_papers[0].title[:60]}...")
    except Exception as e:
        print(f"   ✗ Semantic Scholar Error: {str(e)}")
    
    # Test PubMed
    print("\n3. Testing PubMed Connector...")
    pubmed = PubMedConnector(api_key="9659faaa79740b57807d7f35d5104dd3e008")
    try:
        pubmed_papers = await pubmed.search(query, max_results)
        print(f"   ✓ PubMed: Retrieved {len(pubmed_papers)} papers")
        if pubmed_papers:
            print(f"   First paper: {pubmed_papers[0].title[:60]}...")
    except Exception as e:
        print(f"   ✗ PubMed Error: {str(e)}")
    
    print(f"\n{'='*60}")
    print("Test Summary:")
    print(f"ArXiv: {len(arxiv_papers) if 'arxiv_papers' in locals() else 'ERROR'} papers")
    print(f"Semantic Scholar: {len(ss_papers) if 'ss_papers' in locals() else 'ERROR'} papers")
    print(f"PubMed: {len(pubmed_papers) if 'pubmed_papers' in locals() else 'ERROR'} papers")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    asyncio.run(test_sources())
