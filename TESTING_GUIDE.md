# Module 2: Testing & Validation Guide

## API Testing with cURL & PowerShell

### Test 1: Create a Mission

#### Using cURL:
```bash
curl -X POST http://localhost:8000/api/missions \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Neural Network Interpretability Study",
    "description": "Exploring how different approaches affect NN interpretability",
    "domain": "Machine Learning",
    "research_stage": "Literature Review"
  }'
```

#### Using PowerShell:
```powershell
$body = @{
    title = "Neural Network Interpretability Study"
    description = "Exploring how different approaches affect NN interpretability"
    domain = "Machine Learning"
    research_stage = "Literature Review"
} | ConvertTo-Json

$response = Invoke-WebRequest -Uri "http://localhost:8000/api/missions" `
    -Method POST `
    -Headers @{"Content-Type" = "application/json"} `
    -Body $body

$mission = $response.Content | ConvertFrom-Json
$missionId = $mission.id
Write-Host "Mission created: $missionId"
```

**Save the mission_id for subsequent tests.**

---

### Test 2: Analyze Query (Module 1)

#### Using cURL:
```bash
curl -X POST http://localhost:8000/api/query/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "mission_id": "YOUR_MISSION_ID",
    "user_query": "How do probabilistic and deterministic approaches affect neural network interpretability?"
  }'
```

#### Using PowerShell:
```powershell
$body = @{
    mission_id = $missionId
    user_query = "How do probabilistic and deterministic approaches affect neural network interpretability?"
} | ConvertTo-Json

$response = Invoke-WebRequest -Uri "http://localhost:8000/api/query/analyze" `
    -Method POST `
    -Headers @{"Content-Type" = "application/json"} `
    -Body $body

$analysis = $response.Content | ConvertFrom-Json
Write-Host "Analysis result:"
Write-Host $analysis | ConvertTo-Json -Depth 5
```

**Expected response**:
```json
{
  "id": "...",
  "mission_id": "...",
  "original_query": "How do probabilistic and deterministic approaches affect neural network interpretability?",
  "normalized_query": "How do probabilistic and deterministic approaches affect neural network decision interpretability?",
  "intent_type": "Comparative",
  "key_concepts": ["probabilistic", "deterministic", "neural network", "interpretability"],
  "pico": {
    "population": "Neural network models",
    "intervention": "Probabilistic and deterministic approaches",
    "comparison": "Comparison",
    "outcome": "Interpretability"
  }
}
```

**Save this entire response for the ingestion test.**

---

### Test 3: Trigger Paper Ingestion (Module 2 - MAIN TEST)

#### Using PowerShell (Full Pipeline):
```powershell
# Keep structured_query from Test 2, then:

$ingestionBody = @{
    mission_id = $missionId
    structured_query = @{
        normalized_query = $analysis.normalized_query
        intent_type = $analysis.intent_type
        key_concepts = $analysis.key_concepts
        search_queries = @(
            "probabilistic neural networks interpretability",
            "deterministic approaches neural network transparency",
            "Bayesian deep learning explainability"
        )
        pico = $analysis.pico
    }
    config = @{
        max_candidates = 200
        prefilter_k = 60
        final_k = 20
        relevance_threshold = 0.5
        sources = @("arxiv", "semantic_scholar")
        mmr_lambda = 0.6
        min_abstract_length = 100
    }
} | ConvertTo-Json -Depth 10

$ingestResponse = Invoke-WebRequest -Uri "http://localhost:8000/api/papers/ingest" `
    -Method POST `
    -Headers @{"Content-Type" = "application/json"} `
    -Body $ingestionBody

