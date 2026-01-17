import { useEffect } from "react";
import "./index.css";
import { DashboardGrid } from "@/components/dashboard/DashboardGrid";
import { CommandPalette } from "@/components/dashboard/CommandPalette";
import { AgentStatus } from "@/components/dashboard/AgentStatus";
import { useWorkspaceStore, type PanelInstance } from "@/hooks/useWorkspaceStore";
import { useUIStore } from "@/hooks/useUIStore";
import { Kbd } from "./components/ui/kbd";

import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarHeader,
  SidebarProvider,
  SidebarTrigger,
  useSidebar,
} from "@/components/ui/sidebar"

function AppContent() {
  const panels = useWorkspaceStore((state: { panels: PanelInstance[] }) => state.panels);
  const openPanel = useWorkspaceStore(
    (state: { openPanel: (type: PanelInstance["type"], data?: Record<string, unknown>) => string }) =>
      state.openPanel
  );

  const { openCommandPalette, closeCommandPalette, isCommandPaletteOpen, isSidebarOpen, setSidebarOpen } = useUIStore();
  const { open } = useSidebar();

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.shiftKey && event.key.toLowerCase() === "p") {
        event.preventDefault();
        if (isCommandPaletteOpen) {
          closeCommandPalette();
        } else {
          openCommandPalette();
        }
      }
    };

    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [openCommandPalette, closeCommandPalette, isCommandPaletteOpen]);

  useEffect(() => {
    if (panels.length === 0) {
      openPanel("MARKET_AGGREGATOR_GRAPH", { marketId: "demo-market" });
      openPanel("NEWS_FEED", { query: "prediction markets" });
    }
  }, [openPanel, panels.length]);

  return (
    <>
      <header
        className="grid grid-cols-3 border-b border-border bg-card px-6 py-4"
      >
        <div>
          <div className="text-sm text-muted-foreground">Prediction Market Dashboard</div>
          <div className="text-xl font-semibold">Workspace</div>
        </div>
        <div className="flex items-center gap-3 w-full justify-center">
          <Kbd>⌘ ⇧ P</Kbd>
          <span>Command Palette</span>
        </div>
        <div className="w-full flex justify-end items-center transition-[padding] duration-200 ease-linear" style={{
          paddingRight: open ? 'calc(var(--sidebar-width) + 0rem)' : '0rem'
        }}>
          <SidebarTrigger />
        </div>
      </header>

      <main className="flex flex-1 overflow-hidden max-h-[90vh]">
        <section className="flex-1 overflow-y-auto p-4">
          <DashboardGrid />
        </section>
      </main>

      <Sidebar side="right" variant="floating">
        <SidebarHeader />
        <SidebarContent>
          <AgentStatus />
        </SidebarContent>
        <SidebarFooter />
      </Sidebar>

      <CommandPalette />
    </>
  );
}

export function App() {
  const { isSidebarOpen, setSidebarOpen } = useUIStore();

  return (
    <SidebarProvider
      defaultOpen={false}
      open={isSidebarOpen}
      onOpenChange={setSidebarOpen}
      className="flex flex-col"
    >
      <AppContent />
    </SidebarProvider>
  );
}

export default App;
