import { useState, useEffect, useRef, useMemo } from "react";
import { Search, Loader2, ChevronRight, Check } from "lucide-react";
import { backendInterface, type Market, type Event, type EventSearchResult } from "@/backendInterface";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

interface MarketSearchInputProps {
    isOpen: boolean;
    onOpenChange: (open: boolean) => void;
    onSelect: (market: Market) => void;
    placeholder?: string;
    className?: string; // Additional classes for the trigger input
    autoClose?: boolean; // Whether to automatically close on selection (default: true)
    suggestedMarkets?: Array<{
        value: string;
        label: string;
        description?: string;
    }>; // AI-suggested markets to show at the top
}

type FlatOption =
    | { type: 'event'; data: Event; id: string }
    | { type: 'market'; data: Market; id: string; parentEvent?: Event };

export function MarketSearchInput({ isOpen, onOpenChange, onSelect, placeholder = "Search markets...", className, autoClose = true, suggestedMarkets }: MarketSearchInputProps) {
    const [query, setQuery] = useState("");
    const [results, setResults] = useState<EventSearchResult | null>(null);
    const [loading, setLoading] = useState(false);

    // Interaction state
    const [expandedEventIds, setExpandedEventIds] = useState<Set<string>>(new Set());
    const [selectedIndex, setSelectedIndex] = useState(0);

    const inputRef = useRef<HTMLInputElement>(null);
    const listRef = useRef<HTMLDivElement>(null);

    // Focus input when opened
    useEffect(() => {
        if (isOpen) {
            requestAnimationFrame(() => {
                inputRef.current?.focus();
            });
            // Reset state
            setQuery("");
            setResults(null);
            setExpandedEventIds(new Set());
            setSelectedIndex(0);
        }
    }, [isOpen]);

    // Debounced search - call BOTH endpoints for comprehensive results
    useEffect(() => {
        if (!isOpen) return;

        if (!query || query.length < 2) {
            setResults(null);
            return;
        }

        const timer = setTimeout(async () => {
            setLoading(true);
            try {
                console.log('[MarketSearchInput] Searching for:', query);

                // Call both endpoints in parallel for comprehensive results
                const [eventsData, marketsData] = await Promise.all([
                    backendInterface.searchEvents(query),
                    backendInterface.searchMarkets(query)
                ]);

                console.log('[MarketSearchInput] Events:', eventsData.events.length, 'Markets:', marketsData.total);

                // Merge results: events from searchEvents + standalone markets from searchMarkets
                // Filter out markets that are already in events to avoid duplicates
                const eventMarketIds = new Set(
                    eventsData.events.flatMap(e => e.markets.map(m => m.market_id))
                );

                const standaloneMarkets = marketsData.markets.filter(
                    m => !eventMarketIds.has(m.market_id)
                );

                const mergedResults: EventSearchResult = {
                    events: eventsData.events,
                    markets: [...eventsData.markets, ...standaloneMarkets],
                    total: eventsData.events.length + eventsData.markets.length + standaloneMarkets.length
                };

                setResults(mergedResults);
                // Reset expanded states on new search
                setExpandedEventIds(new Set());
            } catch (e) {
                console.error("Search failed:", e);
            } finally {
                setLoading(false);
            }
        }, 300);

        return () => clearTimeout(timer);
    }, [query, isOpen]);

    // Build flat list for rendering and navigation
    const flatList = useMemo<FlatOption[]>(() => {
        if (!results) return [];
        const list: FlatOption[] = [];

        // Events
        results.events.forEach(event => {
            list.push({ type: 'event', data: event, id: `event-${event.event_id}` });
            if (expandedEventIds.has(event.event_id)) {
                event.markets.forEach(market => {
                    list.push({ type: 'market', data: market, id: market.market_id, parentEvent: event });
                });
            }
        });

        // Standalone Markets
        results.markets.forEach(market => {
            list.push({ type: 'market', data: market, id: market.market_id });
        });

        return list;
    }, [results, expandedEventIds]);

    // Keyboard navigation
    useEffect(() => {
        setSelectedIndex(0);
    }, [flatList.length]);

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (!isOpen) return;

        if (e.key === "ArrowDown") {
            e.preventDefault();
            setSelectedIndex(prev => Math.min(prev + 1, flatList.length - 1));
            // Scroll into view logic could be added here
        } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setSelectedIndex(prev => Math.max(prev - 1, 0));
        } else if (e.key === "Enter") {
            e.preventDefault();
            const selected = flatList[selectedIndex];
            if (!selected) return;

            if (selected.type === 'event') {
                toggleEvent(selected.data);
            } else {
                handleSelect(selected.data);
            }
        } else if (e.key === "Escape") {
            e.preventDefault();
            onOpenChange(false);
        }
    };

    const toggleEvent = (event: Event) => {
        // If the event has only one market, select it directly
        if (event.markets.length === 1 && event.markets[0]) {
            handleSelect(event.markets[0]);
            return;
        }
        // Otherwise, toggle expand/collapse
        setExpandedEventIds(prev => {
            const next = new Set(prev);
            if (next.has(event.event_id)) next.delete(event.event_id);
            else next.add(event.event_id);
            return next;
        });
    };

    const handleSelect = (market: Market) => {
        onSelect(market);
        if (autoClose) {
            onOpenChange(false);
        }
    };

    if (!isOpen) return null;

    return (
        <div
            className="fixed inset-0 z-[60] flex items-start justify-center p-6"
            onKeyDown={handleKeyDown}
        >
            <div className="absolute inset-0 bg-black/40" onPointerDown={() => onOpenChange(false)} />
            <div className="relative z-10 w-full max-w-2xl rounded-xl border border-border bg-card shadow-xl overflow-hidden flex flex-col max-h-[80vh]">
                <div className="border-b border-border p-4 shrink-0">
                    <div className="relative">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                        <Input
                            ref={inputRef}
                            autoFocus
                            value={query}
                            onChange={(e) => setQuery(e.target.value)}
                            placeholder={placeholder}
                            className="pl-9 pr-9"
                        />
                        {loading && (
                            <Loader2 className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 animate-spin text-muted-foreground" />
                        )}
                    </div>
                </div>

                <div className="flex-1 overflow-y-auto p-2" ref={listRef}>
                    {!query && !suggestedMarkets?.length && (
                        <div className="p-4 text-sm text-muted-foreground text-center">
                            Type to search markets...
                        </div>
                    )}

                    {!query && suggestedMarkets && suggestedMarkets.length > 0 && (
                        <div className="space-y-1">
                            <div className="px-3 py-2 text-xs font-medium text-muted-foreground">
                                ✨ Suggested
                            </div>
                            {suggestedMarkets.map((suggestion) => (
                                <button
                                    key={suggestion.value}
                                    onClick={() => {
                                        // Construct a minimal Market object from suggestion data
                                        // Extract source from description (e.g., "POLYMARKET • event title")
                                        const sourceMatch = suggestion.description?.match(/^(POLYMARKET|KALSHI)/i);
                                        const source = sourceMatch && sourceMatch[1]
                                            ? (sourceMatch[1].toLowerCase() as "polymarket" | "kalshi")
                                            : "polymarket"; // default fallback

                                        const market: Market = {
                                            market_id: suggestion.value,
                                            title: suggestion.label,
                                            description: suggestion.description || null,
                                            category: null,
                                            ticker: null,
                                            source,
                                            source_id: suggestion.value, // Use market_id as placeholder
                                            outcomes: [], // Empty for now - will be fetched if needed
                                            status: "active",
                                            image_url: null,
                                            volume_24h: 0,
                                            liquidity: 0,
                                        };
                                        handleSelect(market);
                                    }}
                                    className="w-full px-3 py-2 text-left flex items-center gap-3 rounded-lg transition-colors group hover:bg-muted/50"
                                >
                                    <div className="flex-1 min-w-0">
                                        <div className="text-sm text-foreground truncate font-medium">{suggestion.label}</div>
                                        {suggestion.description && (
                                            <div className="text-xs text-muted-foreground">{suggestion.description}</div>
                                        )}
                                    </div>
                                </button>
                            ))}
                            <div className="border-t border-border my-2"></div>
                            <div className="px-3 py-2 text-xs text-muted-foreground">
                                Or type to search for more markets...
                            </div>
                        </div>
                    )}

                    {query && loading && (
                        <div className="p-4 text-sm text-muted-foreground text-center flex items-center justify-center gap-2">
                            <Loader2 className="h-4 w-4 animate-spin" />
                            Searching...
                        </div>
                    )}

                    {query && !loading && flatList.length === 0 && (
                        <div className="p-4 text-sm text-muted-foreground text-center">
                            No markets found
                        </div>
                    )}

                    <div className="space-y-1">
                        {flatList.map((item, index) => {
                            const isSelected = index === selectedIndex;
                            if (item.type === 'event') {
                                const event = item.data;
                                const isExpanded = expandedEventIds.has(event.event_id);
                                return (
                                    <button
                                        key={item.id}
                                        onClick={() => toggleEvent(event)}
                                        className={cn(
                                            "w-full px-3 py-2.5 text-left flex items-start gap-3 rounded-lg transition-colors",
                                            isSelected ? "bg-muted" : "hover:bg-muted/50",
                                            isExpanded && "bg-muted/30"
                                        )}
                                    >
                                        <div className="mt-0.5 shrink-0">
                                            {event.source === "polymarket" ? (
                                                <div className="w-1.5 h-1.5 rounded-full bg-blue-500" title="Polymarket" />
                                            ) : (
                                                <div className="w-1.5 h-1.5 rounded-full bg-green-500" title="Kalshi" />
                                            )}
                                        </div>
                                        <div className="flex-1 min-w-0">
                                            <div className="text-sm font-medium text-foreground truncate">{event.title}</div>
                                            <div className="text-xs text-muted-foreground flex items-center gap-2 mt-0.5">
                                                <span className="capitalize">{event.source}</span>
                                                <span>•</span>
                                                <span>{event.markets.length} options</span>
                                            </div>
                                        </div>
                                        <ChevronRight
                                            className={cn(
                                                "h-4 w-4 text-muted-foreground transition-transform shrink-0 mt-0.5",
                                                isExpanded && "rotate-90"
                                            )}
                                        />
                                    </button>
                                );
                            } else {
                                const market = item.data;
                                const parent = item.parentEvent;
                                const label = parent
                                    ? (market.title.replace(parent.title, "").replace(/^[ -]+/, "") || market.title)
                                    : market.title;

                                return (
                                    <button
                                        key={item.id}
                                        onClick={() => handleSelect(market)}
                                        className={cn(
                                            "w-full px-3 py-2 text-left flex items-center gap-3 rounded-lg transition-colors group",
                                            isSelected ? "bg-muted" : "hover:bg-muted/50",
                                            parent && "pl-8" // Indent if it's a sub-market
                                        )}
                                    >
                                        {!parent && (
                                            <div className="shrink-0">
                                                {market.source === "polymarket" ? (
                                                    <div className="w-1.5 h-1.5 rounded-full bg-blue-500" title="Polymarket" />
                                                ) : (
                                                    <div className="w-1.5 h-1.5 rounded-full bg-green-500" title="Kalshi" />
                                                )}
                                            </div>
                                        )}
                                        <div className="flex-1 min-w-0">
                                            <div className={cn("text-sm text-foreground truncate", parent && "font-medium opacity-90")}>{label}</div>
                                            {!parent && (
                                                <div className="text-[10px] text-muted-foreground flex items-center gap-2">
                                                    <span className="capitalize">{market.source}</span>
                                                    {market.volume_24h > 0 && <span>• ${(market.volume_24h).toLocaleString(undefined, { maximumFractionDigits: 0, notation: "compact" })} Vol</span>}
                                                </div>
                                            )}
                                            {parent && market.volume_24h > 0 && (
                                                <div className="text-[10px] text-muted-foreground">
                                                    ${(market.volume_24h).toLocaleString(undefined, { maximumFractionDigits: 0, notation: "compact" })} Vol
                                                </div>
                                            )}
                                        </div>
                                        <div className="text-xs font-semibold text-primary shrink-0 opacity-80 group-hover:opacity-100">
                                            {market.outcomes[0] ? (market.outcomes[0].price * 100).toFixed(0) + "%" : "-"}
                                        </div>
                                    </button>
                                );
                            }
                        })}
                    </div>
                </div>
            </div>
        </div>
    );
}