$result = $ingestResponse.Content | ConvertFrom-Json
Write-Host "Ingestion Pipeline Results:"
Write-Host "------------------------"
Write-Host "Batch ID: $($result.batch_id)"
Write-Host "Total retrieved: $($result.total_retrieved)"
Write-Host "After dedup: $($result.after_dedup)"
Write-Host "After prefilter: $($result.after_prefilter)"
Write-Host "After rerank: $($result.after_rerank)"
Write-Host "Final selected: $($result.final_selected)"
Write-Host "Processing time: $($result.processing_time_seconds)s"
Write-Host ""
Write-Host "Sample papers:"
foreach ($paper in $result.selected_papers[0..4]) {
    Write-Host "- $($paper.title) (Score: $($paper.final_score))"
}
```

**Expected response**:
```json
{
  "success": true,
  "batch_id": "batch_20260328_001",
  "total_retrieved": 245,
  "after_dedup": 178,
  "after_prefilter": 57,
  "after_rerank": 56,
  "final_selected": 20,
  "processing_time_seconds": 38.2,
  "selected_papers": [
    {
      "id": "...",
      "title": "Bayesian Neural Networks for Interpretable Machine Learning",
      "authors": ["Author A", "Author B"],
      "source": "arxiv",
      "final_score": 0.92,
      "relevance_score": 0.90,
      "usefulness_score": 0.88,
      "url": "https://arxiv.org/abs/..."
    },
    ...
  ]
}
```

**KEY VALIDATION POINTS**:
- ✅ `success: true`
- ✅ `total_retrieved > 100` (good coverage)
- ✅ `final_selected >= 15` (reasonable selection)
- ✅ `processing_time_seconds < 60` (acceptable speed)
- ✅ Papers have titles, scores, and URLs

---

### Test 4: Retrieve Stored Papers

#### Using PowerShell:
```powershell
$papersResponse = Invoke-WebRequest -Uri "http://localhost:8000/api/papers/mission/$missionId?limit=25" `
    -Method GET

$papersData = $papersResponse.Content | ConvertFrom-Json

Write-Host "Papers in database:"
Write-Host "==================="
Write-Host "Total papers: $($papersData.count)"
Write-Host ""
Write-Host "Top 10 papers (sorted by score):"
foreach ($paper in $papersData.papers[0..9]) {
    Write-Host ""
    Write-Host "Title: $($paper.title)"
    Write-Host "Authors: $($paper.authors -join ', ')"
    Write-Host "Year: $($paper.year)"
    Write-Host "Source: $($paper.source)"
    Write-Host "Final Score: $($paper.final_score)"
    Write-Host "Relevance: $($paper.relevance_score) | Usefulness: $($paper.usefulness_score)"
    if ($paper.url) {
        Write-Host "URL: $($paper.url)"
    }
}
```

**Expected response**:
```json
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
      "final_score": 0.92,
      "relevance_score": 0.90,
      "usefulness_score": 0.88,
      "keywords": ["bayesian", "neural networks", "interpretability"],
      "url": "https://arxiv.org/abs/..."
    },
    ...
  ]
}
```

---

### Test 5: Get Single Paper Details

#### Using PowerShell:
```powershell
# Get first paper ID from previous test
$paperId = $papersData.papers[0].id

$paperResponse = Invoke-WebRequest -Uri "http://localhost:8000/api/papers/paper/$paperId" `
    -Method GET

$paper = $paperResponse.Content | ConvertFrom-Json

