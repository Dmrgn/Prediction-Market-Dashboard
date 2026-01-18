import { useCallback, useEffect, useState, useMemo, useRef } from "react";
import { backendInterface, type OrderBook, type Market } from "@/backendInterface";
import type { PanelInstance } from "@/hooks/useWorkspaceStore";
import { Copy, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { formatCurrency, formatCompactNumber } from "@/lib/utils";

interface OrderBookPanelProps {
    panel: PanelInstance;
}

export function OrderBookPanel({ panel }: OrderBookPanelProps) {
    const marketId = String(panel.data.marketId ?? "");
    const [orderbook, setOrderbook] = useState<OrderBook | null>(null);
    const [market, setMarket] = useState<Market | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [copied, setCopied] = useState(false);

    // Track the outcome_id we're displaying to filter WebSocket messages
    const primaryOutcomeId = useRef<string | null>(null);

    const handleCopyMarketId = useCallback(() => {
        navigator.clipboard.writeText(marketId).then(() => {
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        }).catch(() => { });
    }, [marketId]);

    useEffect(() => {
        let unsubscribe: (() => void) | undefined;
        let isMounted = true;
        setError(null);
        primaryOutcomeId.current = null; // Reset on marketId change

        const init = async () => {
            try {
                const m = await backendInterface.fetchMarket(marketId);
                if (isMounted) setMarket(m);

                const outcomeId = m.outcomes?.[0]?.outcome_id;

                if (!outcomeId) {
                    if (isMounted) setError("No outcomes found");
                    return;
                }

                // Store the primary outcome_id we'll filter by
                primaryOutcomeId.current = outcomeId;

                if (!isMounted) return;

                // Initial fetch
                try {
                    const ob = await backendInterface.fetchOrderbook(marketId, outcomeId);
                    if (isMounted) setOrderbook(ob);
                } catch (e) {
                    // console.error(e);
                }

                // Subscribe - but FILTER by outcome_id in the handler
                unsubscribe = backendInterface.socket.subscribeToOrderBook(marketId, (data) => {
                    // Only update if the outcome_id matches the primary one we're displaying
                    if (isMounted && primaryOutcomeId.current && data.outcome_id === primaryOutcomeId.current) {
                        setOrderbook(data);
                    }
                });

            } catch (err: any) {
                if (isMounted) setError(err.message || "Failed to load market");
            }
        };

        init();

        return () => {
            isMounted = false;
            unsubscribe?.();
        };
    }, [marketId]);

    const processedData = useMemo(() => {
        if (!orderbook) return null;

        // Bids: DESC (Highest price first - Best Bid at top)
        const bidsForDisplay = [...orderbook.bids].sort((a, b) => b.p - a.p).slice(0, 15);

        // Asks: Sort ASC first to get lowest (best) asks, then reverse for display (High -> Low)
        const asksAsc = [...orderbook.asks].sort((a, b) => a.p - b.p).slice(0, 15);
        const asksForDisplay = asksAsc.reverse();

        // Spread
        const bestBid = bidsForDisplay[0]?.p;
        const bestAsk = asksForDisplay[asksForDisplay.length - 1]?.p;
        let spread: number | null = null;

        if (bestBid !== undefined && bestAsk !== undefined) {
            spread = bestAsk - bestBid;
        }

        // Max size for visual depth bars
        const maxSize = Math.max(
            ...asksForDisplay.map(a => a.s),
            ...bidsForDisplay.map(b => b.s),
            1
        );

        return { bids: bidsForDisplay, asks: asksForDisplay, spread, maxSize };
    }, [orderbook]);

    const sourceLabel = market?.source ? market.source.toUpperCase() : null;
    const outcomeName = market?.outcomes?.[0]?.name;

    return (
        <div className="flex flex-col h-full bg-background min-h-0 overflow-hidden font-sans text-xs select-none">
            {/* Header */}
            <div className="p-3 border-b shrink-0 flex items-start justify-between bg-muted/5">
                <div>
                    <h3 className="font-semibold text-sm">Order Book</h3>
                    <div className="flex items-center gap-2 mt-1">
                        {sourceLabel && (
                            <span className="inline-flex items-center rounded-sm bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground border">
                                {sourceLabel}
                            </span>
                        )}
                        {outcomeName && (
                            <span className="text-muted-foreground truncate max-w-[140px]" title={outcomeName}>
                                {outcomeName}
                            </span>
                        )}
                    </div>
                </div>
                <Button
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6 text-muted-foreground hover:text-foreground"
                    onClick={handleCopyMarketId}
                >
                    {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
                </Button>
            </div>

            {error && <div className="p-2 text-destructive">{error}</div>}

            <div className="flex-1 overflow-y-auto overflow-x-hidden min-h-0 scrollbar-thin scrollbar-thumb-muted scrollbar-track-transparent">
                {!processedData ? (
                    <div className="flex items-center justify-center p-8 text-muted-foreground h-full">
                        <div className="flex flex-col items-center gap-2">
                            <div className="h-4 w-4 animate-spin rounded-full border-2 border-primary border-t-transparent" />
                            <span>Loading...</span>
                        </div>
                    </div>
                ) : (
                    <div className="flex flex-col w-full pb-4">
                        {/* Headers */}
                        <div className="grid grid-cols-3 text-[10px] font-medium text-muted-foreground border-b sticky top-0 bg-background/95 backdrop-blur z-20 py-1.5 px-3">
                            <span className="text-left">Price</span>
                            <span className="text-right">Shares</span>
                            <span className="text-right">Total</span>
                        </div>

                        {/* ASKS (Sell Orders) - Red */}
                        {processedData.asks.map((level, i) => (
                            <div key={`ask-${i}`} className="grid grid-cols-3 px-3 py-1 relative group hover:bg-muted/30 text-xs items-center">
                                <div
                                    className="absolute right-0 top-0 bottom-0 bg-rose-500/10 pointer-events-none transition-all duration-300"
                                    style={{ width: `${(level.s / processedData.maxSize) * 100}%` }}
                                />
                                <span className="relative z-10 font-mono text-rose-500 font-medium">{level.p.toFixed(2)}¢</span>
                                <span className="relative z-10 font-mono text-muted-foreground text-right">{formatCompactNumber(level.s)}</span>
                                <span className="relative z-10 font-mono text-muted-foreground text-right">${formatCompactNumber(level.p * level.s)}</span>
                            </div>
                        ))}

                        {/* SPREAD INDICATOR */}
                        <div className="flex items-center justify-between px-3 py-2 bg-muted/10 border-y my-1">
                            <div className="flex items-center gap-2">
                                <span className="text-[10px] uppercase font-bold text-rose-500 bg-rose-500/10 px-1.5 rounded">Asks</span>
                            </div>

                            <div className="text-xs text-muted-foreground font-mono">
                                Spread: <span className="text-foreground font-medium">{processedData.spread !== null ? `${(processedData.spread * 100).toFixed(0)}¢` : "-"}</span>
                            </div>

                            <div className="flex items-center gap-2">
                                <span className="text-[10px] uppercase font-bold text-emerald-500 bg-emerald-500/10 px-1.5 rounded">Bids</span>
                            </div>
                        </div>

                        {/* BIDS (Buy Orders) - Green */}
                        {processedData.bids.map((level, i) => (
                            <div key={`bid-${i}`} className="grid grid-cols-3 px-3 py-1 relative group hover:bg-muted/30 text-xs items-center">
                                <div
                                    className="absolute right-0 top-0 bottom-0 bg-emerald-500/10 pointer-events-none transition-all duration-300"
                                    style={{ width: `${(level.s / processedData.maxSize) * 100}%` }}
                                />
                                <span className="relative z-10 font-mono text-emerald-500 font-medium">{level.p.toFixed(2)}¢</span>
                                <span className="relative z-10 font-mono text-muted-foreground text-right">{formatCompactNumber(level.s)}</span>
                                <span className="relative z-10 font-mono text-muted-foreground text-right">${formatCompactNumber(level.p * level.s)}</span>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}
