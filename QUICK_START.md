# Module 2: Quick Start Guide

## Prerequisites

Ensure you have:
- Docker and Docker Compose installed
- PostgreSQL 16 running (localhost:5432)
- pgAdmin running (localhost:5050) - optional but recommended
- Backend container ready

## Step 1: Rebuild Backend

Navigate to your project directory and rebuild:

```powershell
cd c:\Users\adity\OneDrive\Desktop\final
docker compose up -d --build backend
```

**Verify successful build**:
```powershell
docker logs lhas-backend --tail 30
```

Expected output:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Database initialized
```

## Step 2: Verify Tables Created

Check that `research_papers` and `ingestion_events` tables were created:

```powershell
docker exec lhas-postgres psql -U postgres -d LHAS -c "\dt"
```

**Expected output** (should show 6 tables):
```
          List of relations
 Schema |        Name         | Type  |  Owner
--------+---------------------+-------+----------
 public | alerts              | table | postgres
 public | ingestion_events    | table | postgres
 public | missions            | table | postgres
 public | query_analysis      | table | postgres
 public | research_papers     | table | postgres
 public | sessions            | table | postgres
```

## Step 3: Create a Test Mission

First, create a test mission if you don't have one:

```powershell
$mission_data = @{
    title = "Neural Network Interpretability Research"
    description = "Exploring probabilistic vs deterministic approaches to interpretability"
    domain = "Machine Learning"
    research_stage = "Literature Review"
} | ConvertTo-Json

$response = Invoke-WebRequest -Uri "http://localhost:8000/api/missions" `
    -Method POST `
    -Headers @{"Content-Type" = "application/json"} `
    -Body $mission_data

$mission = $response.Content | ConvertFrom-Json
$mission_id = $mission.id
Write-Host "Created mission: $mission_id"
```

## Step 4: Run Query Analysis (Module 1)

Analyze a research query to get structured outputs:

```powershell
$query_data = @{
    mission_id = $mission_id
    user_query = "How do probabilistic and deterministic approaches affect neural network decision interpretability and model transparency?"
} | ConvertTo-Json

$analysis = Invoke-WebRequest -Uri "http://localhost:8000/api/query/analyze" `
    -Method POST `
    -Headers @{"Content-Type" = "application/json"} `
    -Body $query_data

$result = $analysis.Content | ConvertFrom-Json
Write-Host "Query normalized to:" $result.normalized_query
$structured_query = $result
```

**Expected output**:
```json
{
  "normalized_query": "How do probabilistic and deterministic approaches affect neural network decision interpretability and model transparency?",
  "intent_type": "Comparative",
  "key_concepts": ["neural networks", "interpretability", "probabilistic", "deterministic", "transparency"],
  "pico": {
    "population": "Neural network models",
    "intervention": "Probabilistic and deterministic approaches",
    "comparison": "Comparative analysis",
    "outcome": "Decision interpretability, model transparency"
  }
}
```

## Step 5: Trigger Paper Ingestion (Module 2)

Now trigger the full ingestion pipeline:

```powershell
$ingest_data = @{
    mission_id = $mission_id
    structured_query = $structured_query
    config = @{
        max_candidates = 200
        prefilter_k = 60
        final_k = 20
        relevance_threshold = 0.5
        sources = @("arxiv", "semantic_scholar", "pubmed")
        mmr_lambda = 0.6
    }
} | ConvertTo-Json -Depth 10

$ingest_response = Invoke-WebRequest -Uri "http://localhost:8000/api/papers/ingest" `
    -Method POST `
    -Headers @{"Content-Type" = "application/json"} `
    -Body $ingest_data

$ingest_result = $ingest_response.Content | ConvertFrom-Json
Write-Host "Ingestion complete!"
Write-Host "Total retrieved: $($ingest_result.total_retrieved)"
Write-Host "Final selected: $($ingest_result.final_selected)"
Write-Host "Processing time: $($ingest_result.processing_time_seconds)s"
```

**Expected output**:
```json
{
  "success": true,
  "batch_id": "batch_2026_03_28_001",
  "total_retrieved": 250,
  "after_dedup": 180,
  "after_prefilter": 58,
  "after_rerank": 58,
  "final_selected": 20,
  "processing_time_seconds": 42.5,
  "selected_papers": [
    {
      "id": "...",
      "title": "Bayesian Neural Networks for Interpretable Classification",
      "authors": ["Author 1", "Author 2"],
      "final_score": 0.89,
      "relevance_score": 0.85,
      "usefulness_score": 0.79
    },
    ...
  ]
}
```

