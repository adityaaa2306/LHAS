# Module 2: Paper Ingestion Service - Complete Implementation

## Overview

Module 2 is a production-grade **Hybrid Paper Ingestion Pipeline** that retrieves, filters, ranks, and selects high-quality research papers for a given research mission. The system balances **high recall, high precision, low cost, and robustness**.

### Architecture

```
Mission Query (Module 1 Output)
         ↓
    [STAGE 1] Query Expansion (LLM: 1 call)
         ↓
    [STAGE 2] Multi-Source Retrieval (arXiv, Semantic Scholar, PubMed)
         ↓ (100-300 candidates)
    [STAGE 3] Deduplication & Normalization
         ↓ (Remove duplicates)
    [STAGE 4] Cheap Prefiltering (Embeddings + Keywords, NO LLM)
         ↓ (50-60 papers)
    [STAGE 5] LLM Reranking (LLM: 5-10 calls, batch-based)
         ↓ (Scored papers)
    [STAGE 6] Final Scoring (Weighted combination)
         ↓
    [STAGE 7] MMR Selection (Diversity-aware, 15-25 papers)
         ↓
    [STAGE 8] Full-text Decision Flags
         ↓
    [STAGE 9] Database Storage (PostgreSQL)
         ↓
    [STAGE 10] FAISS Indexing (For vector search)
         ↓
    [STAGE 11] Ingestion Event Recording (Audit trail)
         ↓
    Final Selected Papers ✓
```

---

## Database Schema

### `research_papers` Table
Stores all retrieved and selected papers.

| Column | Type | Purpose |
|--------|------|---------|
| `id` | UUID | Primary key |
| `mission_id` | UUID | Link to mission |
| `paper_id` | String | External ID (arxiv_..., semanticscholar_..., pubmed_...) |
| `doi` | String | Digital Object Identifier |
| `title` | Text | Paper title |
| `authors` | JSON | List of author names |
| `abstract` | Text | Paper abstract |
| `year` | Integer | Publication year |
| `source` | Enum | Source: `arxiv`, `semantic_scholar`, `pubmed` |
| `final_score` | Float | Final combined score (0-1) |
| `relevance_score` | Float | LLM relevance assessment (0-1) |
| `usefulness_score` | Float | LLM usefulness assessment (0-1) |
| `embedding_similarity` | Float | Semantic similarity to query (0-1) |
| `keyword_overlap` | Float | Keyword match score (0-1) |
| `selected` | Integer | 1=selected, 0=rejected |
| `full_text_flag` | Integer | 1=needs full-text parsing, 0=abstract sufficient |
| `full_text_content` | Text | Parsed full-text (if available) |
| `pico_*_match` | Integer | PICO element match flags (0 or 1) |
| `keywords` | JSON | Extracted keywords |
| `citations_count` | Integer | Citation count (if available) |
| `influence_score` | Float | Influence score from Semantic Scholar |
| `ingestion_batch_id` | String | Links to ingestion event |
| `rank_in_ingestion` | Integer | Rank in this ingestion session |

### `ingestion_events` Table
Audit trail for each ingestion session.

| Column | Type | Purpose |
|--------|------|---------|
| `id` | UUID | Primary key |
| `mission_id` | UUID | Link to mission |
| `batch_id` | String | Batch identifier |
| `total_retrieved` | Integer | Papers from all sources |
| `after_dedup` | Integer | After deduplication |
| `after_prefilter` | Integer | After embedding/keyword filter |
| `after_rerank` | Integer | After LLM reranking |
| `final_selected` | Integer | Final MMR selection |
| `avg_relevance_score` | Float | Average relevance in batch |
| `avg_usefulness_score` | Float | Average usefulness in batch |
| `avg_final_score` | Float | Average final score |
| `sources_used` | JSON | List of sources queried |
| `total_llm_calls` | Integer | Number of LLM calls |
| `total_llm_tokens` | Integer | Tokens used in LLM calls |
| `processing_time_seconds` | Float | Total processing time |
| `status` | String | `success`, `partial`, `failed` |
| `error_message` | Text | Error details if failed |

