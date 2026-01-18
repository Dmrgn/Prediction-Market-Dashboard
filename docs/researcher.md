# OddBase Researcher Service Specification

**Version:** 2.0.0  
**Status:** Implementation Ready  
**Target File:** `backend/app/services/researcher.py`

---

## I. Overview

The **Researcher Service** ingests news data related to a prediction market, scores each article for sentiment, and produces a weighted aggregate score with a two-sentence summary.

This document provides **copy-paste ready code** that integrates with the existing codebase.

---

## II. Codebase Integration Map

| Component             | File                                | Class/Function         | Usage                                      |
| --------------------- | ----------------------------------- | ---------------------- | ------------------------------------------ |
| **News Fetching**     | `app/news/fetcher.py`               | `news_fetcher`         | `.fetch_multiple()` for parallel retrieval |
| **Deduplication**     | `app/news/rank.py`                  | `rank_articles()`      | Remove duplicate URLs                      |
| **Direct LLM Calls**  | `app/ai/llm_service.py`             | `LLMService`           | For sentiment scoring (stateless)          |
| **Conversational AI** | `app/ai/agent.py`                   | `AgentService`         | For summary generation (uses memory)       |
| **Market Lookup**     | `app/state.py`                      | `StateManager`         | Resolve market_id to search terms          |

---

## III. Architecture Decision

We use **two different LLM services** strategically:

| Task                 | Service        | Reason                                                   |
| -------------------- | -------------- | -------------------------------------------------------- |
| Sentiment Scoring    | `LLMService`   | Stateless, fast, cheap. Uses OpenRouter `gpt-oss-120b`. |
| Summary Generation   | `AgentService` | Uses Backboard with memory for richer context.          |

---

## IV. Data Structures

Create these in `backend/app/services/researcher.py`:

```python
"""Researcher Service for market sentiment analysis."""

from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime


@dataclass
class SentimentResult:
    """Atomic sentiment output for a single article."""
    score: int              # -100 (bearish) to +100 (bullish)
    confidence: float       # 0.0 to 1.0
    reasoning: str          # Brief explanation from LLM


@dataclass
class ResearchReport:
    """Final aggregated sentiment report."""
    market_id: str
    query: str
    aggregate_score: float
    signal: str             # "bullish", "bearish", "neutral"
    summary: str            # Two-sentence outlook
    articles_analyzed: int
    top_positive_headlines: List[str] = field(default_factory=list)
    top_negative_headlines: List[str] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
```

---

## V. The Harvester

Uses existing `news_fetcher` from `app/news/fetcher.py`.

```python
from app.news.fetcher import news_fetcher
from app.news.rank import rank_articles
from typing import List, Dict


def harvest(query: str, max_articles: int = 50) -> List[Dict]:
    """
    Fetch articles from all available news providers.
    
    Args:
        query: Search term (e.g., "Bitcoin ETF")
        max_articles: Maximum articles to return
        
    Returns:
        List of deduplicated Article dicts
    """
    providers = news_fetcher.available_providers()
    
    # Fetch from all providers in parallel (ThreadPoolExecutor under the hood)
    raw_articles = news_fetcher.fetch_multiple(
        providers=providers,
        query=query,
        limit=20,  # Per provider
    )
    
    print(f"[Researcher] Harvested {len(raw_articles)} raw articles for '{query}'")
    
    # Deduplicate and clean using existing rank module
    cleaned = rank_articles(raw_articles, query=query, dedupe=True)
    
    print(f"[Researcher] After dedup: {len(cleaned)} unique articles")
    
    return cleaned[:max_articles]
```

---

## VI. The Analyst

Uses `LLMService` from `app/ai/llm_service.py` for stateless scoring.

### Key Integration: `LLMService._call_openrouter()`

The existing `LLMService` has a private method `_call_openrouter(prompt: str) -> str` that we'll use.

