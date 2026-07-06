# LHAS: Longitudinal Hypothesis & Analysis System

## Comprehensive Project Documentation

Team SP18: Shashank Kendre, Chinmay Jadhav, Aditya Nimbalkar, Aryan Lokare

---

## 1. Project Overview

LHAS stands for **Longitudinal Hypothesis & Analysis System**. It is an autonomous literature monitoring and evidence reasoning system designed to help researchers track how scientific conclusions evolve over time.

The core idea is simple:

> LHAS does not only summarize research papers. It remembers what the system believed before, reads new evidence, detects contradictions, updates belief confidence, and generates an auditable synthesis explaining why the conclusion changed.

Traditional tools can search papers, summarize PDFs, or answer questions. LHAS goes further by maintaining a persistent scientific memory and a versioned reasoning trail.

---

## 2. Problem Statement

Scientific literature grows faster than humans can manually review. Researchers may need to track hundreds or thousands of papers across time. The main problems are:

- New papers appear continuously.
- Existing review tools usually summarize isolated documents.
- Conclusions can change when new evidence appears.
- Contradictory findings are difficult to organize.
- Most AI tools do not maintain a persistent, auditable belief state.
- Researchers need to know not only what the conclusion is, but why it changed.

LHAS addresses this by turning literature review into a **stateful evidence control loop** instead of a one-time prompt response.

---

## 3. Objectives

The objectives of LHAS are:

- Understand a research question and convert it into a structured research mission.
- Retrieve relevant academic papers from multiple scholarly sources.
- Score, filter, and rank papers based on relevance and evidence quality.
- Extract structured scientific claims from papers.
- Store papers, claims, provenance, graph relationships, belief states, contradictions, and synthesis versions.
- Detect contradictions across claims and group them into topics.
- Revise the system belief over time using deterministic logic.
- Generate a human-readable synthesis from the evidence state.
- Monitor alignment, drift, staleness, bias, and contradiction backlog.
- Provide an auditable backend and dashboard-ready APIs.

---

## 4. Core Distinction / Moat

The greatest distinction of LHAS is:

> **Accountable change over time.**

LHAS is different from a normal chatbot because it does not simply produce an answer. It maintains a changing scientific state.

For a non-technical person:

> ChatGPT gives an answer. NotebookLM explains uploaded sources. LHAS tracks what the evidence says over time, remembers previous conclusions, detects contradictions, and explains why its belief changed.

The core moat is the combination of:

- persistent memory
- structured evidence graph
- contradiction handling
- belief revision
- synthesis versioning
- alignment monitoring
- audit trail

---

## 5. High-Level Architecture

The system is organized as a pipeline:

```text
User Research Question
        |
        v
Query Understanding
        |
        v
Paper Ingestion
        |
        v
Claim Extraction
        |
        v
Memory System
        |
        v
Contradiction Handling
        |
        v
Belief Revision
        |
        v
Synthesis Generation
        |
        v
Alignment Monitoring
        |
        v
Dashboard / User Output
```

Each module produces structured outputs that are stored in the database. Later modules consume these outputs instead of depending only on raw LLM responses.

---

## 6. Technology Stack

### Frontend

- React
- TypeScript
- Dashboard UI

### Backend

- FastAPI
- Python
- SQLAlchemy ORM
- asyncpg

### Database

- PostgreSQL 16
- Dockerized database service

### Scientific Processing

- GROBID for parsing scientific PDFs
- PubMed API for biomedical literature
- Semantic Scholar API for academic paper metadata
- arXiv API for preprints and technical papers

### AI / ML Models

- NVIDIA NIM LLM provider
- Default configured LLM: `deepseek-ai/deepseek-r1`
- Embedding model: `nvidia/llama-nemotron-embed-1b-v2`
- NLI model: `cross-encoder/nli-deberta-v3-small`
- Cross-encoder reranking model for retrieval refinement

---

## 7. Use Of Models And APIs

