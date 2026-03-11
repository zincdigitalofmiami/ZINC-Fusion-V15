"use client";

/**
 * PolicyAiBriefing — Streams a Claude-generated policy intelligence briefing.
 *
 * Uses the Vercel AI SDK useCompletion hook to stream text from
 * /api/policy/briefing. Shows a pulsing indicator while generating,
 * then renders the full briefing with a subtle AI badge.
 */

import { useCallback, useEffect, useState } from "react";
import { Sparkles, AlertTriangle } from "lucide-react";

const FOUR_HOURS_MS = 4 * 60 * 60 * 1000;

interface PolicyAiBriefingProps {
  regime: {
    score: number;
    label: string;
    headline?: string;
    tpu: number;
    emv: number;
  };
  metrics: {
    velocity: number | null;
    deadlinesActive: number;
    shockwaveCount: number;
    agencyCount: number;
    activeEvents: number;
  };
  topAgencies: Array<{ agency: string; count: number }>;
  recentLegislation: Array<{ title: string; agency: string; date: string }>;
  recentExecutive: Array<{ headline: string; date: string; impact: number | null }>;
  recentNews: Array<{ headline: string; source: string; date: string; tags: string[] }>;
}

export function PolicyAiBriefing(props: PolicyAiBriefingProps) {
  const [briefing, setBriefing] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const cacheKey = `policy-ai-briefing:v1:${props.regime.score}:${props.regime.label}`;

  const fetchBriefing = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    if (typeof window !== "undefined") {
      try {
        const cachedRaw = localStorage.getItem(cacheKey);
        if (cachedRaw) {
          const cached = JSON.parse(cachedRaw) as {
            text?: string;
            ts?: number;
          };
          if (
            typeof cached?.text === "string" &&
            typeof cached?.ts === "number" &&
            Date.now() - cached.ts < FOUR_HOURS_MS
          ) {
            setBriefing(cached.text);
            setIsLoading(false);
            return;
          }
        }
      } catch {
        // Ignore cache parse errors and fall through to network fetch.
      }
    }

    setBriefing("");

    try {
      const res = await fetch("/api/policy/briefing", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(props),
      });

      if (!res.ok) {
        if (res.status === 503) {
          setError("AI service unavailable");
        } else {
          setError(`Error ${res.status}`);
        }
        setIsLoading(false);
        return;
      }

      const reader = res.body?.getReader();
      if (!reader) {
        setError("No stream available");
        setIsLoading(false);
        return;
      }

      const decoder = new TextDecoder();
      let fullText = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value, { stream: true });
        fullText += chunk;
        setBriefing(fullText);
      }

      if (typeof window !== "undefined" && fullText.trim().length > 0) {
        localStorage.setItem(
          cacheKey,
          JSON.stringify({ text: fullText, ts: Date.now() }),
        );
      }

      setIsLoading(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load");
      setIsLoading(false);
    }
  }, [cacheKey, props]);

  useEffect(() => {
    fetchBriefing();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Determine threat color for the border
  const score = props.regime.score;
  const borderColor =
    score >= 65
      ? "border-red-500/40"
      : score >= 50
        ? "border-orange-500/30"
        : score >= 35
          ? "border-amber-500/20"
          : "border-green-500/20";

  const glowColor =
    score >= 65
      ? "shadow-red-500/10"
      : score >= 50
        ? "shadow-orange-500/10"
        : "shadow-transparent";

  return (
    <div
      className={`relative bg-[#0a0a0a] border ${borderColor} rounded-2xl p-6 md:p-8 shadow-lg ${glowColor} overflow-hidden`}
    >
      {/* AI badge */}
      <div className="flex items-center mb-4">
        <div className="flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-cyan-400" />
          <span className="text-xs font-mono uppercase tracking-widest text-cyan-400/80">
            AI Policy Briefing
          </span>
          <span className="text-[10px] bg-cyan-900/30 text-cyan-400/60 px-1.5 py-0.5 rounded border border-cyan-800/30">
            Anthropic
          </span>
        </div>
      </div>

      {/* Content */}
      {error ? (
        <div className="flex items-center gap-2 text-amber-400/80 text-sm">
          <AlertTriangle className="w-4 h-4 flex-shrink-0" />
          <span>{error}</span>
        </div>
      ) : isLoading && !briefing ? (
        <div className="space-y-2">
          <div className="h-4 bg-slate-800 rounded animate-pulse w-full" />
          <div className="h-4 bg-slate-800 rounded animate-pulse w-5/6" />
          <div className="h-4 bg-slate-800 rounded animate-pulse w-4/6" />
        </div>
      ) : (
        <div className="text-sm text-slate-300 leading-relaxed whitespace-pre-wrap">
          {briefing}
          {isLoading && (
            <span className="inline-block w-2 h-4 bg-cyan-400 ml-0.5 animate-pulse" />
          )}
        </div>
      )}
    </div>
  );
}
