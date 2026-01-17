import httpx
import asyncio
from ..schemas import Market, Outcome, OrderBookLevel
from ..state import StateManager
from ..taxonomy import get_sector_from_kalshi_category

KALSHI_API_URL = "https://api.elections.kalshi.com/trade-api/v2"

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

    async def fetch_initial_markets(self):
        """Initial cache: just first few pages for browsing"""
        try:
            total = 0
            cursor = None
            
            for _ in range(5):  # 5 pages = ~5K markets
                params = {"limit": 1000}
                if cursor:
                    params["cursor"] = cursor
                
                resp = await self.client.get("/markets", params=params)
                if resp.status_code != 200:
                    break
                
                data = resp.json()
                markets = data.get("markets", [])
                cursor = data.get("cursor")
                
                for item in markets:
                    m = self.normalize_market(item)
                    if m:
                        self.state.update_market(m)
                        total += 1
                
                if not cursor:
                    break
                await asyncio.sleep(0.1)
            
            print(f"[Kalshi] Initial load: {total} markets")
            return total
        except Exception as e:
            print(f"[Kalshi] Error: {e}")
            return 0

    async def search_markets(self, query: str) -> list[Market]:
        """
        Multi-step smart search:
        1. Check cache (instant)
        2. Try exact ticker lookup (instant)
        3. Scan events for matches (progressive)
        """
        q_lower = query.lower()
        q_upper = query.upper()
        results = []
        
        # === STEP 1: Check cache ===
        cached = [
            m for m in self.state.get_all_markets() 
            if m.source == "kalshi" and (
                q_lower in m.title.lower() or 
                q_lower in (m.ticker or "").lower()
            )
        ]
        if cached:
            results.extend(cached)
        
        # === STEP 2: Try exact ticker lookup ===
        # If query looks like a ticker (uppercase, has dash or KX prefix)
        if q_upper.startswith("KX") or "-" in query:
            try:
                resp = await self.client.get(f"/markets/{q_upper}")
                if resp.status_code == 200:
                    data = resp.json()
                    market_data = data.get("market")
                    if market_data:
                        m = self.normalize_market(market_data)
                        if m and m.market_id not in [r.market_id for r in results]:
                            self.state.update_market(m)
                            results.append(m)
            except:
                pass
        
        # === STEP 3: Search events for matches ===
        # Scan event pages looking for title matches
        if len(results) < 10:
            try:
                cursor = None
                pages_scanned = 0
                max_pages = 10  # Limit to avoid long searches
                
                while pages_scanned < max_pages:
                    params = {"limit": 100}
                    if cursor:
                        params["cursor"] = cursor
                    
                    resp = await self.client.get("/events", params=params)
                    if resp.status_code != 200:
                        break
                    
                    data = resp.json()
                    events = data.get("events", [])
                    cursor = data.get("cursor")
                    pages_scanned += 1
                    
                    # Find matching events
                    for event in events:
                        title = event.get("title", "").lower()
                        ticker = event.get("event_ticker", "").lower()
                        
                        if q_lower in title or q_lower in ticker:
                            # Fetch markets for this event
                            event_ticker = event.get("event_ticker")
                            markets_resp = await self.client.get("/markets", params={
                                "event_ticker": event_ticker,
                                "limit": 50
                            })
                            if markets_resp.status_code == 200:
                                for item in markets_resp.json().get("markets", []):
                                    m = self.normalize_market(item)
                                    if m and m.market_id not in [r.market_id for r in results]:
                                        self.state.update_market(m)
                                        results.append(m)
                            
                            # Found enough results
                            if len(results) >= 50:
                                break
                    
                    if not cursor or len(results) >= 50:
                        break
                    
                    await asyncio.sleep(0.05)
                    
            except Exception as e:
                print(f"[Kalshi] Search error: {e}")
        
        return results[:50]

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
            
            outcomes = [
                Outcome(outcome_id=f"{market_ticker}_yes", 
                        name=(data.get("yes_sub_title", "Yes") or "Yes")[:50], 
                        price=yes_price),
                Outcome(outcome_id=f"{market_ticker}_no", 
                        name=(data.get("no_sub_title", "No") or "No")[:50], 
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
                image_url=None
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
