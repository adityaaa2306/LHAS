# LHAS Platform - Module 2: Paper Ingestion System

## 📚 Overview

**Module 2** implements a **Hybrid Paper Ingestion Pipeline** that retrieves, filters, ranks, and selects high-quality research papers from multiple academic sources for a given research mission.

### Key Features

✅ **Multi-Source Retrieval**: arXiv, Semantic Scholar, PubMed (100-300 papers)
✅ **Query Expansion**: LLM generates 5-8 search variants for better coverage
✅ **Intelligent Filtering**: 4-stage selection (dedup → keyword → LLM reranking → MMR diversity)
✅ **High-Quality Output**: 15-25 final papers with comprehensive metadata
✅ **Cost-Efficient**: Only ~10-12 LLM calls per ingestion (~$0.003)
✅ **Audit-Ready**: Full ingestion event tracking and pipeline statistics
✅ **Production-Grade**: Robust error handling, async operations, database persistence

---

## 🚀 Getting Started

### Step 1: Rebuild Backend
```powershell
cd c:\Users\adity\OneDrive\Desktop\final
docker compose up -d --build backend
```

### Step 2: Verify Setup
```powershell
# Check backend logs
docker logs lhas-backend --tail 20 | Select-String "Database initialized"

# Verify tables created
docker exec lhas-postgres psql -U postgres -d LHAS -c "\dt"
```

### Step 3: Run Tests
Follow the [QUICK_START.md](QUICK_START.md) guide to test the complete pipeline end-to-end.

---

## 📖 Documentation Structure

| Document | Purpose |
|----------|---------|
| [MODULE_2_DOCUMENTATION.md](MODULE_2_DOCUMENTATION.md) | Comprehensive technical reference for all 11 pipeline stages |
| [QUICK_START.md](QUICK_START.md) | Simple guide to set up and test the system |
| [TESTING_GUIDE.md](TESTING_GUIDE.md) | Detailed API testing with cURL and PowerShell examples |
| [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) | What's done, what's TODO, and next steps |

---

## 🏗️ Architecture

```
User Query (from Module 1)
         ↓
    [STAGE 1] Query Expansion (LLM: 1 call)
         ↓ 5-8 search variants
    [STAGE 2] Multi-Source Retrieval (concurrent)
         ↓ 100-300 papers
    [STAGE 3] Deduplication
         ↓ ~60% unique papers
    [STAGE 4] Cheap Prefiltering (no LLM)
         ↓ ~50-60 papers
    [STAGE 5] LLM Reranking (LLM: ~10 calls, batched)
         ↓ scored papers
    [STAGE 6] Final Scoring (weighted combination)
         ↓
    [STAGE 7] MMR Selection (diversity-aware)
         ↓ 15-25 papers
    [STAGE 8] Full-Text Decision Flags
         ↓
    [STAGE 9] Database Storage
         ↓
    [STAGE 10] FAISS Indexing (placeholder)
         ↓
    [STAGE 11] Event Recording (audit trail)
         ↓
    Final API Response ✓
```

---

## 📊 Database Schema

### `research_papers` Table
Stores all retrieved and selected papers with comprehensive metadata:
- **Core**: id, mission_id, paper_id, doi, title, authors, abstract, year
- **Scoring**: final_score, relevance_score, usefulness_score, embedding_similarity, keyword_overlap
- **URLs**: arxiv_url, semantic_scholar_url, pubmed_url, pdf_url
- **Metadata**: keywords (JSON), citations_count, influence_score
- **Selection**: selected (1/0), rank_in_ingestion
- **Indices**: mission_id, source, year, final_score

### `ingestion_events` Table
Audit trail for each ingestion session:
- **Batch Tracking**: batch_id, mission_id
- **Pipeline Stats**: total_retrieved, after_dedup, after_prefilter, after_rerank, final_selected
- **Quality**: avg_relevance_score, avg_usefulness_score, avg_final_score
- **Performance**: processing_time_seconds, total_llm_calls, total_llm_tokens
- **Status**: status (success/partial/failed), error_message

---

## 🔌 API Endpoints

### 1. **Trigger Ingestion**
```http
POST /api/papers/ingest
```
Starts the complete 11-stage pipeline for a mission.

**Request**:
```json
{
  "mission_id": "550e8400-e29b-41d4-a716-446655440000",
  "structured_query": { /* from Module 1 */ },
  "config": { /* optional */ }
}
```

**Response**: Batch ID, statistics, and sample papers

---

### 2. **Get Mission Papers**
```http
GET /api/papers/mission/{mission_id}?limit=50&offset=0
```
Retrieve selected papers for a mission (paginated, sorted by score).

---

### 3. **Get Paper Details**
```http
GET /api/paper/{paper_id}
```
Full paper information including all scores, URLs, and metadata.

---

### 4. **Ingestion History**
```http
GET /api/papers/mission/{mission_id}/events
```
View all ingestion batches and their statistics.

---

### 5. **Batch Papers**
```http
GET /api/papers/batch/{batch_id}/papers
```
Papers from a specific ingestion batch.

---

### 6. **Source Statistics**
```http
GET /api/papers/stats/source-distribution
```
Distribution and quality metrics by source.

---

## 💰 Cost Analysis

Per-mission ingestion cost breakdown:

| Stage | LLM Calls | Tokens | Cost |
|-------|-----------|--------|------|
| Query Expansion | 1 | 500 | $0.00025 |
| LLM Reranking | ~10 | 5000 | $0.0025 |
| **TOTAL** | **~11** | **~5500** | **≈ $0.003** |

*Based on NVIDIA NIM pricing: $0.50/M input tokens, $1.50/M output tokens*

---

## ✅ Verification Checklist

After running `docker compose up -d --build backend`:

