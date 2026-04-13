"""Paper Ingestion Module - Multi-stage retrieval and selection pipeline"""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Any, Optional, Dict, List, Tuple
import numpy as np
from dataclasses import dataclass, field
import httpx

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import insert, select
from app.models import ResearchPaper, IngestionEvent, PaperSource, Mission
from app.config import settings
from app.services.llm import get_llm_provider
from app.services.embeddings import get_embedding_service, EmbeddingService
from app.services.claim_extraction import ClaimExtractionService
from app.services.belief_revision import BeliefRevisionService
from app.services.contradiction_handling import ContradictionHandlingService
from app.services.memory_system import MemorySystemService
from app.services.synthesis_generation import SynthesisGenerationService
from app.models.memory import RawPaperStatus, SynthesisTrigger
import time

try:
    import faiss
except ImportError:
    faiss = None

logger = logging.getLogger(__name__)


@dataclass
class PaperObject:
    """Normalized paper representation"""
    paper_id: str
    title: str
    authors: List[str]
    abstract: str
    year: Optional[int]
    source: PaperSource
    doi: Optional[str] = None
    url: Optional[str] = None
    pdf_url: Optional[str] = None
    keywords: Optional[List[str]] = None
    citations_count: Optional[int] = None
    influence_score: Optional[float] = None
    raw_data: Dict[str, Any] = None
    embedding: Optional[List[float]] = field(default=None)  # Embedding vector
    
    # Old scoring fields (deprecated - kept for backward compatibility)
    relevance_score: Optional[float] = field(default=None)
    usefulness_score: Optional[float] = field(default=None)
    embedding_similarity: Optional[float] = field(default=None)
    
    # CEGC scoring fields (NEW)
    pico_match_score: Optional[float] = field(default=None)  # Layer 1
    evidence_strength_score: Optional[float] = field(default=None)  # Layer 2
    mechanism_agreement_score: Optional[float] = field(default=None)  # Layer 3
    assumption_alignment_score: Optional[float] = field(default=None)  # Layer 4
    llm_verification_score: Optional[float] = field(default=None)  # Layer 5
    
    # Final score and breakdown
    final_score: float = field(default=0.0)  # CEGC final score (0-1)
    score_breakdown: Optional[Dict[str, float]] = field(default=None)  # {"pico": 0.93, ...}
    reasoning_graph: Optional[Dict[str, Any]] = field(default=None)  # LLM reasoning if Layer 5 applied
    mechanism_description: Optional[str] = field(default=None)  # Mechanism explanation
    full_text_content: Optional[str] = field(default=None)  # Parsed PDF text for full-paper CEGC scoring
    full_text_sections: Optional[Dict[str, str]] = field(default=None)  # section name -> text
    full_text_source: Optional[str] = field(default=None)  # grobid|abstract_fallback|unavailable
    
    full_text_flag: int = field(default=0)

    def to_dict(self) -> dict:
        return {
            'paper_id': self.paper_id,
            'title': self.title,
            'authors': self.authors,
            'abstract': self.abstract,
            'year': self.year,
            'source': self.source.value if isinstance(self.source, PaperSource) else self.source,
            'doi': self.doi,
            'url': self.url,
            'pdf_url': self.pdf_url,
            'keywords': self.keywords,
            'citations_count': self.citations_count,
            'influence_score': self.influence_score,
            'final_score': self.final_score,
            'score_breakdown': self.score_breakdown,
        }


@dataclass
class IngestionConfig:
    """Configuration for paper ingestion"""
    max_candidates: int = 200
    prefilter_k: int = 100  # Increased from 60 to get more candidates through prefilter
    final_k: int = 50  # Increased from 20 to get 50 papers instead of 20
    relevance_threshold: float = 0.5
    sources: List[str] = None
    mmr_lambda: float = 0.8  # Increased from 0.6 to prioritize relevance (80%) over diversity (20%)
    min_abstract_length: int = 100
    
    def __post_init__(self):
        if self.sources is None:
            self.sources = ["arxiv", "semantic_scholar", "pubmed"]


class ArxivConnector:
    """ArXiv API connector with rate limiting and proper error handling."""
    
    BASE_URL = "https://export.arxiv.org/api/query"
    
    def __init__(self):
        self.client = None
        
        # Import rate limiter
        from app.services.rate_limiter import ArxivRateLimiter
        self.rate_limiter = ArxivRateLimiter()
    
    async def search(self, query: str, max_results: int = 100) -> List[PaperObject]:
        """
        Search arXiv for papers matching query.
        
        Rate limit: 1 request every 3 seconds
        Implemented as 0.25 req/sec (4 second intervals)
        """
        async def _do_search():
            # Build search query - simpler format for better matching
            keywords = query.split()
            if len(keywords) > 1:
                search_query = "+AND+".join(keywords)
            else:
                search_query = keywords[0] if keywords else query
            
            params = {
                'search_query': search_query,
                'start': 0,
                'max_results': min(max_results, 100),
                'sortBy': 'relevance',
                'sortOrder': 'descending'
            }
            
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(self.BASE_URL, params=params)
                response.raise_for_status()
            
            return response.text
        
        try:
            response_text = await self.rate_limiter.request(_do_search)
            papers = self._parse_arxiv_response(response_text)
            logger.info(f"ArXiv: Retrieved {len(papers)} papers for query '{query}'")
            return papers
            
        except Exception as e:
            logger.error(f"ArXiv retrieval error for query '{query}': {str(e)}")
            return []
    
    def _parse_arxiv_response(self, xml_response: str) -> List[PaperObject]:
        """Parse ArXiv XML response with proper namespace handling."""
        papers = []
        try:
            import xml.etree.ElementTree as ET
            
            # Parse XML
            root = ET.fromstring(xml_response)
            
            # ArXiv uses Atom namespace
            ns = {'atom': 'http://www.w3.org/2005/Atom',
                  'arxiv': 'http://arxiv.org/schemas/atom'}
            
            # Find all entries (skip the first which is usually metadata)
            entries = root.findall('atom:entry', ns)
            logger.debug(f"ArXiv: Found {len(entries)} entries in response")
            
            for entry in entries:
                try:
                    # Get ID (arxiv ID is in the id field)
                    id_elem = entry.find('atom:id', ns)
                    if id_elem is None or not id_elem.text:
                        continue
                    
                    # Extract arxiv ID from URL (e.g., http://arxiv.org/abs/2301.05123v1 -> 2301.05123)
                    arxiv_id = id_elem.text.split('/abs/')[-1].split('v')[0]
                    
                    # Get title
                    title_elem = entry.find('atom:title', ns)
                    if title_elem is None or not title_elem.text:
                        continue
                    title = title_elem.text.strip()
                    
                    # Get abstract/summary
                    summary_elem = entry.find('atom:summary', ns)
                    abstract = summary_elem.text.strip() if (summary_elem is not None and summary_elem.text) else ""
                    
                    # Get authors
                    authors = []
                    for author in entry.findall('atom:author', ns):
                        name_elem = author.find('atom:name', ns)
                        if name_elem is not None and name_elem.text:
                            authors.append(name_elem.text)
                    
                    # Get published date
                    published_elem = entry.find('atom:published', ns)
                    year = None
                    if published_elem is not None and published_elem.text:
                        try:
                            year = int(published_elem.text.split('-')[0])
                        except (ValueError, IndexError):
                            pass
                    
                    # Build URLs
                    arxiv_url = f"https://arxiv.org/abs/{arxiv_id}"
                    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
                    
                    paper = PaperObject(
                        paper_id=f"arxiv_{arxiv_id}",
                        title=title,
                        authors=authors,
                        abstract=abstract,
                        year=year,
                        source=PaperSource.ARXIV,
                        url=arxiv_url,
                        pdf_url=pdf_url,
                    )
                    papers.append(paper)
                    
                except Exception as e:
                    logger.debug(f"Error parsing arXiv entry: {str(e)}")
                    continue
            
            logger.debug(f"ArXiv: Successfully parsed {len(papers)} papers")
            return papers
            
        except ET.ParseError as e:
            logger.error(f"ArXiv XML parse error: {str(e)}")
            return []
        except Exception as e:
            logger.error(f"Error parsing arXiv response: {str(e)}")
            return []


