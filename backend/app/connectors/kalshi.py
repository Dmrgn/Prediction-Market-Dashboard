import httpx
import asyncio
import re
from ..schemas import Market, Outcome, OrderBookLevel, Event
from ..state import StateManager
from ..taxonomy import get_sector_from_kalshi_category

KALSHI_API_URL = "https://api.elections.kalshi.com/trade-api/v2"

# Stop words for keyword extraction
STOP_WORDS = {
    "a", "an", "the", "is", "are", "was", "were", "will", "would", "could", 
    "be", "been", "to", "of", "in", "for", "on", "with", "at", "by", "from",
    "and", "but", "if", "or", "this", "that", "it", "what", "which", "who"
}

def extract_keywords(query: str) -> list[str]:
    """Extract meaningful keywords from natural language query."""
    words = re.findall(r'\b[a-zA-Z]+\b', query.lower())
    return [w for w in words if w not in STOP_WORDS and len(w) > 1]

SERIES_TO_SECTOR = {
    "KXNFL": "Sports", "KXNBA": "Sports", "KXMLB": "Sports", 
    "KXNHL": "Sports", "KXSOCCER": "Sports", "KXWNBA": "Sports",
    "KXBTC": "Crypto", "KXETH": "Crypto", "KXSOL": "Crypto",
    "KXSPY": "Economics", "KXGDP": "Economics", "KXFED": "Economics",
    "KXTRUMP": "Politics", "KXBIDEN": "Politics", "KXELEC": "Politics",
    "KXHOUSE": "Politics", "KXSENATE": "Politics",
    "KXAI": "Tech", "KXOPENAI": "Tech",
    "KXMV": "Other",
}


