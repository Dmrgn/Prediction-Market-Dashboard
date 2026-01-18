# Researcher Frontend Implementation Plan

**Goal:** Display Researcher sentiment results in the sidebar (right panel reserved for "agentic activities")

---

## Codebase Analysis

### Existing Architecture (Reusable)

| Component | File | Purpose |
|-----------|------|---------|
| `Sidebar` | `App.tsx` | Right-side floating panel via shadcn |
| `AgentStatus` | `components/dashboard/AgentStatus.tsx` | Shows events in sidebar |
| `useAgentStore` | `hooks/useAgentStore.ts` | Zustand store for agent events |
| `backendInterface` | `backendInterface.ts` | REST API helpers (`fetchJson`, `buildUrl`) |
| `useUIStore` | `hooks/useUIStore.ts` | Sidebar open/close state |

### Current Sidebar Content
```tsx
<Sidebar side="right" variant="floating">
  <SidebarContent>
    <AgentStatus />  <!-- Only shows AgentEvent[] list -->
  </SidebarContent>
</Sidebar>
```

---

## Proposed Changes

### 1. Backend Interface

#### [MODIFY] [backendInterface.ts](file:///c:/Users/varak/Documents/CODE/Projects/Hard%20Projects/OddBase/frontend/src/backendInterface.ts)

Add sentiment API type and method:
```typescript
// Type
type SentimentReport = {
  market_id: string;
  query: string;
  score: number;
  signal: "bullish" | "bearish" | "neutral";
  summary: string;
  articles_analyzed: number;
  top_positive: string[];
  top_negative: string[];
  generated_at: string;
};

// Method
fetchSentiment: async (marketId: string, query?: string): Promise<SentimentReport> =>
  fetchJson<SentimentReport>(buildUrl(`/markets/${marketId}/sentiment`, { q: query })),
```

---

### 2. Researcher Store

#### [NEW] [useResearcherStore.ts](file:///c:/Users/varak/Documents/CODE/Projects/Hard%20Projects/OddBase/frontend/src/hooks/useResearcherStore.ts)

Zustand store for research state:
```typescript
interface ResearcherState {
  report: SentimentReport | null;
  status: "idle" | "loading" | "success" | "error";
  error: string | null;
  query: string;
  setQuery: (q: string) => void;
  fetchReport: (marketId: string, query: string) => Promise<void>;
  clear: () => void;
}
```

---

### 3. Researcher Sidebar Component

#### [NEW] [ResearcherPanel.tsx](file:///c:/Users/varak/Documents/CODE/Projects/Hard%20Projects/OddBase/frontend/src/components/dashboard/ResearcherPanel.tsx)

A sidebar-friendly component:
- Search input for query
- "Analyze" button
- Loading skeleton
- Result card showing:
  - Score gauge/indicator
  - Signal badge (bullish/bearish/neutral)
  - 2-sentence summary
  - Top positive/negative headlines (collapsible)

```tsx
export function ResearcherPanel() {
  const { report, status, query, setQuery, fetchReport, clear } = useResearcherStore();
  // ... render UI
}
```

---

### 4. Update Sidebar Layout

#### [MODIFY] [App.tsx](file:///c:/Users/varak/Documents/CODE/Projects/Hard%20Projects/OddBase/frontend/src/App.tsx)

Add tabs to sidebar for switching between Agent Activity and Researcher:

```tsx
<Sidebar side="right" variant="floating">
  <SidebarHeader>
    {/* Tab buttons: Agent | Research */}
  </SidebarHeader>
  <SidebarContent>
    {activeTab === "agent" && <AgentStatus />}
    {activeTab === "research" && <ResearcherPanel />}
  </SidebarContent>
</Sidebar>
```

---

## File Summary

| Action | File |
|--------|------|
| MODIFY | `src/backendInterface.ts` - Add `SentimentReport` type + `fetchSentiment()` |
| NEW | `src/hooks/useResearcherStore.ts` - Zustand store for research state |
| NEW | `src/components/dashboard/ResearcherPanel.tsx` - Sidebar UI component |
| MODIFY | `src/App.tsx` - Add tab navigation in sidebar |

---

## Verification Plan

### Manual Testing
1. Start backend: `cd backend && uv run python -m uvicorn app.main:app --reload --port 8001`
2. Start frontend: `cd frontend && bun dev`
3. Open browser at `http://localhost:3000`
4. Click sidebar trigger (right side of header)
5. Switch to "Research" tab
6. Enter query (e.g., "Bitcoin ETF") and click Analyze
7. Verify loading state appears
8. Verify result shows score, signal badge, and summary

### Visual Checks
- Signal badge colors: green (bullish), red (bearish), gray (neutral)
- Summary text is readable
- Headlines expand/collapse correctly
- Responsive in narrow sidebar

---

## Design Notes

- **Why tabs?** Keeps sidebar duties separate (agentic logs vs. on-demand research)
- **Reuse patterns**: Follows `NewsFeedPanel.tsx` conventions for loading/error states
- **API call**: Uses existing `backendInterface` pattern for consistency
- **Store pattern**: Matches `useAgentStore` zustand conventions
