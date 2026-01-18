import difflib
from typing import List, Optional, Tuple, TYPE_CHECKING

from .schemas import Market

if TYPE_CHECKING:
    from .ai.embedding_service import EmbeddingService
    from .ai.llm_service import LLMService
    from .connectors.kalshi import KalshiConnector
    from .connectors.polymarket import PolymarketConnector


def find_related_market(target_market: Market, all_markets: List[Market], threshold: float = 0.6) -> Optional[Market]:
    """
    Finds the best matching market from a different source.
    Uses SequenceMatcher on titles (legacy text-based method).
    """
    best_match = None
    best_score = 0.0
    
    # Pre-process target title
    target_tokens = set(target_market.title.lower().split())

    for market in all_markets:
        # Skip same source
        if market.source == target_market.source:
            continue
            
        # 1. Simple Jaccard Token Overlap (Fast filter)
        market_tokens = set(market.title.lower().split())
        intersection = target_tokens.intersection(market_tokens)
        union = target_tokens.union(market_tokens)
        
        if not union: continue
        
        jaccard_index = len(intersection) / len(union)
        
        # 2. Sequence Matcher (Slower but better for phrases)
        # We only run this if jaccard shows some promise or list is small
        # For hackathon size (20-100 markets), run it on everything.
        ratio = difflib.SequenceMatcher(None, target_market.title.lower(), market.title.lower()).ratio()
        
        # Combine or just use ratio
        score = ratio
        
        if score > best_score and score >= threshold:
            best_score = score
            best_match = market
            
    return best_match


async def find_similar_market_embedding(
    target_market: Market,
    embedding_service: "EmbeddingService",
    kalshi_connector: "KalshiConnector",
    polymarket_connector: "PolymarketConnector",
    llm_service: Optional["LLMService"] = None,
    threshold: float = 0.65,
) -> List[Tuple[Market, float]]:
    """
    Find the most similar markets using FAST text matching first,
    then optionally refine with embeddings.
    """
    import asyncio
    
    # Step 1: Build heuristic query from title (FAST - no LLM)
    stop_words = {"will", "the", "a", "an", "in", "on", "at", "by", "to", "of", "for", "is", "be", "?"}
    title_words = [w for w in target_market.title.split() if w.lower() not in stop_words and len(w) > 2]
    query = " ".join(title_words[:4])  # Use first 4 keywords
    if not query:
        query = target_market.title[:30]
    
    print(f"[Matching] Fast search with query: '{query}'")
    
    # Step 2: Search BOTH platforms in parallel (FAST)
    search_tasks = [
        kalshi_connector.search_markets(query),
        polymarket_connector.search_markets(query),
    ]
    
    try:
        results = await asyncio.wait_for(
            asyncio.gather(*search_tasks, return_exceptions=True),
            timeout=8.0  # 8 second timeout for searches
        )
    except asyncio.TimeoutError:
        print("[Matching] Search timeout")
        return []
    
    # Collect candidates
    candidate_map = {}
    for result in results:
        if isinstance(result, Exception):
            continue
        if result:
            for m in result:
                if m.market_id != target_market.market_id:
                    candidate_map[m.market_id] = m
    
    if not candidate_map:
        print("[Matching] No candidates found")
        return []
    
    candidates = list(candidate_map.values())[:20]  # Limit to 20 for speed
    print(f"[Matching] Found {len(candidates)} candidates")
    
    # Step 3: FAST text-based scoring (SequenceMatcher)
    scores = []
    target_lower = target_market.title.lower()
    
    for market in candidates:
        ratio = difflib.SequenceMatcher(None, target_lower, market.title.lower()).ratio()
        scores.append((market, ratio))
    
    scores.sort(key=lambda x: x[1], reverse=True)
    
    # Step 4: Filter and prioritize opposing platform
    opposing = [(m, s) for m, s in scores if m.source != target_market.source]
    same = [(m, s) for m, s in scores if m.source == target_market.source]
    
    # Take top 3 opposing (if > 0.3) + top 2 same (if > 0.4)
    valid_opposing = [(m, s) for m, s in opposing[:3] if s >= 0.3]
    valid_same = [(m, s) for m, s in same[:2] if s >= 0.4]
    
    mixed = valid_opposing + valid_same
    mixed.sort(key=lambda x: x[1], reverse=True)
    
    if mixed:
        print(f"[Matching] Returning {len(mixed)} matches. Top: '{mixed[0][0].title}'")
        return mixed[:5]
    
    return []