class SemanticScholarConnector:
    """Semantic Scholar API connector with rate limiting and retry logic."""
    
    BASE_URL = "https://api.semanticscholar.org/graph/v1"
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.headers = {}
        if api_key:
            self.headers['x-api-key'] = api_key
        
        # Import rate limiter
        from app.services.rate_limiter import SemanticScholarRateLimiter
        self.rate_limiter = SemanticScholarRateLimiter(is_authenticated=bool(api_key))
    
    async def search(self, query: str, max_results: int = 100) -> List[PaperObject]:
        """
        Search Semantic Scholar for papers with rate limiting and retry logic.
        
        Rate limits:
        - Unauthenticated: 100 req/5min → 0.2 req/sec (5s intervals)
        - Authenticated: 1 req/sec (conservative)
        """
        async def _do_search():
            endpoint = f"{self.BASE_URL}/paper/search"
            params = {
                'query': query,
                'limit': min(max_results, 100),
                'fields': 'paperId,title,abstract,authors,year,externalIds,url,citationCount,openAccessPdf'
            }
            
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    endpoint,
                    params=params,
                    headers=self.headers,
                )
                response.raise_for_status()
            
            return response.json()
        
        try:
            data = await self.rate_limiter.request(_do_search)
            papers = self._parse_semantic_scholar_response(data)
            logger.info(f"Semantic Scholar: Retrieved {len(papers)} papers for query '{query}'")
            return papers
            
        except Exception as e:
            logger.error(f"Semantic Scholar retrieval error for query '{query}': {str(e)}")
            return []
    
    def _parse_semantic_scholar_response(self, data: dict) -> List[PaperObject]:
        """Parse Semantic Scholar API response."""
        papers = []
        try:
            for item in data.get('data', []):
                try:
                    paper_id = item.get('paperId')
                    title = item.get('title')
                    abstract = item.get('abstract') or ''
                    year = item.get('year')
                    
                    authors = [author.get('name') for author in item.get('authors', [])]
                    
                    external_ids = item.get('externalIds', {}) or {}
                    doi = external_ids.get('DOI')
                    
                    paper = PaperObject(
                        paper_id=f"semanticscholar_{paper_id}",
                        title=title,
                        authors=authors,
                        abstract=abstract,
                        year=year,
                        source=PaperSource.SEMANTIC_SCHOLAR,
                        doi=doi,
                        url=item.get('url'),
                        pdf_url=(item.get('openAccessPdf') or {}).get('url'),
                        citations_count=item.get('citationCount'),
                        influence_score=item.get('influenceScore'),
                    )
                    papers.append(paper)
                except Exception as e:
                    logger.debug(f"Error parsing Semantic Scholar entry: {str(e)}")
                    continue
            
            return papers
        except Exception as e:
            logger.error(f"Error parsing Semantic Scholar response: {str(e)}")
            return []


