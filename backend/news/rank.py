"""
News Ranking Module

Handles scoring, sorting, deduplication, and prioritization of news articles.
"""

from typing import List, Dict
from datetime import datetime, timezone
import re

from langdetect import detect, LangDetectException

# Article type alias
Article = Dict[str, object]

# Source priority weights (higher = more priority)
SOURCE_WEIGHTS = {
    "gdelt2": 1.2,      # GDELT takes long to return, prioritize when available
    "newsdata": 1.15,
    "exa": 1.22,
    "cpanic": 1.1,
}

# Urgency keywords that boost score
URGENCY_KEYWORDS = [
    "breaking", "urgent", "alert", "just in", "developing",
    "exclusive", "confirmed", "official", "announces", "surges",
    "crashes", "plunges", "soars", "emergency", "critical",
]


def is_english_text(text: str) -> bool:
    """
    Uses langdetect library to detect if text is English.
    Returns True only if the detected language is English.
    """
    if not text or len(text.strip()) < 10:
        return False
    
    try:
        lang = detect(text)
        return lang == "en"
    except LangDetectException:
        # If detection fails, fall back to ASCII check
        ascii_count = sum(1 for c in text if ord(c) < 128)
        return ascii_count / len(text) >= 0.95


def filter_english_articles(articles: List[Article]) -> List[Article]:
    """
    Filter out articles with non-English titles.
    """
    return [
        a for a in articles
        if is_english_text(str(a.get("title", "")))
    ]


def parse_timestamp(ts: object) -> float:
    """
    Parse various timestamp formats to Unix timestamp.
    Returns 0 if parsing fails.
    """
    if ts is None:
        return 0.0
    
    if isinstance(ts, (int, float)):
        # Already a Unix timestamp
        if ts > 1e12:  # Milliseconds
            return ts / 1000
        return float(ts)
    
    if isinstance(ts, str):
        # Try common formats
        formats = [
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ]
        for fmt in formats:
            try:
                dt = datetime.strptime(ts, fmt)
                return dt.replace(tzinfo=timezone.utc).timestamp()
            except ValueError:
                continue
    
    return 0.0


def calculate_recency_score(published_at: object, max_age_hours: float = 168) -> float:
    """
    Calculate recency score from 0 to 1.
    Articles from now = 1.0, articles older than max_age_hours = 0.0
    """
    ts = parse_timestamp(published_at)
    if ts <= 0:
        return 0.3  # Unknown timestamp gets middle-low score
    
    now = datetime.now(timezone.utc).timestamp()
    age_hours = (now - ts) / 3600
    
    if age_hours < 0:
        return 1.0  # Future date (likely timezone issue), treat as fresh
    if age_hours > max_age_hours:
        return 0.0
    
    # Linear decay
    return 1.0 - (age_hours / max_age_hours)


def calculate_urgency_score(title: str, description: str = "") -> float:
    """
    Calculate urgency score based on keywords in title/description.
    Returns 0 to 1.
    """
    text = f"{title} {description or ''}".lower()
    matches = sum(1 for kw in URGENCY_KEYWORDS if kw in text)
    
    # Cap at 3 matches for max score
    return min(matches / 3.0, 1.0)


def score_article(article: Article) -> float:
    """
    Calculate composite score for an article.
    
    Score = (recency * 0.4) + (source_weight * 0.35) + (urgency * 0.25)
    """
    source = str(article.get("source", "")).lower()
    title = str(article.get("title", ""))
    description = str(article.get("description", "") or "")
    published_at = article.get("published_at")
    
    # Component scores
    recency = calculate_recency_score(published_at)
    source_weight = SOURCE_WEIGHTS.get(source, 1.0) / 1.5  # Normalize to 0-1
    urgency = calculate_urgency_score(title, description)
    
    # Weighted composite
    score = (recency * 0.4) + (source_weight * 0.35) + (urgency * 0.25)
    
    return round(score, 4)


def deduplicate_articles(articles: List[Article]) -> List[Article]:
    """
    Remove duplicate articles based on URL or similar titles.
    Keeps the highest-scored version.
    """
    seen_urls: set = set()
    seen_titles: set = set()
    unique: List[Article] = []
    
    for article in articles:
        url = str(article.get("url", "")).lower().strip()
        title = str(article.get("title", "")).lower().strip()
        
        # Normalize title for comparison (remove punctuation, extra spaces)
        normalized_title = re.sub(r'[^\w\s]', '', title)
        normalized_title = re.sub(r'\s+', ' ', normalized_title).strip()
        
        # Skip if we've seen this URL or very similar title
        if url and url in seen_urls:
            continue
        if normalized_title and normalized_title in seen_titles:
            continue
        
        if url:
            seen_urls.add(url)
        if normalized_title:
            seen_titles.add(normalized_title)
        
        unique.append(article)
    
    return unique


def rank_articles(
    articles: List[Article],
    dedupe: bool = True,
    limit: int | None = None,
    english_only: bool = True,
) -> List[Article]:
    """
    Main ranking function.
    
    1. Filter non-English articles
    2. Score each article
    3. Optionally deduplicate
    4. Sort by score descending
    5. Return top N results
    """
    if not articles:
        return []
    
    # Filter English-only
    if english_only:
        articles = filter_english_articles(articles)
    
    # Score all articles
    scored = []
    for article in articles:
        score = score_article(article)
        scored.append({**article, "_score": score})
    
    # Deduplicate if requested
    if dedupe:
        scored = deduplicate_articles(scored)
    
    # Sort by score descending
    scored.sort(key=lambda a: a.get("_score", 0), reverse=True)
    
    # Apply limit
    if limit:
        scored = scored[:limit]
    
    return scored
