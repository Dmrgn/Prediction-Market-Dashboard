import { useCallback, useEffect, useMemo, useState, useRef } from "react";
import { Line, LineChart, XAxis, YAxis, ResponsiveContainer, ReferenceLine } from "recharts";
import { Copy, Check, RefreshCw, Search, X, Loader2, ChevronRight } from "lucide-react";
import { backendInterface, type Market, type MarketPoint, type TimeRange, type OutcomeInfo, type Event, type EventSearchResult } from "@/backendInterface";
import { useWorkspaceStore, type PanelInstance } from "@/hooks/useWorkspaceStore";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { MarketSearchInput } from "@/components/shared/MarketSearchInput";

interface ChartPanelProps {
  panel: PanelInstance;
}

// Color palette for multivariate outcomes
const OUTCOME_COLORS = [
  "hsl(210, 100%, 60%)",   // Blue
  "hsl(45, 100%, 55%)",    // Yellow/Orange
  "hsl(0, 70%, 55%)",      // Red
  "hsl(150, 60%, 50%)",    // Green
  "hsl(280, 60%, 60%)",    // Purple
  "hsl(180, 60%, 50%)",    // Cyan
];

const TIME_RANGES: { label: string; value: TimeRange }[] = [
  { label: "1H", value: "1H" },
  { label: "6H", value: "6H" },
  { label: "1D", value: "1D" },
  { label: "1W", value: "1W" },
  { label: "1M", value: "1M" },
  { label: "ALL", value: "ALL" },
];

const REFRESH_INTERVALS: { label: string; ms: number }[] = [
  { label: "5s", ms: 5000 },
  { label: "10s", ms: 10000 },
  { label: "30s", ms: 30000 },
  { label: "1m", ms: 60000 },
  { label: "Off", ms: 0 },
];

type ChartDataPoint = {
  timestamp: string;
  displayTime: string;
  [outcomeId: string]: number | string;
};

