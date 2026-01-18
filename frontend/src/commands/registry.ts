/**
 * Layer 2: Command Registry
 * A collection of executable actions that modify application state or query the backend.
 */

import type { PanelType } from "@/hooks/useWorkspaceStore";
import { useWorkspaceStore } from "@/hooks/useWorkspaceStore";
import { useLayoutStore } from "@/hooks/useLayoutStore";

export const COMMANDS = {
  OPEN_PANEL: "OPEN_PANEL",
  CLOSE_PANEL: "CLOSE_PANEL",
  QUERY_MARKET: "QUERY_MARKET",
  RUN_AI: "RUN_AI",
  OPTIMIZE_LAYOUT: "OPTIMIZE_LAYOUT",
  SAVE_LAYOUT: "SAVE_LAYOUT",
  LOAD_LAYOUT: "LOAD_LAYOUT",
  DELETE_LAYOUT: "DELETE_LAYOUT",
  FRESH_LAYOUT: "FRESH_LAYOUT",
} as const;

export type CommandType = keyof typeof COMMANDS;

export type CommandPayloads =
  | { type: "OPEN_PANEL"; data: { panelType: PanelType; panelData?: Record<string, unknown> } }
  | { type: "CLOSE_PANEL"; data: { id: string } }
  | { type: "QUERY_MARKET"; data: { marketId: string } }
  | { type: "RUN_AI"; data: { prompt: string } }
  | { type: "OPTIMIZE_LAYOUT"; data: Record<string, never> }
  | { type: "SAVE_LAYOUT"; data: { name: string } }
  | { type: "LOAD_LAYOUT"; data: { profileId: string } }
  | { type: "DELETE_LAYOUT"; data: { profileId: string } };

export type CommandParamType = "text" | "select" | "market";

export interface CommandParamSchema {
  name: string;
  label: string;
  type: CommandParamType;
  placeholder?: string;
  defaultValue?: string;
  options?: string[];
}

export interface CommandEntry {
  id: string;
  type: CommandType;
  label: string;
  description?: string;
  params?: CommandParamSchema[];
  closeOnRun?: boolean;
  handler: (values: Record<string, string>) => void;
}

export const executeCommand = (type: CommandType, data: CommandPayloads["data"]) => {
  const store = useWorkspaceStore.getState();
  const layoutStore = useLayoutStore.getState();

  switch (type) {
    case COMMANDS.OPEN_PANEL: {
      const payload = data as CommandPayloads["data"] & {
        panelType: PanelType;
        panelData?: Record<string, unknown>;
      };
      store.openPanel(payload.panelType, payload.panelData);
      break;
    }
    case COMMANDS.CLOSE_PANEL: {
      const payload = data as CommandPayloads["data"] & { id: string };
      store.closePanel(payload.id);
      break;
    }
    case COMMANDS.QUERY_MARKET: {
      const payload = data as CommandPayloads["data"] & { marketId: string };
      store.openPanel("MARKET_AGGREGATOR_GRAPH", { marketId: payload.marketId });
      store.openPanel("NEWS_FEED", { query: payload.marketId });
      break;
    }
    case COMMANDS.OPTIMIZE_LAYOUT: {
      const panels = store.panels;
      const optimized = layoutStore.optimizeLayout(panels);
      optimized.forEach((panel) => {
        store.updateLayout(panel.id, { x: panel.x, y: panel.y, w: panel.w, h: panel.h });
      });
      break;
    }
    case COMMANDS.SAVE_LAYOUT: {
      const payload = data as { name: string };
      if (payload.name?.trim()) {
        layoutStore.saveProfile(payload.name.trim(), store.panels);
      }
      break;
    }
    case COMMANDS.LOAD_LAYOUT: {
      const payload = data as { profileId: string };
      const newPanels = layoutStore.loadProfile(payload.profileId);
      if (newPanels) {
        store.setPanels(newPanels);
      }
      break;
    }
    case COMMANDS.DELETE_LAYOUT: {
      const payload = data as { profileId: string };
      layoutStore.deleteProfile(payload.profileId);
      break;
    }
    case COMMANDS.FRESH_LAYOUT: {
      store.setPanels([]);
      break;
    }
    default:
      console.warn("Unhandled command", type, data);
  }
};

