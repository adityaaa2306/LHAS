# Module 2: Implementation Status & Next Steps

## Current Implementation Status

### ✅ COMPLETED (Ready for Testing)

#### Database Models (`backend/app/models/paper.py`)
- [x] ResearchPaper table (40+ columns)
  - [x] Core fields: id, mission_id, paper_id, doi, title, authors, abstract, year
  - [x] Source tracking: source enum, arxiv_url, semantic_scholar_url, pubmed_url, pdf_url
  - [x] Scoring fields: final_score, relevance_score, usefulness_score, embedding_similarity, keyword_overlap
  - [x] PICO matching: pico_population_match, pico_intervention_match, pico_comparison_match, pico_outcome_match
  - [x] Metadata: keywords (JSON), citations_count, influence_score
  - [x] Tracking: full_text_flag, full_text_content, ingestion_batch_id, rank_in_ingestion
  - [x] Timestamps: retrieved_at, processed_at
  - [x] Selection flag: selected (1=chosen, 0=rejected)

- [x] IngestionEvent table (17 columns)
  - [x] Batch tracking: id, mission_id, batch_id
  - [x] Pipeline statistics: total_retrieved, after_dedup, after_prefilter, after_rerank, final_selected
  - [x] Quality scores: avg_relevance_score, avg_usefulness_score, avg_final_score
  - [x] Configuration: sources_used (JSON list)
  - [x] Cost tracking: total_llm_calls, total_llm_tokens
  - [x] Performance: processing_time_seconds
  - [x] Status: status (success/partial/failed), error_message
  - [x] Timestamps: created_at, updated_at

- [x] PaperSource enum (3 values): arxiv, semantic_scholar, pubmed

#### Paper Ingestion Service (`backend/app/services/paper_ingestion.py`)
- [x] PaperObject dataclass (Normalized paper representation)
  - [x] All fields properly typed
  - [x] to_dict() method for serialization

- [x] IngestionConfig dataclass
  - [x] max_candidates (default: 200)
  - [x] prefilter_k (default: 60)
  - [x] final_k (default: 20)
  - [x] relevance_threshold (default: 0.5)
  - [x] sources list (default: all 3)
  - [x] mmr_lambda (default: 0.6)
  - [x] min_abstract_length (default: 100)

- [x] ArxivConnector class
  - [x] search() async method
  - [x] XML parsing of API responses
  - [x] Rate limiting handling
  - [x] Abstract extraction from PDF fetching
  - [x] Error handling for failed connections

- [x] SemanticScholarConnector class
  - [x] search() async method
  - [x] REST API integration
  - [x] API key optional support
  - [x] Citation count and influence score extraction
  - [x] Error handling

- [x] PubMedConnector class
  - [x] Two-step search/fetch pattern
  - [x] PMC ID extraction
  - [x] Author list parsing
  - [x] Error handling

- [x] PaperIngestionService class with all 11 stages:
  - [x] Stage 1: _stage1_query_expansion() - LLM query variants
  - [x] Stage 2: _stage2_retrieval() - Multi-source async fetching
  - [x] Stage 3: _stage3_deduplication() - DOI + title matching
  - [x] Stage 4: _stage4_prefilter() - Keyword + embedding scoring
  - [x] Stage 5: _stage5_llm_reranking() - Batch LLM evaluation (5-10 per call)
  - [x] Stage 6: _stage6_final_scoring() - Weighted combination
  - [x] Stage 7: _stage7_mmr_selection() - Diversity-aware selection
  - [x] Stage 8: _stage8_fulltext_decision() - Mark for GROBID
  - [x] Stage 9: _stage9_database_storage() - Insert into PostgreSQL
  - [x] Stage 10: _stage10_faiss_indexing() - Placeholder implementation
  - [x] Stage 11: _stage11_ingestion_event() - Record event with metrics

- [x] Main ingest_papers() orchestrator method

#### API Endpoints (`backend/app/api/papers.py`)
- [x] POST /api/papers/ingest
  - [x] IngestionConfigRequest body model
  - [x] Full pipeline orchestration
  - [x] Response with summary and sample papers

- [x] GET /api/papers/mission/{mission_id}
  - [x] Pagination support
  - [x] Sorting by final_score (DESC)
  - [x] Database query with proper filtering

- [x] GET /api/paper/{paper_id}
  - [x] Full paper details with all fields
  - [x] PICO match information

- [x] GET /api/papers/mission/{mission_id}/events
  - [x] Ingestion history retrieval
  - [x] Statistics aggregation

- [x] GET /api/papers/batch/{batch_id}/papers
  - [x] Batch-specific paper retrieval

- [x] GET /api/papers/stats/source-distribution
  - [x] Distribution analysis by source

#### Integration
- [x] Updated models/__init__.py to export ResearchPaper, IngestionEvent, PaperSource
- [x] Updated database.py to import and register paper models
- [x] Updated api/__init__.py to include papers_router
- [x] Updated requirements.txt with httpx and numpy dependencies
- [x] All imports properly configured

