"""Helper functions for market search and filtering."""

import random
from typing import List, Optional, Dict, Any
from .schemas import Market
from .state import StateManager


def search_markets(
    state: StateManager,
    q: Optional[str] = None,
    sector: Optional[str] = None,
    tags: Optional[List[str]] = None,
    source: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[List[Market], int, Dict[str, Any]]:
    """
    Search and filter markets with relevance scoring.
    
    Args:
        state: StateManager instance
        q: Search query
        sector: Sector filter
        tags: Tags filter
        source: Source filter (polymarket/kalshi)
        limit: Maximum results
        offset: Pagination offset
        
    Returns:
        Tuple of (markets, total, facets)
    """
    markets = state.get_all_markets()

    # === FILTERS ===
    if source:
        markets = [m for m in markets if m.source == source]
    if sector:
        markets = [m for m in markets if m.sector == sector]
    if tags:
        tags_lower = [t.lower() for t in tags]
        markets = [m for m in markets if any(
            t.lower() in tags_lower for t in m.tags
        )]
    
    # === KEYWORD SEARCH with relevance scoring ===
    if q:
        q_lower = q.lower()
        scored = []
        for m in markets:
            score = 0
            if q_lower in m.title.lower():
                score += 10
                if m.title.lower().startswith(q_lower):
                    score += 5
            if m.description and q_lower in m.description.lower():
                score += 3
            if any(q_lower in t.lower() for t in m.tags):
                score += 2
            if any(q_lower in o.name.lower() for o in m.outcomes):
                score += 1
            
            if score > 0:
                scored.append((m, score))
        
        scored.sort(key=lambda x: x[1], reverse=True)
        markets = [m for m, _ in scored]
    else:
        # === SHUFFLE RESULTS if no query ===
        random.shuffle(markets)

    total = len(markets)
    paginated = markets[offset:offset + limit]
    
    # === FACETS for UI ===
    all_markets = state.get_all_markets()
    facets = {
        "sectors": {},
        "sources": {"polymarket": 0, "kalshi": 0},
        "tags": {}
    }
    for m in all_markets:
        if m.sector:
            facets["sectors"][m.sector] = facets["sectors"].get(m.sector, 0) + 1
        facets["sources"][m.source] += 1
        for t in m.tags[:3]:
            facets["tags"][t] = facets["tags"].get(t, 0) + 1
    
    facets["tags"] = dict(sorted(facets["tags"].items(), key=lambda x: -x[1])[:20])
    
    return paginated, total, facets
