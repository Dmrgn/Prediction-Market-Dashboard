import { create } from "zustand";
import { backendInterface, type SentimentReport } from "@/backendInterface";

interface ResearcherState {
    report: SentimentReport | null;
    status: "idle" | "loading" | "success" | "error";
    error: string | null;
    query: string;
    setQuery: (q: string) => void;
    fetchReport: (query: string) => Promise<void>;
    clear: () => void;
}

export const useResearcherStore = create<ResearcherState>((set) => ({
    report: null,
    status: "idle",
    error: null,
    query: "",

    setQuery: (q) => set({ query: q }),

    fetchReport: async (query: string) => {
        if (!query.trim()) return;

        set({ status: "loading", error: null, query });

        try {
            // Use "research" as a placeholder market_id since we're using the query parameter
            const report = await backendInterface.fetchSentiment("research", query);
            set({ report, status: "success" });
        } catch (error) {
            const message = error instanceof Error ? error.message : "Unknown error";
            set({ error: message, status: "error" });
        }
    },

    clear: () => set({ report: null, status: "idle", error: null, query: "" }),
}));
