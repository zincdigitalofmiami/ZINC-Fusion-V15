"use client";

import { useEffect, useState } from "react";

type Summary = {
  symbol: string;
  as_of_date: string | null;
  price: number | null;
  previous_price: number | null;
  abs_change: number | null;
  pct_change: number | null;
  procurement_action: {
    as_of_date: string;
    action: string;
    confidence: number;
    rationale?: string | null;
  } | null;
};

function formatPct(value: number | null) {
  if (value === null || !Number.isFinite(value)) return "";
  const pct = value * 100;
  const sign = pct > 0 ? "+" : "";
  return `${sign}${pct.toFixed(2)}%`;
}

export function PulseStrip() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const run = async () => {
      try {
        setError(null);
        const response = await fetch(`/api/dashboard/summary?symbol=ZL`, { cache: "no-store" });
        if (!response.ok) {
          const detail = await response.json().catch(() => ({}));
          setError(detail?.detail || `dashboard/summary failed (${response.status})`);
          return;
        }
        const data = (await response.json()) as Summary;
        setSummary(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unknown error");
      }
    };
    run();
  }, []);

  return (
    <section className="mx-auto w-full max-w-6xl px-6 pt-8">
      {error ? (
        <div className="mb-6 rounded-lg border border-red-500/30 bg-card-bg p-4 text-sm text-text-secondary">
          <div className="font-semibold text-text-primary">Pulse failed to load.</div>
          <div className="mt-1 text-text-tertiary">{error}</div>
        </div>
      ) : null}
      <div className="grid grid-cols-1 gap-6 rounded-lg border border-white/10 bg-card-bg p-6 md:grid-cols-3">
        <div>
          <div className="text-xs font-medium uppercase tracking-wide text-text-tertiary">
            ZL Price
          </div>
          <div className="mt-2 flex items-baseline gap-3">
            <div className="text-3xl font-bold font-mono text-text-primary">
              {summary?.price ?? ""}
            </div>
            <div className="text-sm font-mono text-text-tertiary">
              {formatPct(summary?.pct_change ?? null)}
            </div>
          </div>
          <div className="mt-2 text-xs text-text-tertiary">
            {summary?.as_of_date ? `As of ${summary.as_of_date}` : ""}
          </div>
        </div>

        <div>
          <div className="text-xs font-medium uppercase tracking-wide text-text-tertiary">
            Pulse
          </div>
          <div className="mt-2 text-sm text-text-secondary">
            {summary?.procurement_action?.action
              ? `${summary.procurement_action.action} (${Math.round((summary.procurement_action.confidence || 0) * 100)}%)`
              : "No procurement action available."}
          </div>
          {summary?.procurement_action?.rationale ? (
            <div className="mt-2 text-xs text-text-tertiary">
              {summary.procurement_action.rationale}
            </div>
          ) : null}
        </div>

        <div>
          <div className="text-xs font-medium uppercase tracking-wide text-text-tertiary">
            Mode
          </div>
          <div className="mt-2 text-sm text-text-secondary">Read-only fusion layer</div>
          <div className="mt-2 text-xs text-text-tertiary">No trading UI</div>
        </div>
      </div>
    </section>
  );
}
