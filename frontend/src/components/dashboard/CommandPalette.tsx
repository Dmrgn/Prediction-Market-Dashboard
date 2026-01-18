import { useEffect, useMemo, useRef, useState } from "react";
import { Command } from "cmdk";
import { backendInterface } from "@/backendInterface";
import { getCommandEntries, type CommandParamSchema } from "@/commands/registry";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { agentController } from "@/commands/agentController";
import { useUIStore } from "@/hooks/useUIStore";
import { useAgentStore } from "@/hooks/useAgentStore";
import { MarketSearchInput } from "@/components/shared/MarketSearchInput";

const DEBUG_AGENT = true;

type FocusMode = "list" | "param" | "run";

type SubPaletteType = "market" | "select";

type SubPaletteOption = {
  value: string;
  label: string;
  description?: string;
  meta?: any;
};

type ParamSuggestion = {
  paramName: string;
  type: "direct" | "market_list";
  value?: string;
  options?: SubPaletteOption[];
  reasoning?: string;
};

type SuggestionState = {
  loading: boolean;
  commandId: string | null;
  suggestions: ParamSuggestion[];
  error?: string;
  requestId?: string;
};

type SubPaletteState = {
  open: boolean;
  type: SubPaletteType | null;
  title: string;
  query: string;
  options: SubPaletteOption[];
  baseOptions: SubPaletteOption[];
  suggestedOptions?: SubPaletteOption[];
  loading: boolean;
  emptyMessage: string;
  paramName: string;
  paramIndex: number;
};

const buildInitialValues = (params?: CommandParamSchema[]) =>
  params?.reduce<Record<string, string>>((acc, param) => {
    acc[param.name] = param.defaultValue ?? "";
    return acc;
  }, {}) ?? {};

const createEmptySubPalette = (): SubPaletteState => ({
  open: false,
  type: null,
  title: "",
  query: "",
  options: [],
  baseOptions: [],
  loading: false,
  emptyMessage: "",
  paramName: "",
  paramIndex: 0,
});


