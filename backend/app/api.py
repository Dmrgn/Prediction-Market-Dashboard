import asyncio
import time
import json
import random
import os
from collections import deque
from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, HTTPException, Request
from fastapi.responses import StreamingResponse
from .state import StateManager
from .schemas import Market, OrderBook, QuotePoint, Event, EventSearchResult
from .news.fetcher import news_fetcher  # type: ignore
from .news.rank import rank_articles
from .search_helper import search_markets as search_markets_helper

DEBUG_WS = True

router = APIRouter()
state = StateManager()

@router.get("/markets/search")
async def search_markets(
    request: Request,
    q: Optional[str] = None,
    sector: Optional[str] = None,
    tags: Optional[List[str]] = Query(None),
    source: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):  
    """
    Advanced search with filters and relevance scoring.
    
    On-demand mode: When searching Kalshi, queries their API directly
    and caches results progressively.
    """
    print(q)

    # === ON-DEMAND SEARCH ===
    # If user has a query, trigger on-demand API search for both platforms
    if q:
        # Polymarket on-demand search
        if not source or source == "polymarket":
            poly = getattr(request.app.state, "poly", None)
            if poly:
                await poly.search_markets(q)
        
        # Kalshi on-demand search
        if not source or source == "kalshi":
            kalshi = getattr(request.app.state, "kalshi", None)
            if kalshi:
                await kalshi.search_markets(q)
    
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
        print(f"[DEBUG] Filtering {len(markets)} markets for query '{q_lower}'")
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
        
        print(f"[DEBUG] After scoring: {len(scored)} markets matched")
        scored.sort(key=lambda x: x[1], reverse=True)
        markets = [m for m, _ in scored]

    # === LOG PLATFORM COUNTS ===
    polymarket_count = sum(1 for m in markets if m.source == "polymarket")
    kalshi_count = sum(1 for m in markets if m.source == "kalshi")
    print(f"Query: '{q}' → Polymarket: {polymarket_count}, Kalshi: {kalshi_count}")

    # === SHUFFLE RESULTS ===
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
    
    return {
        "markets": paginated,
        "total": total,
        "facets": facets
    }

@router.get("/events/search", response_model=EventSearchResult)
async def search_events(
    request: Request,
    q: str,
    source: Optional[str] = None,
    limit: int = 20,
):
    """
    Search for events across both platforms.
    Returns events (multi-market groups) and standalone markets.
    
    Uses smart keyword extraction for natural language queries.
    """
    all_events = []
    all_standalone = []
    
    poly = getattr(request.app.state, "poly", None)
    kalshi = getattr(request.app.state, "kalshi", None)
    
    # Search both platforms in parallel
    tasks = []
    
    if poly and (not source or source == "polymarket"):
        tasks.append(("polymarket", poly.search_events(q)))
    
    if kalshi and (not source or source == "kalshi"):
        tasks.append(("kalshi", kalshi.search_events(q)))
    
    # Execute searches
    for platform, task in tasks:
        try:
            events, standalone = await task
            all_events.extend(events)
            all_standalone.extend(standalone)
        except Exception as e:
            print(f"[{platform}] Event search error: {e}")
    
    # Sort events by number of markets (more markets = more relevant)
    # all_events.sort(key=lambda e: len(e.markets), reverse=True)
    
    # === SMART SCORING ===
    def calculate_score(item, query_keywords):
        score = 0
        title = item.title.lower()
        
        # Keyword relevance
        matches = sum(1 for k in query_keywords if k in title)
        score += matches * 10
        
        if query_keywords and query_keywords[0] in title: 
             score += 5 # Bonus for first keyword match
             
        # Volume weighting (log-ish scale)
        # Use max volume of markets for events
        vol = 0
        if isinstance(item, Event):
             vol = sum(m.volume_24h for m in item.markets)
        else:
             vol = item.volume_24h
             
        if vol > 0:
            import math
            score += min(math.log(vol + 1, 10) * 5, 30) # Max 30 pts for volume

        return score

    keywords = q.lower().split()
    
    # Score all items
    scored_events = [(e, calculate_score(e, keywords)) for e in all_events]
    scored_markets = [(m, calculate_score(m, keywords)) for m in all_standalone]
    
    # Sort by score DESC
    scored_events.sort(key=lambda x: x[1], reverse=True)
    scored_markets.sort(key=lambda x: x[1], reverse=True)
    
    # Flatten back
    final_events = [x[0] for x in scored_events]
    final_markets = [x[0] for x in scored_markets]
    
    # Ensure balance: If we have results from both platforms, try to show at least 2 from each in top 10
    # But only if we have them. (Complex to re-sort, so for now rely on scoring but volume boost helps)
    
    return EventSearchResult(
        events=final_events[:limit],
        markets=final_markets[:limit],
        total=len(final_events) + len(final_markets)
    )

