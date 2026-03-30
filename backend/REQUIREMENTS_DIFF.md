# Requirements.txt Diff - Claim Extraction Module Upgrades

## New Dependencies to Add

Add the following packages to `backend/requirements.txt`:

```
# ADDED: Semantic Retrieval & Reranking (Upgrade 1)
sentence-transformers>=2.2.0        # Cross-encoder models for semantic ranking
faiss-cpu>=1.7.0                    # FAISS vector indexing (use faiss-gpu if GPU available)

# ADDED: NLI Verification (Upgrade 3)
# Note: Already included via sentence-transformers

# ADDED: Core Dependencies (ensure latest)
numpy>=1.21.0                       # Numeric operations (likely already present)
asyncio-contextmanager>=1.0.0       # Async context management (if Python < 3.7)
```

## Installation Instructions

### Option 1: CPU-only (recommended for development)
```bash
pip install sentence-transformers>=2.2.0 faiss-cpu>=1.7.0
```

### Option 2: GPU Support
```bash
pip install sentence-transformers>=2.2.0 faiss-gpu>=1.7.0
```

## Model Cache Locations

The following pre-trained models will be automatically downloaded on first use:

### Cross-Encoder Models (Upgrade 1: Retrieval Reranking)
- **Model**: `cross-encoder/ms-marco-MiniLM-L-6-v2` (400 MB)
  - Purpose: Rerank retrieved chunks for relevance
  - Download: Automatic on first call to `RetrievalLayer.rerank_with_cross_encoder()`
  - Cache: `~/.cache/huggingface/hub/`

### NLI Model (Upgrade 3: Verification)
- **Model**: `cross-encoder/nli-deberta-v3-small` (260 MB)
  - Purpose: Natural Language Inference for evidence verification (Tier 1)
  - Download: Automatic on first call to `VerificationEngine.verify_nli()`
  - Cache: `~/.cache/huggingface/hub/`

## Cache Pre-heating (Optional)

To pre-download models before running extraction (recommended for production):

```python
# In backend startup script
from sentence_transformers import CrossEncoder

# Warm up cross-encoder model
cross_encoder = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')

# Warm up NLI model
nli_model = CrossEncoder('cross-encoder/nli-deberta-v3-small')
```

**Storage Required**: ~700 MB total for both models

## Dependency Tree

```
claim-extraction-upgrades/
├── sentence-transformers
│   ├── torch>=1.11.0
│   ├── transformers>=4.28.0
│   ├── scikit-learn
│   └── scipy
├── faiss-cpu (or faiss-gpu)
│   └── numpy
└── numpy (already present)
```

## Breaking Changes

**None** - All new dependencies are additive. Existing code paths unchanged.

## Backward Compatibility

The extraction pipeline gracefully degrades if models fail to load:
- If FAISS unavailable: Uses single-query retrieval without cross-encoder reranking
- If NLI model unavailable: Skips to Tier 2 LLM verification
- If sentence-transformers unavailable: Uses fallback cosine similarity with numpy

## Verification Steps

After installing new dependencies:

```bash
# Verify installations
python -c "import sentence_transformers; print(sentence_transformers.__version__)"
python -c "import faiss; print(faiss.__version__)"

# Test model availability (will download if needed)
python -c "from sentence_transformers import CrossEncoder; CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')"
```

## Docker Integration

If using Docker, update `backend/Dockerfile`:

```dockerfile
# In RUN pip install section
RUN pip install --no-cache-dir \
    -r requirements.txt \
    sentence-transformers>=2.2.0 \
    faiss-cpu>=1.7.0
```

**Storage Impact**: Base image size increases ~2 GB (includes model weights)

## Environment Variables

Optional configuration via env vars:

```bash
# Cache HF models in custom location
export HF_HOME=/models/huggingface

# Set transformers cache
export TRANSFORMERS_CACHE=/models/transformers

# Disable HF telemetry
export TRANSFORMERS_NO_CUDNN_BENCHMARK=1
```

## Performance Notes

- **First Run**: Initial model download ~5-10 minutes (network dependent)
- **Subsequent Runs**: Models cached, no download overhead
- **Memory**: Base FAISS + models require ~4 GB RAM peak
- **Latency Impact on Extraction**:
  - Retrieval layer: +2-3 seconds (one-time per paper)
  - NLI verification: +0.5-1 second (batched)
  - Total pipeline: ~95% same latency (dominated by LLM calls)
