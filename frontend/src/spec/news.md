# News Feed Search Feature Specification

## Purpose

Provide a unified, search-driven news feed that aggregates results from multiple backend news providers via a single API endpoint.  
The feature enables users to type a query, press Enter, and receive relevant news articles in the existing News Feed panel.

This layer performs **retrieval and display only**. No sentiment analysis, ranking, or deduplication is applied at this stage.

---

## Scope

### In Scope

- Keyword-based news search
- Aggregation across all configured providers
- Display of unified article results
- One-shot fetch with optional pagination
- Integration with existing workspace and News Feed panel

### Out of Scope

- Sentiment scoring
- Importance ranking
- Provider weighting
- Full-text article ingestion
- Authentication or personalization

## Backend Contract

### Endpoint

GET /news/search

### Query Parameters

| Name       | Type            | Required | Description                         |
|------------|-----------------|----------|-------------------------------------|
| `q`        | string          | yes      | Search query                        |
| `providers`| string[]        | no       | Provider names; omit to query all   |
| `limit`    | number          | no       | Articles per provider (default 20)  |

### Response

JSON array of unified articles.

```json
{
  "source": "string",
  "title": "string",
  "description": "string | null",
  "url": "string",
  "published_at": "string | number | null",
  "raw": "object"
}
```

Order is backend-defined. No guarantees beyond completeness.

## Frontend Architecture

### Data Flow

1. User enters a query and presses Enter.
2. Frontend issues `GET /news/search?q=<query>`.
3. Backend queries all registered providers.
4. Unified articles returned.
5. News Feed panel renders results.

## Trigger Mechanism

- Search is triggered **only** on Enter.
- Query originates from:
  - Command Palette input, or
  - News Feed panel search bar.
- Submitting a new query:
  - Replaces the current News Feed content.
  - Cancels any in-flight request.

## State Model

Each News Feed panel maintains its own state:

```ts
idle | loading | success | error
```

Stored data:

- `query: string`
- `articles: Article[]`
- `error?: string`

---

## Rendering Rules

For each article:

- Title (clickable, external link)
- Description (if present)
- Provider badge (`source`)
- Published timestamp (raw, unformatted initially)

Ordering:

- As received from backend
- No client-side sorting

---

## Pagination Strategy

Initial implementation:

- Single fetch per query (`limit` default)
- Optional “Load more” button:

  - Re-issues request with higher `limit`

Future-compatible with:

- Cursor-based pagination
- Provider-specific paging

---

## Error Handling

- Network failure → error state with retry affordance
- Partial provider failure → silently omitted
- Empty result set → explicit “No results” state

---

## Performance Constraints

- Abort previous request when a new query is submitted
- No polling
- No background refresh

---

## Files and Responsibilities

### New

- `frontend/src/lib/api/news.ts`
  Typed API client for `/news/search`.

- `frontend/src/hooks/useNewsSearch.ts`
  Encapsulates fetch logic and state.

- `frontend/spec/news-feed.md`
  This document.

### Existing (extended)

- `NewsFeed` panel component
  Renders results and manages query lifecycle.

---

## Design Principles

- Backend-agnostic
- Deterministic behavior
- Minimal UI state
- No hidden heuristics
- Replaceable downstream ranking layer

---

## Non-Goals (Explicit)

This feature does not attempt to:

- Decide relevance
- Infer sentiment
- Compare providers
- Normalize timestamps
- Persist results

Those concerns belong to later layers.
