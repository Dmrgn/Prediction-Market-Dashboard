import asyncio
import time
from typing import List, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, HTTPException, Request

router = APIRouter()
state = StateManager()

@router.get("/markets", response_model=List[Market])
async def list_markets(request: Request, source: Optional[str] = None, q: Optional[str] = None):
    # If q is present, perform global search via platform APIs
    if q:
        # Check if connectors are available (might be during startup/testing)
        poly = getattr(request.app.state, "poly", None)
        kalshi = getattr(request.app.state, "kalshi", None)
        
        tasks = []
        if poly and (not source or source == "polymarket"):
            tasks.append(poly.search_markets(q))
        if kalshi and (not source or source == "kalshi"):
            tasks.append(kalshi.search_markets(q))
            
        if tasks:
            results_list = await asyncio.gather(*tasks)
            # Flatten results
            external_markets = [item for sublist in results_list for item in sublist]
            
            # Update state with found markets so they can be retrieved/polled later
            for m in external_markets:
                 state.update_market(m)
                 
            return external_markets

    # Fallback to local state if no query or search failed (or for pure listing)
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

