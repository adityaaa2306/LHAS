# LHAS Frontend UI SPECIFICATIONS - Next-Generation Capabilities

**Date:** March 29, 2026  
**Status:** PRODUCTION SPECIFICATION  
**Components:** 5 Next-Gen Capabilities  

---

## Overview

This specification describes the frontend UI updates required to display and interact with the 5 next-generation capabilities integrated into the LHAS backend. The updates focus on:

1. **Enhanced Claims Explorer Card** - Display uncertainty decomposition and confidence components
2. **Evidence Gap Detection UI** - Show detected gaps and retrieval suggestions
3. **Entity Evolution Workflow** - Modal for entity merges and new entity approval
4. **Failure-Driven Learning Dashboard** - Prompt performance and domain adaptation tracking
5. **Argument Coherence Panel** - Display coherence conflicts and confidence adjustments

---

## 1. Enhanced Claims Explorer Card

### 1.1 Card Layout

```
┌─────────────────────────────────────────────────────────────────┐
│ CLAIM EXCERPT                                      [CONFIDENCE]  │
├─────────────────────────────────────────────────────────────────┤
│ Direction: [POS|NEG|NULL]  │  Type: [CAUSAL|CORR...]             │
└─────────────────────────────────────────────────────────────────┘
│ PICO:                                                             │
│  Population:     Intervention:     Outcome:                       │
├─────────────────────────────────────────────────────────────────┤
│ ENTITIES:          [CANONICAL FORM] - Status: [confirmed]        │
│  Intervention:     [canonical_intervention] [status badge]       │
│  Outcome:         [canonical_outcome] [status badge]             │
├─────────────────────────────────────────────────────────────────┤
│ CONFIDENCE BREAKDOWN:                          [% gauge]         │
│  ┌─ COMPOSITE: 0.68 (target: 0.65-0.85)                         │
│  │  • Extraction: 0.72 (extraction × verification × grounding)   │
│  │  • Study: 0.65 (design × causal × consistency)               │
│  │  • Generalizability: 0.80 (1.0 - deductions)                 │
│  │  • Replication: 0.62 (+/- paper relationships)               │
│  └─ COMPOSITE: √(E×S×G×R) = 0.68                                │
├─────────────────────────────────────────────────────────────────┤
│ COHERENCE CHECK:      [passed ✓ | conflict ✗]                   │
│  ┌─ No internal direction conflicts detected                     │
│  └─ Coherence multiplier: 1.0x                                  │
├─────────────────────────────────────────────────────────────────┤
│ EXTRACTION METADATA:                                              │
│  • Prompt version: v3_enhanced_pico                              │
│  • Extraction logged: Nov 8, 2025 ✓                              │
│  • Verification logged: Nov 9, 2025 ✓                            │
│  • Glossary version: 2 (updated Oct 15)                          │
├─────────────────────────────────────────────────────────────────┤
│ [View Details]  [Edit Entity]  [Share]  [Archive]               │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 Confidence Breakdown Panel

**When user clicks "View Details":**

```
┌──────────────────────────────────────────────────────────────────┐
│ CONFIDENCE DECOMPOSITION - CLAIM #1234567890                     │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│ COMPOSITE CONFIDENCE:  68%  ████████░░                           │
│ Target Range:          65-85%                                    │
│                                                                   │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│ 1. EXTRACTION UNCERTAINTY (72%)                                  │
│    ├─ Extraction certainty:     0.850  ←─ LLM confidence       │
│    ├─ Verification confidence:  0.920  ←─ Passed verification   │
│    ├─ Grounding quality:        0.850  ←─ Found in text         │
│    └─ Coherence adjustment:     1.000  ←─ No conflicts          │
│    RESULT: 0.85 × 0.92 × 0.85 × 1.0 = 0.72                     │
│                                                                   │
│ 2. STUDY UNCERTAINTY (65%)                                       │
│    ├─ Study design score:       0.650  ←─ RCT = high            │
│    ├─ Causal factor:           0.850  ←─ Causal claim          │
│    └─ Consistency factor:       0.940  ←─ Consistent w/ design  │
│    RESULT: 0.65 × 0.85 × 0.94 = 0.65                           │
│                                                                   │
│ 3. GENERALIZABILITY UNCERTAINTY (80%)                            │
│    ├─ Base:                     1.000                             │
│    ├─ Population deduction:    -0.000  ←─ Broad population      │
│    ├─ Scope deduction:         -0.150  ←─ Not fully general     │
│    ├─ Conflict deduction:      -0.050  ←─ Some internal conflict│
│    └─ Animal deduction:        -0.000  ←─ Human study           │
│    RESULT: 1.0 - 0.0 - 0.15 - 0.05 - 0.0 = 0.80                │
│                                                                   │
│ 4. REPLICATION UNCERTAINTY (62%)                                 │
│    ├─ Base score:              0.500                              │
│    ├─ Supporting papers:       +0.150 ←─ 2 replications (+0.075)│
│    ├─ Contradicting papers:   -0.100 ←─ 1 contradiction (-0.100)│
│    └─ Isolated claims:        +0.050 ←─ Moderate overlap        │
│    RESULT: 0.5 + 0.15 - 0.1 + 0.05 = 0.62                       │
│                                                                   │
├──────────────────────────────────────────────────────────────────┤
│ FINAL COMPOSITE:                                                  │
│ √(0.72 × 0.65 × 0.80 × 0.62) = √(0.226) = 0.68                 │
│                                                                   │
│ STATUS: ✓ Within acceptable range (0.65-0.85)                   │
│                                                                   │
│ [Export Report]  [Share with Team]  [Audit Trail]  [Close]      │
└──────────────────────────────────────────────────────────────────┘
```

### 1.3 Entity Status Badge Styles

| Status | Badge Style | Color | Icon |
|--------|-----------|-------|------|
| `confirmed` | Rounded pill | Green | ✓ |
| `merge_candidate` | Rounded pill | Orange | ⚠ |
| `new_entity_pending` | Rounded pill | Blue | ★ |
| `rejected` | Strikethrough | Gray | ✗ |

---

## 2. Evidence Gap Detection UI

### 2.1 Gap Detection Alert Panel

**Location:** Top of Claims Explorer, appears when gaps detected

```
┌───────────────────────────────────────────────────────────────────┐
│ ⚠ EVIDENCE GAPS DETECTED - 3 gaps identified in 7 claim clusters   │
├───────────────────────────────────────────────────────────────────┤
│                                                                    │
│ GAP 1: POPULATION_EXPANSION                      [View] [Ignore]   │
│  Found 12 claims about "adults" but none about "children"         │
│  Suggested Query: "effects of [intervention] in pediatric cases"   │
│                                                                    │
│ GAP 2: OUTCOME_VARIATION                        [View] [Ignore]   │
│  Cluster has 8 claims on "symptom reduction" but 0 on "mortality" │
│  Suggested Query: "[intervention] mortality outcomes randomized"   │
│                                                                    │
│ GAP 3: TIMEFRAME_DEFICIT                        [View] [Ignore]   │
│  All 5 claims have <6 month follow-up periods                     │
│  Suggested Query: "[intervention] long-term effects >12 months"    │
│                                                                    │
│ [View All Gaps]  [Run Suggested Queries]  [Dismiss All]           │
└───────────────────────────────────────────────────────────────────┘
```

### 2.2 Gap Details Modal

**When user clicks "View All Gaps":**

```
┌────────────────────────────────────────────────────────────────────┐
│ EVIDENCE GAP ANALYSIS REPORT                      [Export] [Close]  │
├────────────────────────────────────────────────────────────────────┤
│                                                                     │
│ Total Gaps Detected: 3                                              │
│ Affected Claim Clusters: 7/24                                       │
│ Gap Coverage: 87%                                                   │
│                                                                     │
├────────────────────────────────────────────────────────────────────┤
│                                                                     │
│ ▶ GAP 1: POPULATION_EXPANSION (12 claims cluster)                  │
│   Status Breakdown:                                                 │
│   ├─ Claims about ADULTS:     12 ✓✓✓✓✓✓✓✓✓✓✓✓                   │
│   ├─ Claims about CHILDREN:    0                                   │
│   ├─ Claims about ELDERS:      3 ✓✓✓                              │
│   └─ Claims about other:       2 ✓✓                               │
│                                                                     │
│   Gap Type: Missing population segment                              │
│   Confidence Impact: -0.15  (reduces generalizability)             │
│   Retrieval Priority: HIGH                                          │
│                                                                     │
│   Suggested Queries:                                                │
│   🔎 "[intervention] children pediatric ages 0-18"                │
│   🔎 "[intervention] adolescent teenager youth"                   │
│   🔎 "[intervention] pediatric randomized trial"                  │
│                                                                     │
│   [Run Queries]  [Mark Resolved]  [Snooze 1 Week]                  │
│                                                                     │
│ ▶ GAP 2: OUTCOME_VARIATION (8 claims cluster)                      │
│   ...                                                               │
│                                                                     │
│ [Export Gap Report]  [Schedule Retrieval]  [Close]                 │
└────────────────────────────────────────────────────────────────────┘
```

---

## 3. Entity Evolution Workflow UI

### 3.1 Operator Review Queue

**Location:** Right sidebar, Entity Management section

```
┌──────────────────────────────────────────────────┐
│ ENTITY REVIEW QUEUE                 [↻ Refresh]  │
├──────────────────────────────────────────────────┤
│                                                  │
│ Pending Reviews: 5                               │
│                                                  │
│ ▢ MERGE CANDIDATES (2)                           │
│   ┌─────────────────────────────────────────┐   │
│   │ "ACE inhibitor" ←→ "ACE-I"              │   │
│   │ Seen in: 12 papers | Confidence: 0.92   │   │
│   │ [Review Merge]                          │   │
│   └─────────────────────────────────────────┘   │
│   ┌─────────────────────────────────────────┐   │
│   │ "Hypertension" ←→ "High Blood Pressure" │   │
│   │ Seen in: 8 papers | Confidence: 0.88    │   │
│   │ [Review Merge]                          │   │
│   └─────────────────────────────────────────┘   │
│                                                  │
│ ▢ NEW ENTITIES (3)                               │
│   ┌─────────────────────────────────────────┐   │
│   │ "SGLT2i" (Seen in 5 papers)              │   │
│   │ Surface forms: SGLT2 inhibitor, SGLT2i  │   │
│   │ [Approve] [Reject]                      │   │
│   └─────────────────────────────────────────┘   │
│   ┌─────────────────────────────────────────┐   │
│   │ "Empagliflozin" (Seen in 3 papers)       │   │
│   │ [Approve] [Reject]                      │   │
│   └─────────────────────────────────────────┘   │
│   ┌─────────────────────────────────────────┐   │
│   │ "Cardiovascular mortality" (Seen in 2)   │   │
│   │ [Approve] [Reject]                      │   │
│   └─────────────────────────────────────────┘   │
│                                                  │
│ Status: 0 auto-promoted this session             │
└──────────────────────────────────────────────────┘
```

### 3.2 Merge Decision Modal

**When user clicks "Review Merge":**

```
┌────────────────────────────────────────────────────────────┐
│ ENTITY MERGE DECISION                              [Close]  │
├────────────────────────────────────────────────────────────┤
│                                                             │
│ Should these be merged?                                     │
│                                                             │
│   "ACE inhibitor"   ←→   "ACE-I"                            │
│                                                             │
│ ┌─────────────────────────────────────────────────────┐   │
│ │ LEFT (Canonical form)                               │   │
│ │ Entity: "ACE inhibitor"                              │   │
│ │ Type: drug / intervention                            │   │
│ │ Confidence: 0.95                                      │   │
│ │ Surface forms (5): ACE inhibitor, ACEi, ACE-I..     │   │
│ │ Seen in papers: 12                                   │   │
│ │ Glossary version: 2                                  │   │
│ └─────────────────────────────────────────────────────┘   │
│                                                             │
│ ┌─────────────────────────────────────────────────────┐   │
│ │ RIGHT (Candidate for merge)                          │   │
│ │ Entity: "ACE-I"                                       │   │
│ │ Type: drug / intervention                            │   │
│ │ Confidence: 0.88                                      │   │
│ │ Surface forms (3): ACE-I, ACEI, Angiotensin...      │   │
│ │ Seen in papers: 8                                    │   │
│ │ Glossary version: 2                                  │   │
│ └─────────────────────────────────────────────────────┘   │
│                                                             │
│ Recommendation: ✓ MERGE (88% confidence)                   │
│ Reason: Same semantic meaning, one is abbreviation         │
│                                                             │
│ Proposed result:                                            │
│ • Canonical: "ACE inhibitor"                               │
│ • Surface forms: ACE inhibitor, ACE-I, ACEi, ACEI...      │
│ • Confidence: MAX(0.95, 0.88) = 0.95                       │
│ • Status: confirmed                                        │
│ • Affects 20 claims across 18 papers                       │
│                                                             │
│ Re-normalization: Claims using "ACE-I" will be updated    │
│                 Claims flagged: 8 (20 total)               │
│                                                             │
│ [✓ Accept Merge]  [✗ Reject]  [Cancel]                    │
└────────────────────────────────────────────────────────────┘
```

### 3.3 New Entity Approval Modal

**When user clicks "Approve" on new entity:**

```
┌────────────────────────────────────────────────────────────┐
│ NEW ENTITY APPROVAL                              [Close]    │
├────────────────────────────────────────────────────────────┤
│                                                             │
│ Approve new entity to glossary?                             │
│                                                             │
│ Entity: "SGLT2i"                                            │
│ Type: drug / intervention                                   │
│ Classification Confidence: 0.92                             │
│                                                             │
│ Surface forms detected (4):                                 │
│ • SGLT2i         (seen in 3 papers)                        │
│ • SGLT2 inhibitor (seen in 2 papers)                       │
│ • SGLT2-inhibitor (seen in 1 paper)                        │
│ • SGLT2i therapy  (seen in 1 paper)                        │
│                                                             │
│ First appearance:                                           │
│ • Paper: "EMPA-HEART study"  (Nov 8, 2025)                │
│ • Context: "...benefit of SGLT2i in heart failure..."     │
│                                                             │
│ Impact:                                                      │
│ • Will auto-match 5 current claims                          │
│ • Will apply to 5 surface forms across 4 papers            │
│ • Auto-promotion eligible after 3 papers                   │
│ • Glossary entry: will become "confirmed" status           │
│                                                             │
│ [✓ Approve]  [✗ Reject]  [✓ Mark Auto-Acceptable]         │
│                                                             │
│ If marked auto-acceptable, similar future entities will    │
│ be auto-approved by the system (recommended if confident)  │
│                                                             │
│ [✓ Approve]  [✗ Reject]                                    │
└────────────────────────────────────────────────────────────┘
```

---

## 4. Failure-Driven Learning Dashboard

### 4.1 Dashboard Overview

**Location:** New tab "A/B Testing" in main navigation

```
┌────────────────────────────────────────────────────────────────┐
│ FAILURE-DRIVEN LEARNING DASHBOARD             [Refresh] [Export] │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│ PROMPT PERFORMANCE COMPARISON                                   │
│                                                                 │
│ v1_baseline        v2_pico_enhanced  v3_coherence_check        │
│ ┌──────────────┐   ┌──────────────┐  ┌──────────────┐         │
│ │ Pass Rate:   │   │ Pass Rate:   │  │ Pass Rate:   │         │
│ │  64% ████    │   │  72% █████░  │  │  79% ██████░ │         │
│ │              │   │              │  │              │         │
│ │ Passes:  128 │   │ Passes:  144 │  │ Passes:  158 │         │
│ │ Fails:    72 │   │ Fails:    56 │  │ Fails:    42 │         │
│ │ Total:   200 │   │ Total:   200 │  │ Total:   200 │         │
│ └──────────────┘   └──────────────┘  └──────────────┘         │
│                                                                 │
│ PERFORMANCE TREND (Last 30 days)                               │
│                                                                 │
│ Pass Rate                                                       │
│  80% ┤                              ╱▔▔▔               (v3)   │
│  70% ┤          ╱▔╲                ╱                           │
│  60% ┤        ╱┘   ▔▔╲            ╱    (v2)                    │
│  50% ┤    ╱▔▔          ▔▔╲       ╱                             │
│      ├──────────────────────────────────────                   │
│      │ 1d  3d  7d  14d  21d  30d                               │
│                                                                 │
│ v1 (baseline) - DEPRECATED: 64% ▔▔▔                           │
│ v2 (enhanced)  - ACTIVE:    72% ━━━                           │
│ v3 (coherence) - NEW:       79% ▄▄▄ recommended for promotion │
│                                                                 │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│ FAILURE BREAKDOWN                                               │
│                                                                 │
│ Top error types (v3_coherence_check):                          │
│ ❌ PICO_EXTRACTION_FAILED:      14 failures (8.9%)            │
│ ❌ COHERENCE_CONFLICT:           12 failures (7.6%) ← new!    │
│ ❌ ENTITY_NOT_FOUND:             8 failures (5.1%)            │
│ ❌ VERIFICATION_FAILED:          5 failures (3.2%)            │
│ ❌ DIRECTION_UNCLEAR:             3 failures (1.9%)           │
│ ✓  Other:                         0 failures                   │
│                                                                 │
│ [View Failure Details]  [View Section Quality]                │
│                                                                 │
│ SECTION QUALITY ADJUSTMENT                                     │
│                                                                 │
│ Section pass rates are used to weight section retrieval        │
│                                                                 │
│ Abstract:      87% pass rate  →  weight: 1.0x  ↑️ improving  │
│ Results:       79% pass rate  →  weight: 0.9x                │
│ Discussion:    64% pass rate  →  weight: 0.7x  ↓️ declining  │
│ Conclusion:    72% pass rate  →  weight: 0.8x                │
│                                                                 │
│ [Apply Weights]  [Reset to Defaults]  [View History]         │
│                                                                 │
│ ┌─────────────────────────────────────────────────────────┐  │
│ │ RECOMMENDATION                                          │  │
│ │                                                         │  │
│ │ ✓ PROMOTE v3_coherence_check to ACTIVE                │  │
│ │ Reason: +15% improvement over v2, significant reduction│  │
│ │         in coherence-related failures                  │  │
│ │                                                         │  │
│ │ Confidence: MEDIUM (79% > 70% threshold, diff > 5%)  │  │
│ │ Impact: All new claims will use v3 starting today     │  │
│ │ Rollback available for 30 days                         │  │
│ │                                                         │  │
│ │ [✓ Accept Promotion]  [✗ Reject]  [Schedule Later]   │  │
│ └─────────────────────────────────────────────────────────┘  │
│                                                                 │
└────────────────────────────────────────────────────────────────┘
```

---

## 5. Argument Coherence Panel

### 5.1 Coherence Check Result Badge

**Displayed on claim card:**

```
┌─────────────────────────────────────────┐
│ COHERENCE CHECK:     ✓ Passed            │ ← Green if passed
│ Internal conflicts:  0 detected          │
│ Confidence adj:      1.0x (no change)    │
│                                         │
│ [View Details]                          │
└─────────────────────────────────────────┘