---

## 🔧 NEXT IMMEDIATE STEPS (TO RUN NOW)

### 1. Rebuild Backend (Priority: CRITICAL)
```powershell
cd c:\Users\adity\OneDrive\Desktop\final
docker compose up -d --build backend
```

**Verify**:
```powershell
docker logs lhas-backend --tail 20 | Select-String "Database initialized"
```

### 2. Verify Tables Created
```powershell
docker exec lhas-postgres psql -U postgres -d LHAS -c "\dt"
```

Expected output: 6 tables (including research_papers, ingestion_events)

### 3. Test Full Pipeline
Follow the [TESTING_GUIDE.md](TESTING_GUIDE.md) to run tests 1-7 in order

### 4. Validate Performance
Check that:
- Processing time < 60 seconds
- LLM calls < 15
- Papers retrieved from all sources
- Final selection 15-25 papers

---

## 🟡 TODO: Core Functionality (Not Yet Implemented)

### 1. FAISS Vector Indexing (Stage 10)
**Status**: Placeholder only
**Priority**: HIGH
**Complexity**: Medium

```python
# What needs to be done:
def _stage10_faiss_indexing(self, papers, batch_id):
    """
    Implement actual FAISS indexing instead of placeholder.
    
    Steps:
    1. Get embedding model (e.g., from LLM provider)
    2. For each paper, compute embedding of abstract
    3. Create FAISS L2 index
    4. Save index and mapping to storage
    5. Link papers table to FAISS index
    """
    # Current: Just passes papers through (no indexing)
    # Target: Full embedding computation and index storage
```

**Deliverables**:
- [ ] Embedding API integration
- [ ] Batch embedding computation
- [ ] FAISS index creation and storage
- [ ] Index metadata (mapping from paper_id to vector index)
- [ ] Vector similarity search endpoint

**Estimated Effort**: 3-4 hours

### 2. Full-Text Parsing with GROBID (Stage 8 Extension)
**Status**: Not started
**Priority**: MEDIUM (can be added later)
**Complexity**: High

```python
# What needs to be done:
async def parse_full_text_with_grobid(self, paper_id, pdf_url):
    """
    Use GROBID to extract structured text from PDF.
    
    Steps:
    1. Download PDF from pdf_url
    2. Send to GROBID API
    3. Parse structured output (TEI XML)
    4. Extract:
       - Main text with section headings
       - Tables
       - Figures and captions
       - Bibliography
    5. Store full_text_content in research_papers table
    """
    pass
```

**Deliverables**:
- [ ] GROBID container setup (Docker service)
- [ ] PDF download with caching
- [ ] GROBID API integration (async)
- [ ] TEI XML parsing
- [ ] Database storage of parsed content
- [ ] Batch processing for multiple papers

**Estimated Effort**: 6-8 hours

### 3. Semantic Search Endpoint (Using FAISS)
**Status**: Not started
**Priority**: MEDIUM
**Complexity**: Low (depends on FAISS completion)

```python
# New endpoint:
@papers_router.post("/api/papers/search/semantic")
async def semantic_search(
    mission_id: str,
    query: str,
    top_k: int = 10
):
    """
    Search papers using semantic similarity.
    
    Steps:
    1. Get embedding of query
    2. Load FAISS index for mission
    3. Find top_k nearest neighbors
    4. Return papers with distances
    """
    pass
```

---

## 🟠 TODO: Enhancements & Optimizations

### API Key Management
**Priority**: MEDIUM
**Complexity**: Low
- [ ] Add Semantic Scholar API key configuration
- [ ] Add PubMed API key configuration
- [ ] Store securely in environment variables or secrets manager

### Query Filtering
**Priority**: MEDIUM
**Complexity**: Low
- [ ] Add date range filtering: GET /api/papers/mission/{id}?min_year=2020&max_year=2025
- [ ] Add source filtering: GET /api/papers/mission/{id}?sources=arxiv,semantic_scholar
- [ ] Add score range filtering: GET /api/papers/mission/{id}?min_score=0.7&max_score=1.0

### Study Type Filtering
**Priority**: LOW
**Complexity**: High
- [ ] Add study_type field to ResearchPaper (RCT, observational, meta-analysis, etc.)
- [ ] Implement study type detection in reranking stage
- [ ] Add filter: GET /api/papers/mission/{id}?study_types=RCT,systematic_review

### Rate Limiting Improvements
**Priority**: MEDIUM
**Complexity**: Medium
- [ ] Implement token bucket for arXiv API
- [ ] Implement backoff strategy for Semantic Scholar
- [ ] Add retry logic with exponential backoff

### Performance Optimization
**Priority**: MEDIUM
**Complexity**: Medium
- [ ] Cache embedding computations
- [ ] Pool LLM API connections
- [ ] Parallelize database inserts

---

## 🔴 TODO: Production Readiness

