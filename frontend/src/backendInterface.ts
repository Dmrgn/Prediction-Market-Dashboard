/**
 * Layer 1: Backend Interface
 * The source of truth for all external data.
 * Abstracts both REST and Real-time communication.
 */

const API_BASE_URL = import.meta.env?.VITE_API_BASE_URL ?? "http://localhost:8000";
const WS_BASE_URL = API_BASE_URL.replace(/^http/, "ws").replace(/\/$/, "") + "/ws";

type Outcome = {
  outcome_id: string;
  name: string;
  price: number;
};

type Market = {
  market_id: string;
  title: string;
  description?: string | null;
  category?: string | null;
  ticker?: string | null;
  source: "polymarket" | "kalshi";
  source_id: string;
  outcomes: Outcome[];
  status: string;
  image_url?: string | null;
};

type QuotePoint = {
  ts: number;
  mid: number;
  bid?: number | null;
  ask?: number | null;
  volume?: number | null;
};

type OrderBookLevel = {
  p: number;
  s: number;
};

type OrderBook = {
  market_id: string;
  outcome_id: string;
  ts: number;
  bids: OrderBookLevel[];
  asks: OrderBookLevel[];
};

type QuoteMessage = {
  type: "quote";
  market_id: string;
  outcome_id: string;
  ts: number;
  mid: number;
  bid: number;
  ask: number;
};

type OrderBookMessage = {
  type: "orderbook";
  market_id: string;
  outcome_id: string;
  ts: number;
  bids: OrderBookLevel[];
  asks: OrderBookLevel[];
};

type MarketPoint = {
  timestamp: string;
  price: number;
  volume: number;
};

type MarketDataResponse = {
  marketId: string;
  outcomeId: string | null;
  points: MarketPoint[];
};

type NewsItem = {
  id: string;
  title: string;
  source: string;
  sentiment: "positive" | "neutral" | "negative";
  publishedAt: string;
  url: string;
};

type NewsResponse = {
  query: string;
  items: NewsItem[];
};

const randomBetween = (min: number, max: number) => min + Math.random() * (max - min);

const buildMockNews = (query: string): NewsItem[] => {
  const sentiments: NewsItem["sentiment"][] = ["positive", "neutral", "negative"];
  return Array.from({ length: 6 }, (_, index) => {
    const sources = ["Polymarket", "Kalshi", "Forecast Desk"] as const;
    return {
      id: `${query}-${index}`,
      title: `Insight ${index + 1}: ${query} market update`,
      source: sources[index % sources.length] ?? "Market Desk",
      sentiment: sentiments[index % sentiments.length] ?? "neutral",
      publishedAt: new Date(Date.now() - index * 60 * 60 * 1000).toISOString(),
      url: "https://example.com/market-news",
    };
  });
};

const toMarketPoint = (point: QuotePoint): MarketPoint => ({
  timestamp: new Date(point.ts * 1000).toISOString(),
  price: point.mid,
  volume: point.volume ?? 0,
});

class MarketSocketManager {
  private subscriptions = new Map<string, Set<(data: MarketPoint) => void>>();
  private socket: WebSocket | null = null;
  private reconnectTimer: number | null = null;
  private connecting = false;

  private get hasSubscribers() {
    return Array.from(this.subscriptions.values()).some((handlers) => handlers.size > 0);
  }

  private ensureSocket() {
    if (this.socket || this.connecting) return;
    this.connecting = true;
    this.socket = new WebSocket(WS_BASE_URL);

    this.socket.addEventListener("open", () => {
      this.connecting = false;
      this.socket?.send(JSON.stringify({ op: "subscribe" }));
    });

    this.socket.addEventListener("message", (event) => {
      try {
        const payload = JSON.parse(event.data) as QuoteMessage | OrderBookMessage;
        if (payload.type !== "quote") return;
        const handlers = this.subscriptions.get(payload.market_id);
        if (!handlers || handlers.size === 0) return;
        const point: MarketPoint = {
          timestamp: new Date(payload.ts * 1000).toISOString(),
          price: payload.mid,
          volume: 0,
        };
        handlers.forEach((handler) => handler(point));
      } catch (error) {
        console.error("WebSocket message error", error);
      }
    });

    this.socket.addEventListener("close", () => {
      this.socket = null;
      this.connecting = false;
      if (this.hasSubscribers && this.reconnectTimer === null) {
        this.reconnectTimer = window.setTimeout(() => {
          this.reconnectTimer = null;
          this.ensureSocket();
        }, 2000);
      }
    });

    this.socket.addEventListener("error", () => {
      this.socket?.close();
    });
  }