LHAS uses models at specific controlled checkpoints. The LLM is not the entire system. It is one component inside a larger rule-based and database-backed pipeline.

### NVIDIA NIM LLM

Used for:

- query understanding
- clarification generation
- query expansion
- claim extraction
- entity normalization
- selective paper verification
- uncertain claim verification
- contradiction semantic verification
- quantitative extraction from difficult tables/figures
- synthesis generation

The backend uses an adapter layer:

```text
LLMProvider
    -> NIMProvider
        -> NIMClient
            -> NVIDIA NIM OpenAI-compatible API
```

This makes the system provider-flexible. A future model provider can be swapped in without rewriting all module logic.

### Embedding Model

Embedding model:

```text
nvidia/llama-nemotron-embed-1b-v2
```

Used for:

- semantic paper filtering
- paper similarity
- chunk retrieval
- claim clustering
- MMR diversity selection
- synthesis drift detection
- alignment monitoring

An embedding converts text into a numerical vector. Similar meanings have similar vectors.

Similarity is calculated using cosine similarity:

```text
cosine_similarity(A, B) =
dot(A, B) / (norm(A) * norm(B))
```

### GROBID API

GROBID is used to parse PDFs into structured scientific text.

It extracts:

- title
- authors
- abstract
- body sections
- references
- metadata

This allows LHAS to process paper sections instead of raw PDF text.

### Scholarly APIs

LHAS retrieves papers from:

- arXiv
- PubMed
- Semantic Scholar

These APIs provide titles, abstracts, authors, DOI, publication dates, URLs, and source identifiers.

---

## 8. Backend API Design

The backend exposes module APIs through FastAPI.

Important API groups:

```text
/api/query
/api/papers
/api/claims
/api/memory
/api/belief
/api/contradictions
/api/synthesis
/api/monitoring
/api/dashboard
```

### Query API

Used for:

- understanding the research question
- generating clarification questions
- chat-style interaction
- LLM provider health checks

### Papers API

Used for:

- starting paper ingestion
- listing retrieved papers
- viewing paper details
- finding similar papers
- accessing paper embeddings

### Claims API

Used for:

- listing extracted claims
- retrieving curated findings
- showing evidence clusters
- displaying claim statistics
- inspecting provenance

### Memory API

Used for:

- mission snapshots
- provenance logs
- graph records
- synthesis history
- checkpoints

### Belief API

Used for:

- running belief revision
- retrieving current belief state
- handling review/escalation workflows

### Contradictions API

Used for:

- running contradiction detection
- listing contradiction pairs
- showing contradiction topics
- viewing severity and resolution status

### Synthesis API

Used for:

- generating synthesis
- retrieving synthesis versions
- explaining the final conclusion

### Monitoring API

Used for:

- running alignment monitoring
- generating alerts
- showing mission health
- detecting drift, bias, and staleness

### Dashboard API

Used for:

- mission overview
- paper counts
- claim counts
- timeline
- alerts
- results summary

---

## 9. Database Design

The database is central to LHAS. It is what makes the system stateful and auditable.

The database stores:

- mission records
- paper records
- claim records
- raw claim records
- provenance logs
- graph nodes and edges
- belief states
- belief revision records
- contradiction records
- synthesis versions
- monitoring snapshots
- alerts
- checkpoints

The database design follows this principle:

> Every important reasoning step should leave a record.

### Main Table Groups

#### Mission Tables

Examples:

- `missions`
- `sessions`
- `alerts`
- `query_analysis`

Purpose:

- store the research mission
- track status
- store query interpretation
- connect all downstream evidence to one mission

#### Paper Tables

Examples:

- `research_papers`
- `ingestion_events`

Purpose:

- store paper metadata
- store source URLs
- store abstract and parsed text
- store scores
- store embeddings
- log ingestion progress

#### Claim Tables

Examples:

- `research_claims`
- `reasoning_steps`
- `mission_timeline`

Purpose:

