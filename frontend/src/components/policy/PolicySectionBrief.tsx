"use client";

import { useEffect, useState, useRef } from "react";

interface Props {
  section: "agency" | "executive" | "news";
  regime: { score: number; label: string };
  data: Array<Record<string, unknown>>;
}

export function PolicySectionBrief({ section, regime, data }: Props) {
  const [text, setText] = useState("");
  const [done, setDone] = useState(false);
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;

    (async () => {
      try {
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
      <div className="flex items-start gap-2">
        <span className="text-xs text-slate-500 uppercase tracking-widest font-bold shrink-0 mt-0.5">
          AI
        </span>
        <p className="text-sm text-slate-300 leading-relaxed">{text}</p>
      </div>
    </div>
  );
}
