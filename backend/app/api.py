import asyncio
import time
from typing import List, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, HTTPException
from .state import StateManager
from .schemas import Market, OrderBook, QuotePoint

from typing import List, Optional, Union
import json
from fastapi import FastAPI, Query
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

router = APIRouter()
state = StateManager()

@router.get("/markets", response_model=List[Market])
async def list_markets(source: Optional[str] = None, q: Optional[str] = None):
    markets = state.get_all_markets()
    if source:
        markets = [m for m in markets if m.source == source]
    if q:
        q_lower = q.lower()
        # Search in Title OR any Outcome Name
        markets = [
            m for m in markets 
            if q_lower in m.title.lower() or any(q_lower in o.name.lower() for o in m.outcomes)
        ]
    return markets

@router.get("/markets/{market_id}", response_model=Market)
async def get_market(market_id: str):
    market = state.get_market(market_id)
    if not market:
        raise HTTPException(status_code=404, detail="Market not found")
    return market

@router.get("/markets/{market_id}/history", response_model=List[QuotePoint])
async def get_market_history(market_id: str, outcome_id: Optional[str] = None):
    market = state.get_market(market_id)
    if not market:
        raise HTTPException(status_code=404, detail="Market not found")
    
    # Default to first outcome if not specified
    if not outcome_id and market.outcomes:
        outcome_id = market.outcomes[0].outcome_id
        
    if not outcome_id:
         raise HTTPException(status_code=400, detail="outcome_id required")

    return state.get_history(market_id, outcome_id)

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

manager = ConnectionManager()

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Wait for messages (subscribe, etc.)
            # For hackathon MVP, we just broadcast everything to everyone once connected
            # or we can implement basic subscribe logic if time permits.
            # Client sends: {"op": "subscribe"}
            data = await websocket.receive_json()
            # We can log subscriptions here
            
            # Keep connection open
            pass
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# Background Broadcast Loop
# We need a way to send updates from State to Websockets.
# Option: StateManager gets a reference to ConnectionManager?
# Or we poll StateManager for changes? 
# Better: StateManager calls a callback. 
# For Hackathon: let's patch StateManager to call manager.broadcast

async def broadcast_worker():
    # Hack: Monkey patch or just checking state?
    # Actually, StateManager shouldn't depend on API.
    # Let's make StateManager have an async callback list.
    pass


from news.fetcher import news_fetcher, Article
from news.rank import rank_articles

@router.get("/news/search", response_model=List[Article])
def search_news(
    q: str = Query(..., description="Search query"),
    providers: Optional[List[str]] = Query(
        None, description="Providers to query"
    ),
    limit: int = Query(20, ge=1, le=100),
    stream: bool = Query(False, description="Stream results as they arrive"),
):
    """
    Called when the user presses Enter in the search bar.
    Expected Request shape:
    GET /news/search?q=inflation&providers=newsapi&providers=gnews&limit=25
    
    Returns ranked, deduplicated articles from all providers.
    """
    
    selected_providers = providers or news_fetcher.available_providers()

    if stream:
        def event_stream():
            aggregated: List[Article] = []
            last_ranked: List[Article] = []

            for provider, result in news_fetcher.fetch_multiple_iter(
                providers=selected_providers,
                query=q,
                limit=limit,
            ):
                if result:
                    aggregated.extend(result)

                last_ranked = rank_articles(aggregated, dedupe=True, limit=limit)
                payload = {
                    "provider": provider,
                    "articles": last_ranked,
                }
                yield f"event: update\ndata: {json.dumps(payload)}\n\n"

            yield f"event: done\ndata: {json.dumps({'articles': last_ranked})}\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    # Fetch from all providers in parallel (blocking)
    raw_articles = news_fetcher.fetch_multiple(
        providers=selected_providers,
        query=q,
        limit=limit,
    )

    # Rank, dedupe, and limit results
    ranked = rank_articles(raw_articles, dedupe=True, limit=limit)

    return ranked
