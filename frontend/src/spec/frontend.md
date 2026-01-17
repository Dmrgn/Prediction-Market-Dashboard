# Specification: Predictive Market Dashboard

This specification defines a modular, agentic dashboard for prediction market data aggregation. The architecture prioritizes a "Tiles" based UI where panels are treated as instantiated classes, and an AI agent controls the workspace via a dedicated command layer.

## 1. Project Directory Structure
```text
.
├── backend/                  # Layer 0: Python/FastAPI Backend
│   ├── main.py               # API Entry point
│   └── ...
├── frontend/                 # React/TypeScript Frontend
│   ├── src/
│   │   ├── backendInterface.ts # Layer 1: API & WebSocket Logic
│   │   ├── commands/           # Layer 2: Command Registry & Agent Logic
│   │   │   ├── registry.ts
│   │   │   └── agentController.ts
│   │   ├── components/         # Layer 3: UI Components
│   │   │   ├── dashboard/      # Grid and Layout components
│   │   │   ├── panels/         # Panel "Classes" (Aggregator, News)
│   │   │   └── ui/             # Shadcn primitives
│   │   ├── hooks/              # useStore, useSocket, useAgent
│   │   ├── lib/                # Layer 4: Shared utilities (utils.ts)
│   │   ├── spec/               # Specification/Docs
│   │   │   └── frontend.md
│   │   ├── App.tsx             # Main React entry component
│   │   ├── index.tsx           # Web entry point
│   │   └── ...
│   ├── styles/               # Styling (globals.css)
│   ├── package.json
│   └── ...
├── app.md                    # Global Application Specification
└── .gitignore
```

---

## 2. Layer 1: Backend Interface (`./frontend/src/backendInterface.ts`)
The source of truth for all external data. It abstracts both REST and Real-time communication.

- **REST Interface:** Standard `fetch` calls with strict TypeScript return types.
- **WebSocket Interface:** A singleton manager that streams global quote updates (all connected clients receive broadcasts once connected).
- **Functionality:**
  - `fetchMarkets(q?, source?)`: Search markets by title or outcome name.
  - `fetchMarket(id)`: Fetch a single market record (used for panel metadata).
  - `fetchMarketData(id, outcomeId?)`: Returns historical quote points (mid/bid/ask + volume).
  - `fetchRelatedMarket(id)` and `fetchOrderbook(id, outcomeId)` for cross-market linking and depth.
  - `fetchNews(query)`: Currently mocked until a backend endpoint exists.

---

## 3. Layer 2: Command Layer & Agentic AI
This layer acts as the "Operating System" for the dashboard. It is used exclusively by the Command Palette and the AI Agent.

### 3.1 Command Registry
A collection of executable actions that modify the application state or query the backend.
- **Example Commands:** `OPEN_PANEL(type, data)`, `CLOSE_PANEL(id)`, `QUERY_MARKET(id)`.

### 3.2 Agentic AI Loop
The AI does not just execute one-off tasks; it operates in a **Thought-Action-Observation** loop:
1.  **Input:** User says "Find the most volatile political market and show me the latest news for it."
2.  **Step 1 (Action):** AI calls `GET_TRENDING_MARKETS({ category: 'politics' })`.
3.  **Step 2 (Observation):** AI receives data, identifies "Market X" as the most volatile.
4.  **Step 3 (Action):** AI calls `OPEN_PANEL('AGGREGATOR_GRAPH', { marketId: 'Market X' })`.
5.  **Step 4 (Action):** AI calls `OPEN_PANEL('NEWS_FEED', { query: 'Market X' })`.
6.  **Step 5 (Output):** AI informs the user: "I've opened the graph and news for Market X."

---

## 4. Layer 3: Panel System (The "Class" Model)
Panels are functionally self-contained. They interface **directly** with `backendInterface.ts` for data but rely on global state for their configuration.

### 4.1 Panel Instances
Each panel in the dashboard is an instance of a "Panel Class" defined by:
- `instanceId`: Unique UUID.
- `type`: `MARKET_AGGREGATOR_GRAPH` | `NEWS_FEED`.
- `config`: Instance-specific data (e.g., `{ marketId: "eth-price-v-dec-31" }`).

### 4.2 Initial Available Panels
- **Market Aggregator Graph:**
  - Fetches market metadata from `/markets/{id}` and historical quotes from `/markets/{id}/history`.
  - Renders a shadcn-styled Recharts area chart with optional mid-only or bid/ask/mid views.
  - Subscribes to the global WebSocket feed for live quote updates.
- **News Feed:**
  - Fetches news based on a keyword or market ID (mocked for now).
  - Features sentiment badges and timestamps.

---

## 5. Layer 4: Global Logic & Persistence (Zustand)
Manages the "Workspace" state.

- **State Definition:**
  ```ts
  interface PanelInstance {
    id: string;
    type: string;
    x: number; y: number; w: number; h: number; // Grid coordinates
    isVisible: boolean;
    data: any; // Instance-specific props
  }
  ```
- **Persistence:** The `persist` middleware from Zustand automatically saves the array of `PanelInstance` objects to `localStorage`.
- **Rehydration:** On app load, the dashboard iterates through the stored instances and renders the corresponding Panel Components.

---

## 6. UI & Styling
- **CSS:** Tailwind CSS v4 using the new `@theme` engine for highly performant styling.
- **Components:**
  - **Grid:** `react-grid-layout` for the drag/resize functionality.
- **Command Palette:** Built with `cmdk` (via Shadcn `Command`), it can execute agent commands and log activity.
- **Agent UI:** The agent activity feed is shared between the command palette and the right sidebar.
- **Sidebar:** Starts collapsed by default and automatically opens after running agent commands.
- **Market Aggregator Panel:** Provides a copy-to-clipboard button for the market ID.

---

## 7. Implementation Constraints
- **Self-Containment:** A panel must never reach into another panel's state.
- **Interface Only:** Panels use `backendInterface.ts` for data and may invoke the Command Layer for contextual actions like editing.
- **Command Access:** Panels are allowed to trigger the Command Layer for management actions (e.g. open the Command Palette with defaults).
- **Formatting:** All mathematical data (odds, percentages) must be typeset correctly using the dashboard's utility layer before rendering.
