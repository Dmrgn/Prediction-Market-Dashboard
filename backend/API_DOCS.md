# Prediction Market Dashboard - API Documentation

## Base URL
```
http://localhost:8000
```

---

## 1. Search Markets

### `GET /markets/search`

Search and filter markets across Polymarket and Kalshi with **on-demand loading**.

**🔄 On-Demand Behavior:**
- Markets are NOT pre-loaded at startup
- First search for a term queries APIs directly (may take 1-3 seconds)
- Results are progressively cached
- Subsequent searches for the same terms are instant
- Cache grows naturally based on usage

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `q` | string | Keyword search (searches title, description, tags) |
| `sector` | string | Filter by sector: `Sports`, `Politics`, `Crypto`, `Economics`, `Tech`, `Entertainment`, `Science`, `Other` |
| `tags` | string[] | Filter by tags (e.g., `tags=NBA&tags=Lakers`) |
| `source` | string | Filter by platform: `polymarket` or `kalshi` |
| `limit` | int | Max results (default: 50) |
| `offset` | int | Pagination offset (default: 0) |

**Example Requests:**

```bash
# Keyword search
curl "http://localhost:8000/markets/search?q=bitcoin"

# Browse by sector
curl "http://localhost:8000/markets/search?sector=Sports"

# Combined search + filter
curl "http://localhost:8000/markets/search?q=lebron&sector=Sports"

# Filter by source
curl "http://localhost:8000/markets/search?q=trump&source=kalshi"

# Pagination
curl "http://localhost:8000/markets/search?sector=Politics&limit=20&offset=40"
```

**Response:**

```json
{
  "markets": [
    {
      "market_id": "0x...",
      "title": "Bitcoin above $100k by EOY?",
      "description": "This market resolves to Yes if...",
      "category": "Crypto",
      "sector": "Crypto",
      "tags": ["Bitcoin", "Crypto", "2025 Predictions"],
      "ticker": null,
      "source": "polymarket",
      "source_id": "bitcoin-above-100k",
      "outcomes": [
        {"outcome_id": "123...", "name": "Yes", "price": 0.65},
        {"outcome_id": "456...", "name": "No", "price": 0.35}
      ],
      "status": "active",
      "image_url": "https://..."
    }
  ],
  "total": 753,
  "facets": {
    "sectors": {"Sports": 8752, "Politics": 4098, "Crypto": 3400, ...},
    "sources": {"polymarket": 20614, "kalshi": 4029},
    "tags": {"Politics": 3192, "Crypto": 1284, "NBA": 1266, ...}
  }
}
```

**Frontend Usage:**

```typescript
// React example
const [markets, setMarkets] = useState([]);
const [facets, setFacets] = useState({});

async function search(query: string, filters: SearchFilters) {
  const params = new URLSearchParams();
  if (query) params.set('q', query);
  if (filters.sector) params.set('sector', filters.sector);
  if (filters.source) params.set('source', filters.source);
  
  const res = await fetch(`/markets/search?${params}`);
  const data = await res.json();
  
  setMarkets(data.markets);
  setFacets(data.facets); // Use for filter chips/sidebar
}
```

---

## 2. Get Market History (Time Series)

### `GET /markets/{market_id}/history`

Get historical price data for charting.

**Path Parameters:**
- `market_id`: The market's unique ID

**Query Parameters:**
- `outcome_id` (optional): Specific outcome to get history for. Defaults to first outcome.

**Example:**

```bash
curl "http://localhost:8000/markets/0x123abc.../history"
```

**Response:**

```json
[
  {"ts": "2024-01-17T10:00:00Z", "price": 0.65, "bid": 0.64, "ask": 0.66},
  {"ts": "2024-01-17T10:01:00Z", "price": 0.66, "bid": 0.65, "ask": 0.67},
  ...
]
```

---

## 3. Get Order Book

### `GET /markets/{market_id}/orderbook`

Get current order book (bids/asks).

**Example:**

```bash
curl "http://localhost:8000/markets/KXTRUMP-26JAN18/orderbook"
```

**Response:**