---

## Pipeline Stages

### STAGE 1: Query Expansion (LLM: 1 call)

**Purpose**: Create 5-10 semantically diverse search variants

**Input**: 
- Normalized query (from Module 1)
- Key concepts

**Process**:
```python
prompt = """Expand this research query into 5-8 semantically diverse search variants.

Query: "How do probabilistic and deterministic approaches affect neural network interpretability?"
Key concepts: ["neural networks", "interpretability", "probabilistic", "deterministic"]

Return JSON with:
{
    "variants": [
        "neural network interpretability comparison",
        "probabilistic neural networks explainability",
        "deterministic NN decision-making transparency",
        ...
    ],
    "concept_clusters": {
        "methodologies": ["probabilistic", "deterministic", "Bayesian"],
        "properties": ["interpretability", "explainability", "transparency", "trustworthiness"],
        "targets": ["neural networks", "deep learning", "machine learning"]
    }
}"""
```

**Cost**: 1 LLM call (~500 tokens)

**Output**: 
- `expanded_queries`: List of 5-8 variants
- `concept_clusters`: Grouped related concepts

---

### STAGE 2: Multi-Source Retrieval (High Recall)

**Purpose**: Fetch papers from multiple sources in parallel

**Sources**:
1. **arXiv** (No API key required)
   - URL: http://export.arxiv.org/api/query
   - Retrieves: ~100-150 papers per query
   - Prefers recent computational papers

2. **Semantic Scholar** (API key required)
   - Covers: All disciplines, high-quality papers
   - Provides: Citations count, influence scores
   - Retrieves: ~100-150 papers per query

3. **PubMed** (API key optional but recommended)
   - Focus: Biomedical/clinical research
   - URL: NIH NCBI e-utilities
   - Retrieves: ~100-150 papers per query

**Process**:
```python
# For each of top 3 expanded queries, fetch from 2-3 sources
max_candidates = 200
per_source = 200 / 3  # ~67 per source

# Parallel fetching
tasks = [
    arxiv.search(query1, 67),
    semantic_scholar.search(query1, 67),
    pubmed.search(query1, 67),
    arxiv.search(query2, 67),
    ...
]
results = await asyncio.gather(*tasks)
candidates = [paper for result in results for paper in result]
```

**Output**: 
- `candidates`: List of 100-300 PaperObject instances

**Cost**: 0 LLM calls (API rate limits apply)

---

### STAGE 3: Deduplication & Normalization

**Purpose**: Remove duplicates and normalize data

**Process**:
```python
def deduplicate(papers):
    seen_dois = set()
    seen_titles = set()
    deduplicated = []
    
    for paper in papers:
        # Skip if DOI already seen
        if paper.doi in seen_dois:
            continue
        
        # Skip if similar title already seen
        if paper.title.lower() in seen_titles:
            continue
        
        deduplicated.append(paper)
        if paper.doi:
            seen_dois.add(paper.doi)
        seen_titles.add(paper.title.lower())
    
    return deduplicated
```

**Normalization**:
- Title: Trim whitespace, fix encoding
- Authors: List of strings only
- Abstract: Standardize encoding
- Year: Integer only
- Remove entries with missing critical fields

**Output**: 
- Deduplicated, normalized papers

---

### STAGE 4: Cheap Prefiltering (NO LLM)

**Purpose**: Reduce candidate pool using fast, non-LLM methods

**Filters**:

1. **Abstract Length Filter**
   - Drop papers with abstract < 100 characters
   - Reason: Low information content

