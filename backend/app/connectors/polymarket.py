import httpx
import asyncio
import json
import re
from ..schemas import Market, Outcome, OrderBookLevel, Event
from ..state import StateManager
from ..taxonomy import get_sector_from_pm_tags, extract_pm_tag_labels

# Polymarket has 2 APIs:
# - Gamma API: Market discovery (current markets, metadata, clobTokenIds)
# - CLOB API: Trading (orderbooks, order placement)
GAMMA_API_URL = "https://gamma-api.polymarket.com"
CLOB_API_URL = "https://clob.polymarket.com"

# Common stop words to filter out for smarter search
STOP_WORDS = {
    "a", "an", "the", "is", "are", "was", "were", "will", "would", "could", 
    "should", "be", "been", "being", "have", "has", "had", "do", "does", 
    "did", "can", "may", "might", "must", "shall", "to", "of", "in", "for",
    "on", "with", "at", "by", "from", "as", "into", "through", "during",
    "before", "after", "above", "below", "between", "under", "again", "then",
    "once", "here", "there", "when", "where", "why", "how", "all", "each",
    "every", "both", "few", "more", "most", "other", "some", "such", "no",
    "nor", "not", "only", "own", "same", "so", "than", "too", "very", "just",
    "and", "but", "if", "or", "because", "until", "while", "this", "that",
    "these", "those", "what", "which", "who", "whom", "it", "its", "i", "we",
    "you", "he", "she", "they", "them", "his", "her", "our", "your", "their"
}

def extract_keywords(query: str) -> list[str]:
    """Extract meaningful keywords from natural language query."""
    # Lowercase and extract words
    words = re.findall(r'\b[a-zA-Z]+\b', query.lower())
    # Filter stop words and short words
    keywords = [w for w in words if w not in STOP_WORDS and len(w) > 1]
    return keywords



