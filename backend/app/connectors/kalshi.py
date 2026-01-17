import httpx
import asyncio
from ..schemas import Market, Outcome, OrderBookLevel
from ..state import StateManager

# Kalshi public API
KALSHI_API_URL = "https://api.elections.kalshi.com/trade-api/v2"

class KalshiConnector:
    def __init__(self, state_manager: StateManager):
        self.state = state_manager
        self.client = httpx.AsyncClient(base_url=KALSHI_API_URL, timeout=30.0)

    async def fetch_initial_markets(self):
        """Fetch markets from Kalshi by querying events first, then markets per event"""
        try:
            # Get list of events (categories/topics)
            events_resp = await self.client.get("/events", params={"limit": 30})
            if events_resp.status_code != 200:
                print(f"[Kalshi] Failed to fetch events: {events_resp.status_code}")
                return 0
            
            events = events_resp.json().get("events", [])
            
            count = 0
            for event in events[:15]:  # Limit for MVP
                event_ticker = event.get("event_ticker")
                if not event_ticker:
                    continue
                
                # Get markets for this event
                try:
                    markets_resp = await self.client.get("/markets", params={
                        "event_ticker": event_ticker,
                        "limit": 10
                    })
                    if markets_resp.status_code == 200:
                        markets_data = markets_resp.json().get("markets", [])
                        for item in markets_data[:5]:  # Top 5 per event
                            m = self.normalize_market(item, event)
                            if m:
                                self.state.update_market(m)
                                count += 1
                except Exception as e:
                    pass  # Skip failed event
                
                await asyncio.sleep(0.1)  # Rate limit
            
            print(f"[Kalshi] Loaded {count} markets from {len(events)} events")
            return count
            
        except Exception as e:
            print(f"[Kalshi] Error fetching markets: {e}")
            return 0

    def normalize_market(self, data: dict, event: dict = None) -> Market:
        """Convert Kalshi market data to canonical Market schema"""
        try:
            market_ticker = data.get("ticker")
            if not market_ticker:
                return None
            
            # Skip multivariate synthetic markets (they have no direct orderbooks)
            if market_ticker.startswith("KXMV"):
                return None
            
            # Use event title if available, fallback to market title
            title = data.get("title", "Unknown Market")
            if event:
                subtitle = data.get("yes_sub_title") or data.get("subtitle", "")
                if subtitle:
                    title = f"{event.get('title', title)} - {subtitle}"
            
            # Kalshi markets are binary Yes/No
            # yes_bid/yes_ask are in cents (0-100)
            yes_bid = float(data.get("yes_bid", 0)) / 100.0 if data.get("yes_bid") else 0
            yes_ask = float(data.get("yes_ask", 0)) / 100.0 if data.get("yes_ask") else 0
            yes_price = (yes_bid + yes_ask) / 2 if yes_bid and yes_ask else yes_bid or yes_ask
            
            outcomes = [
                Outcome(
                    outcome_id=f"{market_ticker}_yes",
                    name=data.get("yes_sub_title", "Yes"),
                    price=yes_price
                ),
                Outcome(
                    outcome_id=f"{market_ticker}_no",
                    name=data.get("no_sub_title", "No"),
                    price=1.0 - yes_price if yes_price else 0
                )
            ]

            return Market(
                market_id=market_ticker,
                title=title,
                description=data.get("rules_primary"),
                category=event.get("category") if event else None,
                ticker=market_ticker,
                source="kalshi",
                source_id=market_ticker,
                outcomes=outcomes,
                status=data.get("status", "active"),
                image_url=None
            )
        except Exception as e:
            print(f"[Kalshi] Error normalizing market {data.get('ticker')}: {e}")
            return None
    
    async def poll_orderbook(self, market_id: str):
        """Poll orderbook for a Kalshi market"""
        market = self.state.get_market(market_id)
        if not market or market.source != "kalshi":
            return
        
        try:
            resp = await self.client.get(f"/markets/{market.source_id}/orderbook")
            if resp.status_code == 200:
                data = resp.json()
                orderbook = data.get("orderbook", {})
                
                # Kalshi orderbook format:
                # "yes": [[price_cents, quantity], ...] - bids for Yes
                # "no": [[price_cents, quantity], ...] - bids for No
                # 
                # To get asks for Yes, we invert No bids: ask_yes = 1 - bid_no
                
                yes_levels = orderbook.get("yes") or []
                no_levels = orderbook.get("no") or []
                
                # Yes bids (direct from "yes" array)
                yes_bids = []
                for level in yes_levels:
                    if level and len(level) >= 2:
                        yes_bids.append(OrderBookLevel(
                            p=float(level[0]) / 100.0,
                            s=float(level[1])
                        ))
                
                # Yes asks (inverted from "no" array)
                # If someone is bidding 40 for No, that's an ask of 60 for Yes
                yes_asks = []
                for level in no_levels:
                    if level and len(level) >= 2:
                        price_no = float(level[0]) / 100.0
                        yes_asks.append(OrderBookLevel(
                            p=1.0 - price_no,
                            s=float(level[1])
                        ))
                
                # Sort: bids descending, asks ascending
                yes_bids.sort(key=lambda x: x.p, reverse=True)
                yes_asks.sort(key=lambda x: x.p)
                
                # Update State for Yes outcome
                yes_outcome_id = market.outcomes[0].outcome_id
                self.state.update_orderbook(market_id, yes_outcome_id, yes_bids, yes_asks)
                
                # Generate quote
                if yes_bids and yes_asks:
                    best_bid = yes_bids[0].p
                    best_ask = yes_asks[0].p
                    mid = (best_bid + best_ask) / 2
                    self.state.update_quote(market_id, yes_outcome_id, mid, best_bid, best_ask)
                elif yes_bids:
                    best_bid = yes_bids[0].p
                    self.state.update_quote(market_id, yes_outcome_id, best_bid, best_bid, best_bid + 0.01)
                elif yes_asks:
                    best_ask = yes_asks[0].p
                    self.state.update_quote(market_id, yes_outcome_id, best_ask, best_ask - 0.01, best_ask)

        except Exception as e:
            # Silently skip - orderbook may not exist for some markets
            pass

    async def start_polling(self):
        """Continuously poll orderbooks for all Kalshi markets"""
        while True:
            markets = [m for m in self.state.get_all_markets() if m.source == "kalshi"]
            for m in markets:
                await self.poll_orderbook(m.market_id)
                await asyncio.sleep(0.5)  # Rate limit
            await asyncio.sleep(2)  # Wait between full cycles