- store structured claims
- store confidence scores
- store claim type and direction
- track claim extraction and reasoning

#### Memory Tables

Examples:

- `memory_raw_paper_records`
- `memory_raw_claim_records`
- `memory_provenance_log`
- `memory_claim_version_ledger`
- `memory_canonical_entity_index`
- `memory_claim_graph_nodes`
- `memory_claim_graph_edges`
- `memory_mission_snapshots`
- `memory_synthesis_history`
- `memory_drift_metrics`
- `memory_mission_checkpoints`

Purpose:

- preserve raw inputs
- track changes
- store graph relationships
- maintain mission-level memory
- support rollback and auditing

#### Contradiction Tables

Examples:

- `contradiction_records`
- `contradiction_context_resolved_pairs`
- `contradiction_ambiguous_pairs`
- `contradiction_verification_calls`

Purpose:

- store confirmed contradictions
- store resolved false contradictions
- track ambiguous cases
- preserve verification decisions

#### Belief Tables

Examples:

- `belief_states`
- `belief_revision_records`
- `belief_escalations`

Purpose:

- store current belief
- store belief revision history
- store escalations when automatic reversal is unsafe

#### Synthesis Tables

Examples:

- `synthesis_answers`
- `memory_synthesis_history`
- `memory_synthesis_llm_calls`

Purpose:

- store current synthesis
- store version history
- log LLM calls and validation

#### Monitoring Tables

Examples:

- `monitoring_snapshots`
- `monitoring_alerts`

Purpose:

- store alignment metrics
- detect drift
- track mission health
- manage active and resolved alerts

---

## 10. Module 1: Query Understanding

### Purpose

Query Understanding converts a raw user question into a structured research mission.

Example raw query:

```text
Does metformin reduce cancer risk?
```

Structured output:

```text
intent_type: causal
population: patients / humans
intervention: metformin
comparison: placebo / no metformin
outcome: cancer risk
key_concepts: metformin, cancer, risk
search_queries: [...]
ambiguity_flags: [...]
confidence_score: 0.82
decision: PROCEED
```

### Logic

The module uses the LLM to identify:

- research intent
- PICO fields
- key concepts
- ambiguity
- possible interpretation variants
- search queries

Supported intent types:

- causal
- comparative
- exploratory
- descriptive

### Decision Logic

Possible decisions:

```text
PROCEED
PROCEED_WITH_CAUTION
NEED_CLARIFICATION
```

If confidence is high and ambiguity is low, the mission proceeds.

If ambiguity exists, the system may ask clarification questions.

If the LLM fails, fallback heuristic logic estimates confidence:

```text
confidence = max(0.3, 0.7 - 0.15 * number_of_ambiguity_flags)
```

---

## 11. Module 2: Paper Ingestion

### Purpose

Paper Ingestion retrieves, filters, scores, and stores academic papers.

It does not simply download papers. It qualifies papers through a multi-stage evidence selection process.

### Sources

- PubMed
- Semantic Scholar
- arXiv

### Default Configuration

```text
max_candidates = 200
prefilter_k = 100
final_k = 50
min_abstract_length = 100
mmr_lambda = 0.8
```

### Pipeline

```text
query expansion
    -> multi-source retrieval
    -> deduplication
    -> prefiltering
    -> CEGC scoring
    -> MMR selection
    -> full-text parsing
    -> database storage
```

### Deduplication

Papers are deduplicated using:

- DOI
- lowercased title

This avoids counting the same paper multiple times across PubMed, Semantic Scholar, and arXiv.

### Prefiltering

Filtering uses:

- abstract length
- embedding similarity
- keyword overlap fallback

The query and abstracts are embedded, then compared using cosine similarity.

### CEGC Paper Scoring

CEGC stands for a layered paper qualification score.

The approximate weighting is:

```text
PICO match              25%
Evidence strength       30%
Mechanism agreement     20%
Assumption alignment    15%
LLM verification        10%
```

The LLM verification layer is selective and used mainly for ambiguous papers.