export function ChartPanel({ panel }: ChartPanelProps) {
  const updatePanel = useWorkspaceStore(state => state.updatePanel);

  // Current market ID from panel data
  const currentMarketId = String(panel.data.marketId ?? "");

  // State
  const [market, setMarket] = useState<Market | null>(null);
  const [outcomes, setOutcomes] = useState<Record<string, OutcomeInfo>>({});
  const [history, setHistory] = useState<Record<string, MarketPoint[]>>({});
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState(false);
  const [timeRange, setTimeRange] = useState<TimeRange>("1D");
  const [refreshInterval, setRefreshInterval] = useState(10000);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [enabledOutcomes, setEnabledOutcomes] = useState<Set<string>>(new Set());

  // Search state
  const [showSearch, setShowSearch] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const searchContainerRef = useRef<HTMLDivElement>(null);

  const intervalRef = useRef<number | null>(null);

  // Copy handler
  const handleCopyMarketId = useCallback(() => {
    navigator.clipboard.writeText(currentMarketId).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }).catch(() => { });
  }, [currentMarketId]);

  // Search handler (delegated to MarketSearchInput)
  const handleSelectMarket = useCallback((selectedMarket: Market) => {
    updatePanel(panel.id, {
      marketId: selectedMarket.market_id,
      title: selectedMarket.title,
    });
    // Close search
    setShowSearch(false);
    setSearchQuery("");

    // Reset chart state
    setEnabledOutcomes(new Set());
  }, [panel.id, updatePanel]);

  // Fetch data function
  const fetchData = useCallback(async (showLoading = false) => {
    if (showLoading) setLoading(true);
    setIsRefreshing(true);
    setError(null);

    try {
      const data = await backendInterface.fetchAllOutcomesHistory(currentMarketId, timeRange);

      setMarket(data.market);
      setOutcomes(data.outcomes);
      setHistory(data.history);
      setLastUpdate(new Date());

      // Enable all outcomes by default on first load
      if (enabledOutcomes.size === 0) {
        setEnabledOutcomes(new Set(Object.keys(data.outcomes)));
      }

    } catch (err: any) {
      setError(err.message || "Failed to load chart");
    } finally {
      setLoading(false);
      setIsRefreshing(false);
    }
  }, [currentMarketId, timeRange, enabledOutcomes.size]);

  // Initial fetch and re-fetch on timeRange or market change
  useEffect(() => {
    setEnabledOutcomes(new Set()); // Reset outcomes when market changes
    fetchData(true);
  }, [currentMarketId, timeRange]);

  // Set up periodic refresh
  useEffect(() => {
    if (intervalRef.current) {
      window.clearInterval(intervalRef.current);
      intervalRef.current = null;
    }

    if (refreshInterval > 0) {
      intervalRef.current = window.setInterval(() => {
        fetchData(false);
      }, refreshInterval);
    }

    return () => {
      if (intervalRef.current) {
        window.clearInterval(intervalRef.current);
      }
    };
  }, [refreshInterval, fetchData]);

  // Manual refresh
  const handleManualRefresh = useCallback(() => {
    fetchData(false);
  }, [fetchData]);

  // Toggle outcome visibility
  const toggleOutcome = useCallback((outcomeId: string) => {
    setEnabledOutcomes(prev => {
      const next = new Set(prev);
      if (next.has(outcomeId)) {
        next.delete(outcomeId);
      } else {
        next.add(outcomeId);
      }
      return next;
    });
  }, []);

  // Build chart data from historical data
  const chartData = useMemo<ChartDataPoint[]>(() => {
    const timestampMap = new Map<number, ChartDataPoint>();

    for (const [outcomeId, points] of Object.entries(history)) {
      for (const point of points) {
        const ts = new Date(point.timestamp).getTime();

        if (!timestampMap.has(ts)) {
          const date = new Date(point.timestamp);
          let displayTime: string;

          if (timeRange === "1H" || timeRange === "6H" || timeRange === "1D") {
            displayTime = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
          } else {
            displayTime = date.toLocaleDateString([], { month: 'short', day: 'numeric' });
          }

          timestampMap.set(ts, { timestamp: point.timestamp, displayTime });
        }

        timestampMap.get(ts)![outcomeId] = point.price * 100;
      }
    }

    // If no history, create points from current outcome prices
    if (timestampMap.size === 0 && Object.keys(outcomes).length > 0) {
      const now = Date.now();
      const past = now - 3600000;

      const pastPoint: ChartDataPoint = {
        timestamp: new Date(past).toISOString(),
        displayTime: new Date(past).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      const nowPoint: ChartDataPoint = {
        timestamp: new Date(now).toISOString(),
        displayTime: "Now",
      };

      for (const [outcomeId, info] of Object.entries(outcomes)) {
        pastPoint[outcomeId] = info.price * 100;
        nowPoint[outcomeId] = info.price * 100;
      }

      timestampMap.set(past, pastPoint);
      timestampMap.set(now, nowPoint);
    }

    return Array.from(timestampMap.values()).sort((a, b) => {
      return new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime();
    });
  }, [history, outcomes, timeRange]);

  // Build chart config
  const chartConfig = useMemo<ChartConfig>(() => {
    const config: ChartConfig = {};
    const outcomeIds = Object.keys(outcomes);

    outcomeIds.forEach((outcomeId, index) => {
      config[outcomeId] = {
        label: outcomes[outcomeId]?.name ?? outcomeId,
        color: OUTCOME_COLORS[index % OUTCOME_COLORS.length],
      };
    });

    return config;
  }, [outcomes]);

  const sourceLabel = market?.source ? market.source.toUpperCase() : null;
  const hasHistoricalData = Object.values(history).some(h => h.length > 0);



  return (
    <div className="flex flex-col h-full min-h-0 bg-background overflow-hidden relative">
      {/* Header */}
      <div className="p-3 border-b shrink-0 z-20 bg-background/95 backdrop-blur-sm">
        {/* Title Row */}
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1 min-w-0 relative">
            <div className="flex flex-col">
              <button
                onClick={() => setShowSearch(true)}
                className="text-left w-full group flex items-center gap-2"
              >
                <h3 className="font-semibold text-lg leading-tight truncate group-hover:text-primary transition-colors">
                  {market?.title ?? "Market"}
                </h3>
                <Search className="h-3.5 w-3.5 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity shrink-0" />
              </button>
              {sourceLabel && (
                <span className="inline-flex items-center rounded-sm bg-muted px-1.5 py-0.5 text-[10px] font-medium text-foreground mt-1 w-fit">
                  {sourceLabel}
                </span>
              )}
              {/* Modal Search */}
              <MarketSearchInput
                isOpen={showSearch}
                onOpenChange={setShowSearch}
                onSelect={handleSelectMarket}
              />
            </div>
          </div>

          <div className="flex items-center gap-1 shrink-0">
            <Button
              variant="ghost"
              size="icon"
              className={`h-7 w-7 text-muted-foreground hover:text-foreground ${isRefreshing ? 'animate-spin' : ''}`}
              onClick={handleManualRefresh}
              disabled={isRefreshing}
              title="Refresh Now"
            >
              <RefreshCw className="h-3.5 w-3.5" />
            </Button>

            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7 text-muted-foreground"
              onClick={handleCopyMarketId}
              title="Copy Market ID"
            >
              {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
            </Button>
          </div>
        </div>
      </div>

      {/* Outcome Legend */}
      {Object.keys(outcomes).length > 0 && (
        <div className="px-3 py-2 border-b flex flex-wrap gap-x-4 gap-y-1 text-xs">
          {Object.entries(outcomes).map(([outcomeId, info], index) => {
            const color = OUTCOME_COLORS[index % OUTCOME_COLORS.length];
            const isEnabled = enabledOutcomes.has(outcomeId);
            const price = info.price * 100;

            return (
              <button
                key={outcomeId}
                onClick={() => toggleOutcome(outcomeId)}
                className={`flex items-center gap-1.5 hover:opacity-80 transition-opacity ${!isEnabled ? 'opacity-40' : ''}`}
              >
                <span
                  className="w-2.5 h-2.5 rounded-full"
                  style={{ backgroundColor: color }}
                />
                <span className="text-muted-foreground">{info.name}</span>
                <span className="font-medium" style={{ color }}>{price.toFixed(1)}%</span>
              </button>
            );
          })}
        </div>
      )}

      {/* Chart Area */}
      <div className="flex-1 min-h-0 relative w-full h-full py-4 px-2">
        {loading ? (
          <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
            <div className="flex flex-col items-center gap-2">
              <div className="h-4 w-4 animate-spin rounded-full border-2 border-primary border-t-transparent" />
              <span>Loading chart...</span>
            </div>
          </div>
        ) : error ? (
          <div className="flex items-center justify-center h-full text-sm text-destructive">{error}</div>
        ) : chartData.length === 0 ? (
          <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
            No data available
          </div>
        ) : (
          <ChartContainer config={chartConfig} className="absolute inset-0 w-full h-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData} margin={{ left: 0, right: 12, top: 10, bottom: 0 }}>
                <ReferenceLine y={25} stroke="var(--muted)" strokeDasharray="3 3" strokeOpacity={0.3} />
                <ReferenceLine y={50} stroke="var(--muted)" strokeDasharray="3 3" strokeOpacity={0.3} />
                <ReferenceLine y={75} stroke="var(--muted)" strokeDasharray="3 3" strokeOpacity={0.3} />

                <XAxis
                  dataKey="displayTime"
                  tickLine={false}
                  axisLine={false}
                  tickMargin={10}
                  interval="preserveStartEnd"
                  tick={{ fontSize: 10 }}
                  minTickGap={40}
                />
                <YAxis
                  domain={[0, 100]}
                  tickLine={false}
                  axisLine={false}
                  width={35}
                  tickFormatter={(value: number) => `${value}%`}
                  ticks={[0, 25, 50, 75, 100]}
                  tick={{ fontSize: 10 }}
                />
                <ChartTooltip
                  cursor={{ stroke: "var(--muted-foreground)", strokeWidth: 1, strokeDasharray: "4 4" }}
                  content={<ChartTooltipContent />}
                />

                {Object.keys(outcomes).map((outcomeId, index) => {
                  if (!enabledOutcomes.has(outcomeId)) return null;
                  const color = OUTCOME_COLORS[index % OUTCOME_COLORS.length];

                  return (
                    <Line
                      key={outcomeId}
                      dataKey={outcomeId}
                      type="monotone"
                      stroke={color}
                      strokeWidth={2}
                      dot={false}
                      isAnimationActive={false}
                      connectNulls
                    />
                  );
                })}
              </LineChart>
            </ResponsiveContainer>
          </ChartContainer>
        )}
      </div>

      {/* Footer Controls */}
      <div className="p-3 border-t bg-muted/10 flex items-center justify-between gap-4">
        {/* Left: Status */}
        <div className="flex items-center gap-3 text-xs text-muted-foreground min-w-0">
          {lastUpdate && (
            <span className="truncate">
              Updated: {lastUpdate.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
            </span>
          )}
          {hasHistoricalData && (
            <span className="text-emerald-500 shrink-0">● Historical</span>
          )}
        </div>

        {/* Center: Refresh Interval */}
        <div className="flex items-center gap-1 p-0.5 border rounded-lg bg-muted/20 shrink-0">
          {REFRESH_INTERVALS.map(({ label, ms }) => (
            <button
              key={label}
              onClick={() => setRefreshInterval(ms)}
              className={`
                text-[10px] font-medium px-2 py-1 rounded-md transition-all
                ${refreshInterval === ms ? "bg-background shadow-sm text-foreground" : "text-muted-foreground hover:text-foreground"}
              `}
            >
              {label}
            </button>
          ))}
        </div>

        {/* Right: Timeframe Selector */}
        <div className="flex items-center p-0.5 border rounded-lg bg-muted/20 shrink-0">
          {TIME_RANGES.map(({ label, value }) => (
            <button
              key={value}
              onClick={() => setTimeRange(value)}
              className={`
                text-[10px] font-medium px-2 py-1 rounded-md transition-all
                ${timeRange === value ? "bg-background shadow-sm text-foreground" : "text-muted-foreground hover:text-foreground"}
              `}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
