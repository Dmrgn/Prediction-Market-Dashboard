import { useEffect, useState } from "react";
import "./index.css";
import { DashboardGrid } from "@/components/dashboard/DashboardGrid";
import { CommandPalette } from "@/components/dashboard/CommandPalette";
import { AgentStatus } from "@/components/dashboard/AgentStatus";
import { ResearcherPanel } from "@/components/dashboard/ResearcherPanel";
import { useUIStore } from "@/hooks/useUIStore";
import { Kbd } from "./components/ui/kbd";

import logo from "../public/Logo.webp";

import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarProvider,
  SidebarTrigger,
  useSidebar,
} from "@/components/ui/sidebar"

function AppContent() {
  const { openCommandPalette, closeCommandPalette, isCommandPaletteOpen } = useUIStore();
  const { open: sidebarOpen } = useSidebar();
  const [sidebarTab, setSidebarTab] = useState<"agent" | "research">("research");

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

  return (
    <>
      <header className="grid grid-cols-3 border-b border-border bg-card px-6 py-4">
        <div>
          <img className="max-h-10" src={logo}></img>
        </div>
        <div className="flex items-center gap-3 w-full justify-center">
          <Kbd>⌘ ⇧ P</Kbd>
          <span>Command Palette</span>
        </div>
        <div className="w-full flex justify-end items-center">
          <SidebarTrigger />
        </div>
      </header>

      <main
        className="flex flex-1 overflow-hidden max-h-[90vh] transition-[margin] duration-200 ease-linear"
        style={{ marginRight: sidebarOpen ? 'var(--sidebar-width)' : '0' }}
      >
        <section className="flex-1 overflow-y-auto p-4">
          <DashboardGrid />
        </section>
      </main>

      <Sidebar side="right" variant="floating">
        <SidebarHeader className="p-2">
          <div className="flex rounded-lg bg-muted p-1">
            <button
              onClick={() => setSidebarTab("research")}
              className={`flex-1 rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${sidebarTab === "research"
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground"
                }`}
            >
              Research
            </button>
            <button
              onClick={() => setSidebarTab("agent")}
              className={`flex-1 rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${sidebarTab === "agent"
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground"
                }`}
            >
              Agent
            </button>
          </div>
        </SidebarHeader>
        <SidebarContent>
          {sidebarTab === "agent" && <AgentStatus />}
          {sidebarTab === "research" && <ResearcherPanel />}
        </SidebarContent>
        <SidebarFooter className="p-2 border-t border-sidebar-border">
          <SidebarTrigger className="w-full justify-center" />
        </SidebarFooter>
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
