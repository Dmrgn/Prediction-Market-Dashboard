# News Ranking System Implementation Plan

## Executive Summary

This document outlines a comprehensive plan for implementing a robust news article ranking system for the Prediction Market Dashboard. The system must handle asynchronous news fetching from multiple providers, rank articles by relevance and recency, and provide real-time updates to the frontend as results arrive from different sources.

The current implementation has a critical bug: the `rank.py` module was deleted, but `api.py` still imports `rank_articles` from it, causing server crashes. This plan addresses that immediate issue while also designing a more sophisticated and balanced ranking system that doesn't artificially favor any single news source.

---

## Table of Contents

1. [Current Architecture Analysis](#current-architecture-analysis)
2. [Problem Statement](#problem-statement)
3. [Design Goals](#design-goals)
4. [Technical Specification](#technical-specification)
5. [Implementation Details](#implementation-details)
6. [Ranking Algorithm](#ranking-algorithm)
7. [Streaming Architecture](#streaming-architecture)
8. [Testing Strategy](#testing-strategy)
9. [Rollout Plan](#rollout-plan)
10. [Future Enhancements](#future-enhancements)

---

## Current Architecture Analysis

### Backend Components

The news fetching system consists of several interconnected components:

#### 1. News Provider Modules (`backend/app/news/`)

Each provider has its own module that implements a `fetch_*` function with a consistent signature:

```python
def fetch_provider(query: str, limit: int = 20, **kwargs) -> List[Dict]
```

Current providers:
- **EXA.ai** (`exa.py`): AI-curated search, high quality results, returns `url` field directly
- **GDELT 2.0** (`gd.py`): High volume global news database, fast response times
- **Newsdata.io** (`nd.py`): General news API, reliable but rate-limited
- **CryptoPanic** (`cpanic.py`): Crypto-focused news aggregator

Each provider normalizes its response to a common article format:
```python
{
    "source": str,        # Provider name
    "title": str,         # Article headline
    "description": str,   # Snippet or summary
    "url": str,           # Link to original article
    "published_at": str,  # ISO timestamp or Unix timestamp
    "raw": dict,          # Original API response for debugging
}
```

#### 2. News Fetcher (`backend/app/news/fetcher.py`)

The `NewsFetcher` class serves as a dispatcher that:
- Registers provider fetch functions at module load time
- Provides synchronous parallel fetching via `ThreadPoolExecutor`
- Yields results as each provider completes via `fetch_multiple_iter()`

Key implementation detail: The fetcher uses `concurrent.futures.as_completed()` to yield results in completion order, not registration order. This means faster APIs (typically GDELT) return first, followed by slower ones (EXA, Newsdata).

```python
with ThreadPoolExecutor(max_workers=len(valid_providers)) as executor:
    future_to_provider = {
        executor.submit(fetch_from_provider, provider): provider
        for provider in valid_providers
    }
    for future in as_completed(future_to_provider):
        provider = future_to_provider[future]
        result = future.result()
        yield provider, result
```

#### 3. API Endpoint (`backend/app/api.py`)

The `/news/search` endpoint supports two modes:
- **Non-streaming**: Waits for all providers, ranks, returns JSON array
- **Streaming (SSE)**: Yields ranked results as each provider completes

The streaming mode is critical for user experience. As each provider completes:
1. New articles are added to the accumulated pool
2. The entire pool is re-ranked
3. A new SSE event is sent to the frontend
4. The frontend re-renders with the updated, re-ranked list

### Frontend Components

#### 1. News Search Hook (`frontend/src/hooks/useNewsSearch.ts`)

This hook manages the SSE connection lifecycle:
- Opens EventSource connection to `/news/search?stream=true`
- Listens for `update` and `done` events
- Updates React state on each event
- Handles cleanup on query change or unmount

#### 2. News Feed Panel (`frontend/src/components/panels/NewsFeedPanel.tsx`)

Renders the article list. Currently:
- Maps over `state.articles` array
- Each article is an `<a>` tag linking to `article.url`
- Shows source badge and timestamp
- **Bug identified**: Articles render in whatever order they arrive from the backend

---

## Problem Statement

### Immediate Issues

1. **Missing `rank.py` Module**: The file was deleted but `api.py` still imports `rank_articles`. This causes an `ImportError` on server startup or first request.

2. **No Ranking Logic**: Without ranking, articles appear in random order based on which API completes first and how each API orders its results internally.

3. **Source Dominance**: Previous ranking implementations either:
   - Favored high-volume sources (GDELT) due to sheer quantity
   - Favored high-quality sources (EXA) due to artificial score boosts
   - Neither approach provided balanced, relevant results

### Underlying Design Flaws

1. **Static Source Weights**: Assigning fixed quality scores to sources is arbitrary and doesn't reflect actual article quality.

2. **Over-engineered Interleaving**: Round-robin interleaving forced artificial diversity that ignored relevance, resulting in lower-quality articles appearing high in the list.

3. **Single Ranking Pass**: The previous implementation re-ranked on each provider completion but used the same algorithm. No consideration for whether earlier results should be "locked in" to prevent jarring UI changes.

---

## Design Goals

### Primary Goals

1. **Relevance First**: Articles that best match the user's query should rank highest, regardless of source.

2. **Recency Matters**: More recent articles should generally rank higher, but not at the expense of relevance.

3. **Source Agnostic**: No hardcoded source preferences. Let article quality speak for itself.

4. **Stable Rankings**: As new results arrive, existing articles shouldn't jump around unnecessarily. Users should be able to read and click on early results.

5. **Progressive Enhancement**: First results appear fast (from GDELT), then improve in quality as slower, higher-quality APIs respond.

### Secondary Goals

1. **Deduplication**: Same article from multiple sources should appear once.

2. **Quality Signals**: Use heuristics (title length, all-caps detection) to filter low-quality articles.

3. **Debuggability**: Include score breakdowns in article objects for debugging.

---

## Technical Specification

### New `rank.py` Module

The module will export a single function with this signature:

```python
def rank_articles(
    articles: List[Dict],
    query: str = "",
    dedupe: bool = True,
    limit: Optional[int] = None,
) -> List[Dict]
```

#### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `articles` | `List[Dict]` | required | List of article dicts from providers |
| `query` | `str` | `""` | User's search query for relevance scoring |
| `dedupe` | `bool` | `True` | Remove duplicate articles by URL |
| `limit` | `int | None` | `None` | Maximum articles to return |

#### Return Value

Returns a new list of articles, each augmented with:
- `_score`: Composite ranking score (0.0 to 1.0)
- `_relevance`: Query relevance component
- `_recency`: Recency component
- `_quality`: Title quality component

### Scoring Components

#### 1. Query Relevance (50% weight)

This is the most important factor. We use term frequency matching:

```python
def calculate_relevance(query: str, title: str, description: str) -> float:
    query_terms = tokenize(query)
    title_terms = tokenize(title)
    
    # Count matches
    matches = sum(1 for t in query_terms if t in title_terms)
    
    # Exact phrase bonus
    phrase_bonus = 0.2 if query.lower() in title.lower() else 0.0
    
    # Normalize
    if not query_terms:
        return 0.5
    return min((matches / len(query_terms)) * 0.8 + phrase_bonus, 1.0)
```

#### 2. Recency (35% weight)

Uses exponential decay with a 48-hour half-life:

```python
def calculate_recency(published_at: str) -> float:
    ts = parse_timestamp(published_at)
    if ts <= 0:
        return 0.3  # Unknown timestamp gets middle-low score
    
    age_hours = (now() - ts) / 3600
    half_life = 48  # hours
    
    return 0.5 ** (age_hours / half_life)
```

This means:
- Article from now: 1.0
- Article from 48 hours ago: 0.5
- Article from 96 hours ago: 0.25
- Article from 1 week ago: ~0.06

#### 3. Title Quality (15% weight)

Heuristic checks for spam/low-quality titles:

```python
def calculate_title_quality(title: str) -> float:
    score = 1.0
    
    # Penalize ALL CAPS (often clickbait)
    if title.isupper():
        score *= 0.6
    
    # Penalize very short titles
    if len(title) < 15:
        score *= 0.7
    
    # Penalize excessive punctuation
    if title.count("!") > 2 or title.count("?") > 2:
        score *= 0.8
    
    return score
```

### Composite Score

```python
score = (relevance * 0.50) + (recency * 0.35) + (quality * 0.15)
```

No source weighting. No forced interleaving.

---

## Implementation Details

### File: `backend/app/news/rank.py`

```python
"""
News Ranking Module

Simple, balanced ranking by relevance and recency.
No source bias. No forced interleaving.
"""

from typing import List, Dict, Optional
from datetime import datetime, timezone
import re
import math

Article = Dict[str, object]

STOP_WORDS = {"the", "a", "an", "is", "are", "was", "were", "be", "been", 
              "have", "has", "had", "do", "does", "did", "will", "would",
              "to", "of", "in", "for", "on", "with", "at", "by", "from",
              "and", "or", "but", "not", "this", "that", "it", "its"}


def tokenize(text: str) -> set:
    """Extract meaningful terms from text."""
    words = re.findall(r'\b[a-zA-Z]{2,}\b', text.lower())
    return {w for w in words if w not in STOP_WORDS}


def parse_timestamp(ts) -> float:
    """Parse various timestamp formats to Unix timestamp."""
    if ts is None:
        return 0.0
    if isinstance(ts, (int, float)):
        return ts / 1000 if ts > 1e12 else float(ts)
    if isinstance(ts, str):
        for fmt in ["%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", 
                    "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"]:
            try:
                dt = datetime.strptime(ts.split("+")[0].split("-")[0] if "+" in ts else ts, fmt)
                return dt.replace(tzinfo=timezone.utc).timestamp()
            except:
                continue
    return 0.0


def calculate_relevance(query: str, title: str, description: str = "") -> float:
    """Score 0-1 based on query term matches in title."""
    query_terms = tokenize(query)
    if not query_terms:
        return 0.5
    
    title_lower = title.lower()
    title_terms = tokenize(title)
    
    # Term frequency
    matches = sum(1 for t in query_terms if t in title_terms)
    term_score = matches / len(query_terms)
    
    # Exact phrase bonus
    phrase_bonus = 0.25 if query.lower() in title_lower else 0.0
    
    return min(term_score * 0.75 + phrase_bonus, 1.0)


def calculate_recency(published_at) -> float:
    """Score 0-1 using exponential decay, 48h half-life."""
    ts = parse_timestamp(published_at)
    if ts <= 0:
        return 0.3
    
    now = datetime.now(timezone.utc).timestamp()
    age_hours = max((now - ts) / 3600, 0)
    
    return math.pow(0.5, age_hours / 48)


def calculate_title_quality(title: str) -> float:
    """Heuristic quality score for title."""
    if not title:
        return 0.0
    
    score = 1.0
    if title.isupper():
        score *= 0.6
    if len(title) < 15:
        score *= 0.7
    if len(title) > 200:
        score *= 0.8
    if title.count("!") > 2:
        score *= 0.8
    
    return score


def deduplicate(articles: List[Article]) -> List[Article]:
    """Remove duplicates by URL."""
    seen = set()
    unique = []
    for a in articles:
        url = str(a.get("url", "")).lower().strip()
        if url and url not in seen:
            seen.add(url)
            unique.append(a)
        elif not url:
            unique.append(a)  # Keep articles without URLs
    return unique


def rank_articles(
    articles: List[Article],
    query: str = "",
    dedupe: bool = True,
    limit: Optional[int] = None,
) -> List[Article]:
    """
    Rank articles by relevance and recency.
    
    Weights: Relevance 50%, Recency 35%, Quality 15%
    """
    if not articles:
        return []
    
    # Score each article
    scored = []
    for article in articles:
        title = str(article.get("title", ""))
        desc = str(article.get("description", "") or "")
        pub = article.get("published_at")
        
        rel = calculate_relevance(query, title, desc)
        rec = calculate_recency(pub)
        qual = calculate_title_quality(title)
        
        score = (rel * 0.50) + (rec * 0.35) + (qual * 0.15)
        
        scored.append({
            **article,
            "_score": round(score, 4),
            "_relevance": round(rel, 4),
            "_recency": round(rec, 4),
            "_quality": round(qual, 4),
        })
    
    # Sort by score
    scored.sort(key=lambda a: a["_score"], reverse=True)
    
    # Deduplicate
    if dedupe:
        scored = deduplicate(scored)
    
    # Limit
    if limit:
        scored = scored[:limit]
    
    return scored
```

### Changes to `backend/app/api.py`

The current import needs to work with the new module:

```python
from .news.rank import rank_articles
```

Simplify the ranking calls:

```python
# In streaming mode
ranked = rank_articles(accumulated, query=q, dedupe=True)

# In non-streaming mode
articles = rank_articles(articles, query=q, dedupe=True)
```

Remove `english_only` and `diversify` parameters as those are no longer needed.

---

## Streaming Architecture

### Data Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                          FRONTEND                                    │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ NewsFeedPanel                                                │   │
│  │   └─> useNewsSearch(query)                                   │   │
│  │         └─> EventSource(/news/search?stream=true&q=...)     │   │
│  │               └─> onUpdate: setState({articles: [...]})     │   │
│  │               └─> onDone: setState({articles: [...]})       │   │
│  └─────────────────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────────────────—─┘
                                   │
                                   │ SSE Connection
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          BACKEND                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ /news/search endpoint                                        │   │
│  │   └─> news_fetcher.fetch_multiple_iter()                    │   │
│  │         │                                                    │   │
│  │         │ ThreadPoolExecutor (4 workers)                    │   │
│  │         ├──> fetch_gdelt2() ─────────> [articles] ──┐       │   │
│  │         ├──> fetch_exa() ────────────> [articles] ──┤       │   │
│  │         ├──> fetch_newsdata() ───────> [articles] ──┤       │   │
│  │         └──> fetch_cryptopanic() ────> [articles] ──┘       │   │
│  │                                                │             │   │
│  │         for provider, articles in iter:        │             │   │
│  │           accumulated.extend(articles)         │             │   │
│  │           ranked = rank_articles(accumulated)  ◄─────────────┘   │
│  │           yield SSE_event(ranked)                                │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### Timing Example

| Time (ms) | Event | Articles in Pool |
|-----------|-------|------------------|
| 0 | Request starts | 0 |
| 200 | GDELT returns 20 | 20 |
| 200 | SSE update sent | Ranked 20 |
| 800 | EXA returns 15 | 35 |
| 800 | SSE update sent | Ranked 35 (reordered) |
| 1200 | Newsdata returns 10 | 45 |
| 1200 | SSE update sent | Ranked 45 (reordered) |
| 1500 | CryptoPanic returns 8 | 53 |
| 1500 | SSE done sent | Final ranked 53 |

---

## Testing Strategy

### Unit Tests

1. **`test_calculate_relevance`**: Verify term matching works
2. **`test_calculate_recency`**: Verify exponential decay
3. **`test_calculate_title_quality`**: Verify spam detection
4. **`test_rank_articles`**: Verify composite scoring and sorting
5. **`test_deduplicate`**: Verify URL-based deduplication

### Integration Tests

1. **SSE streaming**: Verify events arrive in correct order
2. **Provider failures**: Verify graceful handling of API errors
3. **Empty results**: Verify handling of no-result queries

### Manual Testing

1. Search for "TSLA" - verify mix of sources
2. Search for "breaking news" - verify urgency doesn't dominate
3. Search for "cryptocurrency" - verify recency ordering

---

## Rollout Plan

### Phase 1: Fix Critical Bug (Immediate)

1. Create minimal `rank.py` with basic implementation
2. Restart server
3. Verify no import errors

### Phase 2: Implement Full Ranking (Same Day)

1. Implement complete ranking algorithm
2. Test with various queries
3. Verify SSE streaming works

### Phase 3: Tune Weights (Next Day)

1. Observe which sources dominate
2. Adjust relevance/recency weights if needed
3. Add debug logging for score breakdowns

---

## Future Enhancements

### Semantic Search

Replace term matching with embeddings-based similarity using a model like `sentence-transformers`. This would catch semantic matches that keyword search misses.

### User Preferences

Store per-user source preferences. Some users may prefer GDELT's breadth while others prefer EXA's curation.

### Caching Layer

Cache provider results for popular queries to reduce API costs and improve response times.

### Sentiment Analysis

Add sentiment scoring to surface positive/negative news about specific assets.

---

## Appendix: Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `EXA` | Yes | EXA.ai API key |
| `NDIO` | Yes | Newsdata.io API key |
| `CPANIC` | Yes | CryptoPanic API key |
| `LC` | No | LunarCrush API key (unused) |

### Ranking Weights

These can be adjusted in `rank.py`:

```python
WEIGHT_RELEVANCE = 0.50
WEIGHT_RECENCY = 0.35
WEIGHT_QUALITY = 0.15
```

### Recency Half-Life

Default is 48 hours. Shorter values favor breaking news:

```python
RECENCY_HALF_LIFE_HOURS = 48
```

---

*Document version: 1.0*
*Last updated: 2026-01-17*
*Word count: ~3000*
