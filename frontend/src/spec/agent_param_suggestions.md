# Agent-Powered Parameter Suggestions

## Overview

This feature enhances the Command Palette with AI-powered parameter suggestions based on the user's command execution history. The agent learns from past interactions and suggests contextually relevant default values, creating a more intelligent and personalized user experience.

## Core Principles

1. **Non-Blocking**: Suggestions never prevent the user from typing or interacting with the command palette
2. **Contextual**: Agent uses command history and user patterns to generate relevant suggestions  
3. **Respectful**: Never overwrite user input - only fill empty/default values
4. **Graceful Degradation**: Command palette functions normally even if suggestion service fails

---

## Architecture

### Data Flow

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Command Execution Tracking                               │
│    User runs command → Track params → Send to agent         │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. Agent Context Building                                   │
│    Agent receives execution → Stores in memory/context      │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. Request Suggestions                                      │
│    User highlights command → Request suggestions from agent │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. Display Suggestions                                      │
│    - Market params: Show in sub-palette                     │
│    - Text/select params: Auto-fill if empty                 │
└─────────────────────────────────────────────────────────────┘
```

---

## Component Changes

### CommandPalette Component State

Add new state for managing suggestions:

```typescript
type ParamSuggestion = {
  paramName: string;
  type: 'direct' | 'market_list';
  value?: string; // For direct suggestions (text/select params)
  options?: SubPaletteOption[]; // For market_list suggestions
  reasoning?: string; // Optional explanation from agent
};

type SuggestionState = {
  loading: boolean;
  commandId: string | null;
  suggestions: ParamSuggestion[];
  error?: string;
  requestId?: string; // To handle stale responses
};
```

Update existing state:

```typescript
const [suggestions, setSuggestions] = useState<SuggestionState>({
  loading: false,
  commandId: null,
  suggestions: [],
});

const [userModifiedParams, setUserModifiedParams] = useState<Set<string>>(new Set());
```

---

## Feature Implementation

### 1. Command Execution Tracking

When a command is executed, send the execution data to the agent:

```typescript
const handleRun = () => {
  if (!activeEntry) return;
  
  // Execute the command
  activeEntry.handler(paramValues);
  
  // Track execution for agent learning
  trackCommandExecution(activeEntry.id, paramValues);
  
  // ... existing code ...
};

const trackCommandExecution = (commandId: string, params: Record<string, string>) => {
  // Send to backend via WebSocket
  if (websocket?.readyState === WebSocket.OPEN) {
    websocket.send(JSON.stringify({
      op: 'agent_track_execution',
      command_id: commandId,
      params: params,
      timestamp: new Date().toISOString()
    }));
  }
};
```

### 2. Request Suggestions When Command is Highlighted

Request suggestions when the active command changes:

```typescript
useEffect(() => {
  if (!activeEntry || focusMode !== 'list') return;
  
  // Only request suggestions if command has parameters
  if (!activeEntry.params || activeEntry.params.length === 0) {
    setSuggestions({
      loading: false,
      commandId: null,
      suggestions: []
    });
    return;
  }
  
  requestSuggestions(activeEntry.id, activeEntry.params);
}, [activeEntry?.id, focusMode]);

const requestSuggestions = async (
  commandId: string,
  params: CommandParamSchema[]
) => {
  const requestId = `${commandId}-${Date.now()}`;
  
  setSuggestions(prev => ({
    ...prev,
    loading: true,
    commandId,
    requestId,
    error: undefined
  }));
  
  try {
    if (websocket?.readyState === WebSocket.OPEN) {
      websocket.send(JSON.stringify({
        op: 'agent_suggest_params',
        command_id: commandId,
        params: params.map(p => ({ name: p.name, type: p.type })),
        current_params: paramValues,
        request_id: requestId
      }));
      
      // Set a timeout for suggestions (don't wait forever)
      setTimeout(() => {
        setSuggestions(prev => {
          if (prev.requestId === requestId && prev.loading) {
            return { ...prev, loading: false, error: 'Timeout' };
          }
          return prev;
        });
      }, 3000);
    } else {
      setSuggestions(prev => ({ ...prev, loading: false }));
    }
  } catch (error) {
    console.error('Failed to request suggestions:', error);
    setSuggestions(prev => ({ 
      ...prev, 
      loading: false,
      error: 'Failed to request suggestions'
    }));
  }
};
```

### 3. WebSocket Message Handling

Add handler for incoming suggestion responses:

```typescript
// In WebSocket onMessage handler
const handleWebSocketMessage = (event: MessageEvent) => {
  const data = JSON.parse(event.data);
  
  if (data.type === 'param_suggestions') {
    handleParamSuggestions(data);
  }
  
  // ... other handlers ...
};