### Error Handling & Validation
- [ ] Comprehensive error handling for all API endpoints
- [ ] Validation of ingestion config parameters
- [ ] Graceful degradation if sources unavailable
- [ ] Rollback on partial failures

### Monitoring & Logging
- [ ] Structured logging for all pipeline stages
- [ ] Performance metrics collection
- [ ] Error rate monitoring
- [ ] Cost tracking (LLM tokens)

### Testing
- [ ] Unit tests for each connector (Arxiv, SemanticScholar, PubMed)
- [ ] Integration tests for pipeline stages
- [ ] End-to-end tests for full ingestion
- [ ] Performance benchmarks

### Documentation
- [ ] API documentation (OpenAPI/Swagger)
- [ ] Deployment guide
- [ ] Configuration examples

---

## 📋 Known Limitations & Workarounds

### 1. FAISS Indexing Not Implemented
**Impact**: No semantic search available
**Workaround**: Use keyword/score-based filtering for now
**Timeline**: Implement after testing confirms core pipeline works

### 2. Full-Text Parsing Not Implemented
**Impact**: Only abstracts available, not full papers
**Workaround**: Use abstract analysis; mark papers with `full_text_flag=1` for manual review
**Timeline**: Defer to next phase or on-demand basis

### 3. Study Type Detection Not Implemented
**Impact**: Cannot filter by study design
**Workaround**: Implement basic keyword-based detection if needed
**Timeline**: Low priority, defer to phase 2

### 4. API Keys Required for Full Coverage
**Impact**: Semantic Scholar and PubMed require API keys
**Workaround**: Use arXiv alone (free, covers most ML papers)
**Timeline**: Provide API keys when available

---

## 🎯 Module 2 Success Criteria

### Functional Requirements (ALL DONE ✅)
- [x] Multi-source retrieval (arXiv, Semantic Scholar, PubMed)
- [x] Query expansion with LLM
- [x] Deduplication
- [x] Prefiltering (keyword + embedding)
- [x] LLM-based reranking
- [x] MMR-based selection for diversity
- [x] Database storage with audit trail
- [x] Full API exposure

### Performance Requirements (TO VERIFY)
- [ ] Processing time < 60 seconds per ingestion
- [ ] LLM costs < $0.01 per ingestion
- [ ] Support 100-300 retrieved papers → 20 selected
- [ ] Retrieve papers from 2-3 sources in parallel

### Data Quality Requirements (TO VERIFY)
- [ ] No duplicate papers
- [ ] All papers linked to mission_id
- [ ] Scores properly normalized (0-1)
- [ ] Full metadata (title, authors, year, abstract)

### API Quality Requirements (TO VERIFY)
- [ ] All 6 endpoints respond with 200 status
- [ ] Proper error handling with meaningful messages
- [ ] Pagination working on paper lists
- [ ] Consistent JSON response format

---

## 📊 Test Coverage Plan

### Unit Testing (TODO)
- [ ] PaperObject.to_dict() serialization
- [ ] IngestionConfig validation
- [ ] Score normalization (0-1 range check)
- [ ] Deduplication logic (duplicate detection)

### Integration Testing (TODO)
- [ ] ArxivConnector.search() with mocked API
- [ ] Database insert/retrieve for papers
- [ ] Database insert/retrieve for ingestion events
- [ ] Foreign key integrity

### End-to-End Testing (IN PROGRESS)
- [ ] Follow TESTING_GUIDE.md steps 1-7
- [ ] Verify database contains correct papers
- [ ] Verify ingestion event recorded
- [ ] Verify all API endpoints working

---

## 🚀 Next Major Milestones

After Module 2 is stable:

### Module 3: Full-Text Extraction
- [ ] GROBID integration for PDF parsing
- [ ] Table extraction
- [ ] Figure/caption extraction
- [ ] Structured content storage

### Module 4: Claim Extraction
- [ ] Identify key claims in papers
- [ ] Link claims to PICO elements
- [ ] Quantify findings (effect sizes, p-values, etc.)

### Module 5: Evidence Synthesis
- [ ] Aggregate findings across papers
- [ ] Identify contradictions/gaps
- [ ] Generate narrative summary

### Module 6: Query Refinement
- [ ] Suggest additional searches
- [ ] Identify related topics
- [ ] Adapt pipeline based on results

---

## 👤 Contact & Support

For issues or questions:
1. Check TESTING_GUIDE.md troubleshooting section
2. Review logs: `docker logs lhas-backend --tail 50`
3. Verify database: `docker exec lhas-postgres psql -U postgres -d LHAS`

---

## 📝 Change Log

### Version 1.0.0 (Initial Release)
- [x] Created ResearchPaper database model
- [x] Created IngestionEvent database model
- [x] Implemented 11-stage ingestion pipeline
- [x] Added multi-source connectors (3 sources)
- [x] Created 6 API endpoints
- [x] Integrated with existing backend
- [x] Added comprehensive documentation

