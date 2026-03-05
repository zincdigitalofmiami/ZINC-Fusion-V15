'use client';

import React, { useEffect, useMemo, useState } from 'react';

interface ForecastTarget {
  id: string;
  horizonDays: number;
  horizonLabel: string;
  priceLow: number;
  priceHigh: number;
  oofPrice: number;
  coveragePct: number | null;
}

interface ForecastTargetsResponse {
  asOfDate?: string;
  targets?: ForecastTarget[];
}

const BIN_COUNT = 11;

function clamp(v: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, v));
}

function cellAlpha(price: number, t: ForecastTarget): number {
  const low = Math.min(t.priceLow, t.priceHigh);
  const high = Math.max(t.priceLow, t.priceHigh);
  const halfWidth = Math.max((high - low) / 2, 0.1);
  const centerDist = Math.abs(price - t.oofPrice) / halfWidth;
  const insideZone = price >= low && price <= high;

  if (insideZone) {
    return clamp(1 - centerDist * 0.75, 0.25, 1);
  }

  const outsideDist = Math.abs(price - t.oofPrice) / (halfWidth * 2.5);
  return clamp(0.18 - outsideDist * 0.12, 0.04, 0.18);
}

export function ProbabilityHeatmap() {
  const [targets, setTargets] = useState<ForecastTarget[]>([]);
  const [asOfDate, setAsOfDate] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadTargets() {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch('/api/zl/forecast-targets', { cache: 'no-store' });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json = (await res.json()) as ForecastTargetsResponse;
        if (cancelled) return;
        setTargets(
          (json.targets ?? [])
            .filter(
              (t): t is ForecastTarget =>
                typeof t?.horizonDays === 'number' &&
                typeof t?.priceLow === 'number' &&
                typeof t?.priceHigh === 'number' &&
                typeof t?.oofPrice === 'number',
            )
            .sort((a, b) => a.horizonDays - b.horizonDays),
        );
        setAsOfDate(json.asOfDate ?? null);
      } catch (e) {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : 'Failed to load target zones');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    loadTargets();
    return () => {
      cancelled = true;
    };
  }, []);

  const priceBins = useMemo(() => {
    if (targets.length === 0) return [] as number[];
    const low = Math.min(...targets.map((t) => Math.min(t.priceLow, t.priceHigh)));
    const high = Math.max(...targets.map((t) => Math.max(t.priceLow, t.priceHigh)));
    if (!Number.isFinite(low) || !Number.isFinite(high)) return [] as number[];

    const span = Math.max(high - low, 1);
    const min = low - span * 0.05;
    const max = high + span * 0.05;
    const step = (max - min) / (BIN_COUNT - 1);

    return Array.from(
      { length: BIN_COUNT },
      (_, idx) => Number((max - idx * step).toFixed(2)),
    );
  }, [targets]);

  const gridTemplateColumns = `56px repeat(${Math.max(targets.length, 1)}, minmax(0,1fr))`;

  return (
    <div className="w-full bg-[#0a0a0a] border border-white/5 rounded-xl p-6 shadow-sm overflow-hidden">
      <div className="flex items-center justify-between mb-2">
        <div>
          <h3 className="text-sm font-semibold text-white uppercase tracking-wider">L3 Probability Surface</h3>
          <p className="text-xs text-slate-500">
            Real target zone density from latest production forecast
            {asOfDate ? ` (as of ${asOfDate})` : ''}
          </p>
        </div>
        <div className="flex items-center gap-3 text-[10px] text-slate-500">
          <div className="flex items-center gap-1">
            <span className="inline-block w-2 h-2 rounded-[1px] bg-cyan-400/90" />
            High
          </div>
          <div className="flex items-center gap-1">
            <span className="inline-block w-2 h-2 rounded-[1px] bg-cyan-400/20" />
            Low
          </div>
        </div>
      </div>

      {loading && (
        <div className="mt-6 text-sm text-slate-400">Loading forecast density...</div>
      )}

      {!loading && error && (
        <div className="mt-6 text-sm text-red-400">Failed to load probability data: {error}</div>
      )}

      {!loading && !error && targets.length === 0 && (
        <div className="mt-6 text-sm text-slate-400">
          No production target zones available yet. This view populates automatically once forecast rows are present.
        </div>
      )}

      {!loading && !error && targets.length > 0 && (
        <div className="mt-6 space-y-2">
          <div className="grid gap-1" style={{ gridTemplateColumns }}>
            <div />
            {targets.map((t) => (
              <div key={`h-${t.id}`} className="text-center text-[10px] text-slate-500 font-mono">
                {t.horizonLabel}
              </div>
            ))}

            {priceBins.map((price) => (
              <React.Fragment key={`row-${price}`}>
                <div className="text-[10px] text-slate-600 font-mono pr-2 text-right">
                  ${price.toFixed(2)}
                </div>
                {targets.map((t) => {
                  const alpha = cellAlpha(price, t);
                  return (
                    <div
                      key={`${t.id}-${price}`}
                      className="h-5 rounded-[2px] border border-white/5"
                      style={{
                        backgroundColor: `rgba(34, 211, 238, ${alpha})`,
                        boxShadow:
                          alpha > 0.75 ? '0 0 10px rgba(34, 211, 238, 0.35)' : 'none',
                      }}
                      title={`${t.horizonLabel} | zone $${t.priceLow.toFixed(2)}-$${t.priceHigh.toFixed(2)} | median $${t.oofPrice.toFixed(2)}`}
                    />
                  );
                })}
              </React.Fragment>
            ))}
          </div>

          <div className="grid gap-1 pt-2 border-t border-white/5" style={{ gridTemplateColumns }}>
            <div className="text-[10px] text-slate-600 font-mono pr-2 text-right">Coverage</div>
            {targets.map((t) => (
              <div key={`c-${t.id}`} className="text-center text-[10px] font-mono text-cyan-300/80">
                {t.coveragePct !== null ? `${t.coveragePct}%` : '--'}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
