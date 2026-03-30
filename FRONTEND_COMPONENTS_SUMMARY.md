# ✅ FRONTEND COMPONENTS - MODULE 3 CLAIM EXTRACTION

**Status**: COMPLETE | **Date**: March 29, 2026

---

## 📂 FILES CREATED/MODIFIED

### New Components
- [frontend/src/components/ClaimsExplorer.tsx](../../frontend/src/components/ClaimsExplorer.tsx) — Production-grade claims display component

### New Hooks & Services
- [frontend/src/hooks/useClaimEvents.ts](../../frontend/src/hooks/useClaimEvents.ts) — Event subscription hook
- [frontend/src/services/eventBridge.ts](../../frontend/src/services/eventBridge.ts) — WebSocket event bridge

### Updated Files
- [frontend/src/pages/MissionDetailPage.tsx](../../frontend/src/pages/MissionDetailPage.tsx) — Integrated ClaimsExplorer
- [frontend/src/App.tsx](../../frontend/src/App.tsx) — Initialize event bridge on app load

---

## 🎨 CLAIMS EXPLORER COMPONENT

**Location**: `frontend/src/components/ClaimsExplorer.tsx`

### Features

✅ **Full Claim Listing with Pagination**
- Fetches claims directly from `/api/claims/mission/{mission_id}`
- 20 claims per page with next/previous navigation
- Real-time total count updates

✅ **Advanced Filtering System**
- Filter by claim type (causal, correlational, mechanistic, etc.)
- Filter by direction (positive, negative, null, unclear)
- Confidence range slider (min/max)
- Validation status filter (VALID, EXTRACTION_DEGRADED, UNKNOWN_TYPE)
- Reset all filters button

✅ **Statistics Dashboard**
- Fetches from `/api/claims/mission/{mission_id}/stats`
- Total claims count
- Valid vs degraded claim breakdown
- Quality percentage
- Average confidence score
- Confidence distribution (percentiles)
- Type distribution
- Direction distribution
- Normalization quality percentage

✅ **Rich Claim Visualization**
- **Claim Card**:
  - Normalized statement text (high-contrast display)
  - Epistemic type badge with color coding
  - Direction indicator (icon + label)
  - Confidence score as large percentage with quality label
  - Validation status icon
  - Section source badge
  - Downgrade indicator (if applicable)

- **Expanded Details** (click to expand):
  - **Pass 1**: Intervention, Outcome, Population, Hedging text
  - **Pass 2b**: Canonical entity mapping with confidence
  - **Pass 3**: Confidence breakdown (study design, certainty, overall)
  - **Metadata**: Mission relevance, study design consistency, validation status

✅ **Color-Coded Confidence Visualization**
- Green 80%+: High confidence
- Blue 60-80%: Medium confidence
- Yellow 40-60%: Low confidence
- Red <40%: Very low confidence

✅ **Type-Based Coloring**
- Causal: Red badge
- Correlational: Orange badge
- Mechanistic: Purple badge
- Comparative: Blue badge
- Safety: Pink badge
- Prevalence: Green badge
- Null Result: Gray badge

✅ **Error Handling & Loading States**
- Loading spinner while fetching
- Error messages with context
- Empty state messaging

### API Integration

**Endpoints Used**:
```
GET /api/claims/mission/{mission_id}
  - Query params: skip, limit, claim_type, direction, min_confidence, max_confidence, validation_status
  - Returns: paginated claim list with metadata

GET /api/claims/mission/{mission_id}/stats
  - Returns: Statistics summary with confidence distribution
```

---

## 🪝 EVENT SUBSCRIPTION HOOK

**Location**: `frontend/src/hooks/useClaimEvents.ts`

### Usage

```typescript
import { useClaimEvents } from '@/hooks/useClaimEvents';

const MyComponent = () => {
  const { onClaimsExtracted, onPipelineDegraded } = useClaimEvents();

  useEffect(() => {
    // Listen for claims extraction from specific mission
    const unsubscribe = onClaimsExtracted('mission-123', (data) => {
      console.log(`${data.claim_count} claims extracted for paper ${data.paper_id}`);
      // Refresh claims list, update UI, etc.
    });

    return unsubscribe;
  }, [onClaimsExtracted, missionId]);
};
```

### Events Supported

**claims:extracted**
```json
{
  "mission_id": "uuid",
  "paper_id": "uuid",
  "claim_count": 5,
  "claim_ids": ["id1", "id2", ...],
  "timestamp": "2026-03-29T..."
}
```

**pipeline:degraded**
```json
{
  "mission_id": "uuid",
  "paper_id": "uuid",
  "reason": "All claims failed validation",
  "pass1_candidates": 3,
  "errors": ["error message 1", ...],
  "timestamp": "2026-03-29T..."
}
```

---

## 🌉 EVENT BRIDGE SERVICE

**Location**: `frontend/src/services/eventBridge.ts`

### How It Works

1. **Singleton Pattern**:
   - Single instance per app
   - Lazy initialization via `getEventBridge()`

2. **WebSocket Connection**:
   - Connects to `ws://localhost:8000/ws/events`
   - Automatic reconnection (up to 5 attempts, exponential backoff)
   - Graceful fallback if unavailable

3. **Event Subscription**:
   - `on(eventType, callback)` registers listener
   - Returns unsubscribe function
   - Multiple handlers per event type supported