2. **Keyword Overlap**
   ```python
   query_concepts = {"neural networks", "interpretability", ...}
   abstract_lower = paper.abstract.lower()
   
   matching_concepts = sum(
       1 for concept in query_concepts 
       if concept in abstract_lower
   )
   
   keyword_score = matching_concepts / len(query_concepts)
   if keyword_score >= 0.3:  # Keep papers with 30%+ concept overlap
       prefiltered.append(paper)
   ```

3. **Embedding Similarity** (TODO: Implement FAISS)
   - Compare abstract embeddings to query embedding
   - Keep papers with similarity > threshold
   - Uses pre-computed embeddings (no LLM call)

**Target Output**: 50-60 papers

**Cost**: 0 LLM calls (pure keyword/embedding matching)

---

### STAGE 5: LLM Reranking (CRITICAL)

**Purpose**: Assess relevance and usefulness using LLM - but ONLY on top candidates

**Process**:
```python
# Batch papers 5-10 per LLM call to minimize cost
batch_size = 5
for i in range(0, len(prefiltered), batch_size):
    batch = prefiltered[i:i+batch_size]
    
    prompt = """Evaluate these papers for relevance and usefulness.

Research Question: "How do probabilistic and deterministic approaches affect neural network interpretability?"

Paper 1:
Title: "Bayesian Neural Networks for Interpretable Classification"
Abstract: [...first 500 chars...]

Paper 2:
Title: "Deterministic vs Stochastic NN Explainability"
Abstract: [...first 500 chars...]

For each paper, score:
- relevance_score (0-1): Does it directly address the research question?
- usefulness_score (0-1): Contains actionable evidence/findings?

Return JSON:
{
    "evaluations": [
        {
            "paper_index": 1,
            "relevance_score": 0.85,
            "usefulness_score": 0.75,
            "reason": "Directly compares Bayesian NN interpretability..."
        },
        ...
    ]
}"""
    
    response = await llm.generate(prompt)  # 1 LLM call per batch
```

**Cost Optimization**:
- Only top 50-60 papers evaluated (not all 300+)
- Batched: 5-10 calls instead of 50+ individual calls
- Estimated: ~5-12 LLM calls, ~5K tokens total

**Output**: Papers with LLM-assigned scores

---

### STAGE 6: Final Scoring

**Purpose**: Combine multiple signals into single final score

**Calculation**:
```python
def compute_final_score(paper):
    embedding_sim = paper.embedding_similarity or 0.5  # 40% weight
    relevance = paper.relevance_score or 0.5             # 40% weight
    usefulness = paper.usefulness_score or 0.5           # 20% weight
    
    final_score = (
        embedding_sim * 0.4 +
        relevance * 0.4 +
        usefulness * 0.2
    )
    
    return min(1.0, max(0.0, final_score))  # Clamp to [0,1]
```

**Interpretation**:
- 0.8-1.0: Highly relevant and useful
- 0.6-0.8: Good relevance and usefulness
- 0.4-0.6: Borderline papers
- < 0.4: Likely noise (often dropped)

---

### STAGE 7: MMR Selection (Diversity-Aware)

**Purpose**: Select final set of papers while avoiding redundancy

**Maximal Marginal Relevance (MMR) Algorithm**:
```python
def mmr_selection(papers, k=20, lambda_param=0.6):
    """
    MMR: Balance between relevance and diversity.
    
    lambda=1.0: Pure relevance (greedy by score)
    lambda=0.0: Pure diversity (avoid similar papers)
    lambda=0.6: Balanced (default)
    """
    selected = []
    remaining = papers.copy()
    
    # Start with highest-scoring paper
    best = max(remaining, key=lambda p: p.final_score)
    selected.append(best)
    remaining.remove(best)
    
    while len(selected) < k and remaining:
        # Compute marginal relevance for each remaining paper
        best_mmr_paper = None
        best_mmr_score = -1
        
        for candidate in remaining:
            # Relevance: score of this paper
            relevance = candidate.final_score
            
            # Diversity: minimized similarity to already selected
            diversity = 1.0
            for selected_paper in selected:
                similarity = compute_similarity(candidate, selected_paper)
                diversity = min(diversity, 1.0 - similarity)
            
            # MMR score
            mmr_score = lambda_param * relevance + (1 - lambda_param) * diversity
            
            if mmr_score > best_mmr_score:
                best_mmr_score = mmr_score
                best_mmr_paper = candidate
        
        if best_mmr_paper:
            selected.append(best_mmr_paper)
            remaining.remove(best_mmr_paper)
    
    return selected
```

