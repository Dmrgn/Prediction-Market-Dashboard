import type { PanelInstance } from "@/hooks/useWorkspaceStore";
import { ChartPanel } from "@/components/panels/ChartPanel";
import { OrderBookPanel } from "@/components/panels/OrderBookPanel";
import { NewsFeedPanel } from "@/components/panels/NewsFeedPanel";
import { PanelWrapper } from "@/components/panels/PanelWrapper";

// Import to register panel actions (side-effect import)
import "@/components/panels/panelActionRegistrations";

interface PanelRegistryProps {
  panel: PanelInstance;
}

export function PanelRegistry({ panel }: PanelRegistryProps) {
  switch (panel.type) {
    case "CHART":
    case "MARKET_AGGREGATOR_GRAPH": // Backward compatibility
      return (
        <PanelWrapper panel={panel}>
          <ChartPanel panel={panel} />
        </PanelWrapper>
      );
    case "ORDER_BOOK":
      return (
        <PanelWrapper panel={panel}>
          <OrderBookPanel panel={panel} />
        </PanelWrapper>
      );
    case "NEWS_FEED":
      return (
        <PanelWrapper panel={panel}>
          <NewsFeedPanel panel={panel} />
        </PanelWrapper>
      );
    default:
      return (
        <div className="h-full rounded-xl border border-dashed border-border bg-muted/40 p-4 text-sm text-muted-foreground">
          Unknown panel type: {panel.type}
        </div>
      );
  }
}
