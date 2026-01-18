import { useState } from "react";
import { useResearcherStore } from "@/hooks/useResearcherStore";

export function ResearcherPanel() {
    const { report, status, error, query, fetchReport, clear } = useResearcherStore();
    const [inputValue, setInputValue] = useState("");

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        const q = inputValue.trim();
        if (q) {
            fetchReport(q);
        }
    };

    const getSignalColor = (signal: string) => {
        switch (signal) {
            case "bullish":
                return "bg-green-500/20 text-green-400 border-green-500/30";
            case "bearish":
                return "bg-red-500/20 text-red-400 border-red-500/30";
            default:
                return "bg-gray-500/20 text-gray-400 border-gray-500/30";
        }
    };

    const getScoreColor = (score: number) => {
        if (score >= 30) return "text-green-400";
        if (score <= -30) return "text-red-400";
        return "text-gray-400";
    };

    return (
        <div className="px-4 space-y-4">
            <div className="text-xs uppercase tracking-wide text-muted-foreground">
                Market Research
            </div>

            {/* Search Form */}
            <form onSubmit={handleSubmit} className="space-y-2">
                <input
                    type="text"
                    placeholder="Enter topic (e.g., Bitcoin ETF)"
                    value={inputValue}
                    onChange={(e) => setInputValue(e.target.value)}
                    className="w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                />
                <button
                    type="submit"
                    disabled={status === "loading" || !inputValue.trim()}
                    className="w-full rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                    {status === "loading" ? "Analyzing..." : "Analyze Sentiment"}
                </button>
            </form>

            {/* Loading State */}
            {status === "loading" && (
                <div className="space-y-3">
                    <div className="h-4 w-3/4 animate-pulse rounded bg-muted" />
                    <div className="h-4 w-1/2 animate-pulse rounded bg-muted" />
                    <div className="h-20 w-full animate-pulse rounded bg-muted" />
                </div>
            )}

            {/* Error State */}
            {status === "error" && (
                <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
                    {error}
                </div>
            )}

            {/* Results */}
            {status === "success" && report && (
                <div className="space-y-4">
                    {/* Score & Signal */}
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                            <span className={`text-2xl font-bold ${getScoreColor(report.score)}`}>
                                {report.score > 0 ? "+" : ""}{report.score.toFixed(1)}
                            </span>
                            <span className="text-xs text-muted-foreground">/100</span>
                        </div>
                        <span
                            className={`rounded-full border px-3 py-1 text-xs font-medium uppercase ${getSignalColor(
                                report.signal
                            )}`}
                        >
                            {report.signal}
                        </span>
                    </div>

                    {/* Summary */}
                    <div className="rounded-lg bg-muted p-3 text-sm leading-relaxed">
                        {report.summary}
                    </div>

                    {/* Stats */}
                    <div className="text-xs text-muted-foreground">
                        Analyzed {report.articles_analyzed} articles
                    </div>

                    {/* Headlines */}
                    {report.top_positive.length > 0 && (
                        <div className="space-y-1">
                            <div className="text-xs font-medium text-green-400">Bullish Drivers</div>
                            {report.top_positive.slice(0, 3).map((headline, i) => (
                                <div key={i} className="text-xs text-muted-foreground truncate">
                                    • {headline}
                                </div>
                            ))}
                        </div>
                    )}

                    {report.top_negative.length > 0 && (
                        <div className="space-y-1">
                            <div className="text-xs font-medium text-red-400">Bearish Drivers</div>
                            {report.top_negative.slice(0, 3).map((headline, i) => (
                                <div key={i} className="text-xs text-muted-foreground truncate">
                                    • {headline}
                                </div>
                            ))}
                        </div>
                    )}

                    {/* Clear Button */}
                    <button
                        onClick={clear}
                        className="w-full rounded-md border border-border px-3 py-2 text-xs text-muted-foreground hover:bg-muted"
                    >
                        Clear
                    </button>
                </div>
            )}

            {/* Idle State */}
            {status === "idle" && (
                <div className="text-sm text-muted-foreground">
                    Enter a topic to analyze market sentiment from recent news.
                </div>
            )}
        </div>
    );
}
