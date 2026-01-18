/**
 * Layer 1: Backend Interface
 * The source of truth for all external data.
 * Abstracts both REST and Real-time communication.
 */

import type { Article } from "@/lib/types/news";

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

type MarketSearchResponse = {
  markets: Market[],
  facets: {
    sectors: Record<string, number>,
    sources: { polymarket: 0, kalshi: 0 },
    tags: Record<string, number>
  },
  total: number
}

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
  bid?: number | null;
  ask?: number | null;
  volume: number;
};

type MarketDataResponse = {
  marketId: string;
  outcomeId: string | null;
  points: MarketPoint[];
};

type TimeRange = "1H" | "6H" | "1D" | "5D" | "1W" | "1M" | "ALL";

type OutcomeInfo = {
  name: string;
  price: number;
};

type MultiOutcomeHistoryResponse = {
  market_id: string;
  outcomes: Record<string, OutcomeInfo>;
  history: Record<string, QuotePoint[]>;
};

type NewsSearchParams = {
  query: string;
  providers?: string[];
  limit?: number;
  signal?: AbortSignal;
};

type NewsStreamPayload = {
  provider?: string;
  articles: Article[];
};

const randomBetween = (min: number, max: number) => min + Math.random() * (max - min);

const toMarketPoint = (point: QuotePoint): MarketPoint => ({
  timestamp: new Date(point.ts * 1000).toISOString(),
  price: point.mid,
  bid: point.bid ?? null,
  ask: point.ask ?? null,
  volume: point.volume ?? 0,
});

class MarketSocketManager {
  private subscriptions = new Map<string, Set<(data: MarketPoint) => void>>();
  private orderBooksubscriptions = new Map<string, Set<(data: OrderBook) => void>>();
  private socket: WebSocket | null = null;
  private reconnectTimer: number | null = null;
  private connecting = false;
  private pendingSubscriptions = new Set<string>();

  private get hasSubscribers() {
    return (
      Array.from(this.subscriptions.values()).some((handlers) => handlers.size > 0) ||
      Array.from(this.orderBooksubscriptions.values()).some((handlers) => handlers.size > 0)
    );
  }