## Step 6: Retrieve Papers

Get the selected papers:

```powershell
$papers_response = Invoke-WebRequest -Uri "http://localhost:8000/api/papers/mission/$mission_id" `
    -Method GET

$papers = $papers_response.Content | ConvertFrom-Json
Write-Host "Retrieved $($papers.count) papers"
foreach ($paper in $papers.papers) {
    Write-Host "- $($paper.title) (Score: $($paper.final_score))"
}
```

## Step 7: View Ingestion History

See all ingestion events for a mission:

```powershell
$events_response = Invoke-WebRequest -Uri "http://localhost:8000/api/papers/mission/$mission_id/events" `
    -Method GET

$events = $events_response.Content | ConvertFrom-Json
Write-Host "Total ingestion events: $($events.total_events)"
foreach ($event in $events.events) {
    Write-Host "Batch $($event.batch_id): $($event.final_selected) papers selected"
    Write-Host "  Processing time: $($event.processing_time_seconds)s"
    Write-Host "  LLM calls: $($event.llm_calls)"
    Write-Host "  Status: $($event.status)"
}
```

---

## Database Verification

### Check Papers Stored

```sql
SELECT 
    COUNT(*) as total_papers,
    COUNT(CASE WHEN selected = 1 THEN 1 END) as selected,
    AVG(final_score) as avg_score,
    MAX(final_score) as max_score
FROM research_papers
WHERE mission_id = 'YOUR_MISSION_ID';
```

### View Top Papers

```sql
SELECT 
    title,
    source,
    final_score,
    relevance_score,
    usefulness_score,
    year
FROM research_papers
WHERE mission_id = 'YOUR_MISSION_ID' AND selected = 1
ORDER BY final_score DESC
LIMIT 10;
```

### Check Ingestion Stats

```sql
SELECT 
    batch_id,
    total_retrieved,
    after_dedup,
    after_prefilter,
    after_rerank,
    final_selected,
    processing_time_seconds,
    total_llm_calls,
    status
FROM ingestion_events
WHERE mission_id = 'YOUR_MISSION_ID'
ORDER BY created_at DESC;
```

---

## Troubleshooting

### Issue: "Module not found" error

**Fix**: Rebuild the backend:
```powershell
docker compose down
docker compose up -d --build backend
```

### Issue: Task creation fails with "TypeError: cannot unpack non-iterable PaperObject"

**Fix**: Ensure stage 1 (query expansion) returns a list of strings, not PaperObject instances.

### Issue: "No module named 'httpx'"

**Fix**: Rebuild and ensure requirements.txt is updated:
```powershell
docker compose build --no-cache backend
docker compose up -d backend
```

### Issue: Papers not appearing in database

**Fix**: 
1. Check backend logs: `docker logs lhas-backend --tail 50`
2. Verify mission_id is correct
3. Ensure ingestion completed successfully (`status: "success"`)

### Issue: LLM calls failing or hanging

**Fix**:
1. Verify LLM is configured and accessible
2. Check if API keys are set correctly
3. Monitor rate limiting

---

## Performance Tips

### Reduce Processing Time
1. Decrease `final_k` from 20 to 10-15
2. Use fewer sources: `sources = ["arxiv", "semantic_scholar"]`
3. Increase `mmr_lambda` from 0.6 to 0.8

### Improve Paper Quality
1. Increase `relevance_threshold` from 0.5 to 0.7
2. Set `mmr_lambda` lower (0.4-0.6) for more diversity
3. Use all 3 sources for broader coverage

### Monitor Costs
- Check `ingestion_events.total_llm_calls` and `total_llm_tokens`
- Try to keep **llm_calls < 15** per ingestion
- Total cost typically **< $0.01 per ingestion**

---

## Next Modules

Once paper ingestion is working:

1. **Module 3+**: Full-text extraction using GROBID
2. **Module 4**: Claim extraction and evidence linking
3. **Module 5**: Evidence synthesis and narrative generation
4. **FAISS Integration**: Enable semantic search on all papers

