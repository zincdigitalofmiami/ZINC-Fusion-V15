"use client";

import { useEffect, useRef, useState } from "react";
import { AreaSeries, ColorType, createChart, ISeriesApi } from "lightweight-charts";

type SeriesPoint = { time: string; value: number };

type QuantileRow = {
  as_of_date: string;
  horizon_days: number;
  p10: number;
  p50: number;
  p90: number;
};

function addDays(isoDate: string, days: number) {
  const date = new Date(isoDate);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

function groupForecasts(rows: QuantileRow[]) {
  const grouped = new Map<number, { p10: SeriesPoint[]; p50: SeriesPoint[]; p90: SeriesPoint[] }>();
  rows.forEach((row) => {
    if (!row.as_of_date) return;
    const targetDate = addDays(row.as_of_date, row.horizon_days);
    const entry = grouped.get(row.horizon_days) || { p10: [], p50: [], p90: [] };
    entry.p10.push({ time: targetDate, value: row.p10 });
    entry.p50.push({ time: targetDate, value: row.p50 });
    entry.p90.push({ time: targetDate, value: row.p90 });
    grouped.set(row.horizon_days, entry);
  });
  return grouped;
}

export function HeroChart() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<ReturnType<typeof createChart> | null>(null);
  const seriesRef = useRef<{
    base?: ISeriesApi<"Area">;
    overlays: ISeriesApi<"Area">[];
  }>({ overlays: [] });
  const [priceSeries, setPriceSeries] = useState<SeriesPoint[]>([]);
  const [forecastRows, setForecastRows] = useState<QuantileRow[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchPrice = async () => {
      const response = await fetch(`/api/market/zl`, { cache: "no-store" });
      if (!response.ok) {
        const detail = await response.json().catch(() => ({}));
        throw new Error(detail?.detail || `market/zl failed (${response.status})`);
      }
      const payload = await response.json();
      setPriceSeries(payload.series || []);
    };

    const fetchForecasts = async () => {
      const response = await fetch(`/api/forecast/quantiles?symbol=ZL`, { cache: "no-store" });
      if (!response.ok) {
        const detail = await response.json().catch(() => ({}));
        throw new Error(detail?.detail || `forecast/quantiles failed (${response.status})`);
      }
      const payload = await response.json();
      setForecastRows(payload.quantiles || []);
    };

    (async () => {
      try {
        setError(null);
        await Promise.all([fetchPrice(), fetchForecasts()]);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unknown error");
      }
    })();
  }, []);

  useEffect(() => {
    if (!containerRef.current || chartRef.current) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "#0A0E1A" },
        textColor: "#9CA3AF",
        fontSize: 12,
      },
      grid: {
        vertLines: { color: "rgba(255, 255, 255, 0.05)" },
        horzLines: { color: "rgba(255, 255, 255, 0.05)" },
      },
      rightPriceScale: {
        borderVisible: false,
      },
      timeScale: {
        borderVisible: false,
      },
      crosshair: {
        vertLine: { color: "rgba(255, 255, 255, 0.08)" },
        horzLine: { color: "rgba(255, 255, 255, 0.08)" },
      },
      handleScroll: {
        vertTouchDrag: false,
      },
    });

    chartRef.current = chart;

    const resizeObserver = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) return;
      const { width, height } = entry.contentRect;
      chart.applyOptions({ width, height });
      chart.timeScale().fitContent();
    });

    resizeObserver.observe(containerRef.current);

    return () => {
      resizeObserver.disconnect();
      chart.remove();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!chartRef.current || priceSeries.length === 0) return;

    const chart = chartRef.current;
    if (!seriesRef.current.base) {
      seriesRef.current.base = chart.addSeries(AreaSeries, {
        lineColor: "#2962FF",
        topColor: "rgba(41, 98, 255, 0.45)",
        bottomColor: "rgba(41, 98, 255, 0.02)",
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: true,
      });
    }

    seriesRef.current.base.setData(priceSeries);

    seriesRef.current.overlays.forEach((series) => chart.removeSeries(series));
    seriesRef.current.overlays = [];

    const grouped = groupForecasts(forecastRows);
    const horizonColors: Record<number, { line: string; fill: string }> = {
      7: { line: "#3B82F6", fill: "rgba(59, 130, 246, 0.18)" },
      30: { line: "#0EA5E9", fill: "rgba(14, 165, 233, 0.14)" },
      90: { line: "#14B8A6", fill: "rgba(20, 184, 166, 0.12)" },
      180: { line: "#10B981", fill: "rgba(16, 185, 129, 0.10)" },
      365: { line: "#6366F1", fill: "rgba(99, 102, 241, 0.08)" },
    };

    grouped.forEach((series, horizon) => {
      const colors = horizonColors[horizon] || {
        line: "#94A3B8",
        fill: "rgba(148, 163, 184, 0.06)",
      };

      const p50Series = chart.addSeries(AreaSeries, {
        lineColor: colors.line,
        topColor: colors.fill,
        bottomColor: "rgba(0, 0, 0, 0)",
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
      });
      p50Series.setData(series.p50);
      seriesRef.current.overlays.push(p50Series);

      const p10Series = chart.addSeries(AreaSeries, {
        lineColor: "rgba(148, 163, 184, 0)",
        topColor: "rgba(148, 163, 184, 0.04)",
        bottomColor: "rgba(0, 0, 0, 0)",
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
      });
      p10Series.setData(series.p10);
      seriesRef.current.overlays.push(p10Series);

      const p90Series = chart.addSeries(AreaSeries, {
        lineColor: "rgba(148, 163, 184, 0)",
        topColor: "rgba(148, 163, 184, 0.04)",
        bottomColor: "rgba(0, 0, 0, 0)",
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
      });
      p90Series.setData(series.p90);
      seriesRef.current.overlays.push(p90Series);
    });

    chart.timeScale().fitContent();
  }, [priceSeries, forecastRows]);

  return (
    <section className="w-full">
      <div className="mx-auto w-full max-w-6xl px-6 pt-8">
        {error ? (
          <div className="mb-6 rounded-lg border border-red-500/30 bg-card-bg p-4 text-sm text-text-secondary">
            <div className="font-semibold text-text-primary">Chart data failed to load.</div>
            <div className="mt-1 text-text-tertiary">{error}</div>
          </div>
        ) : null}
        <div className="mb-4 flex items-center justify-between text-xs text-text-tertiary">
          <div className="flex items-center gap-2">
            <span className="rounded-full border border-white/10 px-3 py-1">1D</span>
            <span className="rounded-full border border-white/10 px-3 py-1">1W</span>
            <span className="rounded-full border border-white/10 px-3 py-1">1M</span>
            <span className="rounded-full border border-white/10 px-3 py-1">1Y</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="rounded-full border border-white/10 px-3 py-1">1-line legend</span>
            <span className="rounded-full border border-white/10 px-3 py-1">3-line legend</span>
          </div>
        </div>
      </div>
      <div className="relative left-1/2 right-1/2 h-[70vh] w-screen -translate-x-1/2 overflow-hidden">
        <div ref={containerRef} className="h-full w-full" />
      </div>
    </section>
  );
}
