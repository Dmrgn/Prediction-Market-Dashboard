import React, { useState, useEffect } from "react";
import { backendInterface, type CrossMarketComparison } from "@/backendInterface";
import { useWorkspaceStore } from "@/hooks/useWorkspaceStore";

interface CrossMarketBadgeProps {
    marketId: string;
    onNavigate?: (marketId: string) => void;
}

/**
 * Badge that shows cross-market comparison for a market.
 * Displays the most similar market on the opposing platform.
 */

export function CrossMarketBadge({ marketId, onNavigate }: CrossMarketBadgeProps) {
    const [comparison, setComparison] = useState<CrossMarketComparison | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [isHovered, setIsHovered] = useState(false);

    // Use workspace store for branching
    const openPanel = useWorkspaceStore((state) => state.openPanel);

    useEffect(() => {
        if (!marketId) return;

        let cancelled = false;
        setLoading(true);
        setError(null);

        backendInterface
            .fetchCrossMarketComparison(marketId)
            .then((data) => {
                if (!cancelled) {
                    setComparison(data);
                }
            })
            .catch((err) => {
                if (!cancelled) {
                    setError(err.message || "Failed to fetch comparison");
                }
            })
            .finally(() => {
                if (!cancelled) {
                    setLoading(false);
                }
            });

        return () => {
            cancelled = true;
        };
    }, [marketId]);

    const handleBranch = (targetMarketId: string, event: React.MouseEvent) => {
        event.stopPropagation();
        openPanel("CHART", { marketId: targetMarketId });
    };

    if (loading) {
        return (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs text-gray-400 bg-gray-800/50 rounded-full">
                <span className="animate-pulse">🔗</span>
                <span>Finding match...</span>
            </span>
        );
    }

    if (error || !comparison?.similar_market) {
        return null; // Don't show anything if no match found
    }

    const { similar_market, similar_markets, similarity_score, method } = comparison;
    const platformEmoji = similar_market.source === "kalshi" ? "🔷" : "🟣";
    const platformName = similar_market.source === "kalshi" ? "Kalshi" : "Polymarket";
    const scorePercent = Math.round(similarity_score * 100);

    return (
        <div
            className="relative inline-block"
            onMouseEnter={() => setIsHovered(true)}
            onMouseLeave={() => setIsHovered(false)}
        >
            {/* Badge */}
            <button
                onClick={() => onNavigate?.(similar_market.market_id)}
                className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium text-blue-300 bg-blue-900/40 hover:bg-blue-900/60 border border-blue-700/50 rounded-full transition-all cursor-pointer"
            >
                <span>{platformEmoji}</span>
                <span>Similar on {platformName}</span>
                {method === "embedding" && scorePercent > 0 && (
                    <span className="text-blue-400/70">{scorePercent}%</span>
                )}
            </button>

            {/* Hover Tooltip */}
            {isHovered && (
                <div className="absolute z-50 w-96 p-3 mt-2 bg-gray-900 border border-gray-700 rounded-lg shadow-xl left-0 top-full">
                    <div className="space-y-4">
                        {/* Source Market */}
                        <div>
                            <div className="text-[10px] uppercase tracking-wider text-gray-500 mb-1">
                                Current Market
                            </div>
                            <div className="text-sm text-gray-200 line-clamp-2">
                                {comparison.source_market.title}
                            </div>
                        </div>

                        {/* Divider */}
                        <div className="h-px bg-gray-800" />

                        {/* Similar Markets List */}
                        <div>
                            <div className="text-[10px] uppercase tracking-wider text-gray-500 mb-2 flex items-center justify-between">
                                <span>Related Bets</span>
                                <span className="text-[9px] text-gray-600">Click arrow to branch</span>
                            </div>

                            <div className="space-y-1">
                                {(similar_markets || [similar_market]).slice(0, 4).map((market) => (
                                    <div
                                        key={market.market_id}
                                        className="group flex items-center gap-2 p-2 rounded-lg cursor-pointer hover:bg-blue-900/30 transition-all border border-transparent hover:border-blue-700/40"
                                        onClick={() => onNavigate?.(market.market_id)}
                                    >
                                        <div className="text-sm shrink-0">
                                            {market.source === "kalshi" ? "🔷" : "🟣"}
                                        </div>
                                        <div className="flex-1 min-w-0">
                                            <div className="text-sm text-blue-200 line-clamp-2 group-hover:text-white transition-colors">
                                                {market.title}
                                            </div>
                                            {'score' in market && (market as any).score && (
                                                <div className="mt-1 text-[10px] text-gray-500">
                                                    {Math.round((market as any).score * 100)}% match
                                                </div>
                                            )}
                                        </div>

                                        {/* Branch Button - always visible */}
                                        <button
                                            onClick={(e) => { e.stopPropagation(); handleBranch(market.market_id, e); }}
                                            className="shrink-0 p-2 text-gray-400 hover:text-white hover:bg-white/10 rounded-md transition-all"
                                            title="Open in new chart"
                                        >
                                            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                                            </svg>
                                        </button>
                                    </div>
                                ))}
                            </div>
                        </div>

                        {/* Footer Info */}
                        <div className="text-[10px] text-gray-600 pt-2 border-t border-gray-800 flex justify-between">
                            <span>Matched via {method === "embedding" ? "semantic embedding" : "text similarity"}</span>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
