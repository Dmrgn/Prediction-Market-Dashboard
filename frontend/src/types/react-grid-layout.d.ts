import type { ComponentType } from "react";

declare module "react-grid-layout" {
  export function WidthProvider<P>(
    component: ComponentType<P>
  ): ComponentType<Omit<P, "width"> & { width?: number }>;

  export interface ResponsiveGridLayoutProps<T = string> {
    draggableHandle?: string;
    draggableCancel?: string;
  }
}
