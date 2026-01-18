/**
 * Layout Profile Types
 * 
 * Defines the structure for layout profiles that can be saved, loaded, and optimized.
 */

import type { PanelType, PanelInstance } from "@/hooks/useWorkspaceStore";

/**
 * A saved layout profile containing all panel configurations.
 */
export interface LayoutProfile {
    /** Unique identifier */
    id: string;

    /** Human-readable profile name */
    name: string;

    /** Optional description for this profile */
    description?: string;

    /** All panels in this profile */
    panels: PanelInstance[];

    /** ISO timestamp when profile was created */
    createdAt: string;

    /** ISO timestamp when profile was last modified */
    updatedAt: string;
}

/**
 * Default size constraints for each panel type.
 * Used by the optimizer to determine optimal sizes.
 */
export const PANEL_DEFAULTS: Record<PanelType, { w: number; h: number; minW: number; minH: number }> = {
    NEWS_FEED: { w: 4, h: 6, minW: 3, minH: 4 },
    MARKET_AGGREGATOR_GRAPH: { w: 6, h: 8, minW: 4, minH: 5 },
};

/**
 * Get metadata about a panel type for display purposes.
 */
export const getPanelMeta = (type: PanelType): { label: string; icon: string } => {
    const meta: Record<PanelType, { label: string; icon: string }> = {
        NEWS_FEED: { label: "News Feed", icon: "📰" },
        MARKET_AGGREGATOR_GRAPH: { label: "Market Chart", icon: "📈" },
    };
    return meta[type] ?? { label: type, icon: "❓" };
};
