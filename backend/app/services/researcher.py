"""
Researcher Service for market sentiment analysis.

Uses LLMService (OpenRouter GPT-OSS) for both:
- Sentiment scoring
- Summary generation
"""

import asyncio
import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Tuple

from app.ai.llm_service import LLMService
from app.news.fetcher import news_fetcher
from app.news.rank import rank_articles


# === DATA STRUCTURES ===

@dataclass
class SentimentResult:
    score: int
    confidence: float
    reasoning: str


@dataclass
class ResearchReport:
    market_id: str
    query: str
    aggregate_score: float
    signal: str
    summary: str
    articles_analyzed: int
    top_positive_headlines: List[str] = field(default_factory=list)
    top_negative_headlines: List[str] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")


# === PROMPTS ===

SENTIMENT_PROMPT = """You are a financial analyst. Analyze this news about '{topic}'.
Score sentiment from -100 (very bearish) to +100 (very bullish).
Consider source credibility - promotional or extreme price predictions should lower confidence.

Headline: {title}
Snippet: {snippet}

Respond with JSON only:
{{"score": <int -100 to 100>, "confidence": <float 0.0-1.0>, "reasoning": "<brief explanation>"}}"""

SUMMARY_PROMPT = """Based on aggregated news sentiment for '{topic}':
- Sentiment Score: {score}/100 ({signal})
- Bullish factors: {positive}
- Bearish factors: {negative}

Write exactly 2 sentences: first about current market state, second about near-term outlook. Be objective and avoid extreme predictions. Output only the 2 sentences, nothing else."""


# === HARVESTER ===

def harvest(query: str, max_articles: int = 75) -> List[Dict]:
    providers = news_fetcher.available_providers()
    raw = news_fetcher.fetch_multiple(providers=providers, query=query, limit=30)
    print(f"[Researcher] Harvested {len(raw)} raw articles")
    cleaned = rank_articles(raw, query=query, dedupe=True)
    return cleaned[:max_articles]


# === ANALYST ===

async def analyze_article(llm: LLMService, article: Dict, topic: str) -> SentimentResult:
    prompt = SENTIMENT_PROMPT.format(
        topic=topic,
        title=article.get("title", ""),
        snippet=article.get("description", "") or article.get("snippet", "") or "",
    )
    try:
        response = await llm._call_openrouter(prompt)
        content = response.strip()
        if "```" in content:
            start = content.find("```") + 3
            if content[start:start+4] == "json":
                start += 4
            end = content.find("```", start)
            content = content[start:end].strip()
        data = json.loads(content)
        return SentimentResult(
            score=int(data.get("score", 0)),
            confidence=float(data.get("confidence", 0.5)),
            reasoning=str(data.get("reasoning", "")),
        )
    except Exception as e:
        print(f"[Researcher] Analyze error: {e}")
        return SentimentResult(score=0, confidence=0.0, reasoning="Error")


async def analyze_batch(llm: LLMService, articles: List[Dict], topic: str, concurrency: int = 5) -> List[SentimentResult]:
    sem = asyncio.Semaphore(concurrency)
    async def limited(a): 
        async with sem: 
            return await analyze_article(llm, a, topic)
    return await asyncio.gather(*[limited(a) for a in articles])


# === SYNTHESIZER ===

def calculate_time_weight(published_at, half_life_hours: float = 24.0) -> float:
    if not published_at:
        return 0.3
    now = datetime.now(timezone.utc).timestamp()
    try:
        if isinstance(published_at, str):
            ts = datetime.fromisoformat(published_at.replace("Z", "+00:00")).timestamp()
        else:
            ts = float(published_at)
            if ts > 1e12:
                ts /= 1000
    except:
        return 0.3
    hours_ago = max((now - ts) / 3600, 0)
    return math.pow(0.5, hours_ago / half_life_hours)


def aggregate_scores(articles: List[Dict], sentiments: List[SentimentResult]) -> Tuple[float, List[str], List[str]]:
    if not sentiments:
        return 0.0, [], []
    total_w, weighted_sum = 0.0, 0.0
    scored = []
    for a, s in zip(articles, sentiments):
        w = calculate_time_weight(a.get("published_at")) * s.confidence
        weighted_sum += s.score * w
        total_w += w
        scored.append((a, s))
    agg = weighted_sum / total_w if total_w else 0.0
    scored.sort(key=lambda x: x[1].score, reverse=True)
    pos = [a["title"] for a, s in scored if s.score > 20 and a.get("title")][:5]
    neg = [a["title"] for a, s in scored if s.score < -20 and a.get("title")][:5]
    return agg, pos, neg


async def synthesize_summary(llm: LLMService, topic: str, score: float, signal: str, pos: List[str], neg: List[str]) -> str:
    """Generate summary using LLMService (GPT-OSS via OpenRouter)."""
    prompt = SUMMARY_PROMPT.format(
        topic=topic, score=round(score, 1), signal=signal,
        positive=", ".join(pos[:3]) or "None identified",
        negative=", ".join(neg[:3]) or "None identified",
    )
    try:
        response = await llm._call_openrouter(prompt)
        summary = response.strip()
        
        # Post-process to remove common instruction leakage
        leakage_patterns = [
            "two sentences.", "two-sentence", "2 sentences", 
            "here is the", "here are", "as requested",
            "based on the data", "according to",
        ]
        summary_lower = summary.lower()
        for pattern in leakage_patterns:
            if summary_lower.startswith(pattern):
                # Find the end of the leaked prefix and trim
                idx = len(pattern)
                while idx < len(summary) and summary[idx] in ' :.':
                    idx += 1
                summary = summary[idx:].strip()
                summary_lower = summary.lower()
        
        # Capitalize first letter if needed
        if summary and summary[0].islower():
            summary = summary[0].upper() + summary[1:]
        
        return summary
    except Exception as e:
        print(f"[Researcher] Summary error: {e}")
        return f"Sentiment is {signal} at {score:.0f}/100."


# === MAIN ORCHESTRATOR ===

async def research_market(
    llm: LLMService,
    market_id: str,
    query: str,
    max_articles: int = 50,
) -> ResearchReport:
    """
    Full research pipeline: Harvest -> Analyze -> Synthesize.
    
    Uses only LLMService (GPT-OSS) for all LLM operations.
    """
    print(f"[Researcher] Starting: {query}")
    
    articles = harvest(query, max_articles)
    if not articles:
        return ResearchReport(market_id=market_id, query=query, aggregate_score=0.0,
                              signal="neutral", summary="Insufficient data.", articles_analyzed=0)
    
    sentiments = await analyze_batch(llm, articles, query)
    agg, pos, neg = aggregate_scores(articles, sentiments)
    signal = "bullish" if agg >= 30 else "bearish" if agg <= -30 else "neutral"
    
    summary = await synthesize_summary(llm, query, agg, signal, pos, neg)
    
    return ResearchReport(
        market_id=market_id, query=query, aggregate_score=round(agg, 2),
        signal=signal, summary=summary, articles_analyzed=len(articles),
        top_positive_headlines=pos, top_negative_headlines=neg,
    )