- [ ] Backend container running:
  ```powershell
  docker ps | Select-String "backend"
  ```

- [ ] Tables created:
  ```powershell
  docker exec lhas-postgres psql -U postgres -d LHAS -c "\dt"
  ```

- [ ] API responding:
  ```powershell
  Invoke-WebRequest -Uri "http://localhost:8000/api/papers/stats/source-distribution"
  ```

- [ ] Sample ingestion successful:
  - Follow steps in [QUICK_START.md](QUICK_START.md)
  - Verify papers stored in database

---

## 🔧 Configuration

### IngestionConfig Parameters

```python
{
    "max_candidates": 200,           # Max papers from all sources
    "prefilter_k": 60,              # Keep top N after filtering
    "final_k": 20,                  # Final papers after MMR
    "relevance_threshold": 0.5,     # Min score threshold (0-1)
    "sources": ["arxiv", "semantic_scholar", "pubmed"],
    "mmr_lambda": 0.6               # 0=diversity, 1=relevance
}
```

### Tuning Guide

**More papers** (higher recall):
- Increase `max_candidates` → 300-500
- Increase `final_k` → 30-40
- Set `mmr_lambda` lower → 0.4

**Better papers** (higher precision):
- Decrease `max_candidates` → 100-150
- Increase `relevance_threshold` → 0.7
- Set `mmr_lambda` higher → 0.8

**Faster processing** (reduce cost):
- Decrease `prefilter_k` → 40
- Use fewer sources → `["arxiv", "semantic_scholar"]`
- Decrease `final_k` → 10-15

---

## 🧪 Testing

### Quick Test (5 minutes)
1. Create a mission
2. Analyze a query (Module 1)
3. Trigger ingestion (Module 2)
4. Check papers returned

### Full Test Suite (25 minutes)
Follow all 7 tests in [TESTING_GUIDE.md](TESTING_GUIDE.md):
- Test 1-2: Setup and query analysis
- Test 3: Full ingestion pipeline
- Test 4-6: Paper retrieval and details
- Test 7: Statistics and validation

### Database Validation
Run SQL queries in IMPLEMENTATION_STATUS.md to verify data integrity.

---

## ⚠️ Known Limitations

| Limitation | Impact | Workaround |
|-----------|--------|-----------|
| FAISS indexing not implemented | No semantic search | Use keyword/score filtering |
| Full-text parsing not done | Only abstracts available | Use full_text_flag for flagged papers |
| API keys required | Limited Semantic Scholar/PubMed | Use arXiv alone or provide API keys |
| Study type detection missing | Cannot filter by RCT/observational | Implement keyword-based detection if needed |

---

## 📋 What's Next

### Immediate (This Week)
1. ✅ Backend rebuild and table verification
2. ✅ Run full test suite
3. ✅ Validate performance benchmarks

### Soon (Next Week)
1. Implement FAISS vector indexing (Stage 10)
2. Add semantic search endpoint
3. Set up GROBID for full-text parsing

### Later (Phase 2)
1. Module 3: Full-text extraction with GROBID
2. Module 4: Claim extraction from papers
3. Module 5: Evidence synthesis
4. Module 6: Query refinement

---

## 🐛 Troubleshooting

### Backend not starting?
```powershell
docker logs lhas-backend --tail 50 | Select-String "Error"
```

### Tables not created?
```powershell
# Check if models are imported
docker exec lhas-backend grep -r "ResearchPaper" /app/app/database.py
```

### Ingestion timing out?
- Check LLM connectivity
- Verify API keys (if using Semantic Scholar/PubMed)
- Monitor memory: `docker stats lhas-backend`

### Papers not in database?
- Verify mission_id is correct
- Check ingestion status returned in response
- Query database: `SELECT COUNT(*) FROM research_papers WHERE mission_id = '...';`

---

## 📞 Support

For detailed information:
1. **MODULE_2_DOCUMENTATION.md** - Technical deep dive on all 11 stages
2. **TESTING_GUIDE.md** - API testing with examples
3. **QUICK_START.md** - Step-by-step setup guide
4. **IMPLEMENTATION_STATUS.md** - What's done and what's TODO

---

## 📈 Performance Benchmarks

Expected metrics for a well-tuned system:

| Metric | Value | Status |
|--------|-------|--------|
| Processing time | 30-45 seconds | ✅ Excellent |
| Papers retrieved | 200-300 | ✅ Good coverage |
| Final selected | 18-22 | ✅ Optimal |
| LLM calls | 10-12 | ✅ Efficient |
| Average score | 0.75-0.80 | ✅ High quality |
| Total cost | < $0.005 | ✅ Low cost |

---

## 🎓 Learning Path

**New to this project?** Read in this order:
1. This README (you are here)
2. [QUICK_START.md](QUICK_START.md) - See it in action
3. [MODULE_2_DOCUMENTATION.md](MODULE_2_DOCUMENTATION.md) - Understand how it works
4. [TESTING_GUIDE.md](TESTING_GUIDE.md) - Deep dive with examples

---

## 📦 Dependencies

New packages added:
- **httpx** (>= 0.25.0): Async HTTP client for API calls
- **numpy** (>= 1.24.0): Numerical computations for MMR and scoring

Existing packages used:
- SQLAlchemy: Database ORM
- Pydantic: API request/response validation
- FastAPI: REST API framework

---

## 🎯 Success Criteria

✅ Module 2 is considered successful when:
1. Backend rebuilds without errors
2. All 6 API endpoints respond with 200 status
3. Database contains research_papers and ingestion_events tables
4. Full ingestion pipeline completes in < 60 seconds
5. Papers stored with complete metadata (title, authors, scores, URLs)
6. Ingestion events recorded with full statistics

---

**Status**: Ready for testing
**Last Updated**: 2026-03-28
**Version**: 1.0.0

