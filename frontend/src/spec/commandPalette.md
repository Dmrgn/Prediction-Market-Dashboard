# Command Palette System Overview

This document describes how the command system and command palette workflow operate in the Prediction Market Dashboard.

## 1. Command Registry (Layer 2)
Commands are registered in `frontend/src/commands/registry.ts` and define:
- **`id`**: Unique command identifier.
- **`label` / `description`**: UI copy shown in the palette list and preview.
- **`params`**: Parameter definitions used to render the right-side form.
- **`handler`**: Executes command logic (typically opens panels or runs the agent loop).

### Param Types
`CommandParamSchema.type` controls input behavior:
- **`text`**: Standard text input.
- **`select`**: Reusable sub-palette that lists predefined options.
- **`market`**: Sub-palette with debounced market search via the backend API.

## 2. Command Palette Workflow
The command palette UI is implemented in `frontend/src/components/dashboard/CommandPalette.tsx`.

### 2.1 Focus Modes
The palette maintains a simple focus state machine:
- **`list`**: Focus is on the main search input, allowing cmdk list navigation.
- **`param`**: Focus is in the parameter form on the right.
- **`run`**: Focus is on the Run Command button.

### 2.2 Navigation
- **Enter (List)** → jumps to first param or Run.
- **Enter (Param)** → moves to next param or Run.
- **Enter (Run)** → executes the command.
- **Escape (Param/Run)** → moves backward to previous param or list.

## 3. Sub-Palette Workflow (Reusable)
The sub-palette is a reusable overlay for non-text params. It opens automatically when a param with `type: "market"` or `type: "select"` is focused.

### 3.1 Market Search Sub-Palette
- Opens when a `market` param gains focus.
- Shows a focused search input.
- Debounces calls to `backendInterface.fetchMarkets(query)`.
- Displays matches (title + source + shortened id).
- Selecting a result fills the param with `market_id` and returns focus to the next param/Run button.

### 3.2 Select Sub-Palette
- Opens when a `select` param gains focus.
- Filters static options based on local search input.
- Selecting a value fills the param and returns focus to the next param/Run button.

### 3.3 Keyboard Support
- **Up/Down**: navigate result list.
- **Enter**: select highlighted option.
- **Escape**: close sub-palette and return focus to the param input.

## 4. Backend API Usage
Market search uses the backend endpoint:
- `GET /markets?q=<query>`

The selected `market_id` is passed to commands like `QUERY_MARKET` and `OPEN_PANEL`.

## 5. Extending the System
To add new param types:
1. Extend `CommandParamType`.
2. Define how the sub-palette (or another input) should open and populate.
3. Add rendering or specialized behavior in `CommandPalette`.

This structure keeps command configuration declarative while preserving a predictable palette workflow.
