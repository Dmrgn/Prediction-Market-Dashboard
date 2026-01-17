import { useWorkspaceStore, type PanelInstance } from "@/hooks/useWorkspaceStore";
import { useAgentStore } from "@/hooks/useAgentStore";

export function AgentStatus() {
  const panels = useWorkspaceStore((state: { panels: PanelInstance[] }) => state.panels);
  const events = useAgentStore((state) => state.events);

  return (
    <div className="px-4">
      <div className="text-xs uppercase tracking-wide text-muted-foreground">Agent Activity</div>
      <div className="mt-3 space-y-2">
        {events.length === 0 && (
          <div className="text-muted-foreground">No recent agent activity.</div>
        )}
        {events.map((event) => (
          <div key={event.id} className="rounded-lg bg-muted px-3 py-2 text-xs">
            {event.message}
          </div>
        ))}
      </div>
      <div className="mt-4 text-xs text-muted-foreground">
        Active panels: {panels.filter((panel: PanelInstance) => panel.isVisible).length}
      </div>
    </div>
  );
}