class KalshiConnector:
    def __init__(self, state_manager: StateManager):
        self.state = state_manager
        self.client = httpx.AsyncClient(base_url=KALSHI_API_URL, timeout=30.0)

    async def search_markets(self, query: str) -> list[Market]:
        """
        Search Kalshi markets. Since Kalshi has no keyword search API,
        we scan events with nested markets for better coverage.
        """
        q_lower = query.lower()
        q_upper = query.upper()
        results = []
        seen_ids = set()
        
        # === STEP 1: Check cache ===
        cached = [
            m for m in self.state.get_all_markets() 
            if m.source == "kalshi" and (
                q_lower in m.title.lower() or 
                q_lower in (m.ticker or "").lower()
            )
        ]
        for m in cached:
            if m.market_id not in seen_ids:
                seen_ids.add(m.market_id)
                results.append(m)
        
        # === STEP 2: Try exact ticker lookup ===
        if q_upper.startswith("KX") or "-" in query:
            try:
                resp = await self.client.get(f"/markets/{q_upper}")
                if resp.status_code == 200:
                    data = resp.json()
                    market_data = data.get("market")
                    if market_data:
                        m = self.normalize_market(market_data)
                        if m and m.market_id not in seen_ids:
                            seen_ids.add(m.market_id)
                            self.state.update_market(m)
                            results.append(m)
            except:
                pass
        
        # === STEP 3: Scan events with nested markets ===
        try:
            cursor = None
            pages_scanned = 0
            max_pages = 20  # Increased from 5 for better coverage
            
            while pages_scanned < max_pages and len(results) < 100:
                params = {
                    "limit": 200, 
                    "with_nested_markets": True,
                    "status": "open"
                }
                if cursor:
                    params["cursor"] = cursor
                
                resp = await self.client.get("/events", params=params)
                if resp.status_code != 200:
                    break
                
                data = resp.json()
                events = data.get("events", [])
                cursor = data.get("cursor")
                pages_scanned += 1
                
                # Find matching events by title
                for event in events:
                    title = event.get("title", "").lower()
                    event_ticker = event.get("event_ticker", "").lower()
                    
                    # Match on event title or ticker
                    if q_lower in title or q_lower in event_ticker:
                        # Process nested markets directly
                        for market_data in event.get("markets", []):
                            m = self.normalize_market(market_data)
                            if m and m.market_id not in seen_ids:
                                seen_ids.add(m.market_id)
                                self.state.update_market(m)
                                results.append(m)
                                
                                if len(results) >= 100:
                                    break
                    
                    if len(results) >= 100:
                        break
                
                if not cursor or len(results) >= 100:
                    break
                
                await asyncio.sleep(0.05)
                
        except Exception as e:
            print(f"[Kalshi] Search error: {e}")
        
        return results[:100]

    async def search_events(self, query: str) -> tuple[list[Event], list[Market]]:
        """
        Search for events on Kalshi, grouping markets by event.
        Returns (events, standalone_markets).
        """
        keywords = extract_keywords(query)
        if not keywords:
            keywords = [query.strip()]
        
        search_term = " ".join(keywords[:3])
        q_lower = search_term.lower()
        
        events = []
        standalone_markets = []
        seen_event_ids = set()
        
        try:
            cursor = None
            pages_scanned = 0
            
            while pages_scanned < 3:
                params = {"limit": 100}
                if cursor:
                    params["cursor"] = cursor
                
                resp = await self.client.get("/events", params=params)
                if resp.status_code != 200:
                    break
                
                data = resp.json()
                event_list = data.get("events", [])
                cursor = data.get("cursor")
                pages_scanned += 1
                
                for event_data in event_list:
                    title = event_data.get("title", "").lower()
                    event_ticker = event_data.get("event_ticker", "")
                    
                    # Check if matches query
                    if not any(kw in title for kw in keywords):
                        continue
                    
                    if event_ticker in seen_event_ids:
                        continue
                    seen_event_ids.add(event_ticker)
                    
                    # Fetch markets for this event
                    markets_resp = await self.client.get("/markets", params={
                        "event_ticker": event_ticker,
                        "limit": 50
                    })
                    
                    if markets_resp.status_code != 200:
                        continue
                    
                    markets = []
                    for item in markets_resp.json().get("markets", []):
                        m = self.normalize_market(item)
                        if m:
                            self.state.update_market(m)
                            markets.append(m)
                    
                    if not markets:
                        continue
                    
                    # Multi-market = event, single = standalone
                    if len(markets) > 1:
                        events.append(Event(
                            event_id=event_ticker,
                            title=event_data.get("title", "Unknown Event"),
                            source="kalshi",
                            markets=markets
                        ))
                    else:
                        standalone_markets.extend(markets)
                    
                    if len(events) >= 10:
                        break
                
                if not cursor or len(events) >= 10:
                    break
                
                await asyncio.sleep(0.05)
                
        except Exception as e:
            print(f"[Kalshi] Event search error: {e}")
        
        return events, standalone_markets

    def _get_sector_from_ticker(self, ticker: str) -> str:
        ticker_upper = ticker.upper()
        for prefix, sector in SERIES_TO_SECTOR.items():
            if ticker_upper.startswith(prefix):
                return sector
        return "Other"

    def normalize_market(self, data: dict) -> Market:
        try:
            market_ticker = data.get("ticker")
            if not market_ticker:
                return None
            
            status = data.get("status", "active")
            if status not in ["active", "open"]:
                return None
            
            is_multivariate = market_ticker.startswith("KXMV")
            sector = self._get_sector_from_ticker(market_ticker)
            
            title = data.get("title", "Unknown Market")
            subtitle = data.get("subtitle") or data.get("yes_sub_title", "")
            
            if is_multivariate and subtitle:
                title = f"Combo: {subtitle[:100]}"
            elif not title or title == "Unknown Market":
                title = subtitle or market_ticker
            
            if len(title) > 200:
                title = title[:197] + "..."
            
            yes_bid = float(data.get("yes_bid", 0)) / 100.0 if data.get("yes_bid") else 0
            yes_ask = float(data.get("yes_ask", 0)) / 100.0 if data.get("yes_ask") else 0
            yes_price = (yes_bid + yes_ask) / 2 if yes_bid and yes_ask else yes_bid or yes_ask
            
            # Get outcome names - ensure they're distinct
            yes_name_raw = data.get("yes_sub_title", "")
            no_name_raw = data.get("no_sub_title", "")
            
            # If both subtitles are the same or empty, use Yes/No
            if not yes_name_raw or not no_name_raw or yes_name_raw == no_name_raw:
                yes_name = "Yes"
                no_name = "No"
            else:
                yes_name = yes_name_raw[:50]
                no_name = no_name_raw[:50]
            
            outcomes = [
                Outcome(outcome_id=f"{market_ticker}_yes", 
                        name=yes_name, 
                        price=yes_price),
                Outcome(outcome_id=f"{market_ticker}_no", 
                        name=no_name, 
                        price=1.0 - yes_price if yes_price else 0)
            ]

            return Market(
                market_id=market_ticker,
                title=title,
                description=data.get("rules_primary"),
                category=data.get("event_ticker", "").split("-")[0],
                sector=sector,
                tags=[sector] if sector != "Other" else [],
                ticker=market_ticker,
                source="kalshi",
                source_id=market_ticker,
                outcomes=outcomes,
                status="active",
                image_url=None,
                volume_24h=float(data.get("volume") or 0),
                liquidity=float(data.get("liquidity") or data.get("open_interest") or 0)
            )
        except:
            return None
    
    async def spawn_poller(self, market_id: str):
        async def _poll_loop():
            while True:
                await self.poll_orderbook(market_id)
                await asyncio.sleep(1.0)
        return asyncio.create_task(_poll_loop())

    async def poll_orderbook(self, market_id: str):
        market = self.state.get_market(market_id)
        if not market or market.source != "kalshi":
            return
        try:
            resp = await self.client.get(f"/markets/{market.source_id}/orderbook")
            if resp.status_code == 200:
                data = resp.json().get("orderbook", {})
                yes_bids = [OrderBookLevel(p=float(l[0])/100, s=float(l[1])) 
                           for l in data.get("yes", []) if l and len(l) >= 2]
                yes_asks = [OrderBookLevel(p=1-float(l[0])/100, s=float(l[1])) 
                           for l in data.get("no", []) if l and len(l) >= 2]
                yes_bids.sort(key=lambda x: x.p, reverse=True)
                yes_asks.sort(key=lambda x: x.p)
                
                oid = market.outcomes[0].outcome_id
                self.state.update_orderbook(market_id, oid, yes_bids, yes_asks)
                if yes_bids and yes_asks:
                    self.state.update_quote(market_id, oid, 
                        (yes_bids[0].p + yes_asks[0].p)/2, yes_bids[0].p, yes_asks[0].p)
        except:
            pass
