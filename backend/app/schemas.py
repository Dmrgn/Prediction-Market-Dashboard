from typing import List, Optional, Literal
from pydantic import BaseModel, Field

class Outcome(BaseModel):
    outcome_id: str
    name: str # e.g. "Yes", "Trump"
    price: float = 0.0

class Market(BaseModel):
    market_id: str
    title: str
    description: Optional[str] = None
    category: Optional[str] = None
    ticker: Optional[str] = None
    source: Literal["polymarket", "kalshi"]
    source_id: str
    outcomes: List[Outcome] = []
    status: str = "active"
    image_url: Optional[str] = None

class QuotePoint(BaseModel):
    ts: float
    mid: float
    bid: Optional[float] = None
    ask: Optional[float] = None
    volume: Optional[float] = None

class OrderBookLevel(BaseModel):
    p: float # Price
    s: float # Size

class OrderBook(BaseModel):
    market_id: str
    outcome_id: str
    ts: float
    bids: List[OrderBookLevel]
    asks: List[OrderBookLevel]

class QuoteMessage(BaseModel):
    type: Literal["quote"] = "quote"
    market_id: str
    outcome_id: str
    ts: float
    mid: float
    bid: float
    ask: float

class OrderBookMessage(BaseModel):
    type: Literal["orderbook"] = "orderbook"
    market_id: str
    outcome_id: str
    ts: float
    bids: List[OrderBookLevel]
    asks: List[OrderBookLevel]