class PubMedConnector:
    """PubMed API connector (via NIH NCBI) with rate limiting."""
    
    SEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    FETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        
        # Import rate limiter
        from app.services.rate_limiter import PubMedRateLimiter
        self.rate_limiter = PubMedRateLimiter(is_authenticated=bool(api_key))
    
    async def search(self, query: str, max_results: int = 100) -> List[PaperObject]:
        """
        Search PubMed for papers with rate limiting.
        
        Rate limits:
        - Without API key: 3 req/sec (conservative: 2 req/sec)
        - With API key: 10 req/sec (conservative: 5 req/sec)
        """
        async def _do_search():
            # Step 1: Search to get PMIDs
            search_params = {
                'db': 'pubmed',
                'term': query,
                'retmax': min(max_results, 1000),
                'tool': 'lhas',
                'email': 'lhas@research.local'
            }
            
            if self.api_key:
                search_params['api_key'] = self.api_key
            
            async with httpx.AsyncClient(timeout=30) as client:
                search_response = await client.get(self.SEARCH_URL, params=search_params)
                search_response.raise_for_status()
                
                response_text = search_response.text.strip()
                if not response_text:
                    logger.info(f"PubMed: Empty response for query '{query}'")
                    return []
                
                # Parse XML response to get PMIDs
                try:
                    import xml.etree.ElementTree as ET
                    root = ET.fromstring(response_text)
                    pmids = [id_elem.text for id_elem in root.findall('.//Id')]
                except Exception as e:
                    logger.warning(f"PubMed: Failed to parse search response XML: {str(e)}")
                    return []
            
            if not pmids:
                logger.info(f"PubMed: No results found for query '{query}'")
                return []
            
            # Step 2: Fetch detailed records
            fetch_params = {
                'db': 'pubmed',
                'id': ','.join(pmids[:50]),  # Limit to 50 per fetch
                'rettype': 'medline',
                'retmode': 'text',
                'tool': 'lhas',
                'email': 'lhas@research.local'
            }
            
            if self.api_key:
                fetch_params['api_key'] = self.api_key
            
            async with httpx.AsyncClient(timeout=30) as client:
                fetch_response = await client.get(self.FETCH_URL, params=fetch_params)
                fetch_response.raise_for_status()
                
                return fetch_response.text.strip()
        
        try:
            fetch_text = await self.rate_limiter.request(_do_search)
            papers = self._parse_pubmed_medline_response(fetch_text)
            logger.info(f"PubMed: Retrieved {len(papers)} papers for query '{query}'")
            return papers
            
        except Exception as e:
            logger.error(f"PubMed retrieval error for query '{query}': {str(e)}")
            return []
    
    
    def _parse_pubmed_medline_response(self, medline_text) -> List[PaperObject]:
        """Parse PubMed MEDLINE format response."""
        if not medline_text or isinstance(medline_text, list):
            return []
        papers = []
        try:
            # Split by record separator (records are separated by blank lines)
            records = medline_text.split('\n\n')
            
            for record in records:
                if not record.strip():
                    continue
                    
                try:
                    lines = record.split('\n')
                    pmid = None
                    title = None
                    abstract = None
                    authors = []
                    year = None
                    
                    current_field = None
                    
                    for line in lines:
                        if line.startswith('PMID-'):
                            pmid = line.replace('PMID- ', '').strip()
                        elif line.startswith('TI  -'):
                            title = line.replace('TI  - ', '').strip()
                            current_field = 'title'
                        elif line.startswith('AB  -'):
                            abstract = line.replace('AB  - ', '').strip()
                            current_field = 'abstract'
                        elif line.startswith('AU  -'):
                            author_name = line.replace('AU  - ', '').strip()
                            if author_name:
                                authors.append(author_name)
                        elif line.startswith('DA  -'):
                            # Extract year from date field
                            date_str = line.replace('DA  - ', '').strip()
                            if len(date_str) >= 4:
                                try:
                                    year = int(date_str[:4])
                                except:
                                    pass
                        elif line.startswith('      '):
                            # Continuation of previous field
                            continuation = line.strip()
                            if current_field == 'title' and title:
                                title += ' ' + continuation
                            elif current_field == 'abstract' and abstract:
                                abstract += ' ' + continuation
                    
                    if not pmid or not title:
                        continue
                    
                    paper = PaperObject(
                        paper_id=f"pubmed_{pmid}",
                        title=title,
                        authors=authors,
                        abstract=abstract or '',
                        year=year,
                        source=PaperSource.PUBMED,
                        url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}",
                    )
                    papers.append(paper)
                except Exception as e:
                    logger.debug(f"Error parsing PubMed MEDLINE record: {str(e)}")
                    continue
            
            return papers
        except Exception as e:
            logger.error(f"Error parsing PubMed MEDLINE response: {str(e)}")
            return []
    
    def _parse_pubmed_response(self, data: dict) -> List[PaperObject]:
        """Parse PubMed API response."""
        papers = []
        try:
            articles = data.get('result', {}).get('uids', [])[1:]  # Skip first element (count)
            
            for uid in articles:
                try:
                    article = data.get('result', {}).get(uid, {})
                    if not article:
                        continue
                    
                    title = article.get('title', '')
                    authors = []
                    for author in article.get('authors', []):
                        author_name = author.get('name', 'Unknown')
                        if author_name:
                            authors.append(author_name)
                    
                    abstract = article.get('abstract', '')
                    year = int(article.get('pubdate', '0000').split()[0]) if article.get('pubdate') else None
                    
                    paper = PaperObject(
                        paper_id=f"pubmed_{uid}",
                        title=title,
                        authors=authors,
                        abstract=abstract,
                        year=year,
                        source=PaperSource.PUBMED,
                        url=f"https://pubmed.ncbi.nlm.nih.gov/{uid}",
                    )
                    papers.append(paper)
                except Exception as e:
                    logger.debug(f"Error parsing PubMed entry: {str(e)}")
                    continue
            
            return papers
        except Exception as e:
            logger.error(f"Error parsing PubMed response: {str(e)}")
            return []


class GrobidFullTextExtractor:
    """Parse open-access PDFs into sectioned text using a real GROBID service."""

    def __init__(self, grobid_url: str):
        self.grobid_url = grobid_url.rstrip("/")

    async def parse_pdf_url(self, paper: PaperObject) -> bool:
        """Populate full-text fields for a paper when a PDF URL is available."""
        if not paper.pdf_url:
            paper.full_text_source = "unavailable"
            return False

        try:
            pdf_bytes = await self._download_pdf(paper.pdf_url)
            if not pdf_bytes:
                paper.full_text_source = "unavailable"
                return False

            tei_xml = await self._process_fulltext(pdf_bytes, paper)
            if not tei_xml:
                paper.full_text_source = "unavailable"
                return False

            sections = self._parse_tei_sections(tei_xml)
            full_text = self._sections_to_text(sections)
            if not full_text.strip():
                paper.full_text_source = "unavailable"
                return False

            paper.full_text_sections = sections
            paper.full_text_content = full_text
            paper.full_text_source = "grobid"
            paper.full_text_flag = 1
            return True
        except Exception as e:
            logger.warning("Full-text parsing failed for '%s': %s", paper.title[:80], str(e))
            paper.full_text_source = "unavailable"
            return False

    async def _download_pdf(self, pdf_url: str) -> Optional[bytes]:
        async with httpx.AsyncClient(timeout=45, follow_redirects=True) as client:
            response = await client.get(pdf_url)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()
            content = response.content
            if "pdf" not in content_type and not content.startswith(b"%PDF"):
                logger.warning("PDF URL did not return a PDF: %s (%s)", pdf_url, content_type)
                return None
            return content

    async def _process_fulltext(self, pdf_bytes: bytes, paper: PaperObject) -> Optional[str]:
        files = {
            "input": (
                f"{paper.paper_id}.pdf",
                pdf_bytes,
                "application/pdf",
            )
        }
        data = {
            "consolidateHeader": "1",
            "consolidateCitations": "0",
            "includeRawCitations": "0",
            "includeRawAffiliations": "0",
        }
        last_error: Optional[Exception] = None
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=90) as client:
                    response = await client.post(
                        f"{self.grobid_url}/api/processFulltextDocument",
                        files=files,
                        data=data,
                    )
                    response.raise_for_status()
                    return response.text
            except Exception as e:
                last_error = e
                if attempt < 2:
                    await asyncio.sleep(5 * (attempt + 1))
        if last_error:
            raise last_error
        return None

    def _parse_tei_sections(self, tei_xml: str) -> Dict[str, str]:
        import xml.etree.ElementTree as ET

        root = ET.fromstring(tei_xml)
        ns = {"tei": "http://www.tei-c.org/ns/1.0"}
        sections: Dict[str, List[str]] = {}

        abstract_parts = [
            "".join(node.itertext()).strip()
            for node in root.findall(".//tei:profileDesc/tei:abstract", ns)
        ]
        if abstract_parts:
            sections["abstract"] = abstract_parts

        for div in root.findall(".//tei:text/tei:body//tei:div", ns):
            head = div.find("tei:head", ns)
            section_name = "".join(head.itertext()).strip().lower() if head is not None else "body"
            section_name = self._normalize_section_name(section_name)
            paragraphs = [
                " ".join("".join(paragraph.itertext()).split())
                for paragraph in div.findall(".//tei:p", ns)
            ]
            paragraphs = [p for p in paragraphs if p]
            if paragraphs:
                sections.setdefault(section_name, []).extend(paragraphs)

        return {name: "\n\n".join(parts) for name, parts in sections.items() if parts}

    def _normalize_section_name(self, section_name: str) -> str:
        if "method" in section_name or "material" in section_name:
            return "methods"
        if "result" in section_name or "finding" in section_name:
            return "results"
        if "discussion" in section_name:
            return "discussion"
        if "conclusion" in section_name:
            return "conclusion"
        if "introduction" in section_name or "background" in section_name:
            return "introduction"
        if "abstract" in section_name:
            return "abstract"
        return section_name or "body"

    def _sections_to_text(self, sections: Dict[str, str]) -> str:
        preferred_order = ["abstract", "introduction", "methods", "results", "discussion", "conclusion"]
        ordered_names = [name for name in preferred_order if name in sections]
        ordered_names.extend(name for name in sections if name not in ordered_names)
        return "\n\n".join(f"[{name.upper()}]\n{sections[name]}" for name in ordered_names)


