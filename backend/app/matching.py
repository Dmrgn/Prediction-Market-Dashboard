import difflib
from typing import List, Optional
from .schemas import Market

def find_related_market(target_market: Market, all_markets: List[Market], threshold: float = 0.6) -> Optional[Market]:
    """
    Finds the best matching market from a different source.
    Uses SequenceMatcher on titles.
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
