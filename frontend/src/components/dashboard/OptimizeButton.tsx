import { useLayoutStore } from "@/hooks/useLayoutStore";
import { useWorkspaceStore } from "@/hooks/useWorkspaceStore";

export function OptimizeButton() {
    const optimizeLayout = useLayoutStore((state) => state.optimizeLayout);
    const panels = useWorkspaceStore((state) => state.panels);
    const updateLayout = useWorkspaceStore((state) => state.updateLayout);

    const handleOptimize = () => {
        const optimizedPanels = optimizeLayout(panels);

        // Apply optimized layout
        optimizedPanels.forEach((panel) => {
            updateLayout(panel.id, {
                x: panel.x,
                y: panel.y,
                w: panel.w,
                h: panel.h,
            });
        });
    };

    return (
        <button
            onClick={handleOptimize}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium
                 bg-primary/10 hover:bg-primary/20 text-primary
                 rounded-md transition-colors"
            title="Automatically arrange panels for optimal space usage"
        >
            <span className="text-base">✨</span>
            Optimize
        </button>
    );
}