@router.get("/markets/{market_id}", response_model=Market)
async def get_market(request: Request, market_id: str):
    # Try direct lookup first
    market = state.get_market(market_id)
    if market:
        return market
    
    # If it looks like a Polymarket slug (no 0x prefix, contains letters), try slug lookup
    if not market_id.startswith("0x") and not market_id.startswith("KX"):
        poly = getattr(request.app.state, "poly", None)
        if poly:
            markets = await poly.fetch_by_slug(market_id)
            if markets:
                # Return the first market from the event
                return markets[0]
    
    raise HTTPException(status_code=404, detail="Market not found")

@router.get("/events/{slug}/markets", response_model=List[Market])
async def get_event_markets(request: Request, slug: str):
    """
    Fetch all markets from a Polymarket event by its URL slug.
    
    E.g., GET /events/us-strikes-iran-by/markets
    """
    poly = getattr(request.app.state, "poly", None)
    if not poly:
        raise HTTPException(status_code=503, detail="Polymarket connector not available")
    
    markets = await poly.fetch_by_slug(slug)
    if not markets:
        raise HTTPException(status_code=404, detail="Event not found")
    
    return markets

@router.get("/markets/{market_id}/history", response_model=List[QuotePoint])
async def get_market_history(
    market_id: str, 
    outcome_id: Optional[str] = None,
    range: Optional[str] = None  # 1H, 6H, 1D, 5D, 1W, 1M, ALL
):
    market = state.get_market(market_id)
    if not market:
        raise HTTPException(status_code=404, detail="Market not found")
    
    # Default to first outcome if not specified
    if not outcome_id and market.outcomes:
        outcome_id = market.outcomes[0].outcome_id
        
    if not outcome_id:
         raise HTTPException(status_code=400, detail="outcome_id required")

    # Convert range to seconds
    range_seconds = None
    if range and range.upper() != "ALL":
        range_map = {
            "1H": 3600,
            "6H": 6 * 3600,
            "1D": 24 * 3600,
            "5D": 5 * 24 * 3600,
            "1W": 7 * 24 * 3600,
            "1M": 30 * 24 * 3600,
        }
        range_seconds = range_map.get(range.upper())

    return state.get_history(market_id, outcome_id, range_seconds)

@router.get("/markets/{market_id}/history/all")
async def get_all_outcomes_history(
    request: Request,
    market_id: str,
    range: Optional[str] = None  # 1H, 6H, 1D, 5D, 1W, 1M, ALL
):
    """Get history for ALL outcomes in a market, useful for multivariate charts"""
    market = state.get_market(market_id)
    if not market:
        raise HTTPException(status_code=404, detail="Market not found")
    
    # Get outcome metadata
    outcome_info = {o.outcome_id: {"name": o.name, "price": o.price} for o in market.outcomes}
    history_by_outcome = {}
    
    # For Polymarket markets, fetch real historical data from their API
    if market.source == "polymarket":
        poly = getattr(request.app.state, "poly", None)
        if poly:
            interval = range.upper() if range else "1D"
            
            for outcome in market.outcomes:
                token_id = outcome.outcome_id
                
                # Only fetch for valid numeric token IDs (Polymarket CLOB tokens)
                if token_id.isdigit() or len(token_id) > 20:
                    try:
                        raw_history = await poly.fetch_price_history(token_id, interval)
                        
                        # Convert to QuotePoint format
                        points = []
                        for point in raw_history:
                            ts = point.get("t", 0)
                            price = float(point.get("p", 0))
                            points.append({
                                "ts": ts,
                                "mid": price,
                                "bid": None,
                                "ask": None
                            })
                        
                        if points:
                            history_by_outcome[token_id] = points
                    except Exception as e:
                        print(f"[API] Error fetching history for {token_id}: {e}")
    
    # If no Polymarket history or it's Kalshi, use our collected data
    if not history_by_outcome:
        # Convert range to seconds
        range_seconds = None
        if range and range.upper() != "ALL":
            range_map = {
                "1H": 3600,
                "6H": 6 * 3600,
                "1D": 24 * 3600,
                "5D": 5 * 24 * 3600,
                "1W": 7 * 24 * 3600,
                "1M": 30 * 24 * 3600,
            }
            range_seconds = range_map.get(range.upper())
        
        history_by_outcome = state.get_all_outcomes_history(market_id, range_seconds)
        
        # Convert QuotePoint objects to dicts
        for oid, points in history_by_outcome.items():
            history_by_outcome[oid] = [
                {"ts": p.ts, "mid": p.mid, "bid": p.bid, "ask": p.ask}
                for p in points
            ]
    
    return {
        "market_id": market_id,
        "outcomes": outcome_info,
        "history": history_by_outcome
    }


