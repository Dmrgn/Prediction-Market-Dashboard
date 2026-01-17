import asyncio
from collections import deque
from typing import Dict, List, Optional
from .schemas import Market, OrderBook, QuotePoint, QuoteMessage, OrderBookMessage
import time

MAX_HISTORY_POINTS = 3600  # 1 hour at 1 point/sec

class StateManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(StateManager, cls).__new__(cls)
            cls._instance.markets: Dict[str, Market] = {}
            # history: key = "{market_id}:{outcome_id}"
            cls._instance.quote_history: Dict[str, deque[QuotePoint]] = {}
            cls._instance.latest_orderbooks: Dict[str, OrderBook] = {}
            cls._instance.subscribers = set()
        return cls._instance

    def get_market(self, market_id: str) -> Optional[Market]:
        return self.markets.get(market_id)

    def get_all_markets(self) -> List[Market]:
        return list(self.markets.values())

    def update_market(self, market: Market):
        self.markets[market.market_id] = market

    def update_quote(self, market_id: str, outcome_id: str, price_mid: float, price_bid: float, price_ask: float, ts: float = None):
        if ts is None:
            ts = time.time()
        
        key = f"{market_id}:{outcome_id}"
        if key not in self.quote_history:
            self.quote_history[key] = deque(maxlen=MAX_HISTORY_POINTS)
        
        # Sampling: Only add if last point was > 1s ago (simple dedup)
        # For Hackathon, we just append everything if it's new enough or blindly append
        # Let's simple append for now.
        point = QuotePoint(ts=ts, mid=price_mid, bid=price_bid, ask=price_ask)
        self.quote_history[key].append(point)

        # Broadcast
        msg = QuoteMessage(
            market_id=market_id,
            outcome_id=outcome_id,
            ts=ts,
            mid=price_mid,
            bid=price_bid,
            ask=price_ask
        )
        # TODO: broadcasting handled by manager or api router? 
        # For simple architecture, maybe return the msg and let caller broadcast, 
        # or have an async broadcast method here.
        return msg

    def update_orderbook(self, market_id: str, outcome_id: str, bids: list, asks: list, ts: float = None):
        if ts is None:
            ts = time.time()
        
        key = f"{market_id}:{outcome_id}"
        ob = OrderBook(
            market_id=market_id,
            outcome_id=outcome_id,
            ts=ts,
            bids=bids,
            asks=asks
        )
        self.latest_orderbooks[key] = ob
        
        msg = OrderBookMessage(
            market_id=market_id,
            outcome_id=outcome_id,
            ts=ts,
            bids=bids,
            asks=asks
        )
        return msg

    def get_history(self, market_id: str, outcome_id: str) -> List[QuotePoint]:
        key = f"{market_id}:{outcome_id}"
        if key in self.quote_history:
            return list(self.quote_history[key])
        return []

    def get_orderbook(self, market_id: str, outcome_id: str) -> Optional[OrderBook]:
        key = f"{market_id}:{outcome_id}"
        return self.latest_orderbooks.get(key)