class PaperIngestionService:
    """Main paper ingestion service implementing full pipeline"""
    
    def __init__(
        self,
        db: AsyncSession,
        semantic_scholar_api_key: Optional[str] = None,
        pubmed_api_key: Optional[str] = None,
    ):
        self.db = db
        self.arxiv = ArxivConnector()
        self.semantic_scholar = SemanticScholarConnector(semantic_scholar_api_key)
        self.pubmed = PubMedConnector(pubmed_api_key)
        self.llm_provider = get_llm_provider()
        self.embedding_service = get_embedding_service()
        self.memory_system = MemorySystemService(
            db=db,
            llm_provider=self.llm_provider,
            embedding_service=self.embedding_service,
        )
        self.belief_revision = BeliefRevisionService(
            db=db,
            llm_provider=self.llm_provider,
        )
        self.contradiction_handling = ContradictionHandlingService(
            db=db,
            llm_provider=self.llm_provider,
            embedding_service=self.embedding_service,
        )
        self.synthesis_generation = SynthesisGenerationService(
            db=db,
            llm_provider=self.llm_provider,
        )
        self.full_text_extractor = GrobidFullTextExtractor(settings.GROBID_URL)
        self.faiss_index = None
        self.faiss_mapping = {}  # Maps paper_id to FAISS index position
        
    async def ingest_papers(
        self,
        mission_id: str,
        structured_query: dict,
        config: Optional[IngestionConfig] = None,
    ) -> dict:
        """Execute full paper ingestion pipeline"""
        if config is None:
            config = IngestionConfig()
        
        batch_id = str(uuid.uuid4())
        start_time = time.time()
        
        try:
            # STAGE 1: Query expansion
            logger.info(f"[{batch_id}] Stage 1: Query expansion")
            expanded_queries, concept_clusters = await self._stage1_query_expansion(structured_query)
            
            # STAGE 2: Multi-source retrieval
            logger.info(f"[{batch_id}] Stage 2: Multi-source retrieval")
            candidates = await self._stage2_retrieval(expanded_queries, config)
            logger.info(f"[{batch_id}] Total candidates: {len(candidates)}")
            
            # STAGE 3: Deduplication & normalization
            logger.info(f"[{batch_id}] Stage 3: Deduplication & normalization")
            deduplicated = self._stage3_deduplication(candidates)
            logger.info(f"[{batch_id}] After deduplication: {len(deduplicated)}")
            
            # STAGE 4: Cheap prefiltering
            logger.info(f"[{batch_id}] Stage 4: Cheap prefiltering")
            prefiltered = await self._stage4_prefilter(deduplicated, structured_query, config)
            logger.info(f"[{batch_id}] After prefilter: {len(prefiltered)}")
            
            # STAGE 5: Full-text CEGC scoring (deterministic layers + selective LLM verification)
            logger.info(f"[{batch_id}] Stage 5: Full-text CEGC scoring")
            scored, llm_calls, llm_tokens = await self._stage5_cegc_soft_scoring(
                prefiltered, structured_query, config
            )
            logger.info(f"[{batch_id}] After CEGC soft scoring: {len(scored)}")
            
            # STAGE 6: CEGC Deep Analysis (Layer 5, selective LLM) - SKIPPED FOR PERFORMANCE
            # Layer 5 LLM verification only adds ±0.05 adjustment for edge cases
            # Benefit negligible compared to 3.3 minute cost (80 papers × 2.5 sec each)
            # Stage 5 (Layers 1-4) scores are already very accurate (0.668 avg)
            logger.info(f"[{batch_id}] Stage 6: SKIPPED (using Stage 5 CEGC scores directly)")
            llm_calls_layer5 = 0
            llm_tokens_layer5 = 0
            
            # STAGE 7: Diversity-aware selection (MMR)
            logger.info(f"[{batch_id}] Stage 7: MMR selection")
            selected = await self._stage7_mmr_selection(scored, config)
            logger.info(f"[{batch_id}] Final selected: {len(selected)}")
            
            # STAGE 8: Full-text decision
            logger.info(f"[{batch_id}] Stage 8: Full-text decision")
            selected = self._stage8_fulltext_decision(selected)
            
            # STAGE 9: Database storage
            logger.info(f"[{batch_id}] Stage 9: Database storage")
            await self._stage9_database_storage(mission_id, batch_id, selected, structured_query)
            
            # STAGE 10: FAISS indexing
            logger.info(f"[{batch_id}] Stage 10: FAISS indexing")
            await self._stage10_faiss_indexing(mission_id, selected)
            
            # STAGE 11: Ingestion event recording
            logger.info(f"[{batch_id}] Stage 11: Recording ingestion event")
            processing_time = time.time() - start_time
            await self._stage11_ingestion_event(
                mission_id, batch_id, len(candidates), len(deduplicated),
                len(prefiltered), len(scored), len(selected),
                scored, config, llm_calls, llm_tokens, processing_time
            )
            
            # STAGE 12: CLAIM EXTRACTION (NEW)
            # Extract claims from all selected papers asynchronously
            logger.info(f"[{batch_id}] Stage 12: Claim extraction starting for {len(selected)} papers")
            logger.info(f"🎯 [CLAIM EXTRACTION] Starting extraction for mission {mission_id}...")
            
            try:
                # Fetch mission data for context
                mission_stmt = select(Mission).where(Mission.id == mission_id)
                mission_result = await self.db.execute(mission_stmt)
                mission = mission_result.scalar_one_or_none()
                
                if mission:
                    claim_service = ClaimExtractionService(
                        self.db,
                        llm_provider=self.llm_provider,
                        embedding_service=self.embedding_service,
                    )
                    mission_question = mission.normalized_query or "research claim"
                    mission_domain = mission.intent_type.value if mission.intent_type else "general"
                    
                    # Extract claims for each selected paper in parallel batches
                    total_claims_extracted = 0
                    extracted_claim_ids: List[str] = []
                    batch_size = 1  # AsyncSession is not safe for concurrent extraction writes
                    
                    for batch_start in range(0, len(selected), batch_size):
                        batch_end = min(batch_start + batch_size, len(selected))
                        paper_batch = selected[batch_start:batch_end]
                        
                        # Get paper IDs from database
                        papers_to_extract = []
                        seen_db_paper_ids = set()
                        for paper_obj in paper_batch:
                            paper_stmt = select(ResearchPaper).where(
                                ResearchPaper.mission_id == mission_id,
                                ResearchPaper.paper_id == paper_obj.paper_id
                            )
                            paper_result = await self.db.execute(paper_stmt)
                            db_paper = paper_result.scalar_one_or_none()
                            if db_paper and db_paper.id not in seen_db_paper_ids:
                                papers_to_extract.append(db_paper)
                                seen_db_paper_ids.add(db_paper.id)
                        
                        # Extract claims in parallel for this batch
                        if papers_to_extract:
                            paper_ids_to_extract = papers_to_extract
                            logger.info(f"  📄 Processing paper batch {batch_start // batch_size + 1}: {len(paper_ids_to_extract)} papers...")
                            extraction_tasks = [
                                claim_service.extract_claims_from_paper(
                                    paper_id=db_paper.id,
                                    mission_id=mission_id,
                                    mission_question=mission_question,
                                    mission_domain=mission_domain,
                                    pdf_url=db_paper.pdf_url,
                                    abstract=db_paper.abstract or "",
                                )
                                for db_paper in papers_to_extract
                            ]
                            
                            extraction_results = await asyncio.gather(*extraction_tasks, return_exceptions=True)
                            
                            # Count extracted claims
                            for result in extraction_results:
                                if isinstance(result, dict) and result.get('success'):
                                    claims_count = result.get('claims_extracted', 0)
                                    total_claims_extracted += claims_count
                                    extracted_claim_ids.extend(
                                        [
                                            str(claim.get("id"))
                                            for claim in (result.get("claims") or [])
                                            if claim.get("id")
                                        ]
                                    )
                                    if claims_count > 0:
                                        logger.info(f"    ✅ Extracted {claims_count} claims from paper")
                                elif isinstance(result, Exception):
                                    logger.warning(f"Exception during claim extraction: {str(result)}")
                            
                            # Commit after each batch to avoid session conflicts
                            try:
                                await self.db.commit()
                                logger.debug(f"[{batch_id}] Batch {batch_start // batch_size + 1}: Claims committed")
                            except Exception as batch_commit_err:
                                logger.warning(f"[{batch_id}] Batch commit failed: {str(batch_commit_err)}")
                                try:
                                    await self.db.rollback()
                                except:
                                    pass
                    
                    logger.info(f"🎯 [CLAIM EXTRACTION] ✅ Total {total_claims_extracted} claims extracted and stored in database")
                    logger.info(f"[{batch_id}] Stage 12: Claim extraction completed - {total_claims_extracted} total claims extracted")
                    
                    # Commit all accumulated claims to database
                    try:
                        await self.db.commit()
                        logger.info(f"[{batch_id}] Stage 12: Claims committed to database")
                        try:
                            contradiction_result = await self.contradiction_handling.run_cycle(
                                mission_id=mission_id,
                                new_claim_ids=extracted_claim_ids,
                                actor="paper_ingestion",
                                evaluate_all=not bool(extracted_claim_ids),
                            )
                            await self.db.commit()
                            logger.info(
                                f"[{batch_id}] Stage 12: Contradiction handling completed - "
                                f"{contradiction_result.get('confirmed_contradictions', 0)} confirmed"
                            )
                        except Exception as contradiction_exc:
                            logger.warning(f"[{batch_id}] Stage 12: Contradiction handling failed: {str(contradiction_exc)}")
                            await self.db.rollback()
                        try:
                            revision_result = await self.belief_revision.run_revision_cycle(
                                mission_id=mission_id,
                                actor="paper_ingestion",
                            )
                            await self.db.commit()
                            logger.info(
                                f"[{batch_id}] Stage 12: Belief revision completed - "
                                f"{revision_result.get('revision_type')} cycle {revision_result.get('cycle_number')}"
                            )
                        except Exception as revision_exc:
                            logger.warning(f"[{batch_id}] Stage 12: Belief revision failed: {str(revision_exc)}")
                            await self.db.rollback()
                            revision_result = {"success": False}

                        try:
                            if revision_result.get("success") is False:
                                raise RuntimeError("Belief revision did not complete successfully")
                            synthesis_trigger = SynthesisGenerationService.trigger_from_revision(
                                revision_result.get("revision_type"),
                                revision_result.get("cycle_number"),
                            )
                            if synthesis_trigger:
                                try:
                                    await self.synthesis_generation.generate_synthesis(
                                        mission_id=mission_id,
                                        trigger=synthesis_trigger,
                                        actor="paper_ingestion",
                                    )
                                    await self.db.commit()
                                    logger.info(
                                        f"[{batch_id}] Stage 12: Synthesis generated via {synthesis_trigger.value}"
                                    )
                                except Exception as synthesis_exc:
                                    logger.warning(
                                        f"[{batch_id}] Stage 12: Synthesis generation failed: {str(synthesis_exc)}"
                                    )
                                    await self.db.rollback()
                            await self.memory_system.finalize_cycle(
                                mission_id=mission_id,
                                trigger=synthesis_trigger or SynthesisTrigger.NEW_PAPER,
                                actor="paper_ingestion",
                            )
                            await self.db.commit()
                            logger.info(f"[{batch_id}] Stage 12: Memory cycle finalized")
                        except Exception as memory_exc:
                            logger.warning(f"[{batch_id}] Stage 12: Memory finalization failed: {str(memory_exc)}")
                            await self.db.rollback()
                    except Exception as commit_err:
                        logger.error(f"[{batch_id}] Stage 12: Failed to commit claims: {str(commit_err)}")
                        await self.db.rollback()
                else:
                    logger.warning(f"[{batch_id}] Stage 12: Mission not found")
                    logger.warning(f"[CLAIM EXTRACTION] Mission not found")
                    
            except Exception as e:
                logger.error(f"[{batch_id}] Stage 12: Claim extraction failed: {str(e)}", exc_info=True)
                logger.error(f"[CLAIM EXTRACTION] Error during extraction: {str(e)}")
            
            return {
                'success': True,
                'batch_id': batch_id,
                'total_retrieved': len(candidates),
                'after_dedup': len(deduplicated),
                'after_prefilter': len(prefiltered),
                'after_rerank': len(scored),
                'final_selected': len(selected),
                'processing_time_seconds': processing_time,
                'selected_papers': [p.to_dict() for p in selected[:10]],  # First 10
            }
            
        except Exception as e:
            logger.error(f"[{batch_id}] Ingestion failed: {str(e)}", exc_info=True)
            processing_time = time.time() - start_time
            await self._stage11_ingestion_event(
                mission_id, batch_id, 0, 0, 0, 0, 0, [], config, 0, 0, processing_time,
                status='failed', error_message=str(e)
            )
            return {
                'success': False,
                'batch_id': batch_id,
                'error': str(e),
                'processing_time_seconds': processing_time,
            }
    
    async def _stage1_query_expansion(self, structured_query: dict) -> tuple:
        """STAGE 1: LLM-based query expansion"""
        query_text = structured_query.get('normalized_query', '')
        concepts = structured_query.get('key_concepts', [])
        
        prompt = f"""Expand this research query into 5-8 semantically diverse search variants.

Query: {query_text}
Key concepts: {', '.join(concepts)}

Return JSON only:
{{
    "variants": ["variant1", "variant2", ...],
    "concept_clusters": {{
        "cluster_name": ["concept1", "concept2", ...]
    }}
}}"""
        
        try:
            response = await self.llm_provider.generate_async([
                {'role': 'system', 'content': 'You are a research query expansion expert.'},
                {'role': 'user', 'content': prompt}
            ], max_tokens=1000)
            
            content = response.get('content', '')
            # Parse JSON
            import re
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                variants = data.get('variants', [query_text])
                clusters = data.get('concept_clusters', {})
                return variants, clusters
        except Exception as e:
            logger.warning(f"Query expansion failed, using base query: {str(e)}")
        
        return [query_text], {}
    
    async def _stage2_retrieval(self, expanded_queries: list, config: IngestionConfig) -> List[PaperObject]:
        """STAGE 2: Multi-source parallel retrieval with rate limiting.
        
        Now uses concurrent requests with per-source rate limiting (retry logic
        handles 429s automatically with exponential backoff).
        """
        candidates = []
        per_source = config.max_candidates // len(config.sources)
        
        # Process queries - run each query's sources in parallel
        for query in expanded_queries[:3]:  # Use top 3 expanded queries
            tasks = []
            
            if 'arxiv' in config.sources:
                tasks.append(('arxiv', self.arxiv.search(query, per_source)))
            
            if 'semantic_scholar' in config.sources:
                # Now run in parallel with automatic retry on 429
                tasks.append(('semantic_scholar', self.semantic_scholar.search(query, per_source)))
            
            if 'pubmed' in config.sources:
                tasks.append(('pubmed', self.pubmed.search(query, per_source)))
            
            # Execute all source queries in parallel
            if tasks:
                results = await asyncio.gather(*[t[1] for t in tasks], return_exceptions=True)
                for (source_name, _), result in zip(tasks, results):
                    if isinstance(result, Exception):
                        logger.warning(f"{source_name} retrieval for query '{query}': {str(result)}")
                        continue
                    candidates.extend(result)
        
        return candidates
    
    def _stage3_deduplication(self, papers: List[PaperObject]) -> List[PaperObject]:
        """STAGE 3: Deduplication by DOI and title similarity"""
        seen_dois = set()
        seen_titles = set()
        deduplicated = []
        
        for paper in papers:
            if paper.doi and paper.doi in seen_dois:
                continue
            if paper.title.lower() in seen_titles:
                continue
            
            if paper.doi:
                seen_dois.add(paper.doi)
            seen_titles.add(paper.title.lower())
            deduplicated.append(paper)
        
        return deduplicated
    
    async def _stage4_prefilter(
        self,
        papers: List[PaperObject],
        structured_query: dict,
        config: IngestionConfig
    ) -> List[PaperObject]:
        """STAGE 4: Prefiltering using embedding similarity + keywords"""
        # Filter by abstract length
        papers = [p for p in papers if p.abstract and len(p.abstract) >= config.min_abstract_length]
        
        if not papers:
            return []
        
        # Get query embedding
        query_text = structured_query.get('normalized_query', '')
        query_embedding = await self.embedding_service.embed_text(query_text, input_type="query")
        
        if not query_embedding:
            logger.warning("Failed to get query embedding, falling back to keyword filtering")
            # Fallback to keyword-based filtering
            query_concepts = set(c.lower() for c in structured_query.get('key_concepts', []))
            scored_papers = []
            
            for paper in papers:
                abstract_lower = paper.abstract.lower()
                title_lower = paper.title.lower()
                
                concept_matches = sum(1 for concept in query_concepts if concept in abstract_lower or concept in title_lower)
                keyword_score = concept_matches / len(query_concepts) if query_concepts else 0.5
                
                if keyword_score >= 0.3 or len(query_concepts) == 0:
                    scored_papers.append((paper, keyword_score, None))
            
            scored_papers.sort(key=lambda x: x[1], reverse=True)
            result = [p[0] for p in scored_papers[:config.prefilter_k]]
            return result
        
        # Get paper embeddings and compute similarities
        abstracts = [p.abstract for p in papers]
        paper_embeddings = await self.embedding_service.embed_batch(abstracts, input_type="passage")
        
        scored_papers = []
        for paper, embedding in zip(papers, paper_embeddings):
            if embedding:
                similarity = EmbeddingService.cosine_similarity(query_embedding, embedding)
                paper.embedding = embedding
                paper.embedding_similarity = similarity
                scored_papers.append((paper, similarity))
            else:
                # Fallback to keyword scoring
                query_concepts = set(c.lower() for c in structured_query.get('key_concepts', []))
                abstract_lower = paper.abstract.lower()
                title_lower = paper.title.lower()
                
                concept_matches = sum(1 for concept in query_concepts if concept in abstract_lower or concept in title_lower)
                keyword_score = concept_matches / len(query_concepts) if query_concepts else 0.3
                scored_papers.append((paper, keyword_score))
        
        # Sort by similarity and take top prefilter_k
        scored_papers.sort(key=lambda x: x[1], reverse=True)
        logger.info(f"Stage 4: Filtered {len(papers)} → {min(config.prefilter_k, len(scored_papers))} papers by embedding similarity")
        return [p[0] for p in scored_papers[:config.prefilter_k]]
    
    async def _stage5_cegc_soft_scoring(
        self,
        papers: List[PaperObject],
        structured_query: dict,
        config: IngestionConfig
    ) -> tuple:
        """STAGE 5: CEGC Soft Scoring - Full 5-Layer Implementation
        
        Implements Hyper-Optimized CEGC 5-layer approach:
        - Layer 1 (25%): PICO Soft Matching
        - Layer 2 (30%): Evidence Strength
        - Layer 3 (20%): Mechanism Fingerprinting
        - Layer 4 (15%): Assumption Alignment
        - Layer 5 (10%): LLM Verification (selective for ambiguous papers)
        
        Returns: (papers_with_scores, llm_calls, llm_tokens)
        Cost: ~$0.01 for Layers 1-4 (free), ~$0.40 for Layer 5 selective LLM
        Time: ~2 seconds for 200 papers
        """
        from app.services.cegc_scoring import CEGCScoringService
        
        batch_id = getattr(config, 'ingestion_batch_id', 'unknown')
        
        # Initialize CEGC scoring service
        cegc_service = CEGCScoringService(
            llm_provider=self.llm_provider,
            embedding_service=self.embedding_service,
        )
        
        logger.info(f"[{batch_id}] Stage 5: Parsing full PDFs for {len(papers)} papers before CEGC scoring")
        papers = await self._enrich_with_full_text(papers)
        parsed_count = sum(1 for paper in papers if paper.full_text_source == "grobid")
        logger.info(
            f"[{batch_id}] Stage 5: Full-text available for {parsed_count}/{len(papers)} papers; "
            "remaining papers will use title + abstract fallback"
        )
        
        logger.info(f"[{batch_id}] Stage 5: CEGC scoring {len(papers)} papers through 5-layer pipeline")
        
        # Score papers through all 5 layers
        scored_papers, llm_calls, llm_tokens = await cegc_service.score_papers(
            papers=papers,
            structured_query=structured_query,
            use_llm=True,  # Enable Layer 5 LLM verification for ambiguous papers
        )
        
        # Sort by final score (descending)
        scored_papers.sort(key=lambda p: p.final_score, reverse=True)
        
        logger.info(f"[{batch_id}] Stage 5 CEGC: Complete | "
                   f"Papers: {len(scored_papers)} | "
                   f"LLM Calls: {llm_calls} | "
                   f"Tokens: {llm_tokens} | "
                   f"Top Score: {(scored_papers[0].final_score if scored_papers else 0):.3f}")
        
        # Log sample scores
        for i, paper in enumerate(scored_papers[:3]):
            logger.debug(f"[{batch_id}] Score {i+1}: {paper.final_score:.3f} - "
                        f"PICO:{paper.pico_match_score:.2f} "
                        f"Evidence:{paper.evidence_strength_score:.2f} "
                        f"Mechanism:{paper.mechanism_agreement_score:.2f} "
                        f"Assumption:{paper.assumption_alignment_score:.2f} "
                        f"'{paper.title[:40]}...'")
        
        return scored_papers, llm_calls, llm_tokens

    async def _enrich_with_full_text(self, papers: List[PaperObject]) -> List[PaperObject]:
        """Parse each available PDF with GROBID so CEGC can score full-paper text."""
        semaphore = asyncio.Semaphore(3)

        async def parse_one(paper: PaperObject) -> PaperObject:
            if not paper.pdf_url:
                paper.full_text_source = "abstract_fallback"
                return paper
            async with semaphore:
                parsed = await self.full_text_extractor.parse_pdf_url(paper)
                if not parsed:
                    paper.full_text_source = "abstract_fallback"
                return paper

        return await asyncio.gather(*(parse_one(paper) for paper in papers))
    
    async def _stage6_cegc_deep_analysis(
        self,
        papers: List[PaperObject],
        structured_query: dict
    ) -> Tuple[List[PaperObject], int, int]:
        """STAGE 6: CEGC Deep Analysis - SKIPPED (handled by Stage 5)
        
        Stage 5 now implements the full 5-layer CEGC pipeline including:
        - Layers 1-4: Deterministic scoring (PICO, Evidence, Mechanism, Assumption)
        - Layer 5: Selective LLM verification for ambiguous papers (0.50-0.80)
        
        Stage 6 is retained for backward compatibility but is now a pass-through.
        
        Returns: (papers, 0, 0)
        """
        batch_id = getattr(structured_query, 'batch_id', 'unknown') if hasattr(structured_query, 'batch_id') else 'unknown'
        
        logger.info(f"Stage 6: Skipped (CEGC fully implemented in Stage 5)")
        
        return papers, 0, 0
    
    async def _stage7_mmr_selection(self, papers: List[PaperObject], config: IngestionConfig) -> List[PaperObject]:
        """STAGE 7: Maximal Marginal Relevance selection for diversity using embeddings"""
        if len(papers) <= config.final_k:
            return papers
        
        # MMR: Balance between relevance and diversity using embeddings
        papers_sorted = sorted(papers, key=lambda p: p.final_score, reverse=True)
        selected = []
        
        # Ensure all papers have embeddings
        if papers_sorted[0].embedding is None:
            logger.warning("Papers missing embeddings - using title-based diversity fallback")
            # Fallback to title-based diversity
            for paper in papers_sorted:
                if len(selected) >= config.final_k:
                    break
                
                is_diverse = True
                for selected_paper in selected:
                    title_similarity = self._compute_title_similarity(paper.title, selected_paper.title)
                    if title_similarity > 0.9:
                        is_diverse = False
                        break
                
                if is_diverse:
                    selected.append(paper)
            
            return selected
        
        # Start with highest-score paper
        selected.append(papers_sorted[0])
        
        # Greedily select papers balancing relevance and diversity
        for candidate in papers_sorted[1:]:
            if len(selected) >= config.final_k:
                break
            
            if candidate.embedding is None:
                continue
            
            # Compute MMR score
            relevance = candidate.final_score
            
            # Diversity: minimum distance to any selected paper
            diversity = 1.0
            for selected_paper in selected:
                if selected_paper.embedding:
                    distance = EmbeddingService.embedding_distance(
                        candidate.embedding,
                        selected_paper.embedding
                    )
                    diversity = min(diversity, distance)
            
            # MMR score: balance relevance and diversity
            mmr_score = config.mmr_lambda * relevance + (1 - config.mmr_lambda) * diversity
            
            # Add to selected if diverse enough or if we need more papers
            if diversity > 0.3 or len(selected) < config.final_k * 0.8:
                selected.append(candidate)
        
        logger.info(f"Stage 7: Selected {len(selected)} diverse papers using MMR")
        return selected
    
    def _compute_title_similarity(self, title1: str, title2: str) -> float:
        """Simple title similarity based on common words"""
        words1 = set(title1.lower().split())
        words2 = set(title2.lower().split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        return intersection / union if union > 0 else 0.0

    def _paper_storage_key(self, paper: PaperObject | ResearchPaper) -> str:
        if getattr(paper, "paper_id", None):
            return f"id:{paper.paper_id}"
        title = (getattr(paper, "title", "") or "").strip().lower()
        source = getattr(getattr(paper, "source", None), "value", getattr(paper, "source", "unknown"))
        return f"title:{source}:{title}"
    
    def _stage8_fulltext_decision(self, papers: List[PaperObject]) -> List[PaperObject]:
        """STAGE 8: Decide if full-text parsing needed"""
        for paper in papers:
            # Mark for full-text if abstract is very short
            if len(paper.abstract) < 200 and paper.final_score > 0.7:
                paper.full_text_flag = True
        
        return papers
    
    async def _stage9_database_storage(
        self,
        mission_id: str,
        batch_id: str,
        papers: List[PaperObject],
        structured_query: dict
    ):
        """STAGE 9: Store papers in PostgreSQL with dedupe/update semantics."""
        existing_rows = (
            await self.db.execute(
                select(ResearchPaper).where(ResearchPaper.mission_id == mission_id)
            )
        ).scalars().all()

        existing_by_key = {}
        duplicate_rows = []
        for row in existing_rows:
            key = self._paper_storage_key(row)
            if key in existing_by_key:
                duplicate_rows.append(row)
            else:
                existing_by_key[key] = row

        for duplicate in duplicate_rows:
            await self.db.delete(duplicate)

        seen_batch_keys = set()
        stored_count = 0

        for rank, paper in enumerate(papers, 1):
            key = self._paper_storage_key(paper)
            if key in seen_batch_keys:
                logger.info("Skipping duplicate paper in ingestion batch: %s", paper.title[:120])
                continue
            seen_batch_keys.add(key)

            db_paper = existing_by_key.get(key)
            if db_paper is None:
                db_paper = ResearchPaper(
                    mission_id=mission_id,
                    paper_id=paper.paper_id,
                    source=paper.source,
                    final_score=paper.final_score,
                )
                self.db.add(db_paper)
                existing_by_key[key] = db_paper

            db_paper.doi = paper.doi
            db_paper.title = paper.title
            db_paper.authors = paper.authors
            db_paper.abstract = paper.abstract
            db_paper.year = paper.year
            db_paper.source = paper.source
            db_paper.arxiv_url = paper.url if paper.source == PaperSource.ARXIV else None
            db_paper.semantic_scholar_url = paper.url if paper.source == PaperSource.SEMANTIC_SCHOLAR else None
            db_paper.pubmed_url = paper.url if paper.source == PaperSource.PUBMED else None
            db_paper.pdf_url = paper.pdf_url
            db_paper.final_score = paper.final_score
            db_paper.pico_match_score = paper.pico_match_score
            db_paper.evidence_strength_score = paper.evidence_strength_score
            db_paper.mechanism_agreement_score = paper.mechanism_agreement_score
            db_paper.assumption_alignment_score = paper.assumption_alignment_score
            db_paper.llm_verification_score = paper.llm_verification_score
            db_paper.score_breakdown = paper.score_breakdown
            db_paper.reasoning_graph = paper.reasoning_graph
            db_paper.mechanism_description = paper.mechanism_description
            db_paper.embedding = paper.embedding
            db_paper.selected = 1
            db_paper.full_text_flag = getattr(paper, 'full_text_flag', 0)
            db_paper.full_text_content = paper.full_text_content
            db_paper.ingestion_batch_id = batch_id
            db_paper.rank_in_ingestion = rank
            db_paper.keywords = paper.keywords
            db_paper.citations_count = paper.citations_count
            db_paper.influence_score = paper.influence_score
            await self.db.flush()
            for attempt in range(2):
                try:
                    await self.memory_system.record_paper_record(
                        paper=db_paper,
                        actor="paper_ingestion",
                        status=RawPaperStatus.INGESTED,
                    )
                    break
                except Exception as memory_exc:
                    logger.warning(
                        "Memory paper record write failed for %s (attempt %s/2): %s | title=%s",
                        db_paper.id,
                        attempt + 1,
                        memory_exc,
                        db_paper.title[:160],
                    )
            stored_count += 1

        await self.db.commit()
        logger.info(f"Stored {stored_count} unique papers (with CEGC scores) for mission {mission_id}")
    
    async def _stage10_faiss_indexing(self, mission_id: str, papers: List[PaperObject]):
        """STAGE 10: Create FAISS index for semantic search"""
        if not faiss:
            logger.warning("FAISS not installed - skipping indexing")
            return
        
        if not papers or not papers[0].embedding:
            logger.warning("No papers or embeddings available for FAISS indexing")
            return
        
        try:
            # Collect all embeddings
            embeddings = []
            paper_mapping = {}  # Maps FAISS index to paper_id
            
            for idx, paper in enumerate(papers):
                if paper.embedding:
                    embeddings.append(paper.embedding)
                    paper_mapping[idx] = str(paper.paper_id)
            
            if not embeddings:
                logger.warning("No embeddings to index")
                return
            
            # Create FAISS index
            embeddings_array = np.array(embeddings).astype('float32')
            dimension = embeddings_array.shape[1]
            
            # Use L2 distance index (Euclidean)
            index = faiss.IndexFlatL2(dimension)
            index.add(embeddings_array)
            
            # Store index and mapping
            index_path = f"storage/faiss_indices/{mission_id}.index"
            mapping_path = f"storage/faiss_indices/{mission_id}_mapping.json"
            
            # Create directory if needed
            import os
            os.makedirs(os.path.dirname(index_path), exist_ok=True)
            
            # Save FAISS index
            faiss.write_index(index, index_path)
            
            # Save mapping
            with open(mapping_path, 'w') as f:
                json.dump(paper_mapping, f)
            
            self.faiss_index = index
            self.faiss_mapping = paper_mapping
            
            logger.info(f"FAISS index created for mission {mission_id} with {len(embeddings)} vectors")
            
        except Exception as e:
            logger.error(f"FAISS indexing failed: {str(e)}")
    
    async def _stage11_ingestion_event(
        self,
        mission_id: str,
        batch_id: str,
        total_retrieved: int,
        after_dedup: int,
        after_prefilter: int,
        after_rerank: int,
        final_selected: int,
        reranked_papers: List[PaperObject],
        config: IngestionConfig,
        llm_calls: int,
        llm_tokens: int,
        processing_time: float,
        status: str = 'success',
        error_message: Optional[str] = None,
    ):
        """STAGE 11: Record ingestion event"""
        # Calculate average scores - filter out None values
        relevance_scores = [getattr(p, 'relevance_score', 0.5) or 0.5 for p in reranked_papers if getattr(p, 'relevance_score', 0.5) is not None]
        usefulness_scores = [getattr(p, 'usefulness_score', 0.5) or 0.5 for p in reranked_papers if getattr(p, 'usefulness_score', 0.5) is not None]
        final_scores = [p.final_score for p in reranked_papers if p.final_score is not None]
        
        avg_relevance = np.mean(relevance_scores) if relevance_scores else None
        avg_usefulness = np.mean(usefulness_scores) if usefulness_scores else None
        avg_final = np.mean(final_scores) if final_scores else None
        
        stmt = insert(IngestionEvent).values(
            mission_id=mission_id,
            batch_id=batch_id,
            session_number=1,  # TODO: track session number
            total_retrieved=total_retrieved,
            after_dedup=after_dedup,
            after_prefilter=after_prefilter,
            after_rerank=after_rerank,
            final_selected=final_selected,
            avg_relevance_score=avg_relevance,
            avg_usefulness_score=avg_usefulness,
            avg_final_score=avg_final,
            max_candidates=config.max_candidates,
            prefilter_k=config.prefilter_k,
            final_k=config.final_k,
            relevance_threshold=config.relevance_threshold,
            sources_used=config.sources,
            total_llm_calls=llm_calls,
            total_llm_tokens=llm_tokens,
            processing_time_seconds=processing_time,
            status=status,
            error_message=error_message,
            completed_at=datetime.utcnow(),
        )
        
        await self.db.execute(stmt)
        await self.db.commit()
        logger.info(f"Recorded ingestion event for batch {batch_id}")