**Similarity Computation**:
```python
def compute_title_similarity(title1, title2):
    """Jaccard similarity on title words"""
    words1 = set(title1.lower().split())
    words2 = set(title2.lower().split())
    
    intersection = len(words1 & words2)
    union = len(words1 | words2)
    
    return intersection / union if union > 0 else 0.0
```

**Output**: 15-25 diverse, high-quality papers

---

### STAGE 8: Full-Text Decision

**Purpose**: Decide which papers need full-text parsing

**Rules**:
```python
for paper in selected:
    abstract_length = len(paper.abstract or "")
    
    # Mark for full-text if:
    # 1. Abstract very short AND high relevance
    if abstract_length < 200 and paper.final_score > 0.7:
        paper.full_text_flag = True
    
    # 2. Usefulness score high but abstract unclear
    if paper.usefulness_score > 0.8 and abstract_length < 150:
        paper.full_text_flag = True
```

**Full-text Processing** (Future: GROBID integration):
- Mark papers for async full-text extraction
- GROBID parses PDFs → structured text + tables + figures
- Store extracted content for downstream claim extraction (Module 3+)

---

### STAGE 9: Database Storage

**Process**:
```python
for rank, paper in enumerate(selected, 1):
    stmt = insert(ResearchPaper).values(
        mission_id=mission_id,
        paper_id=paper.paper_id,
        title=paper.title,
        authors=paper.authors,
        abstract=paper.abstract,
        year=paper.year,
        source=paper.source,
        final_score=paper.final_score,
        relevance_score=paper.relevance_score,
        usefulness_score=paper.usefulness_score,
        selected=1,
        full_text_flag=paper.full_text_flag,
        ingestion_batch_id=batch_id,
        rank_in_ingestion=rank,
        arxiv_url=paper.url if paper.source == PaperSource.ARXIV else None,
        semantic_scholar_url=paper.url if paper.source == PaperSource.SEMANTIC_SCHOLAR else None,
        pubmed_url=paper.url if paper.source == PaperSource.PUBMED else None,
        pdf_url=paper.pdf_url,
        keywords=paper.keywords,
        citations_count=paper.citations_count,
        influence_score=paper.influence_score,
    )
    await db.execute(stmt)

await db.commit()
```

**Constraints**:
- NO orphaned papers (each linked to mission_id)
- Batch tracking for audit trail
- Soft deletes preferred (set selected=0 instead of deletion)

---

### STAGE 10: FAISS Indexing

**Purpose**: Enable fast vector-based retrieval on abstracts

**Process** (TODO):
```python
import faiss
import numpy as np

# 1. Get embeddings for all abstracts
embeddings = []
paper_ids = []

for paper in selected:
    # Get embedding from LLM provider
    embedding = await llm.get_embedding(paper.abstract)
    embeddings.append(embedding)
    paper_ids.append(str(paper.id))

embeddings = np.array(embeddings).astype('float32')

# 2. Create FAISS index
index = faiss.IndexFlatL2(embeddings.shape[1])
index.add(embeddings)

# 3. Save mapping
mapping = {str(paper_ids[i]): i for i in range(len(paper_ids))}

# 4. Store index
faiss.write_index(index, f"storage/faiss_indices/{mission_id}.index")
save_json(f"storage/faiss_indices/{mission_id}_mapping.json", mapping)
```

---

### STAGE 11: Ingestion Event Recording