### MMR Selection

MMR means Maximal Marginal Relevance.

It balances:

- relevance
- diversity

Formula idea:

```text
MMR = 0.8 * relevance + 0.2 * diversity
```

This prevents the final set from containing many nearly identical papers.

### Storage

Selected papers are stored in:

- `research_papers`
- `ingestion_events`

Stored fields include:

- title
- abstract
- authors
- source
- DOI
- URLs
- publication date
- relevance score
- usefulness score
- embedding similarity
- CEGC score
- embedding vector

---

## 12. Module 3: Claim Extraction

### Purpose

Claim Extraction turns selected papers into structured evidence units.

A paper may contain many statements. LHAS extracts only the statements that are relevant to the research mission.

### Input

- selected papers
- mission question
- PICO structure
- abstract
- full text or parsed chunks
- paper metadata

### Output

- raw claims
- curated findings
- provenance
- confidence
- graph nodes

### Pipeline

```text
retrieve relevant chunks
    -> Pass 1: evidence-grounded claim extraction
    -> grounding validation
    -> Pass 2A: claim classification
    -> Pass 2B: entity normalization
    -> verification
    -> Pass 3: confidence calculation
    -> validation / deduplication
    -> persistence
```

### Relevant Chunk Retrieval

The paper is divided into chunks:

- abstract
- introduction
- methods
- results
- discussion
- conclusion

Retrieval queries include:

- main mission query
- intervention-outcome query
- mechanism query
- null or negative evidence query
- limitation or uncertainty query

Embeddings retrieve the most relevant chunks before sending them to the LLM.

### Claim Fields

Each claim stores:

```text
statement_raw
source_chunk_ids
evidence_span
grounding_confidence
intervention
outcome
direction
hedging_text
section_source
extraction_certainty
claim_type
verification_status
composite_confidence
```

### Direction Values

Possible directions:

```text
positive
negative
null
unclear
```

### Claim Types

Possible claim types:

```text
causal
correlational
mechanistic
comparative
safety
prevalence
null_result
```

### Grounding Validation

The system checks that the evidence span actually appears in the source chunk.

This reduces hallucination risk.

### Verification Labels

Possible verification outcomes:

```text
true
partial
uncertain
false
hallucination
overgeneralization
scope_drift
unsupported
contradiction
```

### Composite Claim Confidence

The system calculates claim confidence using multiple factors.

Formula idea:

```text
base = (study_design_score - hedging_penalty) * extraction_certainty

composite_confidence =
base
* verification_factor
* grounding_factor
* verification_confidence
* section_factor
* support_factor
* quantitative_factor
```

The result is clamped:

```text
minimum = 0.05
maximum = 0.95
```

### Study Design Scores

Approximate values:

```text
meta_analysis     0.92
RCT               0.90
cohort            0.72
case_control      0.68
observational     0.65
review            0.55
animal_model      0.40
in_vitro          0.30
unknown           0.50
```

### Hedging Penalties

Examples:

```text
may / might / possible               0.20 penalty
suggests / associated with / appears 0.12 penalty
```

### Section Factors

Evidence from different paper sections has different importance:

```text
results       1.08
conclusion    1.06
abstract      1.03
discussion    0.98
body          0.96
introduction  0.92
methods       0.88
unknown       0.95
```

---

## 13. Module 4: Memory System

### Purpose

The Memory System makes LHAS stateful.

It stores:

- raw papers
- raw claims
- curated claims
- provenance
- graph nodes
- graph edges
- mission snapshots
- synthesis versions
- drift metrics
- checkpoints

The memory system is what separates LHAS from a one-time summarizer.

### Provenance

Every important event is logged.

Examples:

```text
claim_created
claim_linked
claim_confidence_revised
belief_state_updated
synthesis_version_created
monitoring_alert_firing
```

### Claim Graph

Claims become graph nodes.

Relationships become graph edges.

Possible edge types:

