/**
 * Layer 2: Agent Controller
 * Manages the Thought-Action-Observation loop for the AI Agent.
 */

import { backendInterface } from "@/backendInterface";
import { COMMANDS, executeCommand, getCommandEntries } from "./registry";
import { useAgentStore, type AgentStep, type ExecutedAction } from "@/hooks/useAgentStore";

export const agentController = {
  runWorkflow: (prompt: string) => {
    const store = useAgentStore.getState();
    store.startWorkflow(prompt);

    // Prepare commands for the agent
    // We pass a recursive reference to runWorkflow so the RUN_AI command is valid, 
    // though the agent likely won't call itself.
    // Prepare commands for the agent
    // We pass all available commands to the agent so it knows what it can do.
    const registryCommands = getCommandEntries().map((cmd) => ({
      id: cmd.id,
      label: cmd.label,
      description: cmd.description,
      params: cmd.params,
    }));

    // Inject agent-specific tools that aren't in the registry
    const commands = [
      ...registryCommands,
      {
        id: "search-markets",
        label: "Search Markets",
        description: "Search for prediction markets by query to get Market IDs",
        params: [{ name: "query", label: "Query", type: "text", placeholder: "e.g. bitcoin, entertainment" } as any],
      }
    ];

    // Start WebSocket connection
    const cleanup = backendInterface.socket.startAgent(
      prompt,
      commands,
      {
        onStep: async (payload) => {
          const { reasoning, actions, done, model } = payload;

          const step: AgentStep = {
            reasoning,
            actions: actions.map(a => ({ command: a.command, params: a.params })),
            done,
            model: model as "gemini" | "gpt"
          };

          store.addStep(step);

          // If there are actions, execute them
          if (actions.length > 0) {
            const results: Array<{ command: string; status: string; result?: string; panelId?: string }> = [];

            for (const action of actions) {
              // Track as pending
              const executedAction: ExecutedAction = {
                command: action.command,
                params: action.params,
                status: "pending"
              };
              store.addExecutedAction(executedAction);

              try {
                // SPECIAL HANDLERS
                if (action.command === "search-markets") {
                  const query = action.params.query || "";
                  const response = await backendInterface.searchMarkets(query);
                  const markets = response.markets.slice(0, 5).map(m =>
                    `- ID: "${m.market_id}" | Title: "${m.title}" | Source: ${m.source}`
                  ).join("\n");

                  const resultText = markets ? `Found markets:\n${markets}` : "No markets found.";

                  store.updateActionStatus(action.command, "success", `Found ${response.markets.length} markets`);
                  results.push({ command: action.command, status: "success", result: resultText });
                  continue;
                }

                // REGISTRY HANDLERS
                // executeCommand takes the TYPE (enum), but we have the ID.
                // We need to look up the command type from the registry ID.
                const entry = getCommandEntries().find(c => c.id === action.command);

                if (entry) {
                  // Execute
                  // Note: executeCommand expects the TYPE, not ID. 
                  // entry.type is the COMMANDS enum value.
                  // Casting params to any because we trust the agent matches the schema we sent.
                  executeCommand(entry.type as any, action.params as any);

                  // Mark success
                  // In a real app we'd get the result/panelId from executeCommand, 
                  // but currently it's void. We assume success.
                  store.updateActionStatus(action.command, "success", "Panel opened");
                  results.push({ command: action.command, status: "success", result: "Executed successfully" });
                } else {
                  throw new Error(`Command ${action.command} not found`);
                }

              } catch (e) {
                console.error(`Failed to execute ${action.command}`, e);
                store.updateActionStatus(action.command, "error", String(e));
                results.push({ command: action.command, status: "error", result: String(e) });
              }
            }


            // Send observations back
            backendInterface.socket.sendObservation(results);
          }
        },

        onComplete: (payload) => {
          store.completeWorkflow(payload.summary);
          // We don't necessarily call cleanup() here to allow viewing the state
        },

        onError: (error) => {
          store.setError(error);
        }
      }
    );

    // We could store cleanup if we wanted to cancel
  }
};
