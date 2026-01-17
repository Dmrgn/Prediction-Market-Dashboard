import { GripVertical, MoreHorizontal } from "lucide-react";
import type { ReactNode } from "react";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useWorkspaceStore, type PanelInstance, type PanelType } from "@/hooks/useWorkspaceStore";
import { useUIStore } from "@/hooks/useUIStore";

interface PanelWrapperProps {
  panel: PanelInstance;
  children: ReactNode;
}

const panelCommandMap: Record<PanelType, string> = {
  MARKET_AGGREGATOR_GRAPH: "open-market-aggregator",
  NEWS_FEED: "open-news-feed",
};

const extractPanelParams = (panel: PanelInstance): Record<string, string> => {
  switch (panel.type) {
    case "MARKET_AGGREGATOR_GRAPH":
      return {
        marketId: String(panel.data.marketId ?? ""),
      };
    case "NEWS_FEED":
      return {
        query: String(panel.data.query ?? ""),
      };
    default:
      return {};
  }
};

export function PanelWrapper({ panel, children }: PanelWrapperProps) {
  const closePanel = useWorkspaceStore((state) => state.closePanel);
  const { openCommandPalette } = useUIStore();

  const handleDelete = () => {
    closePanel(panel.id);
  };

  const handleEdit = () => {
    const commandId = panelCommandMap[panel.type];
    const params = extractPanelParams(panel);

    closePanel(panel.id);
    openCommandPalette(commandId, params);
  };

  return (
    <Card className="flex h-full flex-col">
      <CardHeader className="flex flex-row items-center justify-between gap-3">
        <CardTitle>{String(panel.data.title ?? "Untitled Panel")}</CardTitle>
        <div className="flex items-center gap-2">
          <DropdownMenu>
            <DropdownMenuTrigger className="rounded-md p-1 text-muted-foreground hover:bg-muted">
              <MoreHorizontal className="h-4 w-4" />
              <span className="sr-only">Panel actions</span>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={handleEdit}>Edit</DropdownMenuItem>
              <DropdownMenuItem onClick={handleDelete} variant="destructive">
                Delete
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
                    <button
            type="button"
            className="panel-drag-handle rounded-md p-1 text-muted-foreground hover:bg-muted"
            aria-label="Drag panel"
          >
            <GripVertical className="h-4 w-4" />
          </button>
        </div>
      </CardHeader>
      <CardContent className="min-h-0 flex-1 overflow-hidden">
        {children}
      </CardContent>
    </Card>
  );
}