```text
SUPPORTS
CONTRADICTS
REPLICATES
REFINES
IS_SUBGROUP_OF
```

### Edge Weight Formula

Formula idea:

```text
confidence_product = confidence_A * confidence_B
study_design_delta = abs(study_score_A - study_score_B)

edge_weight =
confidence_product
* recency_weight
* (1 - 0.3 * study_design_delta)
```

### Recency Weight

```text
paper age <= 5 years    1.0
paper age >= 10 years   0.5
missing date            0.75
```

### Mission Snapshots

Snapshots store mission state at a cycle:

```text
cycle number
paper count
claim count
active contradictions
belief statement
belief confidence
belief direction
synthesis version
```

### Checkpoints

Checkpoints preserve:

- graph state
- entity index
- processed paper IDs
- last synthesis
- belief state

This supports auditability and recovery.

---

## 14. Module 5: Contradiction Handling

### Purpose

Contradiction Handling detects when two claims disagree.

It also prevents false contradictions caused by different populations, dosages, study conditions, or study designs.

### Pipeline

```text
load new claims
    -> retrieve candidate pairs
    -> direction opposition check
    -> context reconciliation
    -> semantic verification
    -> severity scoring
    -> storage and topic grouping
```

### Candidate Retrieval

Candidate pairs are found by:

- same canonical intervention
- same canonical outcome
- embedding similarity fallback

Embedding similarity threshold:

```text
>= 0.82
```

### Direction Opposition

Opposed direction pairs include:

```text
positive vs negative
positive vs null
negative vs null
```

### Contextual Reconciliation

Before declaring contradiction, the system checks:

- population difference
- dosage difference
- duration difference
- condition difference
- co-intervention difference
- study design asymmetry

Example:

```text
Claim A: Drug X works in adults.
Claim B: Drug X does not work in children.
```

This may be context difference, not a contradiction.

### Study Design Asymmetry

If two papers disagree but one has much stronger study design, the system may resolve the pair as a study-design asymmetry.

Formula:

```text
score_delta = abs(study_score_A - study_score_B)
```

If score delta is large enough, the stronger claim is favored.

### LLM Semantic Verification

After deterministic checks, the LLM classifies the pair:

```text
GENUINE_CONTRADICTION
COMPATIBLE
AMBIGUOUS
```

### Severity Logic

Severity depends on:

- confidence product
- quality parity
- population overlap
- evidence strength

Formula idea:

```text
confidence_product = confidence_A * confidence_B
quality_parity = abs(study_score_A - study_score_B)
```

Severity:

```text
HIGH    if strong claims conflict under similar context
MEDIUM  if conflict is meaningful but not decisive
LOW     if claims are weak or quality gap is large
```

### Topic Grouping

Contradiction pairs are grouped into broader topics using canonical intervention and outcome.

This explains:

```text
59 contradiction pairs -> 2 topics
```

Meaning:

Many pair-level conflicts exist, but they concentrate around two main scientific disagreement areas.

---

## 15. Module 6: Belief Revision

### Purpose

Belief Revision updates what LHAS currently believes about the mission.

Belief is not a paragraph. It is a structured internal state:

```text
belief_statement
direction
confidence
cycle_number
revision_type
drift_trend
```

### Belief vs Synthesis

Belief:

```text
internal machine-readable evidence state
```

Synthesis:

```text
human-readable explanation of that state
```

Simple line:

> Belief decides what the system currently thinks. Synthesis explains why it thinks that.

### Inputs

Belief revision uses:

- previous belief state
- new claims
- claim confidence
- study design score
- metadata completeness
- contradiction records
- graph relationships
- mission snapshots

### Claim Intake Filter

Claims may be excluded if:

```text
composite_confidence < 0.20
canonical intervention missing
validation status is degraded
study design consistency fails
claim is unsupported or hallucinated
```

### Incoming Weight

Each claim is weighted:

```text
claim_weight =
composite_confidence
* study_design_score
* metadata_completeness
```

Batch incoming weight:

