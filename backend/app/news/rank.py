"""
News Ranking Module

Simple, balanced ranking by relevance and recency.
No source bias. No forced interleaving.
"""

from typing import List, Dict, Optional
from datetime import datetime, timezone
import re
import math

from langdetect import detect, LangDetectException

Article = Dict[str, object]

STOP_WORDS = {"the", "a", "an", "is", "are", "was", "were", "be", "been", 
              "have", "has", "had", "do", "does", "did", "will", "would",
              "to", "of", "in", "for", "on", "with", "at", "by", "from",
              "and", "or", "but", "not", "this", "that", "it", "its"}

# Configurable weights
WEIGHT_RELEVANCE = 0.50
WEIGHT_RECENCY = 0.35
WEIGHT_QUALITY = 0.15

# Recency decay
RECENCY_HALF_LIFE_HOURS = 48


def tokenize(text: str) -> set:
    """Extract meaningful terms from text."""
    words = re.findall(r'\b[a-zA-Z]{2,}\b', text.lower())
    return {w for w in words if w not in STOP_WORDS}


def is_english(text: str) -> bool:
    """Check if text is English using langdetect."""
    if not text or len(text.strip()) < 10:
        return True  # Too short to detect, allow it
    try:
        return detect(text) == "en"
    except LangDetectException:
        return True  # Detection failed, allow it


def parse_timestamp(ts) -> float:
    """Parse various timestamp formats to Unix timestamp."""
    if ts is None:
        return 0.0
    if isinstance(ts, (int, float)):
        return ts / 1000 if ts > 1e12 else float(ts)
    if isinstance(ts, str):
        # Handle timezone suffixes
        clean_ts = ts
        if "+" in ts and ts.index("+") > 10:
            clean_ts = ts[:ts.index("+")]
        elif ts.endswith("Z"):
            clean_ts = ts[:-1]
        
        formats = [
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ]
        for fmt in formats:
            try:
                dt = datetime.strptime(clean_ts, fmt)
                return dt.replace(tzinfo=timezone.utc).timestamp()
            except ValueError:
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
    
    return math.pow(0.5, age_hours / RECENCY_HALF_LIFE_HOURS)


def calculate_title_quality(title: str) -> float:
    """Heuristic quality score for title."""
    if not title:
        return 0.0
    
    score = 1.0
    
    # Penalize ALL CAPS (clickbait)
    if title.isupper():
        score *= 0.6
    
    # Penalize very short titles
    if len(title) < 15:
        score *= 0.7
    
    # Penalize very long titles
    if len(title) > 200:
        score *= 0.8
    
    # Penalize excessive punctuation
    if title.count("!") > 2:
        score *= 0.8
    if title.count("?") > 2:
        score *= 0.9
    
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
    
    Args:
        articles: List of article dicts from providers
        query: User's search query for relevance scoring
        dedupe: Remove duplicate articles by URL
        limit: Maximum articles to return
    
    Returns:
        Sorted list of articles with _score metadata
    """
    if not articles:
        return []
    
    # Filter non-English articles
    articles = [a for a in articles if is_english(str(a.get("title", "")))]
    
    # Score each article
    scored = []
    for article in articles:
        title = str(article.get("title", ""))
        desc = str(article.get("description", "") or "")
        pub = article.get("published_at")
        
        rel = calculate_relevance(query, title, desc)
        rec = calculate_recency(pub)
        qual = calculate_title_quality(title)
        
        score = (rel * WEIGHT_RELEVANCE) + (rec * WEIGHT_RECENCY) + (qual * WEIGHT_QUALITY)
        
        scored.append({
            **article,
            "_score": round(score, 4),
            "_relevance": round(rel, 4),
            "_recency": round(rec, 4),
            "_quality": round(qual, 4),
        })
    
    # Sort by score descending
    scored.sort(key=lambda a: a["_score"], reverse=True)
    
    # Deduplicate (after sorting so we keep highest-scored version)
    if dedupe:
        scored = deduplicate(scored)
    
    # Limit
    if limit:
        scored = scored[:limit]
    
    return scored
