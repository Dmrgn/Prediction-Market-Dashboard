/**
 * Panel Action Registrations
 * 
 * This file registers all panel-specific context menu actions.
 * Import this file once in the app to activate all registrations.
 */

import { registerPanelActions } from "./PanelActions";
import {
    Newspaper,
    BarChart2,
    FileText,
    Sparkles,
    LineChart,
    ExternalLink,
    Copy,
    RefreshCw
} from "lucide-react";

// ============================================
// CHART Panel Actions
// ============================================
registerPanelActions("CHART", [
    {
        id: "open-news",
        label: "View Related News",
        icon: Newspaper,
        handler: (panel, ctx) => {
            // Extract keywords from market title for news search
            const marketTitle = String(panel.data.title || "market");
            const keywords = marketTitle.split(/\s+/).slice(0, 4).join(" ");

            ctx.openPanel("NEWS_FEED", {
                query: keywords,
                title: `News: ${marketTitle.slice(0, 30)}...`
            });
        },
    },
    {
        id: "open-orderbook",
        label: "Open Order Book",
        icon: BarChart2,
        handler: (panel, ctx) => {
            ctx.openPanel("ORDER_BOOK", {
                marketId: panel.data.marketId,
                title: `Order Book`,
            });
        },
        // Only show if we have a valid market ID
        isVisible: (panel) => !!panel.data.marketId && panel.data.marketId !== "demo-market",
    },
    {
        id: "view-rules",
        label: "Market Details",
        icon: FileText,
        handler: (panel, ctx) => {
            // TODO: Open a modal or details panel
            // For now, could use command palette or alert
            const marketId = String(panel.data.marketId || "");
            console.log("View market details for:", marketId);

            // Could open a URL in new tab for Polymarket
            if (marketId.startsWith("0x")) {
                window.open(`https://polymarket.com/event/${marketId}`, "_blank");
            }
        },
        isVisible: (panel) => !!panel.data.marketId && panel.data.marketId !== "demo-market",
    },
    {
        id: "copy-market-id",
        label: "Copy Market ID",
        icon: Copy,
        handler: (panel) => {
            const marketId = String(panel.data.marketId || "");
            navigator.clipboard.writeText(marketId).catch(console.error);
        },
        isVisible: (panel) => !!panel.data.marketId && panel.data.marketId !== "demo-market",
    },
]);

// ============================================
// ORDER_BOOK Panel Actions
// ============================================
registerPanelActions("ORDER_BOOK", [
    {
        id: "open-chart",
        label: "Open Chart",
        icon: LineChart,
        handler: (panel, ctx) => {
            ctx.openPanel("CHART", {
                marketId: panel.data.marketId,
                title: `Chart`,
            });
        },
        isVisible: (panel) => !!panel.data.marketId && panel.data.marketId !== "demo-market",
    },
    {
        id: "open-news",
        label: "View Related News",
        icon: Newspaper,
        handler: (panel, ctx) => {
            const marketTitle = String(panel.data.title || "market");
            const keywords = marketTitle.split(/\s+/).slice(0, 4).join(" ");

            ctx.openPanel("NEWS_FEED", {
                query: keywords,
                title: `News: ${marketTitle.slice(0, 30)}...`
            });
        },
    },
    {
        id: "copy-market-id",
        label: "Copy Market ID",
        icon: Copy,
        handler: (panel) => {
            const marketId = String(panel.data.marketId || "");
            navigator.clipboard.writeText(marketId).catch(console.error);
        },
        isVisible: (panel) => !!panel.data.marketId,
    },
]);

// ============================================
// NEWS_FEED Panel Actions  
// ============================================
registerPanelActions("NEWS_FEED", [
    {
        id: "refine-search",
        label: "Refine Search",
        icon: RefreshCw,
        handler: (panel, ctx) => {
            const currentQuery = String(panel.data.query || "");
            ctx.openCommandPalette("open-news-feed", { query: currentQuery });
            ctx.closePanel(panel.id);
        },
    },
    {
        id: "open-in-browser",
        label: "Search on Google News",
        icon: ExternalLink,
        handler: (panel) => {
            const query = encodeURIComponent(String(panel.data.query || ""));
            window.open(`https://news.google.com/search?q=${query}`, "_blank");
        },
        isVisible: (panel) => !!panel.data.query,
    },
]);

// ============================================
// MARKET_AGGREGATOR_GRAPH Panel Actions (legacy)
// ============================================
registerPanelActions("MARKET_AGGREGATOR_GRAPH", [
    {
        id: "open-news",
        label: "View Related News",
        icon: Newspaper,
        handler: (panel, ctx) => {
            const marketTitle = String(panel.data.title || "market");
            const keywords = marketTitle.split(/\s+/).slice(0, 4).join(" ");

            ctx.openPanel("NEWS_FEED", {
                query: keywords,
                title: `News: ${marketTitle.slice(0, 30)}...`
            });
        },
    },
]);

// Export a no-op to ensure this file is imported
export const panelActionsRegistered = true;
