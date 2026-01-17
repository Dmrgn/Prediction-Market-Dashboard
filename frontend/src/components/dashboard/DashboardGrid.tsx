import { Responsive, WidthProvider } from "react-grid-layout";
import "react-grid-layout/css/styles.css";
import "react-resizable/css/styles.css";
import { PanelRegistry } from "@/components/panels/PanelRegistry";
import { useWorkspaceStore, type PanelInstance } from "@/hooks/useWorkspaceStore";

type GridLayoutItem = {
  i: string;
  x: number;
  y: number;
  w: number;
  h: number;
};

type GridLayout = ReadonlyArray<GridLayoutItem>;

const ResponsiveGridLayout = WidthProvider(Responsive);

export function DashboardGrid() {
  const panels = useWorkspaceStore((state: { panels: PanelInstance[] }) => state.panels);
  const updateLayout = useWorkspaceStore(
    (state: { updateLayout: (id: string, layout: Pick<PanelInstance, "x" | "y" | "w" | "h">) => void }) =>
      state.updateLayout
  );

  const layout: GridLayoutItem[] = panels
    .filter((panel: PanelInstance) => panel.isVisible)
    .map((panel: PanelInstance) => ({
      i: panel.id,
      x: panel.x,
      y: panel.y,
      w: panel.w,
      h: panel.h,
    }));

  return (
    <div className="h-full w-full">
      <ResponsiveGridLayout
        className="layout"
        autoSize
        layouts={{ lg: layout }}
        breakpoints={{ lg: 1200, md: 996, sm: 768, xs: 480, xxs: 0 }}
        cols={{ lg: 12, md: 10, sm: 6, xs: 4, xxs: 2 }}
        rowHeight={60}
        margin={[16, 16]}
        draggableHandle=".panel-drag-handle"
        draggableCancel=".panel-content"
        onLayoutChange={(currentLayout: GridLayout, _allLayouts: Partial<Record<string, GridLayout>>) => {
          currentLayout.forEach((item: GridLayoutItem) => {
            updateLayout(item.i, { x: item.x, y: item.y, w: item.w, h: item.h });
          });
        }}
      >
        {panels
          .filter((panel: PanelInstance) => panel.isVisible)
          .map((panel: PanelInstance) => (
            <div key={panel.id} data-grid={{ x: panel.x, y: panel.y, w: panel.w, h: panel.h }}>
              <PanelRegistry panel={panel} />
            </div>
          ))}
      </ResponsiveGridLayout>
    </div>
  );
}
