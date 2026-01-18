import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { LayoutProfile, PANEL_DEFAULTS } from "@/types/layout";
import type { PanelInstance, PanelType } from "./useWorkspaceStore";

interface LayoutState {
    /** All saved layout profiles */
    profiles: LayoutProfile[];

    /** Currently active profile ID (null = unsaved workspace) */
    activeProfileId: string | null;

    /** Save current workspace as a new profile */
    saveProfile: (name: string, panels: PanelInstance[], description?: string) => LayoutProfile;

    /** Load a profile (returns panels to apply) */
    loadProfile: (profileId: string) => PanelInstance[] | null;

    /** Delete a profile */
    deleteProfile: (profileId: string) => void;

    /** Update an existing profile */
    updateProfile: (profileId: string, panels: PanelInstance[]) => void;

    /** Rename a profile */
    renameProfile: (profileId: string, newName: string) => void;

    /** Get all profiles */
    getProfiles: () => LayoutProfile[];

    /** Optimize layout (returns optimized panels) */
    optimizeLayout: (panels: PanelInstance[]) => PanelInstance[];
}

const PANEL_DEFAULTS_MAP: Record<PanelType, { w: number; h: number; minW: number; minH: number }> = {
    NEWS_FEED: { w: 4, h: 6, minW: 3, minH: 4 },
    MARKET_AGGREGATOR_GRAPH: { w: 6, h: 8, minW: 4, minH: 5 },
};

export const useLayoutStore = create<LayoutState>()(
    persist(
        (set, get) => ({
            profiles: [],
            activeProfileId: null,

            saveProfile: (name: string, panels: PanelInstance[], description?: string) => {
                const id = crypto.randomUUID();
                const now = new Date().toISOString();

                const newProfile: LayoutProfile = {
                    id,
                    name,
                    description,
                    panels: panels.map(p => ({ ...p })), // Deep copy
                    createdAt: now,
                    updatedAt: now,
                };

                set((state) => ({
                    profiles: [...state.profiles, newProfile],
                    activeProfileId: id,
                }));

                return newProfile;
            },

            loadProfile: (profileId: string) => {
                const profile = get().profiles.find((p) => p.id === profileId);
                if (!profile) return null;

                set({ activeProfileId: profileId });

                // Return deep copy of panels with new IDs
                return profile.panels.map((p) => ({
                    ...p,
                    id: crypto.randomUUID(),
                }));
            },

            deleteProfile: (profileId: string) => {
                set((state) => ({
                    profiles: state.profiles.filter((p) => p.id !== profileId),
                    activeProfileId: state.activeProfileId === profileId ? null : state.activeProfileId,
                }));
            },

            updateProfile: (profileId: string, panels: PanelInstance[]) => {
                set((state) => ({
                    profiles: state.profiles.map((p) =>
                        p.id === profileId
                            ? { ...p, panels: panels.map(panel => ({ ...panel })), updatedAt: new Date().toISOString() }
                            : p
                    ),
                }));
            },

            renameProfile: (profileId: string, newName: string) => {
                set((state) => ({
                    profiles: state.profiles.map((p) =>
                        p.id === profileId
                            ? { ...p, name: newName, updatedAt: new Date().toISOString() }
                            : p
                    ),
                }));
            },

            getProfiles: () => get().profiles,

            optimizeLayout: (panels: PanelInstance[]) => {
                const GRID_COLS = 12;
                const visiblePanels = panels.filter((p) => p.isVisible);

                // Sort by area (larger panels first for better packing)
                const sorted = [...visiblePanels].sort((a, b) => {
                    const aDefaults = PANEL_DEFAULTS_MAP[a.type];
                    const bDefaults = PANEL_DEFAULTS_MAP[b.type];
                    const aArea = (aDefaults?.w ?? 4) * (aDefaults?.h ?? 4);
                    const bArea = (bDefaults?.w ?? 4) * (bDefaults?.h ?? 4);
                    return bArea - aArea;
                });

                // Place panels row by row
                let currentRow = 0;
                let currentCol = 0;
                let maxHeightInRow = 0;

                const optimized: PanelInstance[] = [];

                for (const panel of sorted) {
                    const defaults = PANEL_DEFAULTS_MAP[panel.type] ?? { w: 4, h: 4 };
                    const w = Math.min(defaults.w, GRID_COLS);
                    const h = defaults.h;

                    // Check if panel fits in current row
                    if (currentCol + w > GRID_COLS) {
                        // Move to next row
                        currentRow += maxHeightInRow;
                        currentCol = 0;
                        maxHeightInRow = 0;
                    }

                    optimized.push({
                        ...panel,
                        x: currentCol,
                        y: currentRow,
                        w,
                        h,
                    });

                    currentCol += w;
                    maxHeightInRow = Math.max(maxHeightInRow, h);
                }

                // Include hidden panels unchanged
                const hiddenPanels = panels.filter((p) => !p.isVisible);

                return [...optimized, ...hiddenPanels];
            },
        }),
        {
            name: "prediction-market-layouts",
        }
    )
);