@router.get("/markets/{market_id}/orderbook", response_model=Optional[OrderBook])
async def get_market_orderbook(market_id: str, outcome_id: Optional[str] = None):
    market = state.get_market(market_id)
    if not market:
         raise HTTPException(status_code=404, detail="Market not found")
         
    if not outcome_id and market.outcomes:
        outcome_id = market.outcomes[0].outcome_id

    if not outcome_id:
        return None

    return state.get_orderbook(market_id, outcome_id)

@router.get("/markets/{market_id}/related", response_model=Optional[Market])
async def get_related_market(market_id: str):
    market = state.get_market(market_id)
    if not market:
        raise HTTPException(status_code=404, detail="Market not found")
    
    all_markets = state.get_all_markets()
    from .matching import find_related_market
    return find_related_market(market, all_markets)

class SuggestionCache:
    def __init__(self, ttl_seconds: int = 30):
        self.ttl = timedelta(seconds=ttl_seconds)
        self.cache: dict[str, tuple[dict, datetime]] = {}

    def get(self, command_id: str) -> Optional[dict]:
        entry = self.cache.get(command_id)
        if not entry:
            return None
        suggestions, timestamp = entry
        if datetime.utcnow() - timestamp > self.ttl:
            self.cache.pop(command_id, None)
            return None
        return suggestions

    def set(self, command_id: str, suggestions: dict) -> None:
        self.cache[command_id] = (suggestions, datetime.utcnow())

    def invalidate(self, command_id: str) -> None:
        self.cache.pop(command_id, None)


class RateLimiter:
    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window = timedelta(seconds=window_seconds)
        self.requests: deque[datetime] = deque()

    def is_allowed(self) -> bool:
        now = datetime.utcnow()
        while self.requests and now - self.requests[0] > self.window:
            self.requests.popleft()
        if len(self.requests) >= self.max_requests:
            return False
        self.requests.append(now)
        return True


def validate_suggestion_request(data: dict) -> bool:
    command_id = data.get("command_id")
    if not command_id or not isinstance(command_id, str):
        return False
    if len(command_id) > 100:
        return False

    params = data.get("params", [])
    if not isinstance(params, list):
        return False

    for param in params:
        if not isinstance(param, dict):
            return False
        if "name" not in param or "type" not in param:
            return False

    return True


# Simple WebSocket Manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                pass 

# Instantiate manager for export
manager = ConnectionManager()

from .manager import SubscriptionManager
import json

