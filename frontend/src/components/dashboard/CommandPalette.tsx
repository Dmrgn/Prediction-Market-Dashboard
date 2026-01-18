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

type FocusMode = "list" | "param" | "run";

type SubPaletteType = "market" | "select";

type SubPaletteOption = {
  value: string;
  label: string;
  description?: string;
  meta?: any;
};

type SubPaletteState = {
  open: boolean;
  type: SubPaletteType | null;
  title: string;
  query: string;
  options: SubPaletteOption[];
  baseOptions: SubPaletteOption[];
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
  const { events: agentEvents, addEvents } = useAgentStore();

  const [search, setSearch] = useState("");
  const [paramValues, setParamValues] = useState<Record<string, string>>({});
  const [agentCommandRan, setAgentCommandRan] = useState(false);

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
  const debounceRef = useRef<number | null>(null);

  const entries = useMemo(
    () =>
      getCommandEntries(async (prompt) => {
        const events = await agentController.processInput(prompt);
        addEvents(events);
        setAgentCommandRan(true);
      }),
    [addEvents]
  );

  const commandMap = useMemo(() => new Map(entries.map((entry) => [entry.id, entry])), [entries]);

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
      // If command palette is closing and an agent command was run, open the sidebar
      if (agentCommandRan) {
        openSidebar();
        setAgentCommandRan(false);
      }
    }
  }, [isOpen, agentCommandRan, openSidebar]);

  useEffect(() => {
    if (subPalette.open) {
      requestAnimationFrame(() => {
        subPaletteInputRef.current?.focus();
      });
    }
  }, [subPalette.open]);

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

  // When activeEntry changes, reset param values (unless we are deep in editing logic, but usually switching command = reset)
  useEffect(() => {
    if (focusMode === "list") {
      setParamValues(buildInitialValues(activeEntry?.params));
      setActiveParamIndex(0);
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
      backendInterface
        .searchEvents(query)
        .then((result) => {
          if (!active) return;

          // Flatten events into individual market options, grouped by event
          const options: SubPaletteOption[] = [];

          // Add markets from events
          for (const event of result.events) {
            for (const market of event.markets) {
              // Try to make a nice label
              // e.g. "Fed Rate: No Change"
              let label = market.title;
              if (label.startsWith(event.title)) {
                label = event.title + ": " + label.slice(event.title.length).replace(/^[ -]+/, "");
              }

              options.push({
                value: market.market_id,
                label: label,
                description: `${event.source.toUpperCase()} • ${event.title}`,
                meta: {
                  source: event.source,
                  price: market.outcomes?.[0]?.price
                }
              });
            }
          }

          // Add standalone markets
          for (const market of result.markets) {
            options.push({
              value: market.market_id,
              label: market.title,
              description: `${market.source.toUpperCase()} • standalone`,
              meta: {
                source: market.source,
                price: market.outcomes?.[0]?.price
              }
            });
          }

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

    setSubPalette({
      open: true,
      type: param.type,
      title: param.label,
      query: "",
      options: [],
      baseOptions,
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
    if (subPalette.open) return;
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
        // Go back up
        if (activeParamIndex > 0) {
          setActiveParamIndex(activeParamIndex - 1);
        } else {
          setFocusMode("list");
        }
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
        const totalParams = activeEntry?.params?.length ?? 0;
        if (totalParams > 0) {
          setFocusMode("param");
          setActiveParamIndex(totalParams - 1);
        } else {
          setFocusMode("list");
        }
      }
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 p-6">
      <div className="relative w-full max-w-2xl rounded-xl border border-border bg-card shadow-xl" onKeyDown={handleKeyDown}>
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

          <div className="border-t border-border p-4">
            <div className="text-xs uppercase tracking-wide text-muted-foreground">Agent Activity</div>
            {agentEvents.length === 0 ? (
              <div className="mt-2 text-xs text-muted-foreground">No agent activity yet.</div>
            ) : (
              <div className="mt-2 space-y-2">
                {agentEvents.map((event) => (
                  <div key={event.id} className="rounded-lg bg-muted px-3 py-2 text-xs">
                    {event.message}
                  </div>
                ))}
              </div>
            )}
          </div>
        </Command>

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
    </div>
  );
}