Write-Host "Full Paper Details:"
Write-Host "==================="
Write-Host "ID: $($paper.id)"
Write-Host "Title: $($paper.title)"
Write-Host "Authors: $($paper.authors -join ', ')"
Write-Host "Year: $($paper.year)"
Write-Host "Source: $($paper.source)"
Write-Host "DOI: $($paper.doi)"
Write-Host ""
Write-Host "Scores:"
Write-Host "  Final: $($paper.final_score)"
Write-Host "  Relevance: $($paper.relevance_score)"
Write-Host "  Usefulness: $($paper.usefulness_score)"
Write-Host "  Embedding Similarity: $($paper.embedding_similarity)"
Write-Host ""
Write-Host "URLs:"
Write-Host "  arXiv: $($paper.arxiv_url)"
Write-Host "  Semantic Scholar: $($paper.semantic_scholar_url)"
Write-Host "  PubMed: $($paper.pubmed_url)"
Write-Host "  PDF: $($paper.pdf_url)"
Write-Host ""
Write-Host "Metadata:"
Write-Host "  Citations: $($paper.citations_count)"
Write-Host "  Influence Score: $($paper.influence_score)"
Write-Host "  Keywords: $($paper.keywords -join ', ')"
Write-Host "  PICO Matches:"
foreach ($key in $paper.pico_matches.PSObject.Properties.Name) {
    Write-Host "    $key`: $($paper.pico_matches[$key])"
}
```

---

### Test 6: View Ingestion Events

#### Using PowerShell:
```powershell
$eventsResponse = Invoke-WebRequest -Uri "http://localhost:8000/api/papers/mission/$missionId/events" `
    -Method GET

$events = $eventsResponse.Content | ConvertFrom-Json

Write-Host "Ingestion Events History:"
Write-Host "========================="
Write-Host "Total events: $($events.total_events)"
Write-Host ""
foreach ($event in $events.events) {
    Write-Host "Batch: $($event.batch_id)"
    Write-Host "Status: $($event.status)"
    Write-Host "Started: $($event.started_at)"
    Write-Host "Completed: $($event.completed_at)"
    Write-Host ""
    Write-Host "Pipeline Statistics:"
    Write-Host "  Total retrieved: $($event.total_retrieved)"
    Write-Host "  After dedup: $($event.after_dedup)"
    Write-Host "  After prefilter: $($event.after_prefilter)"
    Write-Host "  After rerank: $($event.after_rerank)"
    Write-Host "  Final selected: $($event.final_selected)"
    Write-Host ""
    Write-Host "Quality Metrics:"
    Write-Host "  Avg relevance score: $($event.avg_relevance_score)"
    Write-Host "  Avg usefulness score: $($event.avg_usefulness_score)"
    Write-Host "  Avg final score: $($event.avg_final_score)"
    Write-Host ""
    Write-Host "Processing:"
    Write-Host "  Time (s): $($event.processing_time_seconds)"
    Write-Host "  LLM calls: $($event.total_llm_calls)"
    Write-Host "  LLM tokens: $($event.total_llm_tokens)"
    Write-Host "  Sources: $($event.sources_used -join ', ')"
    Write-Host ""
}
```

---

### Test 7: Get Source Distribution Stats

#### Using PowerShell:
```powershell
$statsResponse = Invoke-WebRequest -Uri "http://localhost:8000/api/papers/stats/source-distribution" `
    -Method GET

$stats = $statsResponse.Content | ConvertFrom-Json

Write-Host "Source Distribution:"
Write-Host "===================="
foreach ($source in $stats.sources) {
    Write-Host ""
    Write-Host "Source: $($source.source)"
    Write-Host "  Total papers: $($source.total_count)"
    Write-Host "  Selected papers: $($source.selected_count)"
    Write-Host "  Average score: $($source.avg_score)"
    Write-Host "  Maximum score: $($source.max_score)"
    Write-Host "  Percentage of total: $($source.percentage)%"
}
```

**Expected response**:
```json
{
  "sources": [
    {
      "source": "arxiv",
      "total_count": 95,
      "selected_count": 12,
      "avg_score": 0.72,
      "max_score": 0.93,
      "percentage": 60.0
    },
    {
      "source": "semantic_scholar",
      "total_count": 83,
      "selected_count": 8,
      "avg_score": 0.68,
      "max_score": 0.88,
      "percentage": 40.0
    }
  ]
}
```

---

## Database Validation Queries

### Verify Table Schema

```sql
-- Check research_papers columns
\d research_papers

-- Check ingestion_events columns
\d ingestion_events
```

### Validate Data Integrity

```sql
-- Count papers by mission
SELECT mission_id, COUNT(*) as total, COUNT(CASE WHEN selected=1 THEN 1 END) as selected
FROM research_papers
GROUP BY mission_id;