export const getCommandEntries = (
  runAi: (prompt: string) => void
): CommandEntry[] => {
  const layoutStore = useLayoutStore.getState();
  const profiles = layoutStore.profiles;

  const baseCommands: CommandEntry[] = [
    {
      id: "open-market-aggregator",
      type: COMMANDS.OPEN_PANEL,
      label: "Open Market Aggregator",
      description: "Add a market graph panel",
      closeOnRun: true,
      params: [
        {
          name: "marketId",
          label: "Market",
          type: "market",
          placeholder: "Search markets",
          defaultValue: "",
        },
      ],
      handler: (values) =>
        executeCommand(COMMANDS.OPEN_PANEL, {
          panelType: "MARKET_AGGREGATOR_GRAPH",
          panelData: { marketId: values.marketId || "demo-market" },
        }),
    },
    {
      id: "open-news-feed",
      type: COMMANDS.OPEN_PANEL,
      label: "Open News Feed",
      description: "Add a market news panel",
      closeOnRun: true,
      params: [
        {
          name: "query",
          label: "Query",
          type: "text",
          placeholder: "prediction markets",
          defaultValue: "prediction markets",
        },
      ],
      handler: (values) =>
        executeCommand(COMMANDS.OPEN_PANEL, {
          panelType: "NEWS_FEED",
          panelData: { query: values.query || "prediction markets" },
        }),
    },
    {
      id: "query-market",
      type: COMMANDS.QUERY_MARKET,
      label: "Query Market",
      description: "Open both market graph + news",
      closeOnRun: true,
      params: [
        {
          name: "marketId",
          label: "Market",
          type: "market",
          placeholder: "Search markets",
          defaultValue: "",
        },
      ],
      handler: (values) =>
        executeCommand(COMMANDS.QUERY_MARKET, {
          marketId: values.marketId || "demo-market",
        }),
    },
    {
      id: "ai-run-agent",
      type: COMMANDS.RUN_AI,
      label: "AI: Run Agent",
      description: "Execute the agent loop on a prompt",
      closeOnRun: false,
      params: [
        {
          name: "prompt",
          label: "Prompt",
          type: "text",
          placeholder: "Find volatile markets and show news",
          defaultValue: "Show me the latest market news",
        },
      ],
      handler: (values) => runAi(values.prompt || "Show me the latest market news"),
    },
    // Layout commands
    {
      id: "layout-optimize",
      type: COMMANDS.OPTIMIZE_LAYOUT,
      label: "Layout: Optimize",
      description: "Auto-arrange panels for optimal space",
      closeOnRun: true,
      handler: () => executeCommand(COMMANDS.OPTIMIZE_LAYOUT, {}),
    },
    {
      id: "layout-save",
      type: COMMANDS.SAVE_LAYOUT,
      label: "Layout: Save Current",
      description: "Save current layout as a profile",
      closeOnRun: true,
      params: [
        {
          name: "name",
          label: "Profile Name",
          type: "text",
          placeholder: "My Layout",
          defaultValue: "",
        },
      ],
      handler: (values) => executeCommand(COMMANDS.SAVE_LAYOUT, { name: values.name || "" }),
    },
    {
      id: "layout-fresh",
      type: COMMANDS.FRESH_LAYOUT,
      label: "Layout: Create Fresh",
      description: "Clear all panels and start with a blank workspace",
      closeOnRun: true,
      handler: () => executeCommand(COMMANDS.FRESH_LAYOUT, {}),
    },
  ];

  // Add dynamic "Load Layout: [name]" commands for each saved profile
  const loadCommands: CommandEntry[] = profiles.map((profile) => ({
    id: `layout-load-${profile.id}`,
    type: COMMANDS.LOAD_LAYOUT,
    label: `Layout: Load "${profile.name}"`,
    description: profile.description || `Load saved layout`,
    closeOnRun: true,
    handler: () => executeCommand(COMMANDS.LOAD_LAYOUT, { profileId: profile.id }),
  }));

  // Add dynamic "Delete Layout: [name]" commands for each saved profile
  const deleteCommands: CommandEntry[] = profiles.map((profile) => ({
    id: `layout-delete-${profile.id}`,
    type: COMMANDS.DELETE_LAYOUT,
    label: `Layout: Delete "${profile.name}"`,
    description: `Remove saved layout`,
    closeOnRun: true,
    handler: () => executeCommand(COMMANDS.DELETE_LAYOUT, { profileId: profile.id }),
  }));

  return [...baseCommands, ...loadCommands, ...deleteCommands];
};
