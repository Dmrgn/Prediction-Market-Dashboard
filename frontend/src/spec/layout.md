# Layout Profile System – Complete Implementation Specification

## Executive Summary

This document specifies a **layout-profile** system for the Prediction Market Dashboard that enables users to create, save, load, and optimize panel arrangements. The system provides a seamless experience where users can switch between different workspace configurations (e.g., "US Sports", "Canadian Equities", "Weather in France") with a single click through the Command Palette.

The implementation follows React best practices with a centralized context for state management, TypeScript for type safety, and localStorage for persistence with optional backend sync.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Type Definitions](#type-definitions)
3. [State Management](#state-management)
4. [Panel Registry](#panel-registry)
5. [Dashboard Grid Integration](#dashboard-grid-integration)
6. [Command Palette Integration](#command-palette-integration)
7. [Optimize Button](#optimize-button)
8. [Optimization Algorithm](#optimization-algorithm)
9. [Persistence Layer](#persistence-layer)
10. [Backend API (Optional)](#backend-api-optional)
11. [UI/UX Guidelines](#uiux-guidelines)
12. [Testing Strategy](#testing-strategy)
13. [Implementation Order](#implementation-order)

---

## Architecture Overview

### System Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              FRONTEND                                        │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                        LayoutContext (Provider)                          ││
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐ ││
│  │  │   current   │  │  profiles   │  │  optimise() │  │ addProfile()    │ ││
│  │  │  (layout)   │  │  (saved)    │  │             │  │ deleteProfile() │ ││
│  │  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └────────┬────────┘ ││
│  └─────────┼────────────────┼────────────────┼──────────────────┼──────────┘│
│            │                │                │                  │           │
│    ┌───────▼───────┐  ┌─────▼─────┐  ┌───────▼───────┐  ┌───────▼───────┐  │
│    │ DashboardGrid │  │ Command   │  │ Optimize      │  │ Profile       │  │
│    │ (panel layout)│  │ Palette   │  │ Button        │  │ Selector      │  │
│    └───────┬───────┘  └───────────┘  └───────────────┘  └───────────────┘  │
│            │                                                                 │
│    ┌───────▼───────┐                                                        │
│    │ PanelRegistry │ ──> Resolves panel type string to React component     │
│    └───────────────┘                                                        │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                     Persistence Layer                                    ││
│  │   ┌─────────────────┐      ┌─────────────────────────────────────────┐  ││
│  │   │  localStorage   │ ◄──► │  Optional: Backend API (/layout/)       │  ││
│  │   └─────────────────┘      └─────────────────────────────────────────┘  ││
│  └─────────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | File Path | Responsibility |
|-----------|-----------|----------------|
| **LayoutContext** | `frontend/src/context/LayoutContext.tsx` | Central state for current layout and saved profiles |
| **Types** | `frontend/src/types/layout.ts` | TypeScript interfaces for panels and profiles |
| **PanelRegistry** | `frontend/src/components/panels/PanelRegistry.tsx` | Maps panel type strings to React components |
| **DashboardGrid** | `frontend/src/components/dashboard/DashboardGrid.tsx` | Renders panels using react-grid-layout |
| **CommandPalette** | `frontend/src/components/dashboard/CommandPalette.tsx` | UI for listing/creating/loading profiles |
| **OptimizeButton** | `frontend/src/components/dashboard/OptimizeButton.tsx` | Triggers layout optimization |
| **Persistence** | `frontend/src/api/layout.ts` | localStorage + optional backend sync |

---

## Type Definitions

### File: `frontend/src/types/layout.ts`

```typescript
/**
 * Unique identifier for a panel instance.
 * Format: "{panelType}-{uuid}" e.g. "NewsFeedPanel-a1b2c3"
 */
export type PanelId = string;

/**
 * Configuration for a single panel in the layout.
 * Stores position, size, and constraints.
 */
export interface PanelConfig {
  /** Unique identifier for this panel instance */
  id: PanelId;
  
  /** Component type name (must match PanelRegistry key) */
  type: PanelType;
  
  /** Grid column position (0-based, left edge) */
  x: number;
  
  /** Grid row position (0-based, top edge) */
  y: number;
  
  /** Width in grid units */
  w: number;
  
  /** Height in grid units */
  h: number;
  
  /** Minimum width constraint (optional) */
  minW?: number;
  
  /** Minimum height constraint (optional) */
  minH?: number;
  
  /** Maximum width constraint (optional) */
  maxW?: number;
  
  /** Maximum height constraint (optional) */
  maxH?: number;
  
  /** Panel-specific data/settings (passed to component) */
  data?: Record<string, unknown>;
}

/**
 * Supported panel types.
 * Add new panel types here as the system expands.
 */
export type PanelType =
  | "NewsFeedPanel"
  | "MarketAggregatorPanel"
  | "AgentStatusPanel"
  | "ChartPanel"
  | "WatchlistPanel";

/**
 * Default size constraints for each panel type.
 * Used by the optimizer to determine optimal sizes.
 */
export const PANEL_DEFAULTS: Record<PanelType, { w: number; h: number; minW: number; minH: number }> = {
  NewsFeedPanel: { w: 4, h: 6, minW: 3, minH: 4 },
  MarketAggregatorPanel: { w: 6, h: 8, minW: 4, minH: 5 },
  AgentStatusPanel: { w: 3, h: 4, minW: 2, minH: 3 },
  ChartPanel: { w: 6, h: 5, minW: 4, minH: 3 },
  WatchlistPanel: { w: 3, h: 6, minW: 2, minH: 4 },
};

/**
 * A saved layout profile containing all panel configurations.
 */
export interface LayoutProfile {
  /** Human-readable profile name (unique) */
  name: string;
  
  /** Optional description for this profile */
  description?: string;
  
  /** All panels in this profile */
  panels: PanelConfig[];
  
  /** ISO timestamp when profile was created */
  createdAt: string;
  
  /** ISO timestamp when profile was last modified */
  updatedAt: string;
  
  /** Optional tags for categorization */
  tags?: string[];
}

/**
 * State shape for the LayoutContext.
 */
export interface LayoutState {
  /** Currently active layout profile */
  current: LayoutProfile;
  
  /** All saved layout profiles */
  profiles: LayoutProfile[];
  
  /** Whether profiles are being loaded */
  isLoading: boolean;
  
  /** Any error that occurred during profile operations */
  error: string | null;
}

/**
 * Actions available through the LayoutContext.
 */
export interface LayoutActions {
  /** Set the current active profile */
  setCurrent: (profile: LayoutProfile) => void;
  
  /** Update a single panel in the current profile */
  updatePanel: (panelId: PanelId, updates: Partial<PanelConfig>) => void;
  
  /** Add a new panel to the current profile */
  addPanel: (panel: PanelConfig) => void;
  
  /** Remove a panel from the current profile */
  removePanel: (panelId: PanelId) => void;
  
  /** Save current layout as a new profile */
  saveAsProfile: (name: string, description?: string) => void;
  
  /** Update an existing profile */
  updateProfile: (name: string, updates: Partial<LayoutProfile>) => void;
  
  /** Delete a saved profile */
  deleteProfile: (name: string) => void;
  
  /** Run the layout optimizer */
  optimise: () => void;
  
  /** Reset to default layout */
  resetToDefault: () => void;
}
```

---

## State Management

### File: `frontend/src/context/LayoutContext.tsx`

```typescript
import React, { createContext, useContext, useReducer, useEffect, useCallback } from "react";
import type {
  LayoutProfile,
  LayoutState,
  LayoutActions,
  PanelConfig,
  PanelId,
  PANEL_DEFAULTS,
} from "../types/layout";
import { v4 as uuid } from "uuid";

// ============================================================================
// Default Profile
// ============================================================================

const DEFAULT_PROFILE: LayoutProfile = {
  name: "Default",
  description: "Default dashboard layout",
  panels: [
    {
      id: `NewsFeedPanel-${uuid()}`,
      type: "NewsFeedPanel",
      x: 0,
      y: 0,
      w: 4,
      h: 6,
      minW: 3,
      minH: 4,
      data: { query: "stock" },
    },
    {
      id: `MarketAggregatorPanel-${uuid()}`,
      type: "MarketAggregatorPanel",
      x: 4,
      y: 0,
      w: 8,
      h: 8,
      minW: 4,
      minH: 5,
    },
  ],
  createdAt: new Date().toISOString(),
  updatedAt: new Date().toISOString(),
  tags: ["default"],
};

// ============================================================================
// Reducer
// ============================================================================

type Action =
  | { type: "SET_CURRENT"; payload: LayoutProfile }
  | { type: "SET_PROFILES"; payload: LayoutProfile[] }
  | { type: "ADD_PROFILE"; payload: LayoutProfile }
  | { type: "UPDATE_PROFILE"; payload: { name: string; updates: Partial<LayoutProfile> } }
  | { type: "DELETE_PROFILE"; payload: string }
  | { type: "UPDATE_PANEL"; payload: { panelId: PanelId; updates: Partial<PanelConfig> } }
  | { type: "ADD_PANEL"; payload: PanelConfig }
  | { type: "REMOVE_PANEL"; payload: PanelId }
  | { type: "SET_LOADING"; payload: boolean }
  | { type: "SET_ERROR"; payload: string | null };

function layoutReducer(state: LayoutState, action: Action): LayoutState {
  switch (action.type) {
    case "SET_CURRENT":
      return { ...state, current: action.payload };

    case "SET_PROFILES":
      return { ...state, profiles: action.payload };

    case "ADD_PROFILE":
      return {
        ...state,
        profiles: [...state.profiles, action.payload],
        current: action.payload,
      };

    case "UPDATE_PROFILE": {
      const { name, updates } = action.payload;
      const updatedProfiles = state.profiles.map((p) =>
        p.name === name ? { ...p, ...updates, updatedAt: new Date().toISOString() } : p
      );
      const updatedCurrent =
        state.current.name === name
          ? { ...state.current, ...updates, updatedAt: new Date().toISOString() }
          : state.current;
      return { ...state, profiles: updatedProfiles, current: updatedCurrent };
    }

    case "DELETE_PROFILE": {
      const filtered = state.profiles.filter((p) => p.name !== action.payload);
      const newCurrent =
        state.current.name === action.payload
          ? filtered[0] ?? DEFAULT_PROFILE
          : state.current;
      return { ...state, profiles: filtered, current: newCurrent };
    }

    case "UPDATE_PANEL": {
      const { panelId, updates } = action.payload;
      const updatedPanels = state.current.panels.map((p) =>
        p.id === panelId ? { ...p, ...updates } : p
      );
      return {
        ...state,
        current: {
          ...state.current,
          panels: updatedPanels,
          updatedAt: new Date().toISOString(),
        },
      };
    }

    case "ADD_PANEL":
      return {
        ...state,
        current: {
          ...state.current,
          panels: [...state.current.panels, action.payload],
          updatedAt: new Date().toISOString(),
        },
      };

    case "REMOVE_PANEL":
      return {
        ...state,
        current: {
          ...state.current,
          panels: state.current.panels.filter((p) => p.id !== action.payload),
          updatedAt: new Date().toISOString(),
        },
      };

    case "SET_LOADING":
      return { ...state, isLoading: action.payload };

    case "SET_ERROR":
      return { ...state, error: action.payload };

    default:
      return state;
  }
}

// ============================================================================
// Context
// ============================================================================

const LayoutContext = createContext<(LayoutState & LayoutActions) | undefined>(undefined);

const STORAGE_KEY = "layout_profiles";
const CURRENT_KEY = "layout_current";

export const LayoutProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [state, dispatch] = useReducer(layoutReducer, {
    current: DEFAULT_PROFILE,
    profiles: [DEFAULT_PROFILE],
    isLoading: true,
    error: null,
  });

  // ---- Load from localStorage on mount ----
  useEffect(() => {
    try {
      const storedProfiles = localStorage.getItem(STORAGE_KEY);
      const storedCurrent = localStorage.getItem(CURRENT_KEY);

      if (storedProfiles) {
        const profiles = JSON.parse(storedProfiles) as LayoutProfile[];
        dispatch({ type: "SET_PROFILES", payload: profiles });

        if (storedCurrent) {
          const currentName = JSON.parse(storedCurrent) as string;
          const found = profiles.find((p) => p.name === currentName);
          if (found) {
            dispatch({ type: "SET_CURRENT", payload: found });
          }
        }
      }
    } catch (err) {
      console.error("Failed to load layout profiles:", err);
      dispatch({ type: "SET_ERROR", payload: "Failed to load saved layouts" });
    } finally {
      dispatch({ type: "SET_LOADING", payload: false });
    }
  }, []);

  // ---- Persist to localStorage on change ----
  useEffect(() => {
    if (!state.isLoading) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state.profiles));
      localStorage.setItem(CURRENT_KEY, JSON.stringify(state.current.name));
    }
  }, [state.profiles, state.current.name, state.isLoading]);

  // ---- Actions ----
  const setCurrent = useCallback((profile: LayoutProfile) => {
    dispatch({ type: "SET_CURRENT", payload: profile });
  }, []);

  const updatePanel = useCallback((panelId: PanelId, updates: Partial<PanelConfig>) => {
    dispatch({ type: "UPDATE_PANEL", payload: { panelId, updates } });
  }, []);

  const addPanel = useCallback((panel: PanelConfig) => {
    dispatch({ type: "ADD_PANEL", payload: panel });
  }, []);

  const removePanel = useCallback((panelId: PanelId) => {
    dispatch({ type: "REMOVE_PANEL", payload: panelId });
  }, []);

  const saveAsProfile = useCallback(
    (name: string, description?: string) => {
      const newProfile: LayoutProfile = {
        ...state.current,
        name,
        description,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      };
      dispatch({ type: "ADD_PROFILE", payload: newProfile });
    },
    [state.current]
  );

  const updateProfile = useCallback((name: string, updates: Partial<LayoutProfile>) => {
    dispatch({ type: "UPDATE_PROFILE", payload: { name, updates } });
  }, []);

  const deleteProfile = useCallback((name: string) => {
    dispatch({ type: "DELETE_PROFILE", payload: name });
  }, []);

  const optimise = useCallback(() => {
    // See "Optimization Algorithm" section for full implementation
    const GRID_COLS = 12;
    const panels = [...state.current.panels];

    // Sort panels by type priority (larger panels first)
    panels.sort((a, b) => {
      const aArea = (PANEL_DEFAULTS[a.type]?.w ?? 4) * (PANEL_DEFAULTS[a.type]?.h ?? 4);
      const bArea = (PANEL_DEFAULTS[b.type]?.w ?? 4) * (PANEL_DEFAULTS[b.type]?.h ?? 4);
      return bArea - aArea;
    });

    // Place panels in a grid, row by row
    let currentRow = 0;
    let currentCol = 0;
    const optimized: PanelConfig[] = [];

    for (const panel of panels) {
      const defaults = PANEL_DEFAULTS[panel.type] ?? { w: 4, h: 4, minW: 2, minH: 2 };
      const w = Math.min(defaults.w, GRID_COLS);
      const h = defaults.h;

      // Check if panel fits in current row
      if (currentCol + w > GRID_COLS) {
        // Move to next row
        currentCol = 0;
        currentRow += Math.max(...optimized.filter((p) => p.y === currentRow).map((p) => p.h), 1);
      }

      optimized.push({
        ...panel,
        x: currentCol,
        y: currentRow,
        w,
        h,
        minW: defaults.minW,
        minH: defaults.minH,
      });

      currentCol += w;
    }

    dispatch({
      type: "SET_CURRENT",
      payload: {
        ...state.current,
        panels: optimized,
        updatedAt: new Date().toISOString(),
      },
    });
  }, [state.current]);

  const resetToDefault = useCallback(() => {
    dispatch({ type: "SET_CURRENT", payload: DEFAULT_PROFILE });
  }, []);

  const value: LayoutState & LayoutActions = {
    ...state,
    setCurrent,
    updatePanel,
    addPanel,
    removePanel,
    saveAsProfile,
    updateProfile,
    deleteProfile,
    optimise,
    resetToDefault,
  };

  return <LayoutContext.Provider value={value}>{children}</LayoutContext.Provider>;
};

export const useLayout = (): LayoutState & LayoutActions => {
  const ctx = useContext(LayoutContext);
  if (!ctx) {
    throw new Error("useLayout must be used within a LayoutProvider");
  }
  return ctx;
};
```

---

## Panel Registry

### File: `frontend/src/components/panels/PanelRegistry.tsx`

```typescript
import React from "react";
import type { PanelType, PanelConfig } from "../../types/layout";
import { NewsFeedPanel } from "./NewsFeedPanel";
import { MarketAggregatorPanel } from "./MarketAggregatorPanel";
// Import other panels as they are created

interface PanelRegistryProps {
  config: PanelConfig;
}

/**
 * Resolves a panel type string to its React component.
 * All panels receive their full config as props.
 */
export const PanelRegistry: React.FC<PanelRegistryProps> = ({ config }) => {
  switch (config.type) {
    case "NewsFeedPanel":
      return <NewsFeedPanel panel={config} />;
    case "MarketAggregatorPanel":
      return <MarketAggregatorPanel panel={config} />;
    // Add new panels here:
    // case "ChartPanel":
    //   return <ChartPanel panel={config} />;
    default:
      return (
        <div className="flex items-center justify-center h-full bg-red-900/20 text-red-400">
          Unknown panel type: {config.type}
        </div>
      );
  }
};

/**
 * Get metadata about a panel type.
 */
export const getPanelMeta = (type: PanelType): { label: string; icon: string } => {
  const meta: Record<PanelType, { label: string; icon: string }> = {
    NewsFeedPanel: { label: "News Feed", icon: "📰" },
    MarketAggregatorPanel: { label: "Markets", icon: "📈" },
    AgentStatusPanel: { label: "Agents", icon: "🤖" },
    ChartPanel: { label: "Chart", icon: "📊" },
    WatchlistPanel: { label: "Watchlist", icon: "👁️" },
  };
  return meta[type] ?? { label: type, icon: "❓" };
};
```

---

## Dashboard Grid Integration

### File: `frontend/src/components/dashboard/DashboardGrid.tsx`

```typescript
import React, { useCallback } from "react";
import GridLayout, { Layout } from "react-grid-layout";
import { useLayout } from "../../context/LayoutContext";
import { PanelRegistry } from "../panels/PanelRegistry";
import { PanelWrapper } from "../panels/PanelWrapper";
import "react-grid-layout/css/styles.css";
import "react-resizable/css/styles.css";

const GRID_COLS = 12;
const ROW_HEIGHT = 60;

export const DashboardGrid: React.FC = () => {
  const { current, updatePanel, removePanel } = useLayout();

  // Convert PanelConfig[] -> react-grid-layout Layout[]
  const layout: Layout[] = current.panels.map((panel) => ({
    i: panel.id,
    x: panel.x,
    y: panel.y,
    w: panel.w,
    h: panel.h,
    minW: panel.minW ?? 2,
    minH: panel.minH ?? 2,
    maxW: panel.maxW,
    maxH: panel.maxH,
  }));

  // Sync grid changes back to context
  const handleLayoutChange = useCallback(
    (newLayout: Layout[]) => {
      for (const item of newLayout) {
        const existing = current.panels.find((p) => p.id === item.i);
        if (
          existing &&
          (existing.x !== item.x ||
            existing.y !== item.y ||
            existing.w !== item.w ||
            existing.h !== item.h)
        ) {
          updatePanel(item.i, {
            x: item.x,
            y: item.y,
            w: item.w,
            h: item.h,
          });
        }
      }
    },
    [current.panels, updatePanel]
  );

  return (
    <div className="flex-1 overflow-auto bg-background p-4">
      <GridLayout
        className="layout"
        layout={layout}
        cols={GRID_COLS}
        rowHeight={ROW_HEIGHT}
        width={1400}
        onLayoutChange={handleLayoutChange}
        draggableHandle=".panel-drag-handle"
        compactType="vertical"
        preventCollision={false}
        margin={[16, 16]}
      >
        {current.panels.map((panel) => (
          <div key={panel.id} className="panel-grid-item">
            <PanelWrapper
              panelId={panel.id}
              panelType={panel.type}
              onClose={() => removePanel(panel.id)}
            >
              <PanelRegistry config={panel} />
            </PanelWrapper>
          </div>
        ))}
      </GridLayout>
    </div>
  );
};
```

---

## Command Palette Integration

### File: `frontend/src/components/dashboard/CommandPalette.tsx` (additions)

Add a "Layouts" section to the existing Command Palette:

```typescript
// Add to existing CommandPalette.tsx

import { useLayout } from "../../context/LayoutContext";
import { getPanelMeta } from "../panels/PanelRegistry";
import type { PanelType } from "../../types/layout";

// Inside the CommandPalette component:
const {
  current,
  profiles,
  setCurrent,
  saveAsProfile,
  deleteProfile,
  optimise,
  addPanel,
} = useLayout();

// Add this section to the palette UI:
<section className="palette-section border-t border-border pt-4 mt-4">
  <h3 className="text-xs font-semibold text-muted-foreground uppercase mb-2">
    Layout Profiles
  </h3>
  
  {/* Current Profile Indicator */}
  <div className="text-sm text-muted-foreground mb-2">
    Current: <span className="text-foreground font-medium">{current.name}</span>
  </div>
  
  {/* Profile List */}
  <ul className="space-y-1 mb-3">
    {profiles.map((profile) => (
      <li
        key={profile.name}
        className={`flex items-center justify-between px-2 py-1.5 rounded cursor-pointer
          ${profile.name === current.name ? "bg-primary/10" : "hover:bg-muted"}`}
      >
        <button
          className="flex-1 text-left text-sm"
          onClick={() => setCurrent(profile)}
        >
          {profile.name}
          {profile.description && (
            <span className="text-xs text-muted-foreground ml-2">
              – {profile.description}
            </span>
          )}
        </button>
        {profile.name !== "Default" && (
          <button
            className="text-destructive hover:text-destructive/80 p-1"
            onClick={(e) => {
              e.stopPropagation();
              if (confirm(`Delete layout "${profile.name}"?`)) {
                deleteProfile(profile.name);
              }
            }}
            title="Delete layout"
          >
            ✕
          </button>
        )}
      </li>
    ))}
  </ul>
  
  {/* Actions */}
  <div className="flex gap-2">
    <button
      className="btn btn-sm btn-secondary flex-1"
      onClick={() => {
        const name = prompt("Enter a name for this layout:");
        if (name?.trim()) {
          saveAsProfile(name.trim());
        }
      }}
    >
      💾 Save Current
    </button>
    <button
      className="btn btn-sm btn-primary flex-1"
      onClick={optimise}
    >
      ✨ Optimise
    </button>
  </div>
</section>

{/* Add Panel Section */}
<section className="palette-section border-t border-border pt-4 mt-4">
  <h3 className="text-xs font-semibold text-muted-foreground uppercase mb-2">
    Add Panel
  </h3>
  <div className="grid grid-cols-2 gap-2">
    {(["NewsFeedPanel", "MarketAggregatorPanel", "ChartPanel", "WatchlistPanel"] as PanelType[]).map(
      (type) => {
        const meta = getPanelMeta(type);
        return (
          <button
            key={type}
            className="btn btn-sm btn-outline text-left"
            onClick={() => {
              addPanel({
                id: `${type}-${crypto.randomUUID()}`,
                type,
                x: 0,
                y: 0,
                w: 4,
                h: 4,
              });
            }}
          >
            {meta.icon} {meta.label}
          </button>
        );
      }
    )}
  </div>
</section>
```

---

## Optimize Button

### File: `frontend/src/components/dashboard/OptimizeButton.tsx`

```typescript
import React from "react";
import { useLayout } from "../../context/LayoutContext";

export const OptimizeButton: React.FC = () => {
  const { optimise } = useLayout();

  return (
    <button
      onClick={optimise}
      className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium
                 bg-primary/10 hover:bg-primary/20 text-primary
                 rounded-md transition-colors"
      title="Automatically arrange panels for optimal space usage"
    >
      <span className="text-base">✨</span>
      Optimise Layout
    </button>
  );
};
```

### Placement in Dashboard Header

```typescript
// File: frontend/src/components/dashboard/DashboardHeader.tsx

import { OptimizeButton } from "./OptimizeButton";

export const DashboardHeader: React.FC = () => {
  return (
    <header className="flex items-center justify-between h-12 px-4 border-b border-border bg-card">
      <div className="flex items-center gap-4">
        <h1 className="font-semibold">Dashboard</h1>
        {/* Other tabs */}
      </div>
      
      <div className="flex items-center gap-2">
        <AgentsTab />
        <OptimizeButton /> {/* Positioned below/beside agents tab */}
      </div>
    </header>
  );
};
```

---

## Optimization Algorithm

The optimizer uses a **bin-packing** approach to arrange panels efficiently:

```typescript
/**
 * Optimization algorithm for panel arrangement.
 * 
 * Strategy:
 * 1. Sort panels by area (largest first) for better packing
 * 2. Apply default sizes based on panel type
 * 3. Place panels row-by-row, left-to-right
 * 4. Minimize vertical space usage
 * 
 * Future enhancements:
 * - Consider panel "importance" or user-defined priority
 * - Group related panels together
 * - Support multiple layout strategies (vertical, horizontal, grid)
 */
function optimiseLayout(panels: PanelConfig[]): PanelConfig[] {
  const GRID_COLS = 12;
  const sorted = [...panels].sort((a, b) => {
    const aDefaults = PANEL_DEFAULTS[a.type];
    const bDefaults = PANEL_DEFAULTS[b.type];
    const aArea = (aDefaults?.w ?? 4) * (aDefaults?.h ?? 4);
    const bArea = (bDefaults?.w ?? 4) * (bDefaults?.h ?? 4);
    return bArea - aArea; // Largest first
  });

  const result: PanelConfig[] = [];
  const rowHeights: Map<number, number> = new Map(); // row index -> max height in that row

  let currentRow = 0;
  let currentCol = 0;

  for (const panel of sorted) {
    const defaults = PANEL_DEFAULTS[panel.type] ?? { w: 4, h: 4, minW: 2, minH: 2 };
    const w = Math.min(defaults.w, GRID_COLS);
    const h = defaults.h;

    // Check if panel fits in current row
    if (currentCol + w > GRID_COLS) {
      // Move to next row
      currentRow += rowHeights.get(currentRow) ?? 1;
      currentCol = 0;
    }

    // Track max height for this row
    const existingHeight = rowHeights.get(currentRow) ?? 0;
    rowHeights.set(currentRow, Math.max(existingHeight, h));

    result.push({
      ...panel,
      x: currentCol,
      y: currentRow,
      w,
      h,
      minW: defaults.minW,
      minH: defaults.minH,
    });

    currentCol += w;
  }

  return result;
}
```

---

## Persistence Layer

### File: `frontend/src/api/layout.ts`

```typescript
import type { LayoutProfile } from "../types/layout";

const API_BASE = "/api";

/**
 * Fetch all saved profiles from the backend.
 */
export async function fetchProfiles(): Promise<LayoutProfile[]> {
  const res = await fetch(`${API_BASE}/layout/`);
  if (!res.ok) throw new Error("Failed to fetch profiles");
  return res.json();
}

/**
 * Save a profile to the backend.
 */
export async function saveProfile(profile: LayoutProfile): Promise<LayoutProfile> {
  const res = await fetch(`${API_BASE}/layout/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(profile),
  });
  if (!res.ok) throw new Error("Failed to save profile");
  return res.json();
}

/**
 * Delete a profile from the backend.
 */
export async function deleteProfileAPI(name: string): Promise<void> {
  const res = await fetch(`${API_BASE}/layout/${encodeURIComponent(name)}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error("Failed to delete profile");
}

/**
 * Sync local profiles with backend (upload local, merge remote).
 */
export async function syncProfiles(local: LayoutProfile[]): Promise<LayoutProfile[]> {
  const remote = await fetchProfiles();
  
  // Simple merge: prefer local for conflicts
  const merged = new Map<string, LayoutProfile>();
  for (const p of remote) merged.set(p.name, p);
  for (const p of local) merged.set(p.name, p); // Local overwrites
  
  return Array.from(merged.values());
}
```

---

## Backend API (Optional)

### File: `backend/app/panels/layout.py`

```python
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

router = APIRouter(prefix="/layout", tags=["layout"])

class PanelConfig(BaseModel):
    id: str
    type: str
    x: int
    y: int
    w: int
    h: int
    minW: Optional[int] = None
    minH: Optional[int] = None
    maxW: Optional[int] = None
    maxH: Optional[int] = None
    data: Optional[dict] = None

class LayoutProfile(BaseModel):
    name: str
    description: Optional[str] = None
    panels: List[PanelConfig]
    createdAt: str
    updatedAt: str
    tags: Optional[List[str]] = None

# In-memory store (replace with database)
_profiles: dict[str, LayoutProfile] = {}

@router.get("/", response_model=List[LayoutProfile])
def list_profiles():
    """List all saved layout profiles."""
    return list(_profiles.values())

@router.post("/", response_model=LayoutProfile)
def save_profile(profile: LayoutProfile):
    """Create or update a layout profile."""
    profile.updatedAt = datetime.utcnow().isoformat() + "Z"
    _profiles[profile.name] = profile
    return profile

@router.get("/{name}", response_model=LayoutProfile)
def get_profile(name: str):
    """Get a specific profile by name."""
    if name not in _profiles:
        raise HTTPException(status_code=404, detail="Profile not found")
    return _profiles[name]

@router.delete("/{name}")
def delete_profile(name: str):
    """Delete a layout profile."""
    if name not in _profiles:
        raise HTTPException(status_code=404, detail="Profile not found")
    del _profiles[name]
    return {"ok": True, "deleted": name}
```

### Register in Main App

```python
# File: backend/app/main.py

from .panels.layout import router as layout_router

# In the app setup:
app.include_router(layout_router)
```

---

## UI/UX Guidelines

| Element | Styling |
|---------|---------|
| **Profile List Item** | Hover state: `bg-muted`, Active: `bg-primary/10` |
| **Delete Button** | Red (`text-destructive`), only show on hover |
| **Optimize Button** | Primary color accent, subtle icon (✨) |
| **Panel Drag Handle** | Visible at top of each panel, cursor: grab |
| **Save Confirmation** | Use prompt() for MVP, upgrade to modal later |
| **Loading State** | Skeleton loaders for grid during profile switch |

---

## Testing Strategy

### Unit Tests

1. **LayoutContext reducer** - All action types produce correct state
2. **optimiseLayout** - Panels don't overlap, respect grid bounds
3. **PanelRegistry** - All types resolve to components

### Integration Tests

1. Create profile → appears in list
2. Switch profile → grid updates
3. Drag panel → position persists after refresh
4. Delete profile → removed from list

### E2E Tests (Playwright)

```typescript
test("can create and load a layout profile", async ({ page }) => {
  // Open dashboard
  await page.goto("/");
  
  // Open command palette
  await page.keyboard.press("Control+K");
  
  // Click save button
  await page.click("text=Save Current");
  
  // Enter name in prompt
  await page.fill('input[type="text"]', "Test Layout");
  await page.press("Enter");
  
  // Verify profile appears
  await expect(page.locator("text=Test Layout")).toBeVisible();
});
```

---

## Implementation Order

1. **Create type definitions** (`frontend/src/types/layout.ts`)
2. **Create LayoutContext** (`frontend/src/context/LayoutContext.tsx`)
3. **Wrap app in LayoutProvider** (`frontend/src/main.tsx`)
4. **Update DashboardGrid** to use context
5. **Update PanelRegistry** to accept config prop
6. **Add layout section to CommandPalette**
7. **Create OptimizeButton** and add to header
8. **Test locally** with multiple profiles
9. **(Optional)** Add backend endpoints
10. **(Optional)** Add sync logic

---

## Summary

This specification provides everything needed to implement a complete layout-profile system:

- **~300 lines** of context code
- **~100 lines** of type definitions
- **~150 lines** of grid integration
- **~100 lines** of Command Palette additions
- **~50 lines** of backend API

Total effort: **4-6 hours** for a senior developer, including testing.

The result is a production-ready layout system that lets users save, load, and optimize their workspace with full persistence and type safety.