class PolymarketConnector:
    def __init__(self, state_manager: StateManager):
        self.state = state_manager
        self.gamma_client = httpx.AsyncClient(base_url=GAMMA_API_URL, timeout=30.0)
        self.clob_client = httpx.AsyncClient(base_url=CLOB_API_URL, timeout=30.0)

    async def search_markets(self, query: str) -> list[Market]:
        """
        On-demand search for markets using Polymarket's /public-search API.
        This endpoint returns many more results than paginating through events.
        """
        q_lower = query.lower()
        results = []
        seen_ids = set()
        
        # === STEP 1: Check cache ===
        cached = [
            m for m in self.state.get_all_markets() 
            if m.source == "polymarket" and (
                q_lower in m.title.lower() or 
                (m.description and q_lower in m.description.lower())
            )
        ]
        for m in cached:
            if m.market_id not in seen_ids:
                seen_ids.add(m.market_id)
                results.append(m)
        
        # === STEP 2: Use /public-search API (much better coverage) ===
        try:
            resp = await self.gamma_client.get("/public-search", params={"q": query})
            if resp.status_code == 200:
                data = resp.json()
                
                for event in data.get("events", []):
                    # Get tags/sector from event
                    tags = event.get("tags", [])
                    sector = get_sector_from_pm_tags(tags)
                    tag_labels = extract_pm_tag_labels(tags)
                    
                    # Process each market in the event
                    for market_data in event.get("markets", []):
                        # Skip closed markets
                        if market_data.get("closed"):
                            continue
                            
                        m = self._normalize_event_market(market_data, event)
                        if m and m.market_id not in seen_ids:
                            m.sector = sector
                            m.tags = tag_labels
                            seen_ids.add(m.market_id)
                            self.state.update_market(m)
                            results.append(m)
                            
                            if len(results) >= 100:
                                break
                    
                    if len(results) >= 100:
                        break
            else:
                print(f"[Polymarket] Public search returned {resp.status_code}")
                    
        except Exception as e:
            print(f"[Polymarket] Public search error: {e}")
        
        return results[:100]

    async def search_events(self, query: str) -> tuple[list[Event], list[Market]]:
        """
        Search for events (groups of related markets) on Polymarket.
        Uses smart keyword extraction for natural language queries.
        
        Returns Event objects containing their child markets.
        """
        keywords = extract_keywords(query)
        if not keywords:
            keywords = [query.strip().lower()]
        
        events = []
        standalone_markets = []
        
        try:
            # Fetch events from API (no title filtering available in API)
            # We'll filter client-side
            resp = await self.gamma_client.get("/events", params={
                "closed": False,
                "limit": 100,  # Fetch more to have enough results after filtering
                "order": "volume24hr",
                "ascending": False
            })
            
            if resp.status_code != 200:
                return [], []
            
            data = resp.json()
            
            # Filter events by keywords
            for event_data in data:
                title = event_data.get("title", "").lower()
                description = event_data.get("description", "").lower()
                
                # Check if any keyword matches the title or description
                if not any(kw in title or kw in description for kw in keywords):
                    continue
                event_markets = event_data.get("markets", [])
                
                # Get tags/sector
                tags = event_data.get("tags", [])
                sector = get_sector_from_pm_tags(tags)
                tag_labels = extract_pm_tag_labels(tags)
                
                # Normalize all markets in this event
                markets = []
                for market_data in event_markets:
                    market = self._normalize_event_market(market_data, event_data)
                    if market:
                        market.sector = sector
                        market.tags = tag_labels
                        self.state.update_market(market)
                        markets.append(market)
                
                if not markets:
                    continue
                
                # If event has multiple markets, it's a true event
                # If single market, treat as standalone
                if len(markets) > 1:
                    events.append(Event(
                        event_id=str(event_data.get("id", "")),
                        title=event_data.get("title", "Unknown Event"),
                        description=event_data.get("description"),
                        source="polymarket",
                        slug=event_data.get("slug"),
                        markets=markets
                    ))
                else:
                    standalone_markets.extend(markets)
        
        except Exception as e:
            print(f"[Polymarket] Event search error: {e}")
        
        return events, standalone_markets

    async def fetch_by_slug(self, slug: str) -> list[Market]:
        """
        Fetch markets from a Polymarket event by its URL slug.
        
        E.g., https://polymarket.com/event/us-strikes-iran-by
        → fetch_by_slug("us-strikes-iran-by")
        
        Returns list of Market objects for all markets in that event.
        """
        try:
            resp = await self.gamma_client.get("/events", params={"slug": slug})
            if resp.status_code != 200:
                print(f"[Polymarket] Slug lookup failed: {resp.status_code}")
                return []
            
            data = resp.json()
            if not data:
                return []
            
            event = data[0]
            tags = event.get("tags", [])
            sector = get_sector_from_pm_tags(tags)
            tag_labels = extract_pm_tag_labels(tags)
            
            results = []
            for market_data in event.get("markets", []):
                market = self._normalize_event_market(market_data, event)
                if market:
                    market.sector = sector
                    market.tags = tag_labels
                    # Cache it
                    self.state.update_market(market)
                    results.append(market)
            
            return results
            
        except Exception as e:
            print(f"[Polymarket] Slug lookup error: {e}")
            return []

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
                image_url=market_data.get("image") or (event.get("image") if event else None),
                volume_24h=float(market_data.get("volume24hr") or market_data.get("volume") or 0),
                liquidity=float(market_data.get("liquidity") or 0)
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
                image_url=data.get("image"),
                volume_24h=float(data.get("volume24hr") or data.get("volume") or 0),
                liquidity=float(data.get("liquidity") or 0)
            )
        except Exception as e:
            print(f"[Polymarket] Error normalizing market: {e}")
            return None

    async def spawn_poller(self, market_id: str):
        """Creates a polling task for a single market"""
        async def _poll_loop():
            print(f"[Polymarket] Starting poll loop for {market_id}")
            poll_count = 0
            while True:
                market = self.state.get_market(market_id)
                if market and market.source == "polymarket":
                    # Poll current prices from Gamma API (more reliable)
                    await self.poll_market_price(market_id)
                    
                    # Also poll orderbook (for OrderBookPanel)
                    await self.poll_orderbook(market_id)
                    
                poll_count += 1
                await asyncio.sleep(2.0)  # Poll every 2 seconds
        
        return asyncio.create_task(_poll_loop())

    async def poll_market_price(self, market_id: str):
        """Poll current prices from Gamma API"""
        try:
            # Fetch market data from Gamma API using conditionId
            resp = await self.gamma_client.get("/markets", params={"condition_ids": market_id})
            if resp.status_code == 200:
                markets = resp.json()
                if markets and len(markets) > 0:
                    market_data = markets[0]
                    
                    # Parse outcome prices
                    outcome_prices = json.loads(market_data.get("outcomePrices", "[]"))
                    clob_tokens = json.loads(market_data.get("clobTokenIds", "[]"))
                    
                    for i, token_id in enumerate(clob_tokens):
                        if i < len(outcome_prices):
                            price = float(outcome_prices[i])
                            # Update quote with current price
                            self.state.update_quote(market_id, token_id, price, price, price)
                            
        except Exception as e:
            print(f"[Polymarket] Error polling market price: {e}")

    async def poll_orderbook(self, market_id: str):
        """Poll orderbook for each outcome (token) in a market"""
        market = self.state.get_market(market_id)
        if not market:
            return

        for outcome in market.outcomes:
            token_id = outcome.outcome_id
            
            # Token IDs should be numeric strings (Polymarket CLOB tokens)
            if not token_id or len(token_id) < 10:
                continue
                
            try:
                resp = await self.clob_client.get("/book", params={"token_id": token_id})
                if resp.status_code == 200:
                    data = resp.json()
                    
                    bids = []
                    for x in data.get("bids", []):
                        price = float(x.get("price", 0)) if isinstance(x, dict) else float(x[0]) if x else 0
                        size = float(x.get("size", 0)) if isinstance(x, dict) else float(x[1]) if len(x) > 1 else 0
                        if price > 0:
                            bids.append(OrderBookLevel(p=price, s=size))
                    
                    asks = []
                    for x in data.get("asks", []):
                        price = float(x.get("price", 0)) if isinstance(x, dict) else float(x[0]) if x else 0
                        size = float(x.get("size", 0)) if isinstance(x, dict) else float(x[1]) if len(x) > 1 else 0
                        if price > 0:
                            asks.append(OrderBookLevel(p=price, s=size))
                    
                    # Sort: bids DESC (highest first), asks ASC (lowest first)
                    bids.sort(key=lambda x: x.p, reverse=True)
                    asks.sort(key=lambda x: x.p)
                    
                    self.state.update_orderbook(market_id, outcome.outcome_id, bids, asks)

                    # Calculate mid price
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
                else:
                    print(f"[Polymarket] Orderbook fetch failed for {token_id}: {resp.status_code}")
                        
            except Exception as e:
                print(f"[Polymarket] Error polling orderbook: {e}")
            
            await asyncio.sleep(0.1)

    async def fetch_price_history(self, token_id: str, interval: str = "1d") -> list[dict]:
        """
        Fetch historical price data from Polymarket CLOB API.
        
        Args:
            token_id: The CLOB token ID (outcome_id)
            interval: Time interval - '1h', '6h', '1d', '1w', '1m', or 'max'
        
        Returns:
            List of {t: timestamp, p: price} objects
        """
        try:
            # Map our intervals to Polymarket's format
            interval_map = {
                "1H": "1h",
                "6H": "6h", 
                "1D": "1d",
                "5D": "1d",  # 5 days = use 1d fidelity
                "1W": "1w",
                "1M": "1m",
                "ALL": "max"
            }
            pm_interval = interval_map.get(interval.upper(), "1d")
            
            resp = await self.clob_client.get("/prices-history", params={
                "market": token_id,
                "interval": pm_interval,
                "fidelity": 60  # 60 minute fidelity for cleaner data
            })
            
            if resp.status_code == 200:
                data = resp.json()
                history = data.get("history", [])
                return history
            else:
                print(f"[Polymarket] Price history failed: {resp.status_code}")
                return []
        except Exception as e:
            print(f"[Polymarket] Error fetching price history: {e}")
            return []