  private sendMessage(message: object) {
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify(message));
    }
  }

  private ensureSocket() {
    if (this.socket || this.connecting) return;
    this.connecting = true;
    this.socket = new WebSocket(WS_BASE_URL);

    this.socket.addEventListener("open", () => {
      this.connecting = false;

      // Send all pending subscriptions
      const allMarkets = new Set([
        ...this.subscriptions.keys(),
        ...this.orderBooksubscriptions.keys(),
        ...this.pendingSubscriptions
      ]);

      allMarkets.forEach((marketId) => {
        this.sendMessage({ op: "subscribe_market", market_id: marketId });
      });

      this.pendingSubscriptions.clear();
    });

    this.socket.addEventListener("message", (event) => {
      try {
        const payload = JSON.parse(event.data) as QuoteMessage | OrderBookMessage;

        if (payload.type === "quote") {
          const handlers = this.subscriptions.get(payload.market_id);
          if (handlers && handlers.size > 0) {
            const point: MarketPoint = {
              timestamp: new Date(payload.ts * 1000).toISOString(),
              price: payload.mid,
              bid: payload.bid,
              ask: payload.ask,
              volume: 0,
            };
            handlers.forEach((handler) => handler(point));
          }
        } else if (payload.type === "orderbook") {
          const handlers = this.orderBooksubscriptions.get(payload.market_id);
          if (handlers && handlers.size > 0) {
            const orderbook: OrderBook = {
              market_id: payload.market_id,
              outcome_id: payload.outcome_id,
              ts: payload.ts,
              bids: payload.bids,
              asks: payload.asks
            };
            handlers.forEach((handler) => handler(orderbook));
          }
        }
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

    // If socket is open, send immediately. Otherwise, queue for when it opens.
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.sendMessage({ op: "subscribe_market", market_id: marketId });
    } else {
      this.pendingSubscriptions.add(marketId);
    }

    return () => {
      const current = this.subscriptions.get(marketId);
      if (!current) return;
      current.delete(handler);
      if (current.size === 0) {
        this.subscriptions.delete(marketId);
        // Only unsubscribe if no orderbook subscribers either
        if (!this.orderBooksubscriptions.has(marketId)) {
          this.sendMessage({ op: "unsubscribe_market", market_id: marketId });
        }
      }
      this.closeSocketIfIdle();
    };
  }

  subscribeToOrderBook(marketId: string, handler: (data: OrderBook) => void) {
    if (!marketId) return () => undefined;
    const handlers = this.orderBooksubscriptions.get(marketId) ?? new Set();
    handlers.add(handler);
    this.orderBooksubscriptions.set(marketId, handlers);

    this.ensureSocket();

    // If socket is open, send immediately. Otherwise, queue for when it opens.
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.sendMessage({ op: "subscribe_market", market_id: marketId });
    } else {
      this.pendingSubscriptions.add(marketId);
    }

    return () => {
      const current = this.orderBooksubscriptions.get(marketId);
      if (!current) return;
      current.delete(handler);
      if (current.size === 0) {
        this.orderBooksubscriptions.delete(marketId);
        // Only unsubscribe if no market (quote) subscribers either
        if (!this.subscriptions.has(marketId)) {
          this.sendMessage({ op: "unsubscribe_market", market_id: marketId });
        }
      }
      this.closeSocketIfIdle();
    };
  }

  unsubscribeFromMarket(marketId: string) {
    // Deprecated, relying on return callbacks
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
  fetchMarkets: async (query?: string, source?: "polymarket" | "kalshi"): Promise<MarketSearchResponse> =>
    fetchJson<MarketSearchResponse>(buildUrl("/markets/search", { q: query, source })),

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
    const history = await fetchJson<QuotePoint[]>(
      buildUrl(`/markets/${market.market_id}/history`, { outcome_id: resolvedOutcomeId }),
    );
    return {
      marketId: market.market_id,
      outcomeId: resolvedOutcomeId,
      points: history.map(toMarketPoint),
    };
  },

  fetchMarketDataWithRange: async (id: string, range: TimeRange, outcomeId?: string): Promise<MarketDataResponse> => {
    if (!id) throw new Error("Market ID is required");
    const market = await backendInterface.fetchMarket(id);
    const resolvedOutcomeId = outcomeId ?? market.outcomes?.[0]?.outcome_id ?? null;
    if (!resolvedOutcomeId) {
      return { marketId: market.market_id, outcomeId: null, points: [] };
    }
    const history = await fetchJson<QuotePoint[]>(
      buildUrl(`/markets/${market.market_id}/history`, { outcome_id: resolvedOutcomeId, range }),
    );
    return {
      marketId: market.market_id,
      outcomeId: resolvedOutcomeId,
      points: history.map(toMarketPoint),
    };
  },

  fetchAllOutcomesHistory: async (id: string, range?: TimeRange): Promise<{
    market: Market;
    outcomes: Record<string, OutcomeInfo>;
    history: Record<string, MarketPoint[]>;
  }> => {
    if (!id) throw new Error("Market ID is required");
    const market = await backendInterface.fetchMarket(id);

    const data = await fetchJson<MultiOutcomeHistoryResponse>(
      buildUrl(`/markets/${id}/history/all`, { range }),
    );

    // Convert QuotePoints to MarketPoints for each outcome
    const history: Record<string, MarketPoint[]> = {};
    for (const [outcomeId, points] of Object.entries(data.history)) {
      history[outcomeId] = points.map(toMarketPoint);
    }

    return { market, outcomes: data.outcomes, history };
  },

  fetchNews: async (params: NewsSearchParams): Promise<Article[]> => {
    const safeQuery = params.query?.trim();
    if (!safeQuery) return [];

    const searchParams = new URLSearchParams();
    searchParams.append("q", safeQuery);

    if (params.providers) {
      params.providers.forEach((provider) => {
        searchParams.append("providers", provider);
      });
    }

    if (params.limit !== undefined) {
      searchParams.append("limit", String(params.limit));
    }

    const url = `${API_BASE_URL.replace(/\/$/, "")}/news/search?${searchParams.toString()}`;
    return fetchJson<Article[]>(url, { signal: params.signal });
  },

  streamNews: (
    params: Omit<NewsSearchParams, "signal"> & {
      onUpdate: (payload: NewsStreamPayload) => void;
      onDone?: (payload: NewsStreamPayload) => void;
      onError?: (error: Error) => void;
    }
  ): (() => void) => {
    const safeQuery = params.query?.trim();
    if (!safeQuery) {
      return () => undefined;
    }

    const searchParams = new URLSearchParams();
    searchParams.append("q", safeQuery);
    searchParams.append("stream", "true");

    if (params.providers) {
      params.providers.forEach((provider) => {
        searchParams.append("providers", provider);
      });
    }

    if (params.limit !== undefined) {
      searchParams.append("limit", String(params.limit));
    }

    const url = `${API_BASE_URL.replace(/\/$/, "")}/news/search?${searchParams.toString()}`;
    const source = new EventSource(url);

    const handleUpdate = (event: MessageEvent<string>) => {
      try {
        const payload = JSON.parse(event.data) as NewsStreamPayload;
        params.onUpdate(payload);
      } catch (error) {
        params.onError?.(error as Error);
      }
    };

    const handleDone = (event: MessageEvent<string>) => {
      try {
        const payload = JSON.parse(event.data) as NewsStreamPayload;
        params.onDone?.(payload);
      } catch (error) {
        params.onError?.(error as Error);
      } finally {
        source.close();
      }
    };

    source.addEventListener("update", handleUpdate);
    source.addEventListener("done", handleDone);
    source.onerror = () => {
      params.onError?.(new Error("News stream error"));
      source.close();
    };

    return () => {
      source.removeEventListener("update", handleUpdate);
      source.removeEventListener("done", handleDone);
      source.close();
    };
  },

  // WebSocket Interface
  socket: {
    subscribeToMarket: (id: string, handler: (data: MarketPoint) => void) =>
      marketSocketManager.subscribeToMarket(id, handler),
    subscribeToOrderBook: (id: string, handler: (data: OrderBook) => void) =>
      marketSocketManager.subscribeToOrderBook(id, handler),
    unsubscribeFromMarket: (id: string) => marketSocketManager.unsubscribeFromMarket(id),
  },
};

export type {
  Market,
  MarketDataResponse,
  MarketPoint,
  NewsSearchParams,
  NewsStreamPayload,
  OrderBook,
  OrderBookLevel,
  Outcome,
  OutcomeInfo,
  QuotePoint,
  TimeRange,
};