const handleParamSuggestions = (data: {
  command_id: string;
  request_id?: string;
  suggestions: Record<string, {
    type: 'direct' | 'market_list';
    value?: string;
    options?: Array<{
      value: string;
      label: string;
      description?: string;
      reason?: string;
    }>;
    reasoning?: string;
  }>;
}) => {
  setSuggestions(prev => {
    // Ignore stale responses
    if (data.request_id && prev.requestId !== data.request_id) {
      return prev;
    }
    
    // Convert to our format
    const suggestions: ParamSuggestion[] = Object.entries(data.suggestions).map(
      ([paramName, suggestion]) => ({
        paramName,
        type: suggestion.type,
        value: suggestion.value,
        options: suggestion.options,
        reasoning: suggestion.reasoning
      })
    );
    
    return {
      loading: false,
      commandId: data.command_id,
      suggestions,
      requestId: prev.requestId
    };
  });
  
  // Apply direct suggestions to params that haven't been modified
  applyDirectSuggestions(data.suggestions);
};

const applyDirectSuggestions = (
  suggestions: Record<string, { type: string; value?: string }>
) => {
  setParamValues(prev => {
    const updated = { ...prev };
    
    for (const [paramName, suggestion] of Object.entries(suggestions)) {
      // Only apply if user hasn't modified this param
      if (
        suggestion.type === 'direct' &&
        suggestion.value &&
        !userModifiedParams.has(paramName) &&
        (!prev[paramName] || prev[paramName] === '')
      ) {
        updated[paramName] = suggestion.value;
      }
    }
    
    return updated;
  });
};
```

### 4. Track User Modifications

Mark parameters as user-modified when they manually edit them:

```typescript
const handleParamChange = (paramName: string, value: string) => {
  setParamValues(prev => ({
    ...prev,
    [paramName]: value
  }));
  
  // Mark as user-modified
  setUserModifiedParams(prev => new Set(prev).add(paramName));
};

