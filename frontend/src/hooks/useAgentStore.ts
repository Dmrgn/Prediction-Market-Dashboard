import { create } from "zustand";

/**
 * Agent step from backend
 */
export interface AgentStep {
  reasoning: string;
  actions: AgentAction[];
  done: boolean;
  model?: "gemini" | "gpt";
}

export interface AgentAction {
  command: string;
  params: Record<string, string>;
}

export interface ExecutedAction {
  command: string;
  params: Record<string, string>;
  status: "pending" | "success" | "error";
  result?: string;
  panelId?: string;
}

interface AgentWorkflowState {
  // Workflow state
  isRunning: boolean;
  currentPrompt: string | null;
  steps: AgentStep[];
  executedActions: ExecutedAction[];
  summary: string | null;
  error: string | null;

  // Actions
  startWorkflow: (prompt: string) => void;
  addStep: (step: AgentStep) => void;
  addExecutedAction: (action: ExecutedAction) => void;
  updateActionStatus: (command: string, status: ExecutedAction["status"], result?: string, panelId?: string) => void;
  completeWorkflow: (summary: string) => void;
  setError: (error: string) => void;
  reset: () => void;
}

export const useAgentStore = create<AgentWorkflowState>((set) => ({
  // Initial state
  isRunning: false,
  currentPrompt: null,
  steps: [],
  executedActions: [],
  summary: null,
  error: null,

  startWorkflow: (prompt) =>
    set({
      isRunning: true,
      currentPrompt: prompt,
      steps: [],
      executedActions: [],
      summary: null,
      error: null,
    }),

  addStep: (step) =>
    set((state) => ({
      steps: [...state.steps, step],
    })),

  addExecutedAction: (action) =>
    set((state) => ({
      executedActions: [...state.executedActions, action],
    })),

  updateActionStatus: (command, status, result, panelId) =>
    set((state) => ({
      executedActions: state.executedActions.map((a) =>
        a.command === command && a.status === "pending"
          ? { ...a, status, result, panelId }
          : a
      ),
    })),

  completeWorkflow: (summary) =>
    set({
      isRunning: false,
      summary,
    }),

  setError: (error) =>
    set({
      isRunning: false,
      error,
    }),

  reset: () =>
    set({
      isRunning: false,
      currentPrompt: null,
      steps: [],
      executedActions: [],
      summary: null,
      error: null,
    }),
}));