```python
import asyncio
import json
from typing import List, Dict
from app.ai.llm_service import LLMService


# === PROMPTS ===

SENTIMENT_PROMPT = """Analyze this news headline regarding '{topic}'.
Assign a sentiment score from -100 (extremely negative) to +100 (extremely positive).
Return JSON only, no explanation outside the JSON:

{{"score": <int>, "confidence": <float 0.0-1.0>, "reasoning": "<one sentence>"}}

Headline: {title}
Snippet: {snippet}
"""


async def analyze_article(
    llm: LLMService,
    article: Dict,
    topic: str,
) -> SentimentResult:
    """
    Score a single article using LLMService.
    
    Uses the existing _call_openrouter() method for direct API access.
    """
    prompt = SENTIMENT_PROMPT.format(
        topic=topic,
        title=article.get("title", ""),
        snippet=article.get("description", "") or article.get("snippet", "") or "",
    )
    
    try:
        # Use the existing OpenRouter call method
        response = await llm._call_openrouter(prompt)
        
        # Parse JSON from response
        content = response.strip()
        if "```json" in content:
            start = content.find("```json") + 7
            end = content.find("```", start)
            content = content[start:end].strip()
        elif "```" in content:
            start = content.find("```") + 3
            end = content.find("```", start)
            content = content[start:end].strip()
        
        data = json.loads(content)
        return SentimentResult(
            score=int(data.get("score", 0)),
            confidence=float(data.get("confidence", 0.5)),
            reasoning=str(data.get("reasoning", "")),
        )
        
    except json.JSONDecodeError as e:
        print(f"[Researcher] JSON parse error: {e} - Response: {response[:100]}")
        return SentimentResult(score=0, confidence=0.0, reasoning="Parse error")
    except Exception as e:
        print(f"[Researcher] LLM call error: {e}")
        return SentimentResult(score=0, confidence=0.0, reasoning=str(e))


async def analyze_batch(
    llm: LLMService,
    articles: List[Dict],
    topic: str,
    concurrency: int = 5,
) -> List[SentimentResult]:
    """
    Analyze multiple articles with controlled concurrency.
    
    Args:
        llm: Initialized LLMService instance
        articles: List of article dicts
        topic: The topic/market name
        concurrency: Max parallel LLM calls (default 5 to avoid rate limits)
        
    Returns:
        List of SentimentResult in same order as input articles
    """
    semaphore = asyncio.Semaphore(concurrency)
    
    async def limited_analyze(article: Dict) -> SentimentResult:
        async with semaphore:
            return await analyze_article(llm, article, topic)
    
    tasks = [limited_analyze(a) for a in articles]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Convert exceptions to neutral results
    final_results = []
    for r in results:
        if isinstance(r, Exception):
            print(f"[Researcher] Task exception: {r}")
            final_results.append(SentimentResult(score=0, confidence=0.0, reasoning="Error"))
        else:
            final_results.append(r)
    
    return final_results
```

---

## VII. The Synthesizer

### Time-Decay Weighting

Recent articles should have more influence.

```python
import math
from datetime import datetime, timezone
from typing import List, Dict, Tuple


def calculate_time_weight(published_at, half_life_hours: float = 24.0) -> float:
    """
    Exponential decay weighting for article recency.
    
    Formula: weight = 0.5 ^ (hours_ago / half_life)
    
    Args:
        published_at: ISO timestamp string or Unix timestamp
        half_life_hours: Hours until weight is halved (default 24h)
        
    Returns:
        Weight between 0.0 and 1.0
    """
    if not published_at:
        return 0.3  # Default for missing timestamps
    
    now = datetime.now(timezone.utc).timestamp()
    
    # Parse timestamp
    if isinstance(published_at, str):
        try:
            # Handle various ISO formats
            clean = published_at.replace("Z", "+00:00")
            ts = datetime.fromisoformat(clean).timestamp()
        except Exception:
            return 0.3
    elif isinstance(published_at, (int, float)):
        ts = float(published_at)
        # Handle milliseconds
        if ts > 1e12:
            ts = ts / 1000
    else:
        return 0.3
    
    hours_ago = max((now - ts) / 3600, 0)
    return math.pow(0.5, hours_ago / half_life_hours)