**Purpose**: Audit trail and optimization feedback

**Recorded Data**:
```python
event = {
    "batch_id": batch_id,
    "mission_id": mission_id,
    "timestamp": datetime.utcnow(),
    "statistics": {
        "total_retrieved": 250,
        "after_dedup": 180,
        "after_prefilter": 58,
        "after_rerank": 58,
        "final_selected": 20,
    },
    "scores": {
        "avg_relevance": 0.78,
        "avg_usefulness": 0.72,
        "avg_final": 0.76,
    },
    "processing": {
        "total_time_seconds": 42.5,
        "llm_calls": 12,
        "llm_tokens": 5847,
        "sources": ["arxiv", "semantic_scholar", "pubmed"],
    },
    "status": "success",
}
```

**Usage**: 
- Track costs (LLM calls/tokens)
- Identify bottlenecks
- Assess source quality (which source yields best papers?)
- Optimize pipeline parameters for future runs

---

## API Endpoints

### 1. Trigger Ingestion
```http
POST /api/papers/ingest

Request:
{
    "mission_id": "550e8400-e29b-41d4-a716-446655440000",
    "structured_query": {
        "normalized_query": "How do probabilistic and deterministic approaches affect neural network interpretability?",
        "key_concepts": ["neural networks", "interpretability", "probabilistic", "deterministic"],
        "search_queries": ["..."],
        "intent_type": "Comparative",
        "pico": {...}
    },
    "config": {
        "max_candidates": 200,
        "prefilter_k": 60,
        "final_k": 20,
        "relevance_threshold": 0.5,
        "sources": ["arxiv", "semantic_scholar", "pubmed"],
        "mmr_lambda": 0.6
    }
}

Response:
{
    "success": true,
    "batch_id": "...",
    "total_retrieved": 250,
    "after_dedup": 180,
    "after_prefilter": 58,
    "after_rerank": 58,
    "final_selected": 20,
    "processing_time_seconds": 42.5,
    "selected_papers": [...]
}
```

### 2. Get Mission Papers
```http
GET /api/papers/mission/{mission_id}?limit=50&offset=0

Response:
{
    "mission_id": "...",
    "count": 20,
    "papers": [
        {
            "id": "...",
            "title": "Bayesian Neural Networks...",
            "authors": ["Author 1", "Author 2"],
            "abstract": "...",
            "year": 2023,
            "source": "arxiv",
            "final_score": 0.89,
            "relevance_score": 0.85,
            "url": "https://arxiv.org/abs/...",
            "pdf_url": "https://arxiv.org/pdf/..."
        }
    ]
}
```

### 3. Get Paper Detail
```http
GET /api/papers/paper/{paper_id}

Response:
{
    "id": "...",
    "title": "...",
    "authors": [...],
    "abstract": "...",
    "year": 2023,
    "source": "arxiv",
    "final_score": 0.89,
    "relevance_score": 0.85,
    "usefulness_score": 0.79,
    "keywords": ["keyword1", "keyword2"],
    "citations_count": 42,
    "influence_score": 0.65,
    "urls": {...},
    "pico_matches": {...},
    "full_text_available": false,
    "retrieved_at": "2026-03-28T...",
    "processed_at": null
}
```

### 4. Get Ingestion Events
```http
GET /api/papers/mission/{mission_id}/events

Response:
{
    "mission_id": "...",
    "total_events": 2,
    "events": [
        {
            "batch_id": "...",
            "started_at": "...",
            "completed_at": "...",
            "status": "success",
            "total_retrieved": 250,
            "after_dedup": 180,
            "after_prefilter": 58,
            "after_rerank": 58,
            "final_selected": 20,
            "avg_scores": {...},
            "processing_time_seconds": 42.5,
            "llm_calls": 12,
            "llm_tokens": 5847,
            "sources_used": ["arxiv", "semantic_scholar", "pubmed"]
        }
    ]
}
```