# ...

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    sub_manager = SubscriptionManager()
    await websocket.accept()
    
    # Agent state for this connection
    current_thread_id = None

    # Caching and rate limiting for suggestions
    suggestion_cache = SuggestionCache(ttl_seconds=30)
    rate_limiter = RateLimiter(max_requests=10, window_seconds=60)
    
    # Get services from app state
    agent_service = getattr(websocket.app.state, "agent", None)
    llm_service = getattr(websocket.app.state, "llm", None)
    
    try:
        while True:
            # Client must send {"op": "subscribe", "market_id": "..."}
            # Or {"op": "unsubscribe", "market_id": "..."}
            # Or {"op": "agent_init"} or {"op": "agent_message", "content": "..."}
            data = await websocket.receive_json()
            op = data.get("op")

            if DEBUG_WS:
                print(f"[WebSocket] Received op={op} payload={data}")
            
            # ===== AGENT OPERATIONS =====
            
            if op == "agent_init":
                if not agent_service:
                    await websocket.send_json({
                        "type": "error",
                        "error": "Agent service not available"
                    })
                    continue
                    
                try:
                    # Ensure assistant is initialized
                    if not agent_service.assistant_id:
                        await agent_service.initialize()
                    
                    # Create new thread for this connection
                    thread = await agent_service.create_thread()
                    current_thread_id = thread.thread_id

                    if DEBUG_WS:
                        print(f"[WebSocket] Agent ready thread_id={current_thread_id}")
                    
                    await websocket.send_json({
                        "type": "agent_ready",
                        "thread_id": current_thread_id,
                        "assistant_id": agent_service.assistant_id
                    })
                except Exception as e:
                    await websocket.send_json({
                        "type": "error",
                        "error": f"Failed to initialize agent: {str(e)}"
                    })

            elif op == "agent_message":
                if not agent_service:
                    await websocket.send_json({
                        "type": "error",
                        "error": "Agent service not available"
                    })
                    continue
                    
                try:
                    prompt = data.get("content")
                    thread_id = data.get("thread_id") or current_thread_id
                    
                    if not prompt:
                        await websocket.send_json({
                            "type": "error",
                            "error": "No content provided"
                        })
                        continue
                    
                    if not thread_id:
                        await websocket.send_json({
                            "type": "error",
                            "error": "No active thread_id. Send 'agent_init' first."
                        })
                        continue

                    # Stream agent response
                    async for chunk in agent_service.stream_chat(thread_id, prompt):
                        await websocket.send_json({
                            "type": "agent_response",
                            "payload": chunk
                        })
                        
                except Exception as e:
                    await websocket.send_json({
                        "type": "error",
                        "error": f"Agent error: {str(e)}"
                    })

            elif op == "agent_track_execution":
                try:
                    command_id = data.get("command_id")
                    params = data.get("params", {})
                    timestamp = data.get("timestamp")

                    if command_id:
                        # Track in LLMService (for param suggestions)
                        if llm_service:
                            await llm_service.track_execution(
                                command_id=command_id,
                                params=params,
                                timestamp=timestamp,
                                state_manager=state,
                            )
                        
                        # Also track in AgentService (for chat context)
                        if agent_service:
                            # Ensure thread exists
                            if not current_thread_id:
                                if not agent_service.assistant_id:
                                    await agent_service.initialize()
                                thread = await agent_service.create_thread()
                                current_thread_id = thread.thread_id
                            
                            # Send to agent to store in memory with market enrichment
                            await agent_service.track_execution(
                                thread_id=current_thread_id,
                                command_id=command_id,
                                params=params,
                                timestamp=timestamp,
                                state_manager=state,
                            )

                        if DEBUG_WS:
                            print(
                                "[WebSocket] Tracked execution "
                                f"command_id={command_id} params={params}"
                            )

                        await websocket.send_json({
                            "type": "execution_tracked",
                            "command_id": command_id,
                        })
                except Exception as e:
                    print(f"[WebSocket] Error tracking execution: {e}")

            elif op == "agent_suggest_params":
                if not llm_service:
                    await websocket.send_json({
                        "type": "error",
                        "error": "LLM service not available",
                        "request_id": data.get("request_id"),
                    })
                    continue

                if not validate_suggestion_request(data):
                    await websocket.send_json({
                        "type": "error",
                        "error": "Invalid suggestion request",
                        "request_id": data.get("request_id"),
                    })
                    continue

                if not rate_limiter.is_allowed():
                    await websocket.send_json({
                        "type": "error",
                        "error": "Too many suggestion requests",
                        "request_id": data.get("request_id"),
                    })
                    continue

                try:
                    command_id = data.get("command_id")
                    params = data.get("params", [])
                    current_params = data.get("current_params", {})
                    request_id = data.get("request_id")

                    cached = suggestion_cache.get(command_id)
                    if cached is not None:
                        if DEBUG_WS:
                            print(f"[WebSocket] Suggestion cache hit command_id={command_id}")
                        await websocket.send_json({
                            "type": "param_suggestions",
                            "command_id": command_id,
                            "request_id": request_id,
                            "suggestions": cached,
                            "cached": True,
                        })
                        continue

                    try:
                        # Use LLMService for parameter suggestions
                        suggestions = await asyncio.wait_for(
                            llm_service.suggest_params(
                                command_id=command_id,
                                params=params,
                                current_params=current_params,
                                state_manager=state,
                            ),
                            timeout=10,  # 10 second timeout for OpenRouter
                        )
                    except asyncio.TimeoutError:
                        if DEBUG_WS:
                            print(
                                "[WebSocket] Suggestion request timed out "
                                f"command_id={command_id} request_id={request_id}"
                            )
                        await websocket.send_json({
                            "type": "error",
                            "error": "Suggestion request timed out",
                            "request_id": request_id,
                        })
                        continue

                    suggestion_cache.set(command_id, suggestions)

                    if DEBUG_WS:
                        print(
                            "[WebSocket] Sending suggestions "
                            f"command_id={command_id} request_id={request_id} "
                            f"payload={suggestions}"
                        )

                    await websocket.send_json({
                        "type": "param_suggestions",
                        "command_id": command_id,
                        "request_id": request_id,
                        "suggestions": suggestions,
                    })

                except Exception as e:
                    print(f"[WebSocket] Error generating suggestions: {e}")
                    await websocket.send_json({
                        "type": "error",
                        "error": f"Failed to generate suggestions: {str(e)}",
                        "request_id": data.get("request_id"),
                    })
            
            # ===== EXISTING MARKET OPERATIONS =====
            
            elif op == "subscribe":
                pass
                
            elif op == "subscribe_market":
                market_id = data.get("market_id")
                if market_id:
                    await sub_manager.subscribe(market_id, websocket)
            
            elif op == "unsubscribe_market":
                market_id = data.get("market_id")
                if market_id:
                    await sub_manager.unsubscribe(market_id, websocket)
                    
    except WebSocketDisconnect:
        await sub_manager.unsubscribe_from_all(websocket)

