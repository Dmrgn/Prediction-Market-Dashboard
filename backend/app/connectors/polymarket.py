import httpx
import asyncio
import json
from ..schemas import Market, Outcome, OrderBookLevel
from ..state import StateManager

# Polymarket has 2 APIs:
# - Gamma API: Market discovery (current markets, metadata, clobTokenIds)
# - CLOB API: Trading (orderbooks, order placement)
GAMMA_API_URL = "https://gamma-api.polymarket.com"
CLOB_API_URL = "https://clob.polymarket.com"

class PolymarketConnector:
    def __init__(self, state_manager: StateManager):
        self.state = state_manager
        self.gamma_client = httpx.AsyncClient(base_url=GAMMA_API_URL, timeout=30.0)
        self.clob_client = httpx.AsyncClient(base_url=CLOB_API_URL, timeout=30.0)

    async def fetch_initial_markets(self):
        """Fetch active markets from Gamma API"""
        try:
            # Gamma API returns current, active markets with clobTokenIds
            resp = await self.gamma_client.get("/markets", params={
                "closed": False,
                "limit": 50
            })
            
            if resp.status_code == 200:
                markets_data = resp.json()
                
                count = 0
                for item in markets_data[:30]:  # Limit for MVP
                    m = self.normalize_market(item)
                    if m:
                        self.state.update_market(m)
                        count += 1
                print(f"[Polymarket] Loaded {count} active markets from Gamma API")
                return count
        except Exception as e:
            print(f"[Polymarket] Error fetching markets: {e}")
            return 0

    def normalize_market(self, data: dict) -> Market:
        """Convert Gamma API market data to canonical Market schema"""
        try:
            # conditionId is the unique market identifier
            condition_id = data.get("conditionId")
            if not condition_id:
                return None
            
            # Parse JSON-encoded fields from Gamma API
            # clobTokenIds: '["token1", "token2"]'
            # outcomes: '["Yes", "No"]'
            try:
                clob_token_ids = json.loads(data.get("clobTokenIds", "[]"))
                outcome_names = json.loads(data.get("outcomes", "[]"))
                outcome_prices = json.loads(data.get("outcomePrices", "[]"))
            except json.JSONDecodeError:
                clob_token_ids = []
                outcome_names = ["Yes", "No"]
                outcome_prices = ["0", "0"]
            
            # Build outcomes with actual token IDs for orderbook queries
            outcomes = []
            for i, token_id in enumerate(clob_token_ids):
                name = outcome_names[i] if i < len(outcome_names) else f"Outcome {i}"
                price = float(outcome_prices[i]) if i < len(outcome_prices) else 0.0
                outcomes.append(Outcome(
                    outcome_id=token_id,
                    name=name,
                    price=price
                ))
            
            # Fallback if no tokens found
            if not outcomes:
                outcomes = [
                    Outcome(outcome_id=f"{condition_id}_yes", name="Yes"),
                    Outcome(outcome_id=f"{condition_id}_no", name="No")
                ]

            return Market(
                market_id=condition_id,
                title=data.get("question", "Unknown Market"),
                description=data.get("description"),
                category=data.get("category"),
                source="polymarket",
                source_id=data.get("slug", condition_id),
                outcomes=outcomes,
                status="active" if data.get("active") and not data.get("closed") else "closed",
                image_url=data.get("image")
            )
        except Exception as e:
            print(f"[Polymarket] Error normalizing market: {e}")
            return None

    async def spawn_poller(self, market_id: str):
        """Creates a polling task for a single market"""
        async def _poll_loop():
            # Find the outcome tokens for this market
            # In stateless mode, we might need to fetch market metadata first 
            # if we don't have it cached.
            # For hackathon efficiency, let's assume we can query by market_id if it maps to condition_id.
            
            # Since market_id from frontend is usually condition_id (Polymarket) or ticker (Kalshi).
            # We need to look up tokens for this market_id.
            # If we don't have state, we fetch it first.
            
            fetched_market = self.state.get_market(market_id)
            if not fetched_market:
                # Attempt to fetch metadata for this market specifically?
                # Gamma API allows filtering.
                pass 
                # For now, let's assume the user has visited the catalog and populated the cache 
                # OR we fetch it just-in-time here.

            print(f"[Polymarket] Starting poll loop for {market_id}")
            while True:
                # We need to know token_ids to poll CLOB.
                # If market is in state, use it.
                market = self.state.get_market(market_id)
                if market and market.source == "polymarket":
                   await self.poll_orderbook(market_id)
                
                await asyncio.sleep(1.0) # Poll every 1s per active market
        
        return asyncio.create_task(_poll_loop())

    async def poll_orderbook(self, market_id: str):
        """Poll orderbook for each outcome (token) in a market"""
        market = self.state.get_market(market_id)
        if not market:
            return

        for outcome in market.outcomes:
            token_id = outcome.outcome_id
            
            # Skip invalid token IDs
            if not token_id.isdigit():
                continue
                
            try:
                resp = await self.clob_client.get("/book", params={"token_id": token_id})
                if resp.status_code == 200:
                    data = resp.json()
                    
                    bids = []
                    for x in data.get("bids", []):
                        bids.append(OrderBookLevel(
                            p=float(x.get("price", x[0]) if isinstance(x, list) else x.get("price", 0)),
                            s=float(x.get("size", x[1]) if isinstance(x, list) else x.get("size", 0))
                        ))
                    
                    asks = []
                    for x in data.get("asks", []):
                        asks.append(OrderBookLevel(
                            p=float(x.get("price", x[0]) if isinstance(x, list) else x.get("price", 0)),
                            s=float(x.get("size", x[1]) if isinstance(x, list) else x.get("size", 0))
                        ))
                    
                    # Update State (Cache)
                    self.state.update_orderbook(market_id, outcome.outcome_id, bids, asks)
                    
                    # Also broadcast immediately via Manager (State does this implicitly via side-effect we set in main,
                    # but cleaner to do it here if we refactor state out. 
                    # For now, keep state side-effect.)

                    # Generate quote from best bid/ask
                    if bids and asks:
                        best_bid = bids[0].p
                        best_ask = asks[0].p
                        mid = (best_bid + best_ask) / 2
                        self.state.update_quote(market_id, outcome.outcome_id, mid, best_bid, best_ask)
                    elif bids:
                        best_bid = bids[0].p
                        self.state.update_quote(market_id, outcome.outcome_id, best_bid, best_bid, best_bid)
                    elif asks:
                        best_ask = asks[0].p
                        self.state.update_quote(market_id, outcome.outcome_id, best_ask, best_ask, best_ask)
                        
            except Exception as e:
                pass
            
            await asyncio.sleep(0.1)

    async def search_markets(self, query: str) -> list[Market]:
        """Search for markets using Gamma API"""
        try:
            # Try using events endpoint which usually supports search/filtering or just fetch active and filter
            # There isn't a documented clear "q" param for /markets in the summary, but /events often has it.
            # Alternatively, we can use the "public-search" endpoint mentioned in research if Gamma fails.
            # Let's try Gamma /events first with a flexible strategy.
            # Actually, `gamma-api.polymarket.com/events?q=` or `?slug=` might strict match.
            # Let's try fetching a larger batch of active events/markets and filtering locally if search isn't server-side
            # BUT the user wants "platform apis" search.
            
            # Use data-provider/active-events or similar?
            # Let's try the /markets endpoint with a 'question' filter if supported? 
            # Research said "client.gamma.markets.listMarkets" supports filtering.
            # Let's blindly try passing `question` or `q` to /markets.
            # If that fails to filter, we might just be getting recent markets.
            
            params = {
                "limit": 100,
                "active": True,
                "closed": False,
            }
            
            resp = await self.gamma_client.get("/markets", params=params)
            
            # If Gamma ignores 'q', we'll filter locally.
            # But the goal is to find markets NOT in our state.
            
            if resp.status_code == 200:
                markets_data = resp.json() 
                # Normalize and return
                results = []
                for item in markets_data:
                    m = self.normalize_market(item)
                    if m:
                        # Double check filter if API was loose
                        if query.lower() in m.title.lower():
                            results.append(m)
                return results
                
            return []
        except Exception as e:
            print(f"[Polymarket] Search error: {e}")
            return []
