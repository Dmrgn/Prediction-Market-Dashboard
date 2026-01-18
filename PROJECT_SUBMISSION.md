# Prediction Market Dashboard – Project Submission

## About the Project

Despite being incredibly powerful predictive tools, **prediction markets aren't very well-understood by the public**. They aggregate the collective wisdom of participants who put real money behind their beliefs, making them remarkably accurate at forecasting future events—from elections to sports to economic indicators. Yet accessing this information requires visiting multiple platforms, understanding complex interfaces, and manually correlating data.

**Prediction Market Dashboard** bridges this gap by using agentic workflows to **aggregate, expand, and clarify expected outcomes** from major prediction market platforms. We provide a unified interface where users can search across markets, view real-time price movements, and access AI-curated news that contextualizes market movements—all in one place.

---

## Inspiration

The idea came from experiencing the 2024 election cycle firsthand. Prediction markets like Polymarket and Kalshi were generating incredibly accurate signals about election outcomes, but:

1. **Fragmentation**: Data was scattered across multiple platforms with different interfaces
2. **No context**: Raw probabilities without news context left users guessing *why* prices moved
3. **Technical barriers**: Order books, spreads, and outcome contracts confused casual users

We asked ourselves: *What if there was a Bloomberg Terminal for prediction markets—one that was accessible to everyone?*

The result is this dashboard: a real-time aggregation platform that combines market data from Polymarket (20,000+ markets) and Kalshi (5,000+ markets) with live news from 4+ sources, all orchestrated by an AI agent that helps users navigate the complexity.

---

## What We Learned

Building this project taught us several key lessons:

### 1. API Design Matters
Polymarket uses a dual-API architecture (Gamma for discovery, CLOB for trading), while Kalshi has a unified REST API. Normalizing these into a single `Market` schema required careful abstraction:

```python
# Our unified schema handles both platforms
class Market(BaseModel):
    market_id: str
    title: str
    source: Literal["polymarket", "kalshi"]
    outcomes: List[Outcome]
    sector: Optional[str]  # Politics, Sports, Economics, etc.
```

### 2. Real-Time Data is Hard
WebSocket connections for live market updates required a subscription manager that:
- Spawns pollers only for actively-viewed markets
- Handles reconnection gracefully
- Broadcasts updates to multiple subscribers

### 3. News Ranking is Nuanced
We built a sophisticated ranking algorithm that balances:

$$\text{Score} = 0.50 \cdot \text{Relevance} + 0.35 \cdot \text{Recency} + 0.15 \cdot \text{Quality}$$

Where recency uses exponential decay with a 48-hour half-life:

$$\text{Recency}(t) = 0.5^{t/48}$$

### 4. Agentic Workflows Need Structure
Our AI agent follows a Thought-Action-Observation loop:

```typescript
// Agent Controller processes natural language
events.push(createEvent(`Thought: analyzing "${input}"`));
if (input.includes("news")) {
    events.push(createEvent("Action: opening news feed panel"));
    executeCommand(COMMANDS.OPEN_PANEL, { panelType: "NEWS_FEED" });
}
```

---

## How We Built It

### Architecture

The project follows a **full-stack TypeScript/Python architecture**:

```
┌─────────────────────────────────────────────────────────────┐
│                        FRONTEND                              │
│  React 19 + TypeScript + Zustand + TailwindCSS              │
│  ├── Resizable drag-and-drop panel grid                     │
│  ├── Real-time WebSocket chart updates                      │
│  ├── Server-Sent Events for streaming news                  │
│  └── Command palette with AI agent integration              │
├─────────────────────────────────────────────────────────────┤
│                        BACKEND                               │
│  FastAPI + Python 3.11+                                      │
│  ├── Polymarket Connector (Gamma + CLOB APIs)               │
│  ├── Kalshi Connector (REST API)                            │
│  ├── Multi-source News Fetcher (EXA, GDELT, Newsdata)       │
│  ├── Intelligent News Ranking (relevance + recency)         │
│  └── WebSocket subscription manager                         │
└─────────────────────────────────────────────────────────────┘
```

### Key Components

**1. Market Connectors**

We built async connectors for Polymarket and Kalshi that:
- Paginate through 25,000+ markets on startup
- Normalize data into a unified schema
- Poll orderbooks for subscribed markets in real-time

```python
# Polymarket fetches 20,000+ markets on startup
async def fetch_initial_markets(self):
    results = await asyncio.gather(
        self._fetch_sports_markets(),
        self._fetch_event_markets()
    )
    print(f"[Polymarket] Loaded {sum(results)} markets")
```