def aggregate_scores(
    articles: List[Dict],
    sentiments: List[SentimentResult],
) -> Tuple[float, List[str], List[str]]:
    """
    Compute weighted average sentiment score.
    
    Weights combine:
    - Time decay (recent = more important)
    - LLM confidence
    
    Returns:
        (aggregate_score, top_positive_headlines, top_negative_headlines)
    """
    if not sentiments:
        return 0.0, [], []
    
    total_weight = 0.0
    weighted_sum = 0.0
    scored_pairs: List[Tuple[Dict, SentimentResult, float]] = []
    
    for article, sentiment in zip(articles, sentiments):
        time_weight = calculate_time_weight(article.get("published_at"))
        confidence_weight = sentiment.confidence
        weight = time_weight * confidence_weight
        
        weighted_sum += sentiment.score * weight
        total_weight += weight
        scored_pairs.append((article, sentiment, weight))
    
    aggregate = weighted_sum / total_weight if total_weight > 0 else 0.0
    
    # Sort by score for top headlines
    scored_pairs.sort(key=lambda x: x[1].score, reverse=True)
    
    top_positive = [
        a["title"] for a, s, _ in scored_pairs 
        if s.score > 20 and a.get("title")
    ][:5]
    
    top_negative = [
        a["title"] for a, s, _ in scored_pairs 
        if s.score < -20 and a.get("title")
    ][:5]
    
    return aggregate, top_positive, top_negative
```

### Summary Generation (Using AgentService)

For the final summary, we use `AgentService` which has memory capabilities.

```python
from app.ai.agent import AgentService


SUMMARY_PROMPT = """Write a strictly two-sentence market outlook for '{topic}'.

Aggregate sentiment: {score}/100 ({signal})
Key bullish drivers: {positive}
Key bearish drivers: {negative}

Rules:
1. Be concise and professional.
2. First sentence: current state. Second sentence: near-term expectation.
3. Do not mention "based on data" or "according to sources".
"""


async def synthesize_summary(
    agent: AgentService,
    thread_id: str,
    topic: str,
    score: float,
    signal: str,
    positive_headlines: List[str],
    negative_headlines: List[str],
) -> str:
    """
    Generate final two-sentence summary using AgentService.
    
    Uses Backboard's conversational API for richer output.
    """
    prompt = SUMMARY_PROMPT.format(
        topic=topic,
        score=round(score, 1),
        signal=signal,
        positive=", ".join(positive_headlines[:3]) if positive_headlines else "None identified",
        negative=", ".join(negative_headlines[:3]) if negative_headlines else "None identified",
    )
    
    try:
        # Use AgentService's client directly (non-streaming)
        response = await agent.client.add_message(
            thread_id=thread_id,
            content=prompt,
            memory="Auto",
            stream=False,
        )
        
        # Extract content from response
        if hasattr(response, 'content'):
            return str(response.content).strip()
        else:
            return str(response).strip()
            
    except Exception as e:
        print(f"[Researcher] Summary generation error: {e}")
        return f"Sentiment analysis indicates a {signal} outlook with score {score:.0f}/100."