```text
incoming_weight =
sum(composite_confidence * study_weight) / sum(study_weight)
```

### Incoming Direction

The module counts directions:

```text
positive
negative
null
mixed
```

If one direction dominates by more than 70%, that becomes the incoming direction.

Otherwise:

```text
incoming_direction = mixed
```

### Contradiction Penalty

Contradictions reduce confidence:

```text
LOW       confidence * 0.97
MEDIUM    confidence * 0.90
HIGH      confidence * 0.75
```

### Revision Types

Possible revision types:

```text
REINFORCE
WEAK_REINFORCE
WEAKEN
MATERIAL_UPDATE
ESCALATE_FOR_REVIEW
REVERSAL
CONTRADICTION_PENALTY
NO_UPDATE
```

### Decision Logic

If new evidence agrees with current belief:

```text
new_confidence = old_confidence + incoming_weight * 0.08
revision_type = REINFORCE
```

If new evidence weakly agrees:

```text
new_confidence = old_confidence + incoming_weight * 0.03
revision_type = WEAK_REINFORCE
```

If new evidence weakly disagrees:

```text
new_confidence = old_confidence - incoming_weight * 0.06
revision_type = WEAKEN
```

If strong new evidence disagrees:

```text
new_confidence = old_confidence * 0.65
new_direction = mixed
revision_type = MATERIAL_UPDATE
```

If very strong opposing evidence arrives:

```text
revision_type = ESCALATE_FOR_REVIEW
```

After approval or strong confirmation:

```text
revision_type = REVERSAL
```

### Safety Guards

Confidence is bounded:

```text
minimum confidence = 0.05
maximum confidence = 0.95
maximum rise per cycle = +0.12
maximum drop per cycle = -0.25
```

This prevents unstable jumps.

---

## 16. Module 7: Synthesis Generation

### Purpose

Synthesis Generation creates the final human-readable conclusion.

It does not directly ask the LLM:

```text
What is the answer?
```

Instead, the system first builds a structured evidence package, then asks the LLM to write from that evidence.

### Inputs

Synthesis uses:

- current belief state
- mission question
- curated claims
- claim scores
- contradiction records
- graph relationships
- previous synthesis version
- revision type
- drift trend

### Pipeline

```text
load mission state
    -> assemble evidence package
    -> group claims into clusters
    -> rank claims
    -> split into evidence tiers
    -> add contradictions
    -> assign confidence tier
    -> generate synthesis with LLM
    -> validate output
    -> store version
```

### Evidence Score

Formula:

```text
evidence_score =
composite_confidence
* study_design_score
* recency_weight
* mission_relevance_weight
* metadata_completeness_factor
```

### Evidence Tiers

Claims are split into:

```text
Tier 1: strongest evidence
Tier 2: supporting evidence
Tier 3: weaker or peripheral evidence
```

### Confidence Tier

The system maps numeric confidence into readable language:

```text
confidence < 0.30                  WEAK
confidence < 0.50                  MIXED
confidence < 0.75                  MODERATE
confidence >= 0.75                 STRONG
```

But direction matters. If direction is mixed, the synthesis remains cautious even if numeric confidence is moderate.

For example:

```text
0.71 mixed belief confidence
```

Means:

```text
mixed evidence with moderate confidence
```

Not:

```text
strong positive evidence
```

### Validation

After LLM generation, the system checks:

- length
- contradiction acknowledgment
- confidence language
- consistency with belief direction
- limitation coverage
- topic relevance

If validation fails, the system can regenerate or use a fallback template.

### Versioning

Each synthesis is stored as a version.

This explains:

```text
2 synthesis versions
```

Meaning:

The conclusion was generated or updated twice, and both versions are preserved.

---

## 17. Module 8: Alignment Monitoring

### Purpose

Alignment Monitoring acts as a watchdog.

It checks whether the system is behaving responsibly over time.

It monitors:

