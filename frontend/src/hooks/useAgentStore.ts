import { create } from "zustand";
import type { AgentEvent } from "@/commands/agentController";

interface AgentState {
  events: AgentEvent[];
  addEvents: (newEvents: AgentEvent[]) => void;
  clearEvents: () => void;
}

const MAX_EVENTS = 6;

export const useAgentStore = create<AgentState>((set) => ({
  events: [],
  addEvents: (newEvents) =>
    set((state) => ({
      events: [...newEvents, ...state.events].slice(0, MAX_EVENTS),
    })),
  clearEvents: () => set({ events: [] }),
}));