---

## Configuration & Tuning

### IngestionConfig Parameters

```python
config = IngestionConfig(
    max_candidates=200,        # Max papers from all sources
    prefilter_k=60,           # Keep top N after keyword/embedding filter
    final_k=20,               # Final papers after MMR selection
    relevance_threshold=0.5,  # Min score threshold (0-1)
    sources=["arxiv", "semantic_scholar", "pubmed"],
    mmr_lambda=0.6,           # 0=diversity, 1=relevance
    min_abstract_length=100   # Reject shorter abstracts
)
```

### Tuning Guide

**Increase Recall** (Get more papers):
- Increase `max_candidates` → 300-500
- Decrease `min_abstract_length` → 50
- Set `mmr_lambda` lower → 0.4 (more diversity, less strict ranking)

**Increase Precision** (Get better papers):
- Decrease `max_candidates` → 100-150
- Increase `min_abstract_length` → 200
- Set `mmr_lambda` higher → 0.8 (strict ranking)
- Increase `relevance_threshold` → 0.7

**Reduce Cost**:
- Decrease `prefilter_k` → 40 (fewer LLM evaluations)
- Use fewer sources → `sources=["arxiv", "semantic_scholar"]`
- Set `final_k` lower → 10-15

---

## Cost Analysis

### Per-Mission Ingestion

| Stage | LLM Calls | Tokens | Cost |
|-------|-----------|--------|------|
| 1. Query Expansion | 1 | 500 | $0.00025 |
| 2. Retrieval | 0 | 0 | $0 |
| 3. Dedup | 0 | 0 | $0 |
| 4. Prefilter | 0 | 0 | $0 |
| 5. LLM Rerank | ~10 | 5000 | $0.0025 |
| 6. Scoring | 0 | 0 | $0 |
| 7. MMR | 0 | 0 | $0 |
| 8-11. Storage | 0 | 0 | $0 |
| **TOTAL** | **~11** | **~5500** | **~$0.003** |

*Costs assume NVIDIA NIM LLM pricing: $0.50/1M input tokens, $1.50/1M output tokens*

---

## Next Steps

1. **Provide API Keys**:
   - Semantic Scholar: Optional but recommended
   - PubMed: Optional for biomedical queries

2. **Implement FAISS** (Stage 10):
   - Add embedding computation
   - Create vector indexes for fast retrieval

3. **Integrate Full-Text Parsing** (Extension):
   - Add GROBID integration for PDF parsing
   - Extract structured tables, figures

4. **Implement Claim Extraction** (Module 3+):
   - Extract key findings from papers
   - Link claims to PICO elements

5. **Add Filtering**:
   - Study type filtering (RCT, observational, etc.)
   - Date range filtering
   - Language filtering

---

## Example Usage

```python
from app.services.paper_ingestion import PaperIngestionService, IngestionConfig

# Initialize service
service = PaperIngestionService(db)

# Define config
config = IngestionConfig(
    max_candidates=200,
    prefilter_k=60,
    final_k=20,
    relevance_threshold=0.5
)

# Run ingestion
result = await service.ingest_papers(
    mission_id="550e8400-e29b-41d4-a716-446655440000",
    structured_query={
        "normalized_query": "How do probabilistic and deterministic approaches affect neural network interpretability?",
        "key_concepts": ["neural networks", "interpretability"],
        "search_queries": [...],
        "intent_type": "Comparative",
        "pico": {}
    },
    config=config
)

print(result)
# {
#   'success': True,
#   'batch_id': '...',
#   'total_retrieved': 250,
#   'final_selected': 20,
#   ...
# }
```

---

## Database Tables

Both tables are automatically created when the backend starts:

```bash
docker logs lhas-backend | grep "Database initialized"
```

To verify in PostgreSQL:

```sql
SELECT * FROM research_papers LIMIT 1;
SELECT * FROM ingestion_events LIMIT 1;
```

