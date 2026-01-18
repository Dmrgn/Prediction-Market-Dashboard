import type { PanelInstance, PanelType } from "@/hooks/useWorkspaceStore";
import type { LucideIcon } from "lucide-react";

/**
 * Represents an action that can be performed on a panel.
 * Actions appear in the panel's context menu.
 */
export interface PanelAction {
    /** Unique identifier for the action */
    id: string;
    /** Display label in the menu */
    label: string;
    /** Optional icon component */
    icon?: LucideIcon;
    /** Optional keyboard shortcut hint */
    shortcut?: string;
    /** Visual variant - destructive shows in red */
    variant?: "default" | "destructive";
    /** Handler function - receives panel and context for performing actions */
    handler: (panel: PanelInstance, context: ActionContext) => void | Promise<void>;
    /** Optional condition - action only shows if this returns true */
    isVisible?: (panel: PanelInstance) => boolean;
    /** Optional condition - action is disabled if this returns true */
    isDisabled?: (panel: PanelInstance) => boolean;
}

/**
 * Context passed to action handlers.
 * Provides access to workspace and UI functions.
 */
export interface ActionContext {
    /** Open a new panel */
    openPanel: (type: PanelType, data?: Record<string, unknown>) => string;
    /** Close a panel by ID */
    closePanel: (id: string) => void;
    /** Update panel data */
    updatePanel: (id: string, data: Record<string, unknown>) => void;
    /** Open command palette, optionally pre-selecting a command */
    openCommandPalette: (commandId?: string, params?: Record<string, string>) => void;
}

/**
 * Registry storing panel-specific actions.
 * Each panel type maps to an array of actions.
 */
const panelActionsRegistry: Partial<Record<PanelType, PanelAction[]>> = {};

/**
 * Register actions for a specific panel type.
 * Actions will appear in the panel's context menu above Edit/Delete.
 * 
 * @example
 * ```typescript
 * registerPanelActions("CHART", [
 *   {
 *     id: "open-news",
 *     label: "View Related News",
 *     icon: Newspaper,
 *     handler: (panel, ctx) => {
 *       ctx.openPanel("NEWS_FEED", { query: panel.data.title });
 *     },
 *   },
 * ]);
 * ```
 */
export function registerPanelActions(panelType: PanelType, actions: PanelAction[]) {
    const existing = panelActionsRegistry[panelType] || [];
    panelActionsRegistry[panelType] = [...existing, ...actions];
}

/**
 * Get all actions for a panel instance.
 * Filters out actions where isVisible returns false.
 * 
 * @param panel - The panel instance
 * @returns Array of visible actions for this panel
 */
export function getPanelActions(panel: PanelInstance): PanelAction[] {
    const panelActions = panelActionsRegistry[panel.type] || [];
    return panelActions.filter(
        action => !action.isVisible || action.isVisible(panel)
    );
}

/**
 * Check if a panel type has any registered actions.
 */
export function hasPanelActions(panelType: PanelType): boolean {
    const actions = panelActionsRegistry[panelType];
    return !!actions && actions.length > 0;
}

/**
 * Clear all registered actions (useful for testing).
 */
export function clearPanelActions() {
    Object.keys(panelActionsRegistry).forEach(key => {
        delete panelActionsRegistry[key as PanelType];
    });
}
