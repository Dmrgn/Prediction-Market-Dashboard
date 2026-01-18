import asyncio
import time
import json
from typing import List, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, HTTPException, Request
from fastapi.responses import StreamingResponse
from .state import StateManager
from .schemas import Market, OrderBook, QuotePoint
from .news.fetcher import news_fetcher  # type: ignore

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

    # === ON-DEMAND KALSHI SEARCH ===
    # If user has a query and is searching Kalshi (or all sources), 
    # trigger on-demand API search
    if q and (not source or source == "kalshi"):
        kalshi = getattr(request.app.state, "kalshi", None)
        if kalshi:
            # This searches Kalshi API and caches results
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

    print(markets)
    
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

@router.get("/markets/{market_id}", response_model=Market)
async def get_market(market_id: str):
    market = state.get_market(market_id)
    if not market:
        raise HTTPException(status_code=404, detail="Market not found")
    return market

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
    # Accept connection
    # Note: SubscriptionManager logic in `subscribe` adds to set.
    # We should perform handshake/accept here? sub_manager.subscribe doesn't accept(), it assumes open.
    await websocket.accept()
    
    try:
        while True:
            # Client must send {"op": "subscribe", "market_id": "..."}
            # Or {"op": "unsubscribe", "market_id": "..."}
            data = await websocket.receive_json()
            op = data.get("op")
            
            if op == "subscribe":
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
                # Send update event
                payload = {
                    "provider": provider,
                    "articles": accumulated
                }
                yield f"event: update\ndata: {json.dumps(payload)}\n\n"
                await asyncio.sleep(0)  # Allow other tasks to run
            
            # Send done event
            final_payload = {
                "provider": None,
                "articles": accumulated
            }
            yield f"event: done\ndata: {json.dumps(final_payload)}\n\n"
        
        return StreamingResponse(generate(), media_type="text/event-stream")
    
    # Non-streaming: fetch all and return
    articles = news_fetcher.fetch_multiple(
        providers=selected_providers,
        query=q,
        limit=limit,
    )
    
    return articles
