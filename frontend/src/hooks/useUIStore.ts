import { create } from "zustand";

interface UIState {
  isCommandPaletteOpen: boolean;
  initialCommandId: string | null;
  initialParams: Record<string, string>;
  isSidebarOpen: boolean;
  openCommandPalette: (commandId?: string, params?: Record<string, string>) => void;
  closeCommandPalette: () => void;
  openSidebar: () => void;
  closeSidebar: () => void;
  setSidebarOpen: (open: boolean) => void;
}

export const useUIStore = create<UIState>((set) => ({
  isCommandPaletteOpen: false,
  initialCommandId: null,
  initialParams: {},
  isSidebarOpen: false,
  openCommandPalette: (commandId, params) =>
    set({
      isCommandPaletteOpen: true,
      initialCommandId: commandId || null,
      initialParams: params || {},
    }),
  closeCommandPalette: () =>
    set({
      isCommandPaletteOpen: false,
      initialCommandId: null,
      initialParams: {},
    }),
  openSidebar: () => set({ isSidebarOpen: true }),
  closeSidebar: () => set({ isSidebarOpen: false }),
  setSidebarOpen: (open) => set({ isSidebarOpen: open }),
}));