- confidence drift
- synthesis drift
- contradiction backlog
- stale evidence
- retrieval bias
- belief oscillation
- evidence drought
- unacknowledged contradictions

### Inputs

Alignment monitoring reads:

- belief revisions
- synthesis history
- mission snapshots
- contradiction records
- paper records
- claim records
- monitoring history

### Outputs

It writes:

- monitoring snapshots
- monitoring alerts
- mission health
- timeline events
- provenance logs

### Confidence Trajectory Monitoring

The system compares actual confidence movement with evidence-justified movement.

Formula idea:

```text
trajectory_divergence =
abs(actual_confidence_velocity - evidence_justified_velocity)
```

If divergence is too high:

```text
UNJUSTIFIED_CONFIDENCE_DRIFT
```

### Synthesis Drift Monitoring

The system compares synthesis versions using embeddings.

If synthesis changes heavily without enough new evidence:

```text
UNJUSTIFIED_DRIFT
```

### Contradiction Monitoring

Tracks:

```text
active_contradiction_count
contradiction_topic_count
contradiction_arrival_rate
acknowledgment_rate
```

Possible alerts:

```text
CONTRADICTION_BACKLOG
UNACKNOWLEDGED_HIGH_SEVERITY
CONTRADICTION_SPIKE
```

### Evidence Balance Monitoring

Checks whether retrieval is biased toward one side.

Possible alert:

```text
RETRIEVAL_BIAS_SUSPECTED
```

### Freshness Monitoring

Checks whether the evidence base is stale.

Possible alerts:

```text
STALE_EVIDENCE_BASE
EVIDENCE_DROUGHT
RECENCY_INVERSION
```

### Mission Health

Overall mission health may be:

```text
HEALTHY
WATCH
DEGRADED
CRITICAL
```

---

## 18. Results Explanation

Poster results:

```text
91 papers ingested
74 raw claims -> 72 curated findings
74 graph nodes / 202 edges
59 contradiction pairs -> 2 topics
2 synthesis versions
0.71 mixed belief confidence
```

### 91 Papers Ingested

The system retrieved and qualified 91 papers through the ingestion pipeline.

This means they passed source retrieval, deduplication, filtering, scoring, and storage.

### 74 Raw Claims -> 72 Curated Findings

The system extracted 74 initial claims from papers.

After validation, grounding, deduplication, and curation, 72 remained as usable findings.

This means only 2 were filtered or merged.

### 74 Graph Nodes / 202 Edges

The graph contains:

```text
74 nodes = evidence claims
202 edges = relationships between claims
```

Edges can represent:

```text
supports
contradicts
replicates
refines
subgroup relationship
```

### 59 Contradiction Pairs -> 2 Topics

The system detected 59 pair-level contradictions.

But these contradictions grouped into only 2 main scientific topics.

Meaning:

> The disagreement is not random. It is concentrated around two major evidence areas.

### 2 Synthesis Versions

The system generated two versions of the final explanation.

This shows that LHAS supports versioned scientific conclusions.

### 0.71 Mixed Belief Confidence

This means:

```text
confidence = 0.71
direction = mixed
```

The system has moderate confidence in the evidence state, but the evidence does not point in one clean direction.

Important:

It does not mean:

```text
the claim is 71% true
```

It means:

```text
LHAS is 0.71 confident in its current mixed belief state
```

---

## 19. Difference From ChatGPT

ChatGPT can answer questions and summarize information, but it usually does not:

- ingest papers through a controlled academic pipeline
- store every paper and claim in a database
- calculate claim confidence
- build an evidence graph
- detect contradictions across many claims
- revise belief over time
- preserve synthesis versions
- monitor drift and alignment

Simple answer:

> ChatGPT gives a response. LHAS maintains a scientific memory and updates its belief as evidence changes.

---

## 20. Difference From NotebookLM

NotebookLM is useful for chatting with uploaded sources.

However, LHAS is different because it:

