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

    async def poll_orderbook(self, market_id: str):
        """Poll orderbook for each outcome (token) in a market"""
        market = self.state.get_market(market_id)
        if not market or market.source != "polymarket":
            return

        for outcome in market.outcomes:
            token_id = outcome.outcome_id
            
            # Skip invalid token IDs (not numeric = not real CLOB tokens)
            if not token_id.isdigit():
                continue
                
            try:
                resp = await self.clob_client.get("/book", params={"token_id": token_id})
                if resp.status_code == 200:
                    data = resp.json()
                    
                    # Parse bids/asks from CLOB response
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
                    
                    # Update State with orderbook
                    self.state.update_orderbook(market_id, outcome.outcome_id, bids, asks)
                    
                    # Generate quote from best bid/ask
                    if bids and asks:
                        best_bid = bids[0].p
                        best_ask = asks[0].p
                        mid = (best_bid + best_ask) / 2
                        self.state.update_quote(market_id, outcome.outcome_id, mid, best_bid, best_ask)
                    elif bids:
                        # Only bids available
                        best_bid = bids[0].p
                        self.state.update_quote(market_id, outcome.outcome_id, best_bid, best_bid, best_bid)
                    elif asks:
                        # Only asks available
                        best_ask = asks[0].p
                        self.state.update_quote(market_id, outcome.outcome_id, best_ask, best_ask, best_ask)
                        
            except Exception as e:
                # Silently skip - some tokens may not have orderbooks
                pass
                
            # Rate limit between token requests
            await asyncio.sleep(0.1)

    async def start_polling(self):
        """Continuously poll orderbooks for all Polymarket markets"""
        while True:
            markets = [m for m in self.state.get_all_markets() if m.source == "polymarket"]
            for m in markets:
                await self.poll_orderbook(m.market_id)
                await asyncio.sleep(0.3)  # Rate limit between markets
            await asyncio.sleep(2)  # Wait between full cycles
