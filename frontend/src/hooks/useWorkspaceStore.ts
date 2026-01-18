import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { StateCreator } from "zustand";

export type PanelType = "MARKET_AGGREGATOR_GRAPH" | "NEWS_FEED" | "CHART" | "ORDER_BOOK";

export interface PanelInstance {
  id: string;
  type: PanelType;
  x: number;
  y: number;
  w: number;
  h: number;
  isVisible: boolean;
  data: Record<string, unknown>;
}

interface WorkspaceState {
  panels: PanelInstance[];
  openPanel: (type: PanelType, data?: Record<string, unknown>) => string;
  closePanel: (id: string) => void;
  updatePanel: (id: string, data: Record<string, unknown>) => void;
  updateLayout: (
    id: string,
    layout: Pick<PanelInstance, "x" | "y" | "w" | "h">
  ) => void;
  setPanelVisibility: (id: string, isVisible: boolean) => void;
  setPanels: (panels: PanelInstance[]) => void;
}

const defaultLayout = {
  x: 0,
  y: 0,
  w: 4,
  h: 6,
};

const defaultPanelData: Record<PanelType, Record<string, unknown>> = {
  MARKET_AGGREGATOR_GRAPH: {
    marketId: "demo-market",
    title: "Market Aggregator",
  },
  CHART: {
    marketId: "demo-market",
    title: "Chart",
  },
  ORDER_BOOK: {
    marketId: "demo-market",
    title: "Order Book",
  },
  NEWS_FEED: {
    query: "stock",
    title: "News Feed",
  },
};

const createId = () => crypto.randomUUID();

const workspaceCreator: StateCreator<WorkspaceState> = (set, get) => ({
  panels: [],
  openPanel: (type: PanelType, data: Record<string, unknown> = {}) => {
    const id = createId();
    const panelData = { ...defaultPanelData[type], ...data };
    const nextPanel: PanelInstance = {
      id,
      type,
      ...defaultLayout,
      isVisible: true,
      data: panelData,
    };
    set((state: WorkspaceState) => ({ panels: [...state.panels, nextPanel] }));
    return id;
  },
  closePanel: (id: string) => {
    set((state: WorkspaceState) => ({
      panels: state.panels.map((panel: PanelInstance) =>
        panel.id === id ? { ...panel, isVisible: false } : panel
      ),
    }));
  },
  updatePanel: (id: string, data: Record<string, unknown>) => {
    set((state: WorkspaceState) => ({
      panels: state.panels.map((panel: PanelInstance) =>
        panel.id === id ? { ...panel, data: { ...panel.data, ...data } } : panel
      ),
    }));
  },
  updateLayout: (
    id: string,
    layout: Pick<PanelInstance, "x" | "y" | "w" | "h">
  ) => {
    set((state: WorkspaceState) => ({
      panels: state.panels.map((panel: PanelInstance) =>
        panel.id === id ? { ...panel, ...layout } : panel
      ),
    }));
  },
  setPanelVisibility: (id: string, isVisible: boolean) => {
    set((state: WorkspaceState) => ({
      panels: state.panels.map((panel: PanelInstance) =>
        panel.id === id ? { ...panel, isVisible } : panel
      ),
    }));
  },
  setPanels: (panels: PanelInstance[]) => {
    set({ panels });
  },
});

export const useWorkspaceStore = create<WorkspaceState>()(
  persist(workspaceCreator, {
    name: "prediction-market-workspace",
  })
);
