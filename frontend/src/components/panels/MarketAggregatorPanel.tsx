import { useCallback, useEffect, useMemo, useState } from "react";
import { Area, AreaChart, CartesianGrid, XAxis } from "recharts";
import { Copy, Check } from "lucide-react";
import { backendInterface, type Market, type MarketPoint } from "@/backendInterface";
import { formatCompactNumber, formatCurrency, formatTimestamp } from "@/lib/utils";
import type { PanelInstance } from "@/hooks/useWorkspaceStore";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";

interface MarketAggregatorPanelProps {
  panel: PanelInstance;
}

type ChartMode = "mid" | "bid-ask-mid";

type ChartPoint = {
  timestamp: string;
  mid: number | null;
  bid: number | null;
  ask: number | null;
};

const chartConfig: ChartConfig = {
  mid: {
    label: "Mid",
    color: "var(--chart-1)",
  },
  bid: {
    label: "Bid",
    color: "var(--chart-2)",
  },
  ask: {
    label: "Ask",
    color: "var(--chart-3)",
  },
};

export function MarketAggregatorPanel({ panel }: MarketAggregatorPanelProps) {
  const marketId = String(panel.data.marketId ?? "");
  const [points, setPoints] = useState<MarketPoint[]>([]);
  const [market, setMarket] = useState<Market | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [chartMode, setChartMode] = useState<ChartMode>("mid");
  const [copied, setCopied] = useState(false);

  const handleCopyMarketId = useCallback(() => {
    navigator.clipboard.writeText(marketId).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }).catch(() => {
      // Silently fail if clipboard isn't available
    });
  }, [marketId]);

  useEffect(() => {
    let unsubscribe: (() => void) | undefined;
    let isMounted = true;

    setError(null);

    backendInterface
      .fetchMarket(marketId)
      .then((data) => {
        if (!isMounted) return;
        setMarket(data);
      })
      .catch((err) => {
        if (!isMounted) return;
        setError(err.message ?? "Unable to load market details");
      });

    backendInterface
      .fetchMarketData(marketId)
      .then((data) => {
        if (!isMounted) return;
        setPoints(data.points ?? []);
      })
      .catch((err) => {
        if (!isMounted) return;
        setError(err.message ?? "Unable to load market data");
      });

    unsubscribe = backendInterface.socket.subscribeToMarket(marketId, (point) => {
      setPoints((prev) => [...prev.slice(-89), point]);
    });

    return () => {
      isMounted = false;
      unsubscribe?.();
    };
  }, [marketId]);

  const latestPoint = points.length ? points[points.length - 1] : null;
  const delta = useMemo(() => {
    if (points.length < 2) return null;
    const last = points[points.length - 1];
    const prev = points[points.length - 2];
    if (!last || !prev) return null;
    return last.price - prev.price;
  }, [points]);

  const chartData = useMemo<ChartPoint[]>(() => {
    return points.map((point) => ({
      timestamp: point.timestamp,
      mid: point.price ?? null,
      bid: point.bid ?? null,
      ask: point.ask ?? null,
    }));
  }, [points]);

  const outcomeLabel = market?.outcomes?.[0]?.name ?? "Primary outcome";
  const sourceLabel = market?.source ? market.source.toUpperCase() : "Market";

  const tickFormatter = useCallback((value: string) => {
    const formatted = formatTimestamp(value);
    return formatted?.split(",")[0] ?? "";
  }, []);

  const tooltipLabelFormatter = useCallback((label: unknown) => {
    return formatTimestamp(String(label));
  }, []);

  const tooltipContent = useMemo(
    () => <ChartTooltipContent labelFormatter={tooltipLabelFormatter} />,
    [tooltipLabelFormatter]
  );

  return (
    <div className="min-h-0 flex-1 h-full overflow-y-auto">
      <Card className="h-full">
        <CardHeader className="space-y-3">
          <div className="flex items-start justify-between gap-4">
            <div>
              <CardTitle className="text-lg">{market?.title ?? "Market"}</CardTitle>
              <CardDescription>
                {sourceLabel} • {outcomeLabel}
              </CardDescription>
            </div>
            <div className="w-[170px]">
              <Select value={chartMode} onValueChange={(value) => setChartMode(value as ChartMode)}>
                <SelectTrigger>
                  <SelectValue placeholder="Chart style" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="mid">Mid only</SelectItem>
                  <SelectItem value="bid-ask-mid">Bid + Ask + Mid</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground">Market ID:</span>
            <Button
              variant="ghost"
              size="sm"
              className="h-6 px-2 text-xs text-muted-foreground hover:text-foreground"
              onClick={handleCopyMarketId}
            >
              {copied ? (
                <>
                  <Check className="mr-1 h-3 w-3" />
                  Copied!
                </>
              ) : (
                <>
                  <Copy className="mr-1 h-3 w-3" />
                  {marketId.slice(0, 12)}...
                </>
              )}
            </Button>
          </div>
          {error && <div className="text-sm text-destructive">{error}</div>}
        </CardHeader>
        <CardContent className="space-y-6">
          {!error && points.length === 0 && (
            <div className="text-sm text-muted-foreground">Loading market data…</div>
          )}
          {points.length > 0 && (
            <ChartContainer config={chartConfig}>
              <AreaChart
                width={600}
                height={260}
                data={chartData}
                margin={{
                  left: 12,
                  right: 12,
                }}
              >
                <CartesianGrid vertical={false} />
                <XAxis
                  dataKey="timestamp"
                  tickLine={false}
                  axisLine={false}
                  tickMargin={8}
                  tickFormatter={tickFormatter}
                />
                <ChartTooltip cursor={false} content={tooltipContent} />
                <defs>
                  <linearGradient id="fillMid" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="var(--color-mid)" stopOpacity={0.8} />
                    <stop offset="95%" stopColor="var(--color-mid)" stopOpacity={0.1} />
                  </linearGradient>
                  <linearGradient id="fillBid" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="var(--color-bid)" stopOpacity={0.65} />
                    <stop offset="95%" stopColor="var(--color-bid)" stopOpacity={0.08} />
                  </linearGradient>
                  <linearGradient id="fillAsk" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="var(--color-ask)" stopOpacity={0.65} />
                    <stop offset="95%" stopColor="var(--color-ask)" stopOpacity={0.08} />
                  </linearGradient>
                </defs>
                {(chartMode === "bid-ask-mid" || chartMode === "mid") && (
                  <Area
                    dataKey="mid"
                    type="natural"
                    fill="url(#fillMid)"
                    fillOpacity={0.35}
                    stroke="var(--color-mid)"
                    strokeWidth={2}
                    dot={false}
                  />
                )}
                {chartMode === "bid-ask-mid" && (
                  <>
                    <Area
                      dataKey="bid"
                      type="natural"
                      fill="url(#fillBid)"
                      fillOpacity={0.25}
                      stroke="var(--color-bid)"
                      strokeWidth={2}
                      dot={false}
                    />
                    <Area
                      dataKey="ask"
                      type="natural"
                      fill="url(#fillAsk)"
                      fillOpacity={0.25}
                      stroke="var(--color-ask)"
                      strokeWidth={2}
                      dot={false}
                    />
                  </>
                )}
              </AreaChart>
            </ChartContainer>
          )}
        </CardContent>
        <CardFooter className="grid w-full gap-3 text-sm">
          <div className="grid gap-2">
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Latest Price</span>
              <span className="font-medium">{latestPoint ? formatCurrency(latestPoint.price) : "—"}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Price Change</span>
              <span className={delta !== null && delta >= 0 ? "text-emerald-500" : "text-rose-500"}>
                {delta !== null ? formatCurrency(delta) : "—"}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Volume</span>
              <span className="font-medium">{latestPoint ? formatCompactNumber(latestPoint.volume) : "—"}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Last Update</span>
              <span className="font-medium">
                {latestPoint ? formatTimestamp(latestPoint.timestamp) : "—"}
              </span>
            </div>
          </div>
        </CardFooter>
      </Card>
    </div>
  );
}