**2. News Aggregation**

Our news fetcher queries 4 providers in parallel and streams results:
- **EXA.ai**: AI-curated semantic search
- **GDELT 2.0**: Global event database
- **Newsdata.io**: Traditional news API
- **CryptoPanic**: Crypto-focused aggregator

```python
with ThreadPoolExecutor(max_workers=4) as executor:
    for future in as_completed(futures):
        provider, articles = future.result()
        yield provider, articles  # Stream to frontend via SSE
```

**3. Real-Time Updates**

The frontend maintains a WebSocket connection that:
- Subscribes to specific markets on-demand
- Receives quote updates (mid/bid/ask prices)
- Updates charts with sub-second latency

```typescript
// WebSocket subscription pattern
backendInterface.socket.subscribeToMarket(marketId, (point) => {
    setPoints(prev => [...prev.slice(-89), point]);
});
```

**4. Command Palette + AI Agent**

A keyboard-driven interface (Ctrl+K) lets users:
- Search markets across both platforms
- Open panels with specific configurations
- Interact with the AI agent using natural language

```typescript
// Natural language → structured commands
if (input.toLowerCase().includes("news")) {
    executeCommand(COMMANDS.OPEN_PANEL, {
        panelType: "NEWS_FEED",
        panelData: { query: input }
    });
}
```

---

## Challenges We Faced

### 1. Rate Limiting and API Costs
Both Polymarket and Kalshi have rate limits. We mitigated this by:
- Caching market data in memory
- Polling orderbooks only for subscribed markets
- Adding 100ms delays between paginated requests

### 2. Data Normalization
Polymarket encodes outcome data as JSON strings within JSON:

```python
# Polymarket returns: {"clobTokenIds": "[\"123\", \"456\"]"}
clob_token_ids = json.loads(data.get("clobTokenIds", "[]"))
```

Kalshi uses a different structure entirely. We wrote normalization functions for each.

### 3. Streaming News with Ranking
When news streams in from multiple providers:
1. First results arrive (e.g., GDELT in 200ms)
2. User sees initial ranked results
3. More results arrive (EXA in 800ms)
4. **Challenge**: Re-rank without jarring UI changes

Our solution: Re-rank the entire pool on each update and let React handle smooth re-renders.

### 4. English Language Filtering
GDELT returns articles in many languages. We integrated `langdetect` to filter:

```python
from langdetect import detect
def is_english(text: str) -> bool:
    try:
        return detect(text) == "en"
    except:
        return True  # Allow on failure
```

---

## Built With

### Languages
- TypeScript
- Python 3.11+

### Frontend
- React 19
- Zustand (state management)
- TailwindCSS 4
- react-grid-layout (resizable panels)
- Recharts (charting)
- cmdk (command palette)
- Radix UI (accessible components)

### Backend
- FastAPI
- httpx (async HTTP)
- python-dotenv
- langdetect

### APIs & Data Sources
- **Polymarket** (Gamma API + CLOB API)
- **Kalshi** (Elections API)
- **EXA.ai** (AI-powered news search)
- **GDELT 2.0** (Global news database)
- **Newsdata.io** (General news API)
- **CryptoPanic** (Crypto news aggregator)

### Tools
- Bun (frontend runtime/bundler)
- uv (Python package manager)
- Git

---

## "Try It Out" Links

| Type | URL |
|------|-----|
| **GitHub Repository** | https://github.com/[username]/Prediction-Market-Dashboard |
| **Live Demo** | *(Deploy pending)* |

---

## Running Locally

### Prerequisites
- Python 3.11+
- uv (`pip install uv`)
- Bun (https://bun.sh/)

### Backend
```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload
```

### Frontend
```bash
cd frontend
bun install
bun dev
```

### Environment Variables
Create a `.env` file in the project root:
```
EXA=your_exa_api_key
NDIO=your_newsdata_api_key
CPANIC=your_cryptopanic_api_key
```

---

## Future Roadmap

1. **User Authentication**: Save workspaces and preferences
2. **Layout Profiles**: Switch between "Sports", "Politics", "Crypto" presets
3. **Advanced AI Agent**: Natural language queries like "Show me markets where Trump is favored"
4. **Trade Execution**: Connect wallets for Polymarket, API keys for Kalshi
5. **Alerts**: Notify users when market prices cross thresholds

---

## Team

Built with ❤️ by [Your Name/Team]

---

*Last updated: 2026-01-17*