-- Check for orphaned papers
SELECT COUNT(*) as orphaned_count
FROM research_papers
WHERE mission_id NOT IN (SELECT id FROM missions);

-- Verify scores are in valid range [0, 1]
SELECT COUNT(*) as invalid_scores
FROM research_papers
WHERE final_score < 0 OR final_score > 1 OR
      relevance_score < 0 OR relevance_score > 1 OR
      usefulness_score < 0 OR usefulness_score > 1;

-- Check ingestion events
SELECT batch_id, status, COUNT(*) as papers_in_batch
FROM research_papers
WHERE selected = 1
GROUP BY batch_id;
```

### Performance Analysis

```sql
-- Papers by source and score
SELECT source, 
       COUNT(*) as total,
       MIN(final_score) as min_score,
       AVG(final_score) as avg_score,
       MAX(final_score) as max_score
FROM research_papers
WHERE selected = 1
GROUP BY source;

-- Pipeline efficiency
SELECT 
    batch_id,
    total_retrieved,
    final_selected,
    ROUND(100.0 * final_selected / total_retrieved, 2) as selection_rate,
    processing_time_seconds,
    total_llm_calls,
    ROUND(processing_time_seconds / total_llm_calls, 2) as time_per_llm_call
FROM ingestion_events
ORDER BY created_at DESC;
```

---

## Success Criteria Checklist

### ✅ Backend Running
- [ ] `docker logs lhas-backend | grep "Database initialized"`
- [ ] Backend container status: `docker ps | grep backend`

### ✅ Tables Created
- [ ] `research_papers` table exists with 40+ columns
- [ ] `ingestion_events` table exists with 17 columns
- [ ] Tables have proper indexes

### ✅ API Endpoints Working
- [ ] POST `/api/papers/ingest` returns 200 with results
- [ ] GET `/api/papers/mission/{id}` returns list of papers
- [ ] GET `/api/paper/{id}` returns full paper details
- [ ] GET `/api/papers/mission/{id}/events` returns ingestion history
- [ ] GET `/api/papers/stats/source-distribution` returns stats

### ✅ Data Quality
- [ ] Papers have titles, authors, abstracts, years
- [ ] All scores are between 0 and 1
- [ ] Foreign key integrity (all papers linked to mission)
- [ ] Duplicate detection working (deduplicated correctly)

### ✅ Pipeline Performance
- [ ] Processing time < 60 seconds
- [ ] LLM calls < 15
- [ ] Papers retrieved from multiple sources
- [ ] Final selection 15-25 papers
- [ ] Average score > 0.6

### ✅ Cost Control
- [ ] Total LLM tokens < 10,000 per ingestion
- [ ] Cost per ingestion < $0.01
- [ ] Batching working (5-10 papers per LLM call)

---

## Troubleshooting Tests

### Test: Check Backend Health

```powershell
$response = Invoke-WebRequest -Uri "http://localhost:8000/health" -Method GET
Write-Host $response.StatusCode
Write-Host $response.Content
```

### Test: Check Database Connection

```powershell
docker exec lhas-postgres psql -U postgres -d LHAS -c "SELECT COUNT(*) FROM missions;"
```

### Test: Verify LLM Integration

Check if LLM is working:
```powershell
# This will be tested during query analysis (Test 2)
# If normalized_query differs from original, LLM is working
```

### Test: Monitor API Logs

```powershell
docker logs -f lhas-backend | Select-String "Query expansion|papers/ingest|Error"
```

---

## Performance Benchmarks

Expected performance for a well-tuned system:

| Metric | Expected | Acceptable | Concerning |
|--------|----------|------------|------------|
| Processing time | 30-40s | < 60s | > 90s |
| Total retrieved | 200-300 | 100-400 | < 100 |
| Final selected | 18-22 | 15-25 | < 10 |
| LLM calls | 10-12 | < 15 | > 20 |
| Avg final score | 0.75-0.80 | > 0.60 | < 0.50 |
| Selection rate | 6-10% | 5-15% | < 2% or > 20% |

