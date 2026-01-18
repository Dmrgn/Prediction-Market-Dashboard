/**
 * Layer 2: Agent Controller
 * Manages the Thought-Action-Observation loop for the AI Agent.
 */

import { COMMANDS, executeCommand, type CommandPayloads } from "./registry";

const DEBUG_AGENT = "true";

export type AgentEvent = {
  id: string;
  message: string;
  createdAt: string;
};

const createEvent = (message: string): AgentEvent => ({
  id: crypto.randomUUID(),
  message,
  createdAt: new Date().toISOString(),
});

export const agentController = {
  processInput: async (input: string): Promise<AgentEvent[]> => {
    const events: AgentEvent[] = [];
    events.push(createEvent(`Thought: analyzing "${input}"`));

    if (DEBUG_AGENT) {
      console.debug("[Agent Controller] input", input);
    }

    if (input.toLowerCase().includes("news")) {
      events.push(createEvent("Action: opening news feed panel"));
      executeCommand(COMMANDS.OPEN_PANEL, {
        panelType: "NEWS_FEED",
        panelData: { query: input },
      });
      events.push(createEvent("Observation: news panel requested"));
    } else if (input.toLowerCase().includes("market")) {
      events.push(createEvent("Action: opening market aggregator panel"));
      executeCommand(COMMANDS.OPEN_PANEL, {
        panelType: "MARKET_AGGREGATOR_GRAPH",
        panelData: { marketId: "demo-market" },
      });
      events.push(createEvent("Observation: market panel requested"));
    } else {
      events.push(createEvent("Action: defaulting to market + news panels"));
      executeCommand(COMMANDS.QUERY_MARKET, { marketId: "demo-market" });
      events.push(createEvent("Observation: panels requested"));
    }

    if (DEBUG_AGENT) {
      console.debug("[Agent Controller] events", events);
    }

    return events;
  },

  performAction: (actionType: string, params: CommandPayloads["data"]) => {
    executeCommand(actionType as keyof typeof COMMANDS, params);
  },
};