OR (if conflicts detected)

┌─────────────────────────────────────────┐
│ COHERENCE CHECK:     ✗ Conflict Found    │ ← Red if issues
│ Internal conflicts:  1 detected          │
│ - Direction conflict w/ claim #7 (-0.2x) │
│ Confidence adj:      0.8x (reduced)      │
│                                         │
│ [View Details]  [Review Conflict]       │
└─────────────────────────────────────────┘
```

### 5.2 Coherence Details Modal

**When user clicks "View Details":**

```
┌──────────────────────────────────────────────────────────────┐
│ ARGUMENT COHERENCE ANALYSIS               [Export] [Close]    │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│ Paper: "Effects of Drug X on Blood Pressure"                 │
│                                                               │
│ COHERENCE CHECKS:                                             │
│                                                               │
│ 1. INTERNAL DIRECTION CONFLICT                               │
│    Status: ✗ CONFLICT DETECTED                               │
│                                                               │
│    Claim #7 (POSITIVE direction):                            │
│    "Drug X reduced blood pressure by 8mmHg"                  │
│    (Abstract, verified)                                       │
│                                                               │
│    Claim #12 (NEGATIVE direction):                           │
│    "Drug X increased diastolic pressure in subgroup"         │
│    (Discussion, hedged)                                       │
│                                                               │
│    Analysis:                                                  │
│    • Primary claims show consistent effect (positive)        │
│    • Subgroup analysis shows opposite direction             │
│    • Subgroup is well-characterized (N=45, age>65)         │
│    • This is coherent science: differential effects         │
│    • Confidence adjustment: -0.20x (accounts for nuance)    │
│                                                               │
│ 2. SCOPE ESCALATION CHECK                                    │
│    Status: ✓ PASSED                                          │
│                                                               │
│    • All claims within same study population                │
│    • No unjustified generalization detected                 │
│                                                               │
│ 3. EXTRACTION CONSISTENCY CHECK                              │
│    Status: ✓ PASSED                                          │
│                                                               │
│    • All claims properly grounded in source text            │
│    • No missing context that would change meaning           │
│                                                               │
│ OVERALL COHERENCE ASSESSMENT:                                │
│                                                               │
│   Coherence Status: COHERENT WITH NUANCE                     │
│   Confidence Multiplier: 0.80x (was 1.0x)                    │
│   Impact on composite confidence:                             │
│     OLD: Extraction × Study × Gen = 0.68                     │
│     NEW: (Extraction × 0.80) × Study × Gen = 0.54            │
│                                                               │
│   Reasoning: The direction conflict is scientifically        │
│   sound (differential subgroup effects) but represents       │
│   increased certainty requirements for claim acceptance.     │
│                                                               │
│ [Accept Analysis]  [Flag for Review]  [Adjust Multiplier]  │
│                                                               │
│ [Export Analysis]  [Close]                                   │
└──────────────────────────────────────────────────────────────┘
```

---

## 6. Component Integration in Existing UI

### 6.1 Claims Explorer Updates

**Before:** Simple claim card  
**After:** Enhanced card with:
- New "Confidence Breakdown" tab
- Entity status badges with merge workflow access
- Coherence check indicator
- Extraction metadata

### 6.2 Sidebar Updates

**New "Entity Review Queue"** section showing:
- # of pending reviews
- Merge candidates
- New entities
- Quick approve/reject

### 6.3 Main Navigation Updates

**New tab: "A/B Testing"** for Failure-Driven Learning Dashboard

### 6.4 Alert System Updates

**New: Evidence Gap alerts** appear at top when gaps detected

---

## 7. Data Flow & API Contracts

### 7.1 Enhanced Claim Response

```json
{
  "id": "claim-123",
  "statement_raw": "Drug X reduced blood pressure",
  "composite_confidence": 0.68,
  "confidence_components": {
    "extraction_uncertainty": 0.72,
    "study_uncertainty": 0.65,
    "generalizability_uncertainty": 0.80,
    "replication_uncertainty": 0.62
  },
  "coherence_check": {
    "passed": false,
    "flags": ["INTERNAL_DIRECTION_CONFLICT"],
    "coherence_confidence_adjustment": 0.80
  },
  "entity_evolution": {
    "intervention_canonical": "Drug X",
    "intervention_status": "confirmed",
    "outcome_canonical": "systolic blood pressure",
    "outcome_status": "merge_candidate",
    "glossary_version": 2
  },
  "failure_logging": {
    "pass1_prompt_version": "v3_coherence_check",
    "verification_failure_logged": false,
    "verification_success_logged": true
  }
}
```

### 7.2 Evidence Gap Entity

```json
{
  "id": "gap-001",
  "mission_id": "mission-123",
  "cluster_id": "cluster-adults-bp",
  "gap_type": "POPULATION_EXPANSION",
  "cluster_claim_count": 12,
  "suggestion_query": "drug X children pediatric ages 0-18",
  "detected_at": "2026-03-29T22:30:00Z"
}
```

---

## 8. Accessibility & Responsive Design

### 8.1 Mobile Responsive

- Confidence breakdown available via accordion
- Entity review queue accessible via modal
- Gap alerts collapsible with full details modal

### 8.2 Accessibility (WCAG 2.1 Level AA)

- All badges use color + text/icons (not color-only)
- High contrast for all important information
- Keyboard navigation for modals
- Screen reader friendly confidence components

### 8.3 Data Visualization

- Use approved color palettes for gauges
- All charts have text equivalents
- Number formatting: 0.68 (2 decimal places)
- Abbreviations defined on first use

---

## 9. Implementation Priority

### Phase 1 (Week 1): Core UI Updates
- Enhanced Claims Card with confidence breakdown
- Entity Evolution workflow (merge + approve)
- Coherence check indicator

### Phase 2 (Week 2): Dashboards
- Evidence Gap detection panel
- Failure-Driven Learning dashboard
- A/B testing interface

### Phase 3 (Week 3): Polish & Integration
- Responsive mobile design
- Accessibility audit
- Integration tests
- User acceptance testing

---

## 10. Testing Checklist

- [ ] Claims card renders with all new fields
- [ ] Confidence breakdown calculation accurate
- [ ] Entity merge flow works end-to-end
- [ ] Evidence gaps display correctly
- [ ] A/B testing dashboard updates in real-time
- [ ] All modals keyboard navigable
- [ ] Mobile layout responsive
- [ ] Accessibility tests pass (WCAG AA)
- [ ] API responses match contracts
- [ ] Error states handled gracefully

---

**Status:** READY FOR DEVELOPMENT  
**Approval:** Pending  
**Next:** Frontend Development Sprint