4. **Initialization**:
   - Call `initializeEventBridge()` on app startup
   - Non-blocking: continues if connection fails
   - Logs warnings but doesn't crash

### Example Integration

```typescript
// In App.tsx or main component
useEffect(() => {
  initializeEventBridge();
}, []);

// In any component
const bridge = getEventBridge();
const unsubscribe = bridge.on('claims:extracted', (data) => {
  console.log(`${data.claim_count} claims ready`);
});
```

---

## 🔌 APP INITIALIZATION

**Updated**: `frontend/src/App.tsx`

```typescript
useEffect(() => {
  // Initialize real-time event bridge on app load
  initializeEventBridge().catch(error => {
    console.warn('Event bridge initialization failed...', error);
  });
}, []);
```

**Behavior**:
- Runs once on app mount
- Non-blocking: doesn't prevent app from loading
- Warns user if connection fails, app continues
- Real-time updates available if connection succeeds

---

## 🔄 INTEGRATION WITH MISSION DETAIL PAGE

**Updated**: `frontend/src/pages/MissionDetailPage.tsx`

### Before
```typescript
<ClaimsExplorerCard claims={claims} />
```

### After
```typescript
<ClaimsExplorer missionId={missionId || ''} />
```

**Key Differences**:
- Old: Used local state claims array (stale, limited data)
- New: Fetches fresh data from API (real-time, complete)
- Old: Only showed first 6 claims
- New: Full pagination, filtering, statistics
- Old: Basic display
- New: Rich visualization with expandable details

---

## 🎯 USER WORKFLOWS

### View All Extracted Claims
1. Navigate to Mission Detail page
2. ClaimsExplorer loads automatically
3. See statistics dashboard at top
4. Browse claims with pagination
5. Click claim to see full details

### Filter Claims
1. Click "Filters" button
2. Set filter criteria (claim type, confidence, etc.)
3. Filters apply immediately
4. Reset button clears all filters

### Inspect Claim Details
1. Click any claim card to expand
2. See Pass 1-3 breakdown
3. View confidence components
4. Check metadata and validation status
5. Click again to collapse

### Real-Time Updates (When Extraction Runs)
1. Event bridge receives `claims:extracted` event
2. Frontend components listening via `useClaimEvents`
3. Can trigger refresh or local state updates
4. Users see new claims appear in real-time

---

## 📊 DATA FLOW

```
Backend:
  ClaimExtractionService
    ↓
  ResearchClaim (persisted)
    ↓
  Event: claims.extracted
    ↓
  Frontend
    ↓
  EventBridge (WebSocket)
    ↓
  Components listening via useClaimEvents
    ↓
  ClaimsExplorer fetches fresh data
    ↓
  UI displays updated claims list
```

---

## 🧪 TESTING CHECKLIST

- [ ] Backend API endpoints respond correctly
  - [ ] GET /api/claims/mission/{id} returns paginated claims
  - [ ] GET /api/claims/{claim_id} returns full details
  - [ ] GET /api/claims/mission/{id}/stats returns statistics

- [ ] Frontend loads claims
  - [ ] ClaimsExplorer appears on Mission Detail page
  - [ ] Statistics dashboard displays correctly
  - [ ] Claims list populates with data

- [ ] Filtering works
  - [ ] Claim type filter works
  - [ ] Direction filter works
  - [ ] Confidence slider works
  - [ ] Validation status filter works
  - [ ] Reset filters clears all

- [ ] Pagination works
  - [ ] Previous/Next buttons navigate
  - [ ] Shows correct range
  - [ ] Buttons disabled at boundaries

- [ ] Claim expansion works
  - [ ] Click expands to show details
  - [ ] Shows all Pass 1-3 fields
  - [ ] Confidence breakdown displays
  - [ ] Click again collapses

- [ ] Event system works
  - [ ] EventBridge connects to WebSocket (optional)
  - [ ] useClaimEvents hook subscribes successfully
  - [ ] Events trigger callbacks

---

## 🚀 PERFORMANCE CONSIDERATIONS

✅ **Optimizations Implemented**:
- Pagination (20 claims per page, not all)
- Async loading states
- Memoized callbacks
- Separate stats query
- Efficient re-renders

⚠️ **Potential Improvements**:
- Virtual scrolling for very large lists
- Local caching of claims
- Debounce filter changes
- Lazy load claim details
- Indexed database queries

---

## 📝 NEXT STEPS

1. ✅ Start Docker containers
2. ✅ Run database migrations
3. ✅ Ingest sample papers
4. ✅ Extract claims via API
5. [ ] Verify API endpoints respond
6. [ ] Test frontend loads Claims Explorer
7. [ ] Verify filtering works
8. [ ] Test claim expansion
9. [ ] Monitor backend logs for errors

---

## 🔗 RELATED FILES

- **Backend API**: [backend/app/api/claims.py](../../backend/app/api/claims.py)
- **Database Models**: [backend/app/models/claims.py](../../backend/app/models/claims.py)
- **Extraction Service**: [backend/app/services/claim_extraction.py](../../backend/app/services/claim_extraction.py)
- **Mission Detail Page**: [frontend/src/pages/MissionDetailPage.tsx](../../frontend/src/pages/MissionDetailPage.tsx)

