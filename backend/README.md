# Antigravity API Documentation

This backend aggregates prediction market data from **Polymarket** and **Kalshi** into a unified, real-time API. It is designed to power a professional "Bloomberg-style" terminal.

## Quick Start

```bash
cd backend
uv sync
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## Base URL
`http://localhost:8000`

---

## 1. Search & Discovery (The Command Palette)

### `GET /markets`
Use this to power your global search bar.

- **Params**:
    - `q` (string, optional): Text to search. Matches **Title** (e.g. "Election") OR **Outcome Name** (e.g. "Trump").
    - `source` (string, optional): Filter by `polymarket` or `kalshi`.
- **Response**: List of `Market` objects.

```json
[
  {
    "market_id": "0xaf9d0e...",
    "title": "Will Trump deport less than 250,000?",
    "source": "polymarket",
    "outcomes": [
      { "outcome_id": "101676997...", "name": "Yes", "price": 0.041 },
      { "outcome_id": "415329280...", "name": "No", "price": 0.959 }
    ]
  }
]
```

---

## 2. Market Context & Linking

### `GET /markets/{id}`
Get details for a specific selected market.

### `GET /markets/{id}/related` (The "Arbitrage" Link)
Finds the **matching market** on the competitor exchange. Use this to automatically open the comparison view.

- **Response**: A single `Market` object (or 404 if no match found).
- **Workflow**:
    1. User selects Polymarket "Election".
    2. Call `related`.
    3. Backend returns Kalshi "Election".
    4. Frontend displays both side-by-side.

---

## 3. Real-Time Data (The Panels)

### `GET /markets/{id}/orderbook`
Get the current Order Book (Bids/Asks) for a specific outcome.

- **Params**: `outcome_id` (Required for multi-outcome markets).
- **Response**:
```json
{
  "market_id": "...",
  "outcome_id": "...",
  "ts": 1768637041.29,
  "bids": [ { "p": 0.06, "s": 10.0 }, { "p": 0.05, "s": 985.0 } ],
  "asks": [ { "p": 0.09, "s": 10.0 }, { "p": 0.10, "s": 100.0 } ]
}
```

### `GET /markets/{id}/history`
Get recent price history for the chart (up to 1 hour at 1 point/second).

- **Params**: `outcome_id` (Required).
- **Response**: List of quote points.
```json
[
  { "ts": 1705470000.0, "mid": 0.55, "bid": 0.54, "ask": 0.56, "volume": null },
  ...
]
```

### `WS /ws` (Live Stream)
Connect once to stream updates for *all* active markets.

- **URL**: `ws://localhost:8000/ws`
- **On Connect**: Send `{"op": "subscribe"}` to start receiving updates
- **Messages**:
    - `type: "quote"`: New Best Bid/Offer updates.
    - `type: "orderbook"`: Full orderbook snapshot updates.

```json
{"type": "quote", "market_id": "...", "outcome_id": "...", "ts": 1768637039.89, "mid": 0.5, "bid": 0.06, "ask": 0.09}
```

---

## Data Sources

### Polymarket
- **Market Discovery**: [Gamma API](https://gamma-api.polymarket.com) - Active markets with `clobTokenIds`
- **Orderbooks**: [CLOB API](https://clob.polymarket.com) - Real-time depth

### Kalshi
- **Events**: `/events` endpoint for market categories
- **Markets**: `/markets?event_ticker=...` for markets per event
- **Orderbooks**: `/markets/{ticker}/orderbook`

---

## Frontend Integration Recipes

### 📊 Recipe: The "Aggregated View"
To show a unified view of "Trump 2024":

1.  **Search**: `GET /markets?q=Trump` -> Result: `PolyMarket_A`
2.  **Pair**: `GET /markets/PolyMarket_A/related` -> Result: `KalshiMarket_B`
3.  **Fetch Data**:
    - `GET .../PolyMarket_A/orderbook?outcome_id=TrumpToken`
    - `GET .../KalshiMarket_B/orderbook?outcome_id=TrumpToken`
4.  **Visualize**:
    - **Chart**: Plot both history lines on one graph.
    - **Composite Book**: Merge the `bids` arrays. Sort by `p` DESC. Show "Best Bid" regardless of source.

### 📈 Recipe: Real-Time Chart with Historical Data
1. **Load History**: `GET /markets/{id}/history?outcome_id=...` -> Initial chart data points
2. **Connect WebSocket**: `ws://localhost:8000/ws`
3. **Subscribe**: Send `{"op": "subscribe"}`
4. **On Quote**: Append new points to chart in real-time
5. **On Orderbook**: Update depth visualization

---

## Testing

```bash
# Verify WebSocket streaming
python3 verify_ws.py

# Check markets loaded
curl http://localhost:8000/markets | python3 -c "import sys, json; print(f'Loaded {len(json.load(sys.stdin))} markets')"

# Test orderbook
curl "http://localhost:8000/markets?source=kalshi" | python3 -c "
import sys, json
m = json.load(sys.stdin)[0]
print(f'Market: {m[\"market_id\"]}')"
```
