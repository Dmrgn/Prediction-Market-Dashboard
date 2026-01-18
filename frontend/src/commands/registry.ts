/**
 * Layer 2: Command Registry
 * A collection of executable actions that modify application state or query the backend.
 */

import type { PanelType } from "@/hooks/useWorkspaceStore";
import { useWorkspaceStore } from "@/hooks/useWorkspaceStore";

export const COMMANDS = {
  OPEN_PANEL: "OPEN_PANEL",
  CLOSE_PANEL: "CLOSE_PANEL",
  QUERY_MARKET: "QUERY_MARKET",
  RUN_AI: "RUN_AI",
} as const;

export type CommandType = keyof typeof COMMANDS;

export type CommandPayloads =
  | { type: "OPEN_PANEL"; data: { panelType: PanelType; panelData?: Record<string, unknown> } }
  | { type: "CLOSE_PANEL"; data: { id: string } }
  | { type: "QUERY_MARKET"; data: { marketId: string } }
  | { type: "RUN_AI"; data: { prompt: string } };

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
      // Backward compatibility: keep MARKET_AGGREGATOR_GRAPH check if needed, but we'll use CHART now.
      store.openPanel("CHART", { marketId: payload.marketId });
      store.openPanel("ORDER_BOOK", { marketId: payload.marketId });
      store.openPanel("NEWS_FEED", { query: payload.marketId });
      break;
    }
    default:
      console.warn("Unhandled command", type, data);
  }
};

export const getCommandEntries = (
  runAi: (prompt: string) => void
): CommandEntry[] => [
    {
      id: "open-chart",
      type: COMMANDS.OPEN_PANEL,
      label: "Open Chart",
      description: "Add a price chart panel",
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
          panelType: "CHART",
          panelData: { marketId: values.marketId || "demo-market" },
        }),
    },
    {
      id: "open-order-book",
      type: COMMANDS.OPEN_PANEL,
      label: "Open Order Book",
      description: "Add an order book panel",
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
          panelType: "ORDER_BOOK",
          panelData: { marketId: values.marketId || "demo-market" },
        }),
    },
    {
      id: "query-market",
      type: COMMANDS.QUERY_MARKET,
      label: "Query Market",
      description: "Open Chart, Order Book + News",
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
  ];
