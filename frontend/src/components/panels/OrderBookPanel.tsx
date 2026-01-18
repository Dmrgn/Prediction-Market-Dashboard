import { useCallback, useEffect, useState, useMemo, useRef } from "react";
import { backendInterface, type OrderBook, type Market, type Outcome } from "@/backendInterface";
import type { PanelInstance } from "@/hooks/useWorkspaceStore";
import { Copy, Check, ChevronDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { formatCompactNumber } from "@/lib/utils";
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

interface OrderBookPanelProps {
    panel: PanelInstance;
}

export function OrderBookPanel({ panel }: OrderBookPanelProps) {
    const marketId = String(panel.data.marketId ?? "");
    const [orderbook, setOrderbook] = useState<OrderBook | null>(null);
    const [market, setMarket] = useState<Market | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [copied, setCopied] = useState(false);
    const [selectedOutcome, setSelectedOutcome] = useState<Outcome | null>(null);

    // Track the outcome_id we're displaying to filter WebSocket messages
    const selectedOutcomeRef = useRef<string | null>(null);

    const handleCopyMarketId = useCallback(() => {
        navigator.clipboard.writeText(marketId).then(() => {
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        }).catch(() => { });
    }, [marketId]);

    // Fetch market data
    useEffect(() => {
        let isMounted = true;
        setError(null);

        const fetchMarket = async () => {
            try {
                const m = await backendInterface.fetchMarket(marketId);
                if (isMounted) {
                    setMarket(m);
                    // Auto-select first outcome
                    if (m.outcomes?.length > 0) {
                        setSelectedOutcome(m.outcomes[0]);
                    }
                }
            } catch (err: any) {
                if (isMounted) setError(err.message || "Failed to load market");
            }
        };

        fetchMarket();

        return () => { isMounted = false; };
    }, [marketId]);

    // Fetch orderbook and subscribe when outcome changes
    useEffect(() => {
        if (!selectedOutcome) return;

        let unsubscribe: (() => void) | undefined;
        let isMounted = true;

        selectedOutcomeRef.current = selectedOutcome.outcome_id;

        const init = async () => {
            // Initial fetch
            try {
                const ob = await backendInterface.fetchOrderbook(marketId, selectedOutcome.outcome_id);
                if (isMounted) setOrderbook(ob);
            } catch (e) {
                // Orderbook might not exist
            }

            // Subscribe to updates
            unsubscribe = backendInterface.socket.subscribeToOrderBook(marketId, (data) => {
                if (isMounted && data.outcome_id === selectedOutcomeRef.current) {
                    setOrderbook(data);
                }
            });
        };

        init();

        return () => {
            isMounted = false;
            unsubscribe?.();
        };
    }, [marketId, selectedOutcome]);

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
    const hasMultipleOutcomes = (market?.outcomes?.length ?? 0) > 1;

    return (
        <div className="flex flex-col h-full bg-background min-h-0 overflow-hidden font-sans text-xs select-none">
            {/* Header */}
            <div className="p-3 border-b shrink-0 bg-muted/5">
                {/* Market Title */}
                <div className="flex items-start justify-between gap-2">
                    <div className="flex-1 min-w-0">
                        <h3 className="font-semibold text-sm leading-tight truncate" title={market?.title}>
                            {market?.title ?? "Order Book"}
                        </h3>
                        <div className="flex items-center gap-2 mt-1">
                            {sourceLabel && (
                                <span className="inline-flex items-center rounded-sm bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground border shrink-0">
                                    {sourceLabel}
                                </span>
                            )}
                        </div>
                    </div>
                    <Button
                        variant="ghost"
                        size="icon"
                        className="h-6 w-6 text-muted-foreground hover:text-foreground shrink-0"
                        onClick={handleCopyMarketId}
                    >
                        {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
                    </Button>
                </div>

                {/* Outcome Selector */}
                {market?.outcomes && market.outcomes.length > 0 && (
                    <div className="mt-2">
                        <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                                <Button
                                    variant="outline"
                                    size="sm"
                                    className="w-full justify-between h-8 text-xs"
                                >
                                    <div className="flex items-center gap-2 truncate">
                                        <span className="w-2 h-2 rounded-full bg-primary shrink-0" />
                                        <span className="truncate">
                                            {selectedOutcome?.name ?? "Select Outcome"}
                                        </span>
                                        {selectedOutcome && (
                                            <span className="text-muted-foreground shrink-0">
                                                {(selectedOutcome.price * 100).toFixed(1)}%
                                            </span>
                                        )}
                                    </div>
                                    <ChevronDown className="h-3 w-3 opacity-50 shrink-0" />
                                </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent className="w-[var(--radix-dropdown-menu-trigger-width)]" align="start">
                                {market.outcomes.map((outcome) => (
                                    <DropdownMenuItem
                                        key={outcome.outcome_id}
                                        onClick={() => setSelectedOutcome(outcome)}
                                        className="flex items-center justify-between"
                                    >
                                        <span className="truncate">{outcome.name}</span>
                                        <span className="text-muted-foreground text-xs shrink-0 ml-2">
                                            {(outcome.price * 100).toFixed(1)}%
                                        </span>
                                    </DropdownMenuItem>
                                ))}
                            </DropdownMenuContent>
                        </DropdownMenu>
                    </div>
                )}
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
                ) : processedData.asks.length === 0 && processedData.bids.length === 0 ? (
                    <div className="flex items-center justify-center p-8 text-muted-foreground h-full">
                        <div className="flex flex-col items-center gap-2 text-center">
                            <span>No orderbook data</span>
                            <span className="text-[10px]">This market may not have active orders</span>
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
