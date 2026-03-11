"use client";

import { useEffect, useState } from "react";

const MORNING_REFRESH_UTC_HOUR = 10;

function getMorningRefreshBoundary(now = new Date()): number {
  const boundary = new Date(now);
  if (boundary.getUTCHours() < MORNING_REFRESH_UTC_HOUR) {
    boundary.setDate(boundary.getDate() - 1);
  }
  boundary.setUTCHours(MORNING_REFRESH_UTC_HOUR, 0, 0, 0);
  return boundary.getTime();
}

interface Props {
  section: "agency" | "executive" | "news";
  regime: { score: number; label: string };
  data: Array<Record<string, unknown>>;
  dataVersion?: string;
}

const SECTION_TITLES: Record<string, string> = {
  agency: "AI Agency Intel",
  executive: "AI Executive Action Synthesis",
  news: "AI News Intel Synthesis",
};

export function PolicySectionBrief({ section, regime, data, dataVersion }: Props) {
  const [text, setText] = useState("");
  const [done, setDone] = useState(false);

  const getLastDeliveredSection = (prefix: string): string | null => {
    if (typeof window === "undefined") return null;
    let best: { text: string; ts: number } | null = null;
    for (let i = 0; i < localStorage.length; i += 1) {
      const key = localStorage.key(i);
      if (!key || !key.startsWith(prefix)) continue;
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
  };

  useEffect(() => {
    setDone(false);

    (async () => {
      const cacheKey = `policy-section-brief:v2:${section}:${regime.score}:${regime.label}:${dataVersion ?? "na"}`;
      const cachePrefix = `policy-section-brief:v2:${section}:`;
      try {
        if (typeof window !== "undefined") {
          const cachedRaw = localStorage.getItem(cacheKey);
          if (cachedRaw) {
            const cached = JSON.parse(cachedRaw) as { text?: string; ts?: number };
            if (typeof cached?.text === "string") {
              setText(cached.text);
              if (
                typeof cached?.ts === "number" &&
                cached.ts >= getMorningRefreshBoundary()
              ) {
                setDone(true);
                return;
              }
            }
          }

          const lastDelivered = getLastDeliveredSection(cachePrefix);
          if (lastDelivered) {
            setText(lastDelivered);
          }
        }

        const res = await fetch("/api/policy/section-brief", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ section, regime, data }),
        });
        if (!res.ok || !res.body) {
          setDone(true);
          return;
        }
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buf = "";
        while (true) {
          const { done: streamDone, value } = await reader.read();
          if (streamDone) break;
          buf += decoder.decode(value, { stream: true });
          setText(buf);
        }
        setText(buf);

        if (typeof window !== "undefined" && buf.trim().length > 0) {
          localStorage.setItem(
            cacheKey,
            JSON.stringify({ text: buf, ts: Date.now() }),
          );
        }
      } catch {
        /* silent */
      } finally {
        setDone(true);
      }
    })();
  }, [section, regime, data, dataVersion]);

  if (!text && !done) {
    return (
      <div className="bg-white/[0.02] border border-white/5 rounded-xl p-4 mb-4">
        <div className="h-4 w-2/3 bg-white/5 rounded animate-pulse" />
      </div>
    );
  }

  if (!text) return null;

  return (
    <div className="bg-white/[0.02] border border-white/5 rounded-xl p-4 mb-4">
      <div className="text-xs text-white uppercase tracking-widest font-bold mb-2">
        {SECTION_TITLES[section] ?? "AI Analysis"}
      </div>
      <p className="text-sm text-slate-300 leading-relaxed">{text}</p>
    </div>
  );
}
