import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .api import router, manager
from .state import StateManager
from .connectors.polymarket import PolymarketConnector
from .connectors.kalshi import KalshiConnector
from contextlib import asynccontextmanager

from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

# Global connectors
poly_connector = None
kalshi_connector = None

async def broadcast_listener(msg):
    # This function receives messages from StateManager (if we link them)
    # and broadcasts via WS manager.
    await manager.broadcast(msg.model_dump())

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    state = StateManager()
    
    # Initialize connectors
    global poly_connector, kalshi_connector
    poly_connector = PolymarketConnector(state)
    kalshi_connector = KalshiConnector(state)
    
    # Expose connectors to app state for API access
    app.state.poly = poly_connector
    app.state.kalshi = kalshi_connector
    
    # Initialize SubscriptionManager
    from .manager import SubscriptionManager
    sub_manager = SubscriptionManager()
    
    # Define spawner function that routes to correct connector
    async def spawner(market_id: str):
        market = state.get_market(market_id)
        if not market:
            print(f"Cannot spawn poller: Market {market_id} not found in state")
            # In a real app we might fetch it here.
            return None
        
        if market.source == "polymarket":
            return await poly_connector.spawn_poller(market_id)
        elif market.source == "kalshi":
            return await kalshi_connector.spawn_poller(market_id)
        return None

    sub_manager.set_spawner(spawner)

    # Initial fetch (Backgrounded so server starts immediately)
    print("Starting background market fetch...")
    async def fetch_all():
        print("Fetching Polymarket data...")
        await poly_connector.fetch_initial_markets()
        print("Fetching Kalshi data...")
        await kalshi_connector.fetch_initial_markets()
        print("Market fetch complete.")
        
    asyncio.create_task(fetch_all())
    print("Server startup complete. Markets loading in background.")
    
    # Link StateManager to WS manager (Broadcast)
    # Note: Connectors call state.update_*, state calls us back.
    # We route broadcast to SubscriptionManager.
    original_update_quote = state.update_quote
    def side_effect_quote(*args, **kwargs):
        msg = original_update_quote(*args, **kwargs)
        asyncio.create_task(sub_manager.broadcast(msg.market_id, msg.model_dump()))
        return msg
    state.update_quote = side_effect_quote
    
    original_update_ob = state.update_orderbook
    def side_effect_ob(*args, **kwargs):
        msg = original_update_ob(*args, **kwargs)
        asyncio.create_task(sub_manager.broadcast(msg.market_id, msg.model_dump()))
        return msg
    state.update_orderbook = side_effect_ob

    yield
    
    # Shutdown (Manager handles task cleanup if we implemented it, 
    # but for now we just let them die with loop or explicit cancel)
    # TODO: Shutdown logic

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/")
def read_root():
    return {"status": "ok", "service": "antigravity-backend"}