- searches and ingests papers from scholarly APIs
- scores and filters papers
- extracts structured claims
- maintains a belief state
- detects contradictions
- groups contradiction topics
- revises confidence mathematically
- generates versioned synthesis
- monitors evidence drift over time

Simple answer:

> NotebookLM helps understand a source collection. LHAS manages an evolving evidence system.

---

## 21. Difference From ChatGPT + NotebookLM Combined

Even if someone uses ChatGPT and NotebookLM together, they still need to manually:

- decide which papers matter
- track what changed
- compare claim directions
- detect contradictions
- calculate confidence
- update belief over time
- store versions
- audit reasoning

LHAS automates and structures that entire loop.

Best jury line:

> ChatGPT and NotebookLM are answer tools. LHAS is an evidence governance system.

---

## 22. End-To-End Example Flow

Example mission:

```text
Does intervention X improve outcome Y?
```

### Step 1: Query Understanding

The system extracts:

```text
Population
Intervention
Comparison
Outcome
Intent
Search queries
```

### Step 2: Paper Ingestion

The system searches PubMed, Semantic Scholar, and arXiv.

It retrieves papers, deduplicates them, embeds abstracts, filters irrelevant papers, scores them, and stores selected papers.

### Step 3: Claim Extraction

The system parses paper text, retrieves relevant chunks, and extracts structured claims.

Example:

```text
Claim: X improves Y in adults.
Direction: positive
Confidence: 0.82
Study design score: 0.90
```

### Step 4: Memory System

The claim becomes a graph node.

If it supports another claim, a support edge is added.

If it conflicts, a contradiction edge may be added.

### Step 5: Contradiction Handling

The system compares claims.

It checks whether conflicts are genuine or caused by context differences.

### Step 6: Belief Revision

The system updates:

```text
direction
confidence
revision type
drift trend
```

### Step 7: Synthesis Generation

The system writes a human-readable conclusion using the current belief and ranked evidence.

### Step 8: Alignment Monitoring

The system checks whether confidence, synthesis, contradiction handling, and evidence freshness are still aligned.

---

## 23. Presentation Flow

If problem statement, introduction, and objectives are already done, the recommended presentation flow is:

```text
1. System architecture
2. Module walkthrough
3. Technical stack
4. Database and backend
5. Results
6. Distinction from existing tools
7. Limitations
8. Future scope
9. Conclusion
```

### Suggested Module Distribution

Member 1:

- Query Understanding
- Paper Ingestion

Member 2:

- Claim Extraction
- Memory System
- Backend / Database

Member 3:

- Belief Revision
- Contradiction Handling

Member 4:

- Synthesis Generation
- Alignment Monitoring
- Results and conclusion

---

## 24. Limitations

Possible limitations:

- LLM outputs still require validation.
- Paper access depends on source availability.
- Full-text extraction may fail for some PDFs.
- Contradiction detection depends on correct entity normalization.
- Evidence confidence is a model of reliability, not absolute truth.
- Benchmarking against expert systematic reviews would improve validation.
- Some fields may require domain-specific scoring adjustments.

---

## 25. Future Scope

Possible future improvements:

- add more scholarly sources
- support clinical trial registries
- improve citation graph integration
- add human expert review interface
- add domain-specific scoring profiles
- improve contradiction visualization
- add automated scheduled literature updates
- add multi-mission comparison
- export systematic review reports
- integrate reference managers like Zotero or Mendeley
- add stronger benchmark evaluation against expert reviews

---

## 26. Conclusion

LHAS demonstrates that autonomous literature monitoring can be built as a stateful, auditable control loop.

The system does not stop at summarization. It:

- understands the research mission
- retrieves and qualifies papers
- extracts claims
- builds memory
- detects contradictions
- revises belief
- generates synthesis
- monitors alignment

The key innovation is not only using AI to read papers, but using AI inside a controlled system that remembers, calculates, verifies, and explains how scientific conclusions evolve.

Final presentation line:

> **LHAS turns literature review from a one-time summary into a living, auditable evidence system.**