```json
{
  "bids": [
    {"p": 0.65, "s": 1000.0},
    {"p": 0.64, "s": 500.0}
  ],
  "asks": [
    {"p": 0.66, "s": 800.0},
    {"p": 0.67, "s": 1200.0}
  ]
}
```

---

## 4. WebSocket - Live Updates

### `WS /ws`

Subscribe to real-time market updates.

**Connect:**

```javascript
const ws = new WebSocket('ws://localhost:8000/ws');
```

**Subscribe to a Market:**

```javascript
ws.send(JSON.stringify({
  op: "subscribe_market",
  market_id: "0x123abc..."
}));
```

**Unsubscribe:**

```javascript
ws.send(JSON.stringify({
  op: "unsubscribe_market", 
  market_id: "0x123abc..."
}));
```

**Incoming Messages:**

```json
// Quote update
{
  "type": "quote",
  "market_id": "0x123...",
  "outcome_id": "456...",
  "price": 0.67,
  "bid": 0.66,
  "ask": 0.68,
  "ts": "2024-01-17T10:05:00Z"
}

// Orderbook update
{
  "type": "orderbook",
  "market_id": "0x123...",
  "outcome_id": "456...",
  "bids": [...],
  "asks": [...]
}
```

**React Hook Example:**

```typescript
function useMarketStream(marketId: string) {
  const [quote, setQuote] = useState(null);
  const [orderbook, setOrderbook] = useState(null);
  
  useEffect(() => {
    const ws = new WebSocket('ws://localhost:8000/ws');
    
    ws.onopen = () => {
      ws.send(JSON.stringify({
        op: "subscribe_market",
        market_id: marketId
      }));
    };
    
    ws.onmessage = (e) => {
      const data = JSON.parse(e.data);
      if (data.type === 'quote') setQuote(data);
      if (data.type === 'orderbook') setOrderbook(data);
    };
    
    return () => {
      ws.send(JSON.stringify({
        op: "unsubscribe_market",
        market_id: marketId
      }));
      ws.close();
    };
  }, [marketId]);
  
  return { quote, orderbook };
}
```

---

## 5. List All Markets (Legacy)

### `GET /markets`

Simple market listing without facets.

```bash
curl "http://localhost:8000/markets?source=polymarket&q=bitcoin"
```

---

## Market Object Schema

```typescript
interface Market {
  market_id: string;      // Unique identifier
  title: string;          // Display title
  description?: string;   // Full description/rules
  category?: string;      // Source category
  sector?: string;        // Normalized: Sports, Politics, Crypto, etc.
  tags: string[];         // Filterable tags
  ticker?: string;        // Kalshi ticker (e.g., KXTRUMP-26JAN18)
  source: "polymarket" | "kalshi";
  source_id: string;      // Original ID from source
  outcomes: Outcome[];    // Yes/No or multiple outcomes
  status: string;         // "active", "closed"
  image_url?: string;     // Market image
}

interface Outcome {
  outcome_id: string;     // Use for orderbook/history lookups
  name: string;           // "Yes", "No", or custom
  price: number;          // 0.0 - 1.0 (probability)
}
```

---

## Typical Frontend Flow

1. **Initial Load:** `GET /markets/search` → Display markets + facets for filters
2. **User Searches:** `GET /markets/search?q=bitcoin` → Update results
3. **User Filters:** `GET /markets/search?sector=Sports` → Update results
4. **User Clicks Market:** 
   - `GET /markets/{id}/history` → Show price chart
   - `GET /markets/{id}/orderbook` → Show order book
   - `WS subscribe_market` → Start live updates
5. **User Leaves Market:** `WS unsubscribe_market` → Stop updates

---

## Notes

- **On-Demand Loading:** Both Polymarket and Kalshi use on-demand loading. First search for a term may take 1-3 seconds as it queries the API, but results are cached. Subsequent searches are instant.
- **Cache Behavior:** Markets are only cached when searched or subscribed to via WebSocket. The cache grows naturally based on actual usage.
- **Facets:** Facets reflect only cached markets. In a fresh instance, facets will be empty until users search. Your frontend should handle this appropriately.
- **Outcome Prices:** Range 0.0-1.0, representing probability. Multiply by 100 for percentage display.
- **Startup Time:** Server starts instantly with no pre-loading delay.