```

---

## VIII. Main Orchestrator

The public function that ties everything together.

```python
async def research_market(
    agent: AgentService,
    llm: LLMService,
    market_id: str,
    query: str,
    max_articles: int = 50,
) -> ResearchReport:
    """
    Full research pipeline: Harvest -> Analyze -> Synthesize.
    
    Args:
        agent: Initialized AgentService (for summary)
        llm: Initialized LLMService (for sentiment scoring)
        market_id: The market being researched
        query: Search term (e.g., "Bitcoin price prediction")
        max_articles: Maximum articles to analyze
        
    Returns:
        ResearchReport with aggregated sentiment and summary
    """
    print(f"[Researcher] Starting research for market={market_id} query='{query}'")
    
    # === Step 1: Harvest ===
    articles = harvest(query, max_articles)
    
    if not articles:
        return ResearchReport(
            market_id=market_id,
            query=query,
            aggregate_score=0.0,
            signal="neutral",
            summary="Insufficient data available to generate a sentiment analysis.",
            articles_analyzed=0,
        )
    
    # === Step 2: Analyze (using LLMService) ===
    print(f"[Researcher] Analyzing {len(articles)} articles...")
    sentiments = await analyze_batch(llm, articles, query, concurrency=5)
    
    # === Step 3: Aggregate ===
    aggregate_score, top_positive, top_negative = aggregate_scores(articles, sentiments)
    
    # Determine signal
    if aggregate_score >= 30:
        signal = "bullish"
    elif aggregate_score <= -30:
        signal = "bearish"
    else:
        signal = "neutral"
    
    print(f"[Researcher] Aggregate score: {aggregate_score:.1f} ({signal})")
    
    # === Step 4: Synthesize Summary (using AgentService) ===
    thread = await agent.create_thread()
    summary = await synthesize_summary(
        agent=agent,
        thread_id=thread.thread_id,
        topic=query,
        score=aggregate_score,
        signal=signal,
        positive_headlines=top_positive,
        negative_headlines=top_negative,
    )
    
    return ResearchReport(
        market_id=market_id,
        query=query,
        aggregate_score=round(aggregate_score, 2),
        signal=signal,
        summary=summary,
        articles_analyzed=len(articles),
        top_positive_headlines=top_positive,
        top_negative_headlines=top_negative,
    )
```

---

## IX. API Endpoint

Add to `backend/app/api.py`:

```python
from .services.researcher import research_market, ResearchReport
from .ai.llm_service import LLMService

# Near the top of the file, after other imports
_llm_service: Optional[LLMService] = None

def get_llm_service() -> LLMService:
    """Lazy initialization of LLMService singleton."""
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service


