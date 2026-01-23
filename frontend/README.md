# OddsBase Frontend

This is the React-based frontend for the OddsBase Prediction Market Dashboard. It features a highly customizable layout, real-time data visualizations, and an integrated AI command palette.

## Highlights

- **Dynamic Command Palette**: Access all features via `⌘/Ctrl + Shift + P`. Execute agent-powered commands and track activity logs in real-time.
- **Intelligent Sidebar**: A collapsible agent interface that automatically expands when AI activities are triggered, keeping the focus on your analysis.
- **Customizable Dashboards**: Drag-and-drop panel grid (using `react-grid-layout`) allows you to build the perfect market terminal.
- **Market Aggregator**: Unified views for Polymarket and Kalshi, including one-click copying of market IDs for quick sharing or command execution.

## Development

This project uses **Bun** for fast dependency management and development.

### Setup

```bash
# Install dependencies
bun install
```

### Running Locally

```bash
# Start the development server
bun dev
```

The application will be available at `http://localhost:3000`.

### Production Build

```bash
# Build the production bundle
bun run build

# Start the production server
bun start
```

## Stack

- **React 19**: Latest React features for a modern UI.
- **Tailwind CSS 4**: High-performance, low-runtime styling.
- **Zustand**: Fast and scalable state management with persistence.
- **Recharts**: Responsive chart components for market data.
- **cmdk**: Powering the accessible and extensible command palette.