// Reset user modifications when command changes
useEffect(() => {
  if (focusMode === 'list') {
    setUserModifiedParams(new Set());
  }
}, [activeEntry?.id, focusMode]);
```

### 5. Market Sub-Palette with Suggestions

Enhance the market sub-palette to show suggestions at the top:

```typescript
const openSubPaletteForParam = (param: CommandParamSchema, index: number) => {
  if (param.type === 'text') return;
  
  // Find suggestions for this param
  const paramSuggestion = suggestions.suggestions.find(
    s => s.paramName === param.name
  );
  
  const baseOptions =
    param.type === 'select'
      ? (param.options ?? []).map(option => ({ value: option, label: option }))
      : [];
  
  // For market type, use suggested options if available
  const suggestedOptions = 
    param.type === 'market' && 
    paramSuggestion?.type === 'market_list'
      ? paramSuggestion.options || []
      : [];
  
  setSubPalette({
    open: true,
    type: param.type,
    title: param.label,
    query: '',
    options: [], // Search results
    baseOptions, // For select type
    suggestedOptions, // Agent suggestions for market type
    loading: false,
    emptyMessage: param.type === 'market' ? 'Type at least 2 characters' : 'No options',
    paramName: param.name,
    paramIndex: index,
  });
  setSubPaletteIndex(0);
};
```

Update SubPaletteState type:

```typescript
type SubPaletteState = {
  open: boolean;
  type: SubPaletteType | null;
  title: string;
  query: string;
  options: SubPaletteOption[]; // Search results
  baseOptions: SubPaletteOption[]; // Static options for select
  suggestedOptions?: SubPaletteOption[]; // Agent suggestions for market
  loading: boolean;
  emptyMessage: string;
  paramName: string;
  paramIndex: number;
};
```

### 6. Render Suggestions in Sub-Palette

Update the sub-palette rendering to show suggestions:

```tsx
{subPalette.open && (
  <div className="fixed inset-0 z-[60] flex items-start justify-center bg-black/40 p-6">
    <div className="w-full max-w-xl rounded-xl border border-border bg-card shadow-xl">
      <div className="border-b border-border p-4">
        <div className="text-sm font-semibold">{subPalette.title}</div>
        <div className="mt-2">
          <Input
            ref={subPaletteInputRef}
            value={subPalette.query}
            placeholder={
              subPalette.type === 'market' ? 'Search markets...' : 'Search options...'
            }
            onChange={(event) =>
              setSubPalette((prev) => ({
                ...prev,
                query: event.target.value,
              }))
            }
          />
        </div>
      </div>
      <div className="max-h-64 overflow-y-auto p-2">
        {/* Show suggestions first if no query and suggestions exist */}
        {!subPalette.query.trim() && 
         subPalette.suggestedOptions && 
         subPalette.suggestedOptions.length > 0 && (
          <>
            <div className="px-3 py-2 text-xs font-medium text-muted-foreground">
              ✨ Suggested
            </div>
            <div className="space-y-1 mb-2">
              {subPalette.suggestedOptions.map((option, index) => (
                <button
                  key={`suggested-${option.value}`}
                  type="button"
                  onClick={() => handleSubPaletteSelect(option)}
                  className={`w-full rounded-lg px-3 py-2 text-left text-sm transition ${
                    index === subPaletteIndex ? 'bg-muted' : 'hover:bg-muted'
                  }`}
                >
                  <div className="font-medium text-foreground">{option.label}</div>
                  {option.description && (
                    <div className="text-xs text-muted-foreground">
                      {option.description}
                    </div>
                  )}
                </button>
              ))}
            </div>
            {filteredSubPaletteOptions.length > 0 && (
              <div className="border-t border-border my-2"></div>
            )}
          </>
        )}
        
        {/* Show search results or loading state */}
        {subPalette.loading ? (
          <div className="p-4 text-sm text-muted-foreground">Searching…</div>
        ) : filteredSubPaletteOptions.length === 0 ? (
          <div className="p-4 text-sm text-muted-foreground">
            {subPalette.emptyMessage || 'No results'}
          </div>
        ) : (
          <div className="space-y-1">
            {filteredSubPaletteOptions.map((option, index) => (
              <button
                key={option.value}
                type="button"
                onClick={() => handleSubPaletteSelect(option)}
                className={`w-full rounded-lg px-3 py-2 text-left text-sm transition ${
                  index === subPaletteIndex ? 'bg-muted' : 'hover:bg-muted'
                }`}
              >
                <div className="font-medium text-foreground">{option.label}</div>
                {option.description && (
                  <div className="text-xs text-muted-foreground">{option.description}</div>
                )}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  </div>
)}
```

---

## UI/UX Patterns

### Loading States

**For direct suggestions (text/select params):**
- Show a subtle shimmer/skeleton in the input field
- Display for max 3 seconds, then hide even if no response

**For market suggestions in sub-palette:**
- Show "Loading suggestions..." in the suggested section
- Display actual suggestions when received
- If timeout/error: Hide the suggested section, show search normally

### Visual Indicators

**Suggested markets in sub-palette:**
- Section header: "✨ Suggested" 
- Optional: Show reasoning in description (e.g., "Recently queried" or "You searched this 5 min ago")

**Auto-filled text params:**
- Optional: Show a subtle indicator (e.g., faded text) that value was suggested
- Clears when user starts editing

### Error Handling

**Graceful degradation:**
1. If WebSocket is not connected: Skip suggestions, work normally
2. If suggestion request times out: Continue without suggestions
3. If agent returns error: Log to console, no user-facing error

---

## Performance Considerations

### Debouncing & Throttling

- **Don't** request suggestions on every keystroke
- **Do** request when command is highlighted (focusMode changes to 'list')
- **Cache** suggestions for 30 seconds per command
- **Cancel** pending requests when user switches commands

### Memory Management

- Clear old suggestions when command palette closes
- Limit suggestion history to last 50 command executions (backend-managed)
- Use request IDs to ignore stale responses

---

## TypeScript Interfaces

```typescript
// WebSocket Operations
interface AgentTrackExecutionMessage {
  op: 'agent_track_execution';
  command_id: string;
  params: Record<string, string>;
  timestamp: string;
}

interface AgentSuggestParamsMessage {
  op: 'agent_suggest_params';
  command_id: string;
  params: Array<{ name: string; type: CommandParamType }>;
  current_params: Record<string, string>;
  request_id: string;
}

interface ParamSuggestionsResponse {
  type: 'param_suggestions';
  command_id: string;
  request_id?: string;
  suggestions: Record<string, {
    type: 'direct' | 'market_list';
    value?: string; // For direct type
    options?: Array<{ // For market_list type
      value: string;
      label: string;
      description?: string;
      reason?: string;
    }>;
    reasoning?: string;
  }>;
}

// Component State
interface ParamSuggestion {
  paramName: string;
  type: 'direct' | 'market_list';
  value?: string;
  options?: SubPaletteOption[];
  reasoning?: string;
}

interface SuggestionState {
  loading: boolean;
  commandId: string | null;
  suggestions: ParamSuggestion[];
  error?: string;
  requestId?: string;
}

interface SubPaletteState {
  open: boolean;
  type: SubPaletteType | null;
  title: string;
  query: string;
  options: SubPaletteOption[];
  baseOptions: SubPaletteOption[];
  suggestedOptions?: SubPaletteOption[]; // NEW: Agent suggestions
  loading: boolean;
  emptyMessage: string;
  paramName: string;
  paramIndex: number;
}
```

---

## Testing Scenarios

### Manual Testing Checklist

1. **Basic Flow:**
   - [ ] Execute a command with market parameter
   - [ ] Re-open command palette and highlight same command
   - [ ] Verify market suggestion appears in sub-palette

2. **User Input Respect:**
   - [ ] Highlight command with text param
   - [ ] Manually type a value
   - [ ] Change to different command and back
   - [ ] Verify manual value is preserved (not overwritten)

3. **Loading States:**
   - [ ] Verify loading indicator shows while waiting
   - [ ] Simulate slow network (throttle)
   - [ ] Verify timeout occurs after 3 seconds

4. **Error Handling:**
   - [ ] Disconnect WebSocket
   - [ ] Verify command palette still works
   - [ ] Reconnect and verify suggestions resume

5. **Market Sub-Palette:**
   - [ ] Open market param with suggestions
   - [ ] Verify suggestions show at top
   - [ ] Start typing in search
   - [ ] Verify suggestions hide, search results show
   - [ ] Clear search
   - [ ] Verify suggestions re-appear

6. **Multiple Parameters:**
   - [ ] Command with text + market params
   - [ ] Verify text param auto-fills
   - [ ] Verify market param shows suggestions in sub-palette

---

## Future Enhancements

1. **Intelligent Context:** Use current workspace state (open panels) as context
2. **Cross-Command Learning:** Suggest market from "Open Market Aggregator" when using "Query Market"
3. **Frequency-Based Ranking:** Most-used markets float to top of suggestions
4. **Time-Aware Suggestions:** Prefer recent executions over old ones
5. **Collaborative Filtering:** Learn from other users' patterns (optional, privacy-aware)

---

## Integration Points

### Dependencies
- WebSocket connection from `backendInterface.ts`
- Command registry from `commands/registry.ts`
- Agent store from `hooks/useAgentStore.ts` (optional, for tracking)

### Files to Modify
- `frontend/src/components/dashboard/CommandPalette.tsx` - Main implementation
- `frontend/src/backendInterface.ts` - WebSocket message types (optional)
- `frontend/src/commands/registry.ts` - TypeScript types (if needed)

---

## Summary

This feature creates a feedback loop where:
1. User executes commands → Agent learns patterns
2. User opens command palette → Agent suggests relevant values
3. Suggestions respect user input and degrade gracefully
4. Market parameters show suggestions in sub-palette (non-intrusive)
5. Text/select parameters auto-fill if empty

The implementation maintains the command palette's existing UX while adding intelligent assistance that becomes more useful over time.
