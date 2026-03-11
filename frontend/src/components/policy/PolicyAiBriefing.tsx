"use client";

/**
 * PolicyAiBriefing — Streams a Claude-generated policy intelligence briefing.
 *
 * Uses the Vercel AI SDK useCompletion hook to stream text from
 * /api/policy/briefing. Shows a pulsing indicator while generating,
 * then renders the full briefing with a subtle AI badge.
 */

import { useCallback, useEffect, useState } from "react";
import { Sparkles } from "lucide-react";

const MORNING_REFRESH_UTC_HOUR = 10;

function getMorningRefreshBoundary(now = new Date()): number {
  const boundary = new Date(now);
  if (boundary.getUTCHours() < MORNING_REFRESH_UTC_HOUR) {
    boundary.setDate(boundary.getDate() - 1);
  }
  boundary.setUTCHours(MORNING_REFRESH_UTC_HOUR, 0, 0, 0);
  return boundary.getTime();
}

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
  dataVersion?: string;
}

export function PolicyAiBriefing(props: PolicyAiBriefingProps) {
  const [briefing, setBriefing] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const cacheKey = `policy-ai-briefing:v2:${props.regime.score}:${props.regime.label}:${props.dataVersion ?? "na"}`;

  const getLastDeliveredBriefing = useCallback((): string | null => {
    if (typeof window === "undefined") return null;
    let best: { text: string; ts: number } | null = null;
    for (let i = 0; i < localStorage.length; i += 1) {
      const key = localStorage.key(i);
      if (!key || !key.startsWith("policy-ai-briefing:v2:")) continue;
      try {
        const raw = localStorage.getItem(key);
        if (!raw) continue;
        const parsed = JSON.parse(raw) as { text?: string; ts?: number };
        if (typeof parsed.text !== "string" || typeof parsed.ts !== "number") continue;
        if (!best || parsed.ts > best.ts) {
          best = { text: parsed.text, ts: parsed.ts };
        }
      } catch {
        // Ignore malformed cache rows.
      }
    }
    return best?.text ?? null;
  }, []);

  const fetchBriefing = useCallback(async () => {
    setIsLoading(true);

    if (typeof window !== "undefined") {
      try {
        const cachedRaw = localStorage.getItem(cacheKey);
        if (cachedRaw) {
          const cached = JSON.parse(cachedRaw) as {
            text?: string;
            ts?: number;
          };
          if (typeof cached?.text === "string") {
            setBriefing(cached.text);
            if (
              typeof cached?.ts === "number" &&
              cached.ts >= getMorningRefreshBoundary()
            ) {
              setIsLoading(false);
              return;
            }
          }
        }
      } catch {
        // Ignore cache parse errors and fall through to network fetch.
      }
    }

    if (!briefing) {
      const lastDelivered = getLastDeliveredBriefing();
      if (lastDelivered) setBriefing(lastDelivered);
    }

    try {
      const res = await fetch("/api/policy/briefing", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(props),
      });

      if (!res.ok) {
        setIsLoading(false);
        return;
      }

      const reader = res.body?.getReader();
      if (!reader) {
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
      void err;
      setIsLoading(false);
    }
  }, [briefing, cacheKey, getLastDeliveredBriefing, props]);

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
      {isLoading && !briefing ? (
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