@router.get("/news/search")
async def search_news(
    q: str = Query(..., description="Search query"),
    providers: Optional[List[str]] = Query(None, description="List of providers to query"),
    limit: int = Query(20, ge=1, le=100, description="Number of results per provider"),
    stream: bool = Query(False, description="Enable SSE streaming"),
):
    """
    Search news articles across multiple providers.
    
    Returns a JSON array of articles or streams results via SSE.
    """
    
    if not q or not q.strip():
        return []
    
    # Default to all providers if none specified
    available = news_fetcher.available_providers()
    selected_providers = providers if providers else available
    
    # Filter to valid providers
    selected_providers = [p for p in selected_providers if p in available]
    
    if not selected_providers:
        return []
    
    # Streaming mode
    if stream:
        async def generate():
            accumulated = []
            for provider, articles in news_fetcher.fetch_multiple_iter(
                providers=selected_providers,
                query=q,
                limit=limit,
            ):
                accumulated.extend(articles)
                # Rank and dedupe accumulated articles
                ranked = rank_articles(accumulated, query=q, dedupe=True)
                # Send update event
                payload = {
                    "provider": provider,
                    "articles": ranked
                }
                yield f"event: update\ndata: {json.dumps(payload)}\n\n"
                await asyncio.sleep(0)  # Allow other tasks to run
            
            # Final ranking pass
            final_ranked = rank_articles(accumulated, query=q, dedupe=True)
            # Send done event
            final_payload = {
                "provider": None,
                "articles": final_ranked
            }
            yield f"event: done\ndata: {json.dumps(final_payload)}\n\n"
        
        return StreamingResponse(generate(), media_type="text/event-stream")
    
    # Non-streaming: fetch all and return
    articles = news_fetcher.fetch_multiple(
        providers=selected_providers,
        query=q,
        limit=limit,
    )
    
    # Rank and dedupe
    articles = rank_articles(articles, query=q, dedupe=True)
    
    return articles
