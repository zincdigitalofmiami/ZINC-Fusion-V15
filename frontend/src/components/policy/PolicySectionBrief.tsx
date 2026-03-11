"use client";

import { useEffect, useState, useRef } from "react";

const FOUR_HOURS_MS = 4 * 60 * 60 * 1000;

interface Props {
  section: "agency" | "executive" | "news";
  regime: { score: number; label: string };
  data: Array<Record<string, unknown>>;
}

const SECTION_TITLES: Record<string, string> = {
  agency: "AI Agency Intel",
  executive: "AI Executive Action Synthesis",
  news: "AI News Intel Synthesis",
};

export function PolicySectionBrief({ section, regime, data }: Props) {
  const [text, setText] = useState("");
  const [done, setDone] = useState(false);
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;

    (async () => {
      const cacheKey = `policy-section-brief:v1:${section}:${regime.score}:${regime.label}`;
      try {
        if (typeof window !== "undefined") {
          const cachedRaw = localStorage.getItem(cacheKey);
          if (cachedRaw) {
            const cached = JSON.parse(cachedRaw) as { text?: string; ts?: number };
            if (
              typeof cached?.text === "string" &&
              typeof cached?.ts === "number" &&
              Date.now() - cached.ts < FOUR_HOURS_MS
            ) {
              setText(cached.text);
              setDone(true);
              return;
            }
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
  }, [section, regime, data]);

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