@router.get("/markets/{market_id}/sentiment")
async def get_market_sentiment(
    request: Request,
    market_id: str,
    q: Optional[str] = None,
):
    """
    Generate sentiment analysis for a market.
    
    Query param `q` overrides the market title as the search term.
    
    WARNING: This is an expensive operation (multiple LLM calls).
    Results should be cached for 15-60 minutes.
    """
    agent = getattr(request.app.state, "agent", None)
    if not agent:
        raise HTTPException(status_code=503, detail="Agent service not available")
    
    try:
        llm = get_llm_service()
    except ValueError as e:
        raise HTTPException(status_code=503, detail=f"LLM service not available: {e}")
    
    # Resolve market to get search terms
    market = state.get_market(market_id)
    if not market and not q:
        raise HTTPException(status_code=404, detail="Market not found. Provide ?q= parameter.")
    
    query = q or market.title
    
    try:
        report = await research_market(
            agent=agent,
            llm=llm,
            market_id=market_id,
            query=query,
            max_articles=50,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Research failed: {e}")
    
    return {
        "market_id": report.market_id,
        "query": report.query,
        "score": report.aggregate_score,
        "signal": report.signal,
        "summary": report.summary,
        "articles_analyzed": report.articles_analyzed,
        "top_positive": report.top_positive_headlines,
        "top_negative": report.top_negative_headlines,
        "generated_at": report.generated_at,
    }
```

---

## X. Complete File: `researcher.py`

Here is the complete, copy-paste ready file:

```python
"""
Researcher Service for market sentiment analysis.

Uses:
- news_fetcher for data harvesting
- LLMService for sentiment scoring (OpenRouter)
- AgentService for summary generation (Backboard)
"""

import asyncio
import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from app.ai.agent import AgentService
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

SENTIMENT_PROMPT = """Analyze this news headline regarding '{topic}'.
Assign a sentiment score from -100 (extremely negative) to +100 (extremely positive).
Return JSON only: {{"score": <int>, "confidence": <float 0.0-1.0>, "reasoning": "<one sentence>"}}

Headline: {title}
Snippet: {snippet}
"""

SUMMARY_PROMPT = """Write a strictly two-sentence market outlook for '{topic}'.
Aggregate sentiment: {score}/100 ({signal})
Key bullish drivers: {positive}
Key bearish drivers: {negative}

Rules: Be concise. First sentence: current state. Second sentence: expectation.
"""


# === HARVESTER ===

def harvest(query: str, max_articles: int = 50) -> List[Dict]:
    providers = news_fetcher.available_providers()
    raw = news_fetcher.fetch_multiple(providers=providers, query=query, limit=20)
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


async def synthesize_summary(agent: AgentService, thread_id: str, topic: str, score: float, signal: str, pos: List[str], neg: List[str]) -> str:
    prompt = SUMMARY_PROMPT.format(
        topic=topic, score=round(score, 1), signal=signal,
        positive=", ".join(pos[:3]) or "None",
        negative=", ".join(neg[:3]) or "None",
    )
    try:
        resp = await agent.client.add_message(thread_id=thread_id, content=prompt, memory="Auto", stream=False)
        return str(resp.content).strip() if hasattr(resp, 'content') else str(resp).strip()
    except Exception as e:
        return f"Sentiment is {signal} at {score:.0f}/100."


# === MAIN ORCHESTRATOR ===

async def research_market(
    agent: AgentService,
    llm: LLMService,
    market_id: str,
    query: str,
    max_articles: int = 50,
) -> ResearchReport:
    print(f"[Researcher] Starting: {query}")
    
    articles = harvest(query, max_articles)
    if not articles:
        return ResearchReport(market_id=market_id, query=query, aggregate_score=0.0,
                              signal="neutral", summary="Insufficient data.", articles_analyzed=0)
    
    sentiments = await analyze_batch(llm, articles, query)
    agg, pos, neg = aggregate_scores(articles, sentiments)
    signal = "bullish" if agg >= 30 else "bearish" if agg <= -30 else "neutral"
    
    thread = await agent.create_thread()
    summary = await synthesize_summary(agent, thread.thread_id, query, agg, signal, pos, neg)
    
    return ResearchReport(
        market_id=market_id, query=query, aggregate_score=round(agg, 2),
        signal=signal, summary=summary, articles_analyzed=len(articles),
        top_positive_headlines=pos, top_negative_headlines=neg,
    )
```

---

## XI. File Structure

```
backend/
├── app/
│   ├── ai/
│   │   ├── agent.py         # AgentService (Backboard)
│   │   └── llm_service.py   # LLMService (OpenRouter)
│   ├── news/
│   │   ├── fetcher.py       # news_fetcher singleton
│   │   └── rank.py          # rank_articles()
│   ├── services/
│   │   └── researcher.py    # NEW - ResearchReport, research_market()
│   └── api.py               # Add /markets/{id}/sentiment
```

---

## XII. Test Command

After implementation:

```bash
curl "http://localhost:8000/markets/test/sentiment?q=Bitcoin%20ETF"
```

Expected response:
```json
{
  "market_id": "test",
  "query": "Bitcoin ETF",
  "score": 42.5,
  "signal": "bullish",
  "summary": "Bitcoin ETF sentiment remains positive amid institutional adoption. Near-term momentum suggests continued upside.",
  "articles_analyzed": 35,
  "top_positive": ["BlackRock Bitcoin ETF sees record inflows", "..."],
  "top_negative": ["SEC delays decision on spot ETF", "..."],
  "generated_at": "2026-01-18T06:35:52Z"
}
```

---

## XIII. Next Steps

1. **Create** `backend/app/services/researcher.py` with the code from Section X.
2. **Add** the endpoint from Section IX to `api.py`.
3. **Test** with the curl command above.
4. **(Optional)** Add caching with `cachetools.TTLCache` to avoid repeated expensive calls.

Ready to implement.
