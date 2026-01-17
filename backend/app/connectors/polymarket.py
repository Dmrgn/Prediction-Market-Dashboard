import httpx
import asyncio
import json
from ..schemas import Market, Outcome, OrderBookLevel
from ..state import StateManager
from ..taxonomy import get_sector_from_pm_tags, extract_pm_tag_labels

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
        """Fetch ALL active markets: sports via /sports, others via /events"""
        # Run sports and events fetch in parallel
        # Note: Event fetch might contain some sports, but unique IDs handle dupes in State
        results = await asyncio.gather(
            self._fetch_sports_markets(),
            self._fetch_event_markets()
        )
        sports_count, events_count = results
        total = sports_count + events_count
        print(f"[Polymarket] Loaded {total} markets ({sports_count} sports, {events_count} events)")
        return total

    async def _fetch_sports_markets(self) -> int:
        """Fetch sports markets using /sports metadata"""
        try:
            sports_resp = await self.gamma_client.get("/sports")
            if sports_resp.status_code != 200:
                print(f"[Polymarket] Failed to fetch /sports: {sports_resp.status_code}")
                return 0
            
            sports = sports_resp.json()
            total = 0
            
            for sport in sports:
                series_id = sport.get("series")
                sport_name = sport.get("sport", "").upper()
                if not series_id:
                    continue
                
                # Fetch events for this sport
                events = await self._fetch_events_paginated(series_id=series_id)
                
                for event in events:
                    for market_data in event.get("markets", []):
                        m = self._normalize_event_market(market_data, event)
                        if m:
                            m.sector = "Sports"
                            m.tags = [sport_name] if sport_name else ["Sports"]
                            self.state.update_market(m)
                            total += 1
                
                await asyncio.sleep(0.1)
            
            return total
        except Exception as e:
            print(f"[Polymarket] Error fetching sports markets: {e}")
            return 0

    async def _fetch_event_markets(self) -> int:
        """Fetch non-sports markets using /events with native tags"""
        try:
            events = await self._fetch_events_paginated()
            total = 0
            
            for event in events:
                tags = event.get("tags", [])
                sector = get_sector_from_pm_tags(tags)
                tag_labels = extract_pm_tag_labels(tags)
                
                # Skip sports (handled by _fetch_sports_markets)
                if sector == "Sports":
                    continue
                
                for market_data in event.get("markets", []):
                    m = self._normalize_event_market(market_data, event)
                    if m:
                        m.sector = sector
                        m.tags = tag_labels
                        self.state.update_market(m)
                        total += 1
            
            return total
        except Exception as e:
            print(f"[Polymarket] Error fetching event markets: {e}")
            return 0

    async def _fetch_events_paginated(self, series_id: str = None) -> list:
        """Paginated fetch of events"""
        events = []
        offset = 0
        limit = 100
        
        while True:
            params = {"closed": False, "limit": limit, "offset": offset}
            if series_id:
                params["series_id"] = series_id
            
            try:
                resp = await self.gamma_client.get("/events", params=params)
                if resp.status_code != 200:
                    break
                
                data = resp.json()
                if not data:
                    break
                
                events.extend(data)
                offset += len(data)
                
                if len(data) < limit:
                    break
                
                await asyncio.sleep(0.1)
            except Exception as e:
                print(f"[Polymarket] Pagination error: {e}")
                break
        
        return events

    def _normalize_event_market(self, market_data: dict, event: dict = None) -> Market:
        """Convert Gamma API event market data to canonical Market schema"""
        try:
            condition_id = market_data.get("conditionId")
            if not condition_id:
                return None
            
            # Skip closed markets
            if market_data.get("closed") or not market_data.get("active", True):
                return None
            
            # Parse JSON-encoded fields
            try:
                clob_token_ids = json.loads(market_data.get("clobTokenIds", "[]"))
                outcome_names = json.loads(market_data.get("outcomes", "[]"))
                outcome_prices = json.loads(market_data.get("outcomePrices", "[]"))
            except (json.JSONDecodeError, TypeError):
                clob_token_ids = []
                outcome_names = ["Yes", "No"]
                outcome_prices = ["0", "0"]
            
            # Build outcomes
            outcomes = []
            for i, token_id in enumerate(clob_token_ids):
                name = outcome_names[i] if i < len(outcome_names) else f"Outcome {i}"
                price = float(outcome_prices[i]) if i < len(outcome_prices) else 0.0
                outcomes.append(Outcome(
                    outcome_id=token_id,
                    name=name,
                    price=price
                ))
            
            if not outcomes:
                outcomes = [
                    Outcome(outcome_id=f"{condition_id}_yes", name="Yes"),
                    Outcome(outcome_id=f"{condition_id}_no", name="No")
                ]
            
            # Use event title if market title is generic
            title = market_data.get("question", "Unknown Market")
            if event and event.get("title"):
                event_title = event.get("title", "")
                if title == "Unknown Market" or len(title) < 10:
                    title = event_title
            
            return Market(
                market_id=condition_id,
                title=title,
                description=market_data.get("description") or event.get("description") if event else None,
                category=event.get("tags", [{}])[0].get("label") if event and event.get("tags") else None,
                source="polymarket",
                source_id=market_data.get("slug", condition_id),
                outcomes=outcomes,
                status="active" if market_data.get("active") and not market_data.get("closed") else "closed",
                image_url=market_data.get("image") or (event.get("image") if event else None)
            )
        except Exception as e:
            print(f"[Polymarket] Error normalizing market: {e}")
            return None

    def normalize_market(self, data: dict) -> Market:
        """Convert Gamma API market data to canonical Market schema (legacy)"""
        try:
            condition_id = data.get("conditionId")
            if not condition_id:
                return None
            
            try:
                clob_token_ids = json.loads(data.get("clobTokenIds", "[]"))
                outcome_names = json.loads(data.get("outcomes", "[]"))
                outcome_prices = json.loads(data.get("outcomePrices", "[]"))
            except json.JSONDecodeError:
                clob_token_ids = []
                outcome_names = ["Yes", "No"]
                outcome_prices = ["0", "0"]
            
            outcomes = []
            for i, token_id in enumerate(clob_token_ids):
                name = outcome_names[i] if i < len(outcome_names) else f"Outcome {i}"
                price = float(outcome_prices[i]) if i < len(outcome_prices) else 0.0
                outcomes.append(Outcome(
                    outcome_id=token_id,
                    name=name,
                    price=price
                ))
            
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
            print(f"[Polymarket] Starting poll loop for {market_id}")
            while True:
                market = self.state.get_market(market_id)
                if market and market.source == "polymarket":
                    await self.poll_orderbook(market_id)
                await asyncio.sleep(1.0)
        
        return asyncio.create_task(_poll_loop())

    async def poll_orderbook(self, market_id: str):
        """Poll orderbook for each outcome (token) in a market"""
        market = self.state.get_market(market_id)
        if not market:
            return

        for outcome in market.outcomes:
            token_id = outcome.outcome_id
            
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
                    
                    self.state.update_orderbook(market_id, outcome.outcome_id, bids, asks)

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
        """Search for markets (uses cached data now)"""
        # Search is now done against local cache in api.py
        # This method is kept for backwards compatibility
        q_lower = query.lower()
        all_markets = self.state.get_all_markets()
        results = [
            m for m in all_markets 
            if m.source == "polymarket" and q_lower in m.title.lower()
        ]
        return results[:50]