export function CommandPalette() {
  const { isCommandPaletteOpen: isOpen, closeCommandPalette: onClose, initialCommandId, initialParams, openSidebar } = useUIStore();

  // Use new agent store state if needed, or just trigger via controller
  // const { isRunning } = useAgentStore(); 

  const [search, setSearch] = useState("");
  const [paramValues, setParamValues] = useState<Record<string, string>>({});
  const [agentCommandRan, setAgentCommandRan] = useState(false);
  const [suggestions, setSuggestions] = useState<SuggestionState>({
    loading: false,
    commandId: null,
    suggestions: [],
  });
  const [userModifiedParams, setUserModifiedParams] = useState<Set<string>>(new Set());
  const [agentSocket, setAgentSocket] = useState<WebSocket | null>(null);

  const suggestionTimeoutRef = useRef<number | null>(null);
  const currentRequestIdRef = useRef<string | null>(null);
  const debounceRef = useRef<number | null>(null);
  const pendingAgentMessagesRef = useRef<string[]>([]);

  // State for selection & focus
  const [selectedValue, setSelectedValue] = useState<string>("");
  const [focusMode, setFocusMode] = useState<FocusMode>("list");
  const [activeParamIndex, setActiveParamIndex] = useState(0);

  // Sub-palette state
  const [subPalette, setSubPalette] = useState<SubPaletteState>(createEmptySubPalette());
  const [subPaletteIndex, setSubPaletteIndex] = useState(0);

  // Refs for focusing elements
  const searchInputRef = useRef<HTMLInputElement>(null);
  const paramRefs = useRef<(HTMLInputElement | null)[]>([]);
  const runButtonRef = useRef<HTMLButtonElement | null>(null);
  const subPaletteInputRef = useRef<HTMLInputElement | null>(null);

  const entries = useMemo(
    () => getCommandEntries(),
    []
  );

  const commandMap = useMemo(() => new Map(entries.map((entry) => [entry.id, entry])), [entries]);

  useEffect(() => {
    const socket = backendInterface.socket.createAgentSocket();

    const handleMessage = (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data);
        if (DEBUG_AGENT) {
          console.debug("[Agent WS] inbound", data);
        }
        if (data.type === "param_suggestions") {
          handleParamSuggestions(data);
        } else if (data.type === "execution_tracked") {
          setSuggestions((prev) => ({
            ...prev,
            loading: false,
          }));
        }
      } catch (error) {
        console.error("Agent WebSocket message error", error);
      }
    };

    const handleClose = () => {
      if (DEBUG_AGENT) {
        console.debug("[Agent WS] closed");
      }
      setAgentSocket(null);
    };

    const handleOpen = () => {
      if (DEBUG_AGENT) {
        console.debug("[Agent WS] open");
      }
    };

    const handleError = () => {
      if (DEBUG_AGENT) {
        console.debug("[Agent WS] error");
      }
      socket.close();
    };

    socket.addEventListener("message", handleMessage);
    socket.addEventListener("close", handleClose);
    socket.addEventListener("open", handleOpen);
    socket.addEventListener("error", handleError);

    setAgentSocket(socket);

    return () => {
      socket.removeEventListener("message", handleMessage);
      socket.removeEventListener("close", handleClose);
      socket.removeEventListener("open", handleOpen);
      socket.removeEventListener("error", handleError);
    };
  }, []);

  // Handle initial store values when opening
  useEffect(() => {
    if (!isOpen) return;

    if (initialCommandId) {
      const entry = commandMap.get(initialCommandId);
      if (entry) {
        setSelectedValue(initialCommandId);
        const defaults = buildInitialValues(entry.params);
        setParamValues({ ...defaults, ...initialParams });
        if (entry.params && entry.params.length > 0) {
          setFocusMode("param");
          setActiveParamIndex(0);
        } else {
          setFocusMode("run");
        }
      }
      return;
    }

    setSearch("");
    setFocusMode("list");
    setActiveParamIndex(0);
  }, [isOpen, initialCommandId, initialParams, commandMap]);

  useEffect(() => {
    if (!isOpen) {
      setSearch("");
      setFocusMode("list");
      setActiveParamIndex(0);
      setSubPalette(createEmptySubPalette());

      // If command palette is closing and an agent command was run, open the sidebar
      if (agentCommandRan) {
        openSidebar();
        setAgentCommandRan(false);
      }
    }
  }, [isOpen, agentCommandRan, openSidebar]);

  useEffect(() => {
    if (subPalette.open) {
      // Small timeout to allow render
      const timer = setTimeout(() => {
        if (subPalette.type === 'market') {
          // processed inside MarketSearchInput via autoFocus, but just in case
        } else {
          subPaletteInputRef.current?.focus();
        }
      }, 50);
      return () => clearTimeout(timer);
    }
  }, [subPalette.open, subPalette.type]);

  const filteredEntries = entries.filter((entry) => {
    if (!search.trim()) return true;
    const haystack = `${entry.label} ${entry.description ?? ""}`.toLowerCase();
    return haystack.includes(search.toLowerCase());
  });

  // Derived active entry based on what's highlighted in the list
  const activeEntry = useMemo(() => commandMap.get(selectedValue) ?? null, [selectedValue, commandMap]);

  const filteredSubPaletteOptions = useMemo(() => {
    if (!subPalette.open) return [] as SubPaletteOption[];
    if (subPalette.type === "select") {
      const needle = subPalette.query.trim().toLowerCase();
      if (!needle) return subPalette.baseOptions;
      return subPalette.baseOptions.filter((option) => option.label.toLowerCase().includes(needle));
    }
    return subPalette.options;
  }, [subPalette]);

  const handleParamSuggestions = (data: {
    command_id: string;
    request_id?: string;
    suggestions: Record<string, {
      type: "direct" | "market_list";
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
    setSuggestions((prev) => {
      if (data.request_id && prev.requestId !== data.request_id) {
        return prev;
      }

      const suggestionList: ParamSuggestion[] = Object.entries(data.suggestions).map(
        ([paramName, suggestion]) => ({
          paramName,
          type: suggestion.type,
          value: suggestion.value,
          options: suggestion.options?.map((option) => ({
            value: option.value,
            label: option.label,
            description: option.description ?? option.reason,
          })),
          reasoning: suggestion.reasoning,
        })
      );

      return {
        loading: false,
        commandId: data.command_id,
        suggestions: suggestionList,
        requestId: prev.requestId,
      };
    });

    if (DEBUG_AGENT) {
      console.debug("[Agent Suggestions]", data.suggestions);
    }

    applyDirectSuggestions(data.suggestions);
  };

  const applyDirectSuggestions = (
    suggestionData: Record<string, { type: string; value?: string }>
  ) => {
    setParamValues((prev) => {
      const updated = { ...prev };

      for (const [paramName, suggestion] of Object.entries(suggestionData)) {
        if (
          suggestion.type === "direct" &&
          suggestion.value &&
          !userModifiedParams.has(paramName) &&
          (!prev[paramName] || prev[paramName] === "")
        ) {
          updated[paramName] = suggestion.value;
        }
      }

      if (DEBUG_AGENT) {
        console.debug("[Agent Suggestions] applied", updated);
      }

      return updated;
    });
  };

  const requestSuggestions = (commandId: string, params: CommandParamSchema[]) => {
    if (!agentSocket || agentSocket.readyState !== WebSocket.OPEN) {
      if (DEBUG_AGENT) {
        console.debug("[Agent WS] socket not open", agentSocket?.readyState);
      }
      setSuggestions((prev) => ({ ...prev, loading: false }));
      return;
    }

    const requestId = `${commandId}-${Date.now()}`;
    currentRequestIdRef.current = requestId;

    setSuggestions((prev) => ({
      ...prev,
      loading: true,
      commandId,
      requestId,
      error: undefined,
    }));

    if (suggestionTimeoutRef.current) {
      window.clearTimeout(suggestionTimeoutRef.current);
    }

    suggestionTimeoutRef.current = window.setTimeout(() => {
      setSuggestions((prev) => {
        if (prev.requestId === requestId && prev.loading) {
          return { ...prev, loading: false, error: "Timeout" };
        }
        return prev;
      });
    }, 3000);

    const payload = {
      op: "agent_suggest_params",
      command_id: commandId,
      params: params.map((param) => ({ name: param.name, type: param.type })),
      current_params: paramValues,
      request_id: requestId,
    };

    if (DEBUG_AGENT) {
      console.debug("[Agent WS] outbound", payload);
    }

    agentSocket.send(JSON.stringify(payload));
  };

  useEffect(() => {
    if (DEBUG_AGENT) {
      console.debug("[Agent Trigger]", {
        focusMode,
        activeEntry: activeEntry?.id,
        params: activeEntry?.params?.length ?? 0,
        socketReadyState: agentSocket?.readyState,
      });
    }

    if (!activeEntry || focusMode !== "list") return;

    if (!activeEntry.params || activeEntry.params.length === 0) {
      setSuggestions({ loading: false, commandId: null, suggestions: [] });
      return;
    }

    requestSuggestions(activeEntry.id, activeEntry.params);
  }, [activeEntry?.id, focusMode, agentSocket]);

  // When activeEntry changes, reset param values (unless we are deep in editing logic, but usually switching command = reset)
  useEffect(() => {
    if (focusMode === "list") {
      setParamValues(buildInitialValues(activeEntry?.params));
      setActiveParamIndex(0);
      setUserModifiedParams(new Set());
    }
  }, [activeEntry, focusMode]);

  useEffect(() => {
    if (!subPalette.open || subPalette.type !== "market") return;

    if (debounceRef.current) {
      window.clearTimeout(debounceRef.current);
    }

    const query = subPalette.query.trim();
    if (query.length < 2) {
      setSubPalette((prev) => ({
        ...prev,
        options: [],
        loading: false,
        emptyMessage: "Type at least 2 characters",
      }));
      return;
    }

    setSubPalette((prev) => ({ ...prev, loading: true }));

    let active = true;
    debounceRef.current = window.setTimeout(() => {
      console.log('[CommandPalette] Searching markets for:', query);
      backendInterface
        .searchMarkets(query)
        .then((result) => {
          if (!active) return;

          console.log('[CommandPalette] Search results:', result.total, 'markets');

          // Convert markets to options
          const options: SubPaletteOption[] = result.markets.map((market) => ({
            value: market.market_id,
            label: market.title,
            description: `${market.source.toUpperCase()} • ${market.category || 'Market'}`,
            meta: {
              source: market.source,
              price: market.outcomes?.[0]?.price
            }
          }));

          setSubPalette((prev) => ({
            ...prev,
            options,
            loading: false,
            emptyMessage: options.length ? "" : "No markets found",
          }));
        })
        .catch((err) => {
          console.error("Market search error:", err);
          if (!active) return;
          setSubPalette((prev) => ({
            ...prev,
            options: [],
            loading: false,
            emptyMessage: "Unable to load markets",
          }));
        });
    }, 300);

    return () => {
      active = false;
      if (debounceRef.current) {
        window.clearTimeout(debounceRef.current);
      }
    };
  }, [subPalette.open, subPalette.query, subPalette.type]);

  useEffect(() => {
    if (!subPalette.open) return;
    setSubPaletteIndex(0);
  }, [subPalette.open, filteredSubPaletteOptions.length]);

  // Effects to handle focus moves
  useEffect(() => {
    if (!isOpen || subPalette.open) return;

    if (focusMode === "list") {
      // Focus the search input so up/down arrows work in cmdk list
      searchInputRef.current?.focus();
    } else if (focusMode === "param") {
      requestAnimationFrame(() => {
        paramRefs.current[activeParamIndex]?.focus();
      });
    } else if (focusMode === "run") {
      requestAnimationFrame(() => {
        runButtonRef.current?.focus();
      });
    }
  }, [focusMode, activeParamIndex, isOpen, subPalette.open]);

  // Reset state when opening/closing or filtering
  useEffect(() => {
    if (isOpen && filteredEntries.length > 0) {
      // Default select first item if none selected
      if (!selectedValue || !filteredEntries.some((entry) => entry.id === selectedValue)) {
        const first = filteredEntries[0];
        if (first) setSelectedValue(first.id);
      }
    }
  }, [isOpen, filteredEntries, selectedValue]);

  const moveFocusAfterParam = (index: number) => {
    const totalParams = activeEntry?.params?.length ?? 0;
    if (index < totalParams - 1) {
      setFocusMode("param");
      setActiveParamIndex(index + 1);
    } else {
      setFocusMode("run");
    }
  };

  const closeSubPalette = (returnToParam = true) => {
    setSubPalette((prev) => ({ ...prev, open: false }));
    if (returnToParam) {
      setFocusMode("param");
      setActiveParamIndex(subPalette.paramIndex);
    }
  };

  const handleSubPaletteSelect = (option: SubPaletteOption) => {
    setParamValues((prev) => ({
      ...prev,
      [subPalette.paramName]: option.value,
    }));
    setSubPalette((prev) => ({ ...prev, open: false }));
    moveFocusAfterParam(subPalette.paramIndex);
  };

  const openSubPaletteForParam = (param: CommandParamSchema, index: number) => {
    if (param.type === "text") return;

    const baseOptions =
      param.type === "select"
        ? (param.options ?? []).map((option) => ({ value: option, label: option }))
        : [];

    const paramSuggestion = suggestions.suggestions.find(
      (suggestion) => suggestion.paramName === param.name
    );

    const suggestedOptions =
      param.type === "market" && paramSuggestion?.type === "market_list"
        ? paramSuggestion.options ?? []
        : [];

    if (DEBUG_AGENT) {
      console.debug("[Sub-Palette] Opening for param", {
        paramName: param.name,
        paramType: param.type,
        hasSuggestion: !!paramSuggestion,
        suggestionType: paramSuggestion?.type,
        suggestedOptionsCount: suggestedOptions.length,
        suggestedOptions,
      });
    }

    setSubPalette({
      open: true,
      type: param.type,
      title: param.label,
      query: "",
      options: [],
      baseOptions,
      suggestedOptions,
      loading: false,
      emptyMessage: param.type === "market" ? "Type at least 2 characters" : "No options",
      paramName: param.name,
      paramIndex: index,
    });
    setSubPaletteIndex(0);
  };

  const handleRun = () => {
    if (!activeEntry) return;
    activeEntry.handler(paramValues);

    if (agentSocket?.readyState === WebSocket.OPEN) {
      const payload = {
        op: "agent_track_execution",
        command_id: activeEntry.id,
        params: paramValues,
        timestamp: new Date().toISOString(),
      };

      if (DEBUG_AGENT) {
        console.debug("[Agent WS] outbound", payload);
      }

      agentSocket.send(JSON.stringify(payload));
    }

    const shouldClose = activeEntry.closeOnRun !== false;
    if (shouldClose) {
      onClose();
    }

    // Reset state
    setSearch("");
    setFocusMode("list");
    setActiveParamIndex(0);
    // Select first available again
    if (filteredEntries[0]) {
      setSelectedValue(filteredEntries[0].id);
      setParamValues(buildInitialValues(filteredEntries[0].params));
    }
  };

  const handleSubPaletteKeyDown = (event: React.KeyboardEvent) => {
    if (!subPalette.open) return;
    event.stopPropagation();

    if (event.key === "Escape") {
      event.preventDefault();
      setSubPalette((prev) => ({ ...prev, open: false }));
      if (subPalette.paramIndex > 0) {
        setFocusMode("param");
        setActiveParamIndex(subPalette.paramIndex - 1);
      } else {
        setFocusMode("list");
      }
      return;
    }

    if (event.key === "ArrowDown") {
      event.preventDefault();
      setSubPaletteIndex((prev) => Math.min(prev + 1, Math.max(0, filteredSubPaletteOptions.length - 1)));
      return;
    }

    if (event.key === "ArrowUp") {
      event.preventDefault();
      setSubPaletteIndex((prev) => Math.max(prev - 1, 0));
      return;
    }

    if (event.key === "Enter") {
      event.preventDefault();
      const option = filteredSubPaletteOptions[subPaletteIndex];
      if (option) {
        handleSubPaletteSelect(option);
      }
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    // If sub-palette is open, we generally let it handle its own keys (like in MarketSearchInput)
    // BUT if the focus somehow leaked to this container, we should trap Escape to close it.
    if (subPalette.open) {
      if (e.key === "Escape") {
        e.preventDefault();
        e.stopPropagation();
        closeSubPalette(true);
      }
      return;
    }

    // If we're in the list, cmdk handles Up/Down. We listen for Enter to move to params.
    if (focusMode === "list") {
      if (e.key === "Enter") {
        e.preventDefault();
        // If the command has params, go to first param. Else go to run button.
        if (activeEntry?.params?.length) {
          setFocusMode("param");
          setActiveParamIndex(0);
        } else {
          setFocusMode("run");
        }
      } else if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
      return;
    }

    // If we're editing params
    if (focusMode === "param") {
      if (e.key === "Enter") {
        e.preventDefault();
        const totalParams = activeEntry?.params?.length ?? 0;
        if (activeParamIndex < totalParams - 1) {
          setActiveParamIndex(activeParamIndex + 1);
        } else {
          setFocusMode("run");
        }
      }
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
      return;
    }

    // If we're on the run button
    if (focusMode === "run") {
      if (e.key === "Enter") {
        e.preventDefault();
        handleRun();
      }
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center p-6">
      <div className="absolute inset-0 bg-black/40" onPointerDown={() => onClose()} />
      <div className="relative z-10 w-full max-w-2xl rounded-xl border border-border bg-card shadow-xl" onKeyDown={handleKeyDown}>
        <Command
          className="w-full"
          loop
          value={selectedValue}
          onValueChange={(val) => {
            if (subPalette.open) return;
            // Only allow changing selection via mouse/keyboard if we are in list mode
            // If we are editing params, we don't want hover to change the active entry on the left
            if (focusMode === "list") {
              setSelectedValue(val);
            }
          }}
          shouldFilter={false} // We filter manually
        >
          <div className="border-b border-border p-3">
            <Input
              ref={searchInputRef}
              autoFocus
              placeholder="Type a command..."
              value={search}
              onChange={(event) => {
                setSearch(event.target.value);
                setFocusMode("list"); // Typing resets focus to list
              }}
            />
          </div>
          <div className="grid gap-0 md:grid-cols-[1.3fr_1fr]">
            <Command.List className="max-h-72 overflow-y-auto p-2">
              <Command.Empty className="p-4 text-sm text-muted-foreground">No matching commands.</Command.Empty>
              {filteredEntries.map((entry) => (
                <Command.Item
                  key={entry.id}
                  value={entry.id}
                  className="flex cursor-pointer flex-col gap-1 rounded-lg px-3 py-2 text-sm text-foreground aria-selected:bg-muted data-[selected=true]:bg-muted"
                  onSelect={() => {
                    if (subPalette.open) return;
                    // Clicking an item should enter param mode
                    if (focusMode === "list") {
                      if (entry.params?.length) {
                        setFocusMode("param");
                        setActiveParamIndex(0);
                      } else {
                        setFocusMode("run");
                      }
                    }
                  }}
                >
                  <span className="font-medium">{entry.label}</span>
                  {entry.description && <span className="text-xs text-muted-foreground">{entry.description}</span>}
                </Command.Item>
              ))}
            </Command.List>

            {/* Right Pane: Preview / Form */}
            <div className="border-l border-border p-4 bg-card/50">
              {activeEntry ? (
                <div className="space-y-4">
                  <div>
                    <div className="text-sm font-semibold">{activeEntry.label}</div>
                    {activeEntry.description && (
                      <div className="text-xs text-muted-foreground">{activeEntry.description}</div>
                    )}
                  </div>

                  {activeEntry.params?.length ? (
                    <div className="space-y-3">
                      {activeEntry.params.map((param, index) => {
                        const isSelectable = param.type !== "text";
                        return (
                          <label key={param.name} className="block space-y-1 text-xs text-muted-foreground">
                            <span>{param.label}</span>
                            <Input
                              ref={(node) => {
                                paramRefs.current[index] = node;
                              }}
                              value={paramValues[param.name] ?? ""}
                              placeholder={param.placeholder}
                              readOnly={isSelectable}
                              onFocus={() => {
                                setFocusMode("param");
                                setActiveParamIndex(index);
                                if (isSelectable) {
                                  openSubPaletteForParam(param, index);
                                }
                              }}
                              onChange={(event) => {
                                if (isSelectable) return;
                                setParamValues((prev) => ({
                                  ...prev,
                                  [param.name]: event.target.value,
                                }));
                                setUserModifiedParams((prev) => new Set(prev).add(param.name));
                              }}
                            />
                          </label>
                        );
                      })}
                    </div>
                  ) : (
                    <div className="text-xs text-muted-foreground">No parameters required.</div>
                  )}

                  <Button
                    ref={runButtonRef}
                    onClick={handleRun}
                    onFocus={() => setFocusMode("run")}
                    className="w-full"
                  >
                    Run Command
                  </Button>
                </div>
              ) : (
                <div className="text-xs text-muted-foreground">Select a command to configure.</div>
              )}
            </div>
          </div>


        </Command>
      </div>

      {subPalette.open && subPalette.type === 'market' ? (
        <MarketSearchInput
          isOpen={subPalette.open}
          onOpenChange={(open) => {
            if (!open) closeSubPalette(true);
          }}
          onSelect={(market) => {
            // Construct a mock option to reuse existing handler
            const option: SubPaletteOption = {
              value: market.market_id,
              label: market.title,
              meta: {
                source: market.source
              }
            };
            handleSubPaletteSelect(option);
          }}
          autoClose={false}
        />
      ) : subPalette.open && (
        <div
          className="fixed inset-0 z-[60] flex items-start justify-center bg-black/40 p-6"
          onKeyDown={handleSubPaletteKeyDown}
        >
          <div className="w-full max-w-xl rounded-xl border border-border bg-card shadow-xl">
            <div className="border-b border-border p-4">
              <div className="text-sm font-semibold">{subPalette.title}</div>
              <div className="mt-2">
                <Input
                  ref={subPaletteInputRef}
                  value={subPalette.query}
                  placeholder="Search options..."
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
              {subPalette.loading ? (
                <div className="p-4 text-sm text-muted-foreground">Searching…</div>
              ) : filteredSubPaletteOptions.length === 0 ? (
                <div className="p-4 text-sm text-muted-foreground">
                  {subPalette.emptyMessage || "No results"}
                </div>
              ) : (
                <div className="space-y-1">
                  {filteredSubPaletteOptions.map((option, index) => (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => handleSubPaletteSelect(option)}
                      className={`w-full rounded-lg px-3 py-2 text-left text-sm transition ${index === subPaletteIndex ? "bg-muted" : "hover:bg-muted"
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
    </div>
  );
}