  private closeSocketIfIdle() {
    if (this.hasSubscribers) return;
    if (this.socket) {
      this.socket.close();
      this.socket = null;
    }
    if (this.reconnectTimer !== null) {
      window.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  subscribeToMarket(marketId: string, handler: (data: MarketPoint) => void) {
    if (!marketId) return () => undefined;
    const handlers = this.subscriptions.get(marketId) ?? new Set();
    handlers.add(handler);
    this.subscriptions.set(marketId, handlers);

    this.ensureSocket();

    return () => {
      const current = this.subscriptions.get(marketId);
      if (!current) return;
      current.delete(handler);
      if (current.size === 0) {
        this.subscriptions.delete(marketId);
      }
      this.closeSocketIfIdle();
    };
  }

  unsubscribeFromMarket(marketId: string) {
    this.subscriptions.delete(marketId);
    this.closeSocketIfIdle();
  }
}

const marketSocketManager = new MarketSocketManager();

const fetchJson = async <T>(input: RequestInfo | URL, init?: RequestInit): Promise<T> => {
  const response = await fetch(input, init);
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
};

const buildUrl = (path: string, params?: Record<string, string | undefined>) => {
  const url = new URL(path, API_BASE_URL);
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value) url.searchParams.set(key, value);
    });
  }
  return url.toString();
};

export const backendInterface = {
  // REST Interface
  fetchMarkets: async (query?: string, source?: "polymarket" | "kalshi"): Promise<Market[]> =>
    fetchJson<Market[]>(buildUrl("/markets", { q: query, source })),

  fetchMarket: async (id: string): Promise<Market> => {
    if (!id) throw new Error("Market ID is required");
    return fetchJson<Market>(buildUrl(`/markets/${id}`));
  },

  fetchRelatedMarket: async (id: string): Promise<Market> => {
    if (!id) throw new Error("Market ID is required");
    return fetchJson<Market>(buildUrl(`/markets/${id}/related`));
  },

  fetchOrderbook: async (id: string, outcomeId: string): Promise<OrderBook> => {
    if (!id || !outcomeId) throw new Error("Market ID and outcome ID are required");
    return fetchJson<OrderBook>(buildUrl(`/markets/${id}/orderbook`, { outcome_id: outcomeId }));
  },

  fetchMarketData: async (id: string, outcomeId?: string): Promise<MarketDataResponse> => {
    if (!id) throw new Error("Market ID is required");
    const market = await backendInterface.fetchMarket(id);
    const resolvedOutcomeId = outcomeId ?? market.outcomes?.[0]?.outcome_id ?? null;
    if (!resolvedOutcomeId) {
      return { marketId: market.market_id, outcomeId: null, points: [] };
    }
    console.log(buildUrl(`/markets/${market.market_id}/history`, { outcome_id: resolvedOutcomeId }));
    const history = await fetchJson<QuotePoint[]>(
      buildUrl(`/markets/${market.market_id}/history`, { outcome_id: resolvedOutcomeId }),
    );
    return {
      marketId: market.market_id,
      outcomeId: resolvedOutcomeId,
      points: history.map(toMarketPoint),
    };
  },

  fetchNews: async (query: string): Promise<NewsResponse> => {
    const safeQuery = query || "prediction markets";
    return {
      query: safeQuery,
      items: buildMockNews(safeQuery),
    };
  },

  // WebSocket Interface
  socket: {
    subscribeToMarket: (id: string, handler: (data: MarketPoint) => void) =>
      marketSocketManager.subscribeToMarket(id, handler),
    unsubscribeFromMarket: (id: string) => marketSocketManager.unsubscribeFromMarket(id),
  },
};

export type {
  Market,
  MarketDataResponse,
  MarketPoint,
  NewsItem,
  NewsResponse,
  OrderBook,
  OrderBookLevel,
  Outcome,
  QuotePoint,
};
