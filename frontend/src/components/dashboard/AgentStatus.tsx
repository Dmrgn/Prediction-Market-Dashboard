import { useState, useRef, useEffect } from "react";
import { useAgentStore } from "@/hooks/useAgentStore";
import { Loader2, Brain, CheckCircle, AlertCircle, Bot, Send, Square } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { agentController } from "@/commands/agentController";

export function AgentStatus() {
  const { isRunning, steps, summary, error } = useAgentStore();
  const [prompt, setPrompt] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when steps change
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [steps, isRunning, summary, error]);

  const handleRun = () => {
    if (!prompt.trim() || isRunning) return;
    agentController.runWorkflow(prompt);
    setPrompt("");
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleRun();
    }
  };

  return (
    <div className="h-full flex flex-col">
      <div className="flex-1 overflow-y-auto p-4 space-y-4" ref={scrollRef}>
        {steps.length === 0 && !isRunning && !summary && !error && (
          <div className="flex flex-col items-center justify-center h-40 text-muted-foreground text-center">
            <Bot className="h-8 w-8 mb-2 opacity-50" />
            <p className="text-sm">Ready to help.</p>
            <p className="text-xs">Type a request below to start.</p>
          </div>
        )}

        {steps.map((step, index) => (
          <div key={index} className="space-y-2 border-l-2 border-border pl-3 ml-1">
            <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
              {step.model === "gemini" ? (
                <Brain className="h-3 w-3 text-cyan-500" />
              ) : (
                <Bot className="h-3 w-3 text-green-500" />
              )}
              <span className="uppercase">{step.model}</span>
            </div>

            {step.reasoning && (
              <div className="text-sm prose prose-invert max-w-none text-foreground">
                {step.reasoning}
              </div>
            )}

            {step.actions.length > 0 && (
              <div className="space-y-1">
                {step.actions.map((action, i) => (
                  <div key={i} className="bg-muted/50 rounded p-2 text-xs font-mono">
                    <span className="text-blue-400">{action.command}</span>
                    <span className="ml-2 text-muted-foreground">
                      {JSON.stringify(action.params)}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}

        {isRunning && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground animate-pulse p-2">
            <Loader2 className="h-4 w-4 animate-spin" />
            <span>Thinking...</span>
          </div>
        )}

        {summary && (
          <div className="rounded-lg bg-green-500/10 border border-green-500/20 p-3 mt-4">
            <div className="flex items-center gap-2 mb-2 text-green-500 font-medium text-sm">
              <CheckCircle className="h-4 w-4" />
              <span>Completed</span>
            </div>
            <div className="text-sm text-foreground">
              {summary}
            </div>
          </div>
        )}

        {error && (
          <div className="rounded-lg bg-red-500/10 border border-red-500/20 p-3 mt-4 text-red-500 text-sm flex items-center gap-2">
            <AlertCircle className="h-4 w-4" />
            {error}
          </div>
        )}
      </div>

      <div className="p-4 border-t border-border bg-card">
        <div className="flex gap-2">
          <Input
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask the agent..."
            disabled={isRunning}
            className="flex-1"
          />
          <Button
            onClick={handleRun}
            disabled={!prompt.trim() || isRunning}
            size="icon"
          >
            {isRunning ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
          </Button>
        </div>
      </div>
    </div>
  );
}

