import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .api import router, manager
from .state import StateManager
from .connectors.polymarket import PolymarketConnector
from .connectors.kalshi import KalshiConnector
from contextlib import asynccontextmanager

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
    
    # Initial fetch
    print("Fetching initial markets...")
    await poly_connector.fetch_initial_markets()
    await kalshi_connector.fetch_initial_markets()
    print("Market fetch complete.")
    
    # Start polling loops
    polling_task_p = asyncio.create_task(poly_connector.start_polling())
    polling_task_k = asyncio.create_task(kalshi_connector.start_polling())
    
    # Hack to link Broadcast:
    # We replace the update methods in StateManager? 
    # Or cleaner: StateManager emits events.
    # Let's modify StateManager to broadcast directly for MVP simplicity?
    # No, let's keep it separate.
    # We will run a loop that checks 'outbox' or just modify StateManager to accept a callback.
    
    original_update_quote = state.update_quote
    def side_effect_quote(*args, **kwargs):
        msg = original_update_quote(*args, **kwargs)
        asyncio.create_task(manager.broadcast(msg.model_dump()))
        return msg
    state.update_quote = side_effect_quote
    
    original_update_ob = state.update_orderbook
    def side_effect_ob(*args, **kwargs):
        msg = original_update_ob(*args, **kwargs)
        asyncio.create_task(manager.broadcast(msg.model_dump()))
        return msg
    state.update_orderbook = side_effect_ob

    yield
    
    # Shutdown
    polling_task_p.cancel()
    polling_task_k.cancel()

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
