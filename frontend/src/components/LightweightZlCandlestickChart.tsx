"use client";

import React, { useEffect, useRef, useState } from "react";
import Image from "next/image";
import {
  createChart,
  CandlestickSeries,
  ColorType,
  IChartApi,
  ISeriesApi,
  UTCTimestamp,
  LineStyle,
  CandlestickData,
  WhitespaceData,
} from "lightweight-charts";
import { ensureFutureWhitespace } from "@/lib/charts/ensureFutureWhitespace";
import {
  ForecastTargetsPrimitive,
  type ForecastTarget,
} from "@/lib/charts/ForecastTargetsPrimitive";

interface PriceData {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

// TradingView exact settings (from user screenshots)
const THEME = {
  // Candle body colors
  upColor: "#26C6DA",
  downColor: "#FF0000",
  // Borders: 0% opacity (transparent per TradingView settings)
  borderUpColor: "transparent",
  borderDownColor: "transparent",
  // Wicks: White/light gray (NOT body color - per TradingView)
  wickUpColor: "#FFFFFF", // 100% white
  wickDownColor: "rgba(178,181,190,0.83)", // ~83% gray
  // Grid: 4-7% opacity (TradingView default)
  gridColor: "rgba(255,255,255,0.04)",
  // Crosshair
  crosshairColor: "rgba(139,92,246,0.6)",
  labelBgColor: "rgba(20,10,40,0.9)",
  textColor: "rgba(255,255,255,0.4)",
};

const DAILY_REFRESH_INTERVAL_MS = 300_000; // refresh daily bars every 5m
const LIVE_TICKER_INTERVAL_MS  = 10_000;  // refresh live price ticker every 10s
const INITIAL_VISIBLE_BARS = 150;
const RIGHT_PADDING_BARS = 16;

export function LightweightZlCandlestickChart({
  height = "70vh",
}: {
  height?: string | number;
}) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const fitContentCalledRef = useRef(false);
  const forecastPrimitiveRef = useRef<ForecastTargetsPrimitive | null>(null);

  // Keep a stable reference for change detection during 5-minute refreshes.
  const priceDataRef = useRef<PriceData[]>([]);

  const [priceData, setPriceData] = useState<PriceData[]>([]);
  const [lastPrice, setLastPrice] = useState<number | null>(null);
  const [priceChange, setPriceChange] = useState<number>(0);
  const [volatility, setVolatility] = useState<string>("--");
  const [highPrice, setHighPrice] = useState<number | null>(null);
  const [lowPrice, setLowPrice] = useState<number | null>(null);
  const [isLive, setIsLive] = useState<boolean>(false);
  const [lastUpdate, setLastUpdate] = useState<string>("");
  const [forecastTargets, setForecastTargets] = useState<ForecastTarget[]>([]);

  // Fetch historical data (daily bars)
  useEffect(() => {
    const fetchData = async () => {
      try {
        const res = await fetch("/api/zl/price-1d?days=730"); // ~2 years of daily data
        if (!res.ok) throw new Error("Failed to fetch");
        const json = await res.json();
        if (json.data && json.data.length > 0) {
          const parsed = json.data.map((d: PriceData) => ({
            ...d,
            open: parseFloat(String(d.open)),
            high: parseFloat(String(d.high)),
            low: parseFloat(String(d.low)),
            close: parseFloat(String(d.close)),
            volume: parseFloat(String(d.volume)),
          }));
          // Only update state if data actually changed (prevents chart recreation).
          // Compare length + latest close/high/low so that an intraday live-rollup
          // bar updating its range triggers a re-render even when close is unchanged.
          const oldData = priceDataRef.current;
          const oldLast = oldData[oldData.length - 1];
          const newLast = parsed[parsed.length - 1];
          const changed =
            oldData.length !== parsed.length ||
            oldLast?.close !== newLast?.close ||
            oldLast?.high  !== newLast?.high  ||
            oldLast?.low   !== newLast?.low;
          priceDataRef.current = parsed;
          if (changed) setPriceData(parsed);
          const latest = parsed[parsed.length - 1];
          const prev = parsed[parsed.length - 2];
          setLastPrice(latest.close);

          const highs = parsed.map((d: PriceData) => d.high);
          const lows = parsed.map((d: PriceData) => d.low);
          const h = Math.max(...highs);
          const l = Math.min(...lows);
          setHighPrice(h);
          setLowPrice(l);

          if (prev) {
            setPriceChange(((latest.close - prev.close) / prev.close) * 100);
          }

          setIsLive(Boolean(json.live_rollup));
          if (json.live_rollup_latest_intraday_ts) {
            setLastUpdate(
              new Date(
                json.live_rollup_latest_intraday_ts,
              ).toLocaleTimeString(),
            );
          } else {
            setLastUpdate(new Date().toLocaleTimeString());
          }

          // Calculate 20-day volatility
          const last20 = parsed.slice(-20);
          if (last20.length >= 2) {
            const returns: number[] = [];
            for (let i = 1; i < last20.length; i++) {
              returns.push(Math.log(last20[i].close / last20[i - 1].close));
            }
            const mean =
              returns.reduce((a: number, b: number) => a + b, 0) /
              returns.length;
            const variance =
              returns.reduce(
                (a: number, b: number) => a + Math.pow(b - mean, 2),
                0,
              ) / returns.length;
            const dailyVol = Math.sqrt(variance);
            const annualizedVol = dailyVol * Math.sqrt(252) * 100;
            setVolatility(annualizedVol.toFixed(1) + "%");
          }
        }
      } catch (err) {
        console.error("Fetch error:", err);
      }
    };
    fetchData();
    const interval = setInterval(fetchData, DAILY_REFRESH_INTERVAL_MS);
    return () => clearInterval(interval);
  }, []);

  // Live price ticker — polls /api/zl/live every 10s to update the last candle and header
  // in real-time without rebuilding the full chart from 730 daily bars.
  useEffect(() => {
    const fetchLive = async () => {
      try {
        const res = await fetch("/api/zl/live");
        if (!res.ok) return;
        const json = await res.json();
        if (!json.price) return;

        const livePrice: number = parseFloat(String(json.price));
        const liveOpen: number  = parseFloat(String(json.open  ?? json.price));
        const liveHigh: number  = parseFloat(String(json.high  ?? json.price));
        const liveLow: number   = parseFloat(String(json.low   ?? json.price));

        // Update header stats
        setLastPrice(livePrice);
        setIsLive(Boolean(json.live));
        if (json.timestamp) {
          setLastUpdate(new Date(json.timestamp).toLocaleTimeString());
        }
        if (json.change_pct != null) {
          setPriceChange(parseFloat(String(json.change_pct)));
        }
        // Update today's high/low displayed in header
        if (Number.isFinite(liveHigh) && Number.isFinite(liveLow)) {
          setHighPrice(liveHigh);
          setLowPrice(liveLow);
        }

        // Patch the last candle in-place — no full chart rebuild needed.
        // This is the key to showing a live-updating rightmost bar.
        if (candleSeriesRef.current && priceDataRef.current.length > 0) {
          const lastBar = priceDataRef.current[priceDataRef.current.length - 1];
          const barTime = Math.floor(
            new Date(lastBar.timestamp).getTime() / 1000,
          ) as UTCTimestamp;
          candleSeriesRef.current.update({
            time: barTime,
            open:  liveOpen,
            high:  Math.max(liveHigh, lastBar.high),
            low:   Math.min(liveLow,  lastBar.low),
            close: livePrice,
          });
        }
      } catch {
        // Live ticker errors are non-fatal — chart continues showing cached data
      }
    };

    // Run immediately, then on interval
    fetchLive();
    const interval = setInterval(fetchLive, LIVE_TICKER_INTERVAL_MS);
    return () => clearInterval(interval);
  }, []);

  // Fetch forecast targets (separate from price data — non-blocking, fail-safe)
  useEffect(() => {
    let cancelled = false;
    async function fetchTargets() {
      try {
        const res = await fetch("/api/zl/forecast-targets");
        if (!res.ok) {
          if (!cancelled) setForecastTargets([]);
          return;
        }
        const json = await res.json();
        if (cancelled) return;
        if (!json.targets || json.targets.length === 0) {
          setForecastTargets([]);
          return;
        }

        const mapped: ForecastTarget[] = json.targets.map(
          (t: {
            id: string;
            kind: "ENTRY" | "TP" | "SL";
            label: string;
            horizonLabel?: string;
            horizonDays: number;
            asOfDate: string;
            forecastDate: string;
            oofPrice: number;
            priceLow: number;
            priceHigh: number;
            mae: number | null;
            probabilityMethod?: string;
            probabilityZone?: string;
            coveragePct?: number;
          }) => ({
            id: t.id,
            kind: t.kind,
            label: t.label,
            horizonLabel: t.horizonLabel,
            startTime: Math.floor(
              new Date(t.asOfDate).getTime() / 1000,
            ) as UTCTimestamp,
            endTime: Math.floor(
              new Date(t.forecastDate).getTime() / 1000,
            ) as UTCTimestamp,
            oofPrice: t.oofPrice,
            priceLow: t.priceLow,
            priceHigh: t.priceHigh,
            mae: t.mae,
            probabilityMethod: t.probabilityMethod,
            probabilityZone: t.probabilityZone,
            coveragePct: t.coveragePct,
            asOfDate: t.asOfDate,
            horizonDays: t.horizonDays,
          }),
        );

        const validTargets = mapped.filter(
          (t) =>
            Number.isFinite(t.startTime as number) &&
            Number.isFinite(t.endTime as number) &&
            Number.isFinite(t.oofPrice) &&
            Number.isFinite(t.priceLow) &&
            Number.isFinite(t.priceHigh),
        );

        setForecastTargets(validTargets);
      } catch {
        // Forecast overlay is optional — never break the chart
        if (!cancelled) setForecastTargets([]);
      }
    }
    fetchTargets();
    return () => {
      cancelled = true;
    };
  }, []);

  // Initialize chart
  useEffect(() => {
    if (!chartContainerRef.current || priceData.length === 0) return;

    // Clean up previous chart
    if (chartRef.current) {
      try { chartRef.current.remove(); } catch { /* already disposed */ }
      chartRef.current = null;
      candleSeriesRef.current = null;
      forecastPrimitiveRef.current = null;
      fitContentCalledRef.current = false;
    }

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: THEME.textColor,
        fontFamily: "Inter, sans-serif",
        fontSize: 11,
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: THEME.gridColor },
        horzLines: { color: THEME.gridColor },
      },
      crosshair: {
        vertLine: {
          color: THEME.crosshairColor,
          width: 1,
          style: LineStyle.Solid,
          labelBackgroundColor: THEME.labelBgColor,
        },
        horzLine: {
          color: THEME.crosshairColor,
          width: 1,
          style: LineStyle.Solid,
          labelBackgroundColor: THEME.labelBgColor,
        },
      },
      rightPriceScale: {
        borderColor: "transparent",
        autoScale: true,
        scaleMargins: {
          top: 0.05, // 5% padding at top (TradingView-tight)
          bottom: 0.05, // 5% padding at bottom
        },
      },
      timeScale: {
        borderColor: "transparent",
        timeVisible: false,
        fixLeftEdge: false, // Allow scroll back past data start
        fixRightEdge: false, // Allow scroll forward past data end
        rightOffset: RIGHT_PADDING_BARS,
        barSpacing: 8,
        minBarSpacing: 4,
      },
      // Interactions: axis drag to scroll, double-click to reset
      handleScroll: {
        mouseWheel: false, // Page scroll not hijacked
        pressedMouseMove: true, // Allow drag to pan horizontally
        horzTouchDrag: true, // Touch horizontal pan
        vertTouchDrag: false, // Allow page scroll on vertical swipe
      },
      handleScale: {
        mouseWheel: false, // No wheel zoom on plot area
        pinch: true, // Pinch to zoom on touch
        axisPressedMouseMove: { time: true, price: true },
        axisDoubleClickReset: { time: true, price: true }, // Double-click axis to reset
      },
    });

    chartRef.current = chart;

    // Transform price data to LWC format
    const candleData: CandlestickData<UTCTimestamp>[] = priceData.map((d) => ({
      time: Math.floor(new Date(d.timestamp).getTime() / 1000) as UTCTimestamp,
      open: d.open,
      high: d.high,
      low: d.low,
      close: d.close,
    }));

    // Sort chronologically
    candleData.sort((a, b) => (a.time as number) - (b.time as number));

    // Add candlestick series (TradingView exact: transparent borders, white/gray wicks)
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: THEME.upColor,
      downColor: THEME.downColor,
      borderUpColor: THEME.borderUpColor,
      borderDownColor: THEME.borderDownColor,
      wickUpColor: THEME.wickUpColor,
      wickDownColor: THEME.wickDownColor,
      priceLineVisible: true,
    });

    // If forecast targets exist, extend the time scale with whitespace so
    // zones can render to the right of the last candle.
    let seriesData: Array<
      CandlestickData<UTCTimestamp> | WhitespaceData<UTCTimestamp>
    > = candleData;
    if (forecastTargets.length > 0) {
      const maxEndTime = Math.max(
        ...forecastTargets.map((t) => t.endTime as number),
      ) as UTCTimestamp;
      seriesData = ensureFutureWhitespace(candleData, maxEndTime);
    }

    candleSeries.setData(seriesData);
    candleSeriesRef.current = candleSeries;

    // Attach forecast target zones as a series primitive overlay
    if (forecastTargets.length > 0) {
      const primitive = new ForecastTargetsPrimitive(forecastTargets);
      candleSeries.attachPrimitive(primitive);
      forecastPrimitiveRef.current = primitive;
    }

    // Set initial visible range to last 5 months (~150 bars) instead of all data
    if (!fitContentCalledRef.current && candleData.length > 0) {
      const totalBars = candleData.length;
      const visibleBars = Math.min(INITIAL_VISIBLE_BARS, totalBars); // 5 months or all if less
      const from = Math.max(0, totalBars - visibleBars);
      const to = Math.max(0, totalBars - 1) + RIGHT_PADDING_BARS;
      chart.timeScale().setVisibleLogicalRange({
        from,
        to,
      });
      fitContentCalledRef.current = true;
    }

    // Resize observer — guard against disposed chart
    let disposed = false;
    const resizeObserver = new ResizeObserver((entries) => {
      if (disposed || entries.length === 0 || !entries[0].target) return;
      const newRect = entries[0].contentRect;
      try {
        chart.applyOptions({ width: newRect.width, height: newRect.height });
      } catch { /* chart already disposed */ }
    });
    resizeObserver.observe(chartContainerRef.current);

    return () => {
      disposed = true;
      resizeObserver.disconnect();
      try { chart.remove(); } catch { /* already disposed */ }
    };
  }, [priceData, forecastTargets]);

  return (
    <div
      className="relative w-full rounded-xl overflow-hidden border border-white/5 flex flex-col"
      style={{
        background: "linear-gradient(180deg, #131722 0%, #0d1117 100%)",
        height: typeof height === "number" ? `${height}px` : height,
      }}
    >
      {/* Header - compact */}
      <div className="flex-shrink-0 flex items-center justify-between px-4 py-2 border-b border-white/5">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <div
              className={`w-2 h-2 rounded-full ${
                isLive
                  ? "bg-green-400 animate-pulse shadow-lg shadow-green-400/50"
                  : "bg-cyan-400 animate-pulse shadow-lg shadow-cyan-400/50"
              }`}
            />
            <span className="text-sm font-semibold text-white tracking-tight">
              ZL1!
            </span>
            {isLive && (
              <span className="px-1.5 py-0.5 text-[8px] font-bold bg-green-500/20 text-green-400 border border-green-500/30 rounded uppercase tracking-wider">
                LIVE
              </span>
            )}
          </div>
          <span className="text-[11px] text-white/30 font-medium">
            Soybean Oil • 1D
          </span>
          {lastUpdate && (
            <span className="text-[9px] text-white/20 font-mono">
              {lastUpdate}
            </span>
          )}
        </div>
        <div className="flex items-center gap-4">
          {highPrice && lowPrice && (
            <div className="flex items-center gap-3 text-[11px]">
              <div className="flex items-center gap-1">
                <span className="text-white/30">H</span>
                <span className="text-white/60 font-mono">
                  {highPrice.toFixed(2)}
                </span>
              </div>
              <div className="flex items-center gap-1">
                <span className="text-white/30">L</span>
                <span className="text-white/60 font-mono">
                  {lowPrice.toFixed(2)}
                </span>
              </div>
            </div>
          )}
          <div className="h-3 w-px bg-white/10" />
          <div className="flex items-center gap-1 px-1.5 py-0.5 rounded bg-white/5">
            <span className="text-[9px] text-white/30 uppercase">IV</span>
            <span className="text-[11px] font-mono text-violet-400">
              {volatility}
            </span>
          </div>
          {lastPrice && (
            <div className="flex items-center gap-2">
              <span className="text-xl font-semibold text-white tabular-nums">
                {lastPrice.toFixed(2)}
              </span>
              <span
                className="text-xs font-medium tabular-nums"
                style={{ color: priceChange >= 0 ? "#26C6DA" : "#EC0000" }}
              >
                {priceChange >= 0 ? "+" : ""}
                {priceChange.toFixed(2)}%
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Chart area */}
      <div className="relative w-full flex-1 min-h-0">
        {/* Watermark (DOM overlay - 10% opacity per TradingView) */}
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none z-0">
          <Image
            src="/chart_watermark.svg"
            alt=""
            width={280}
            height={140}
            className="opacity-[0.10]"
            style={{ filter: "grayscale(100%)" }}
            priority
          />
        </div>
        <div
          ref={chartContainerRef}
          style={{
            width: "100%",
            height: "100%",
            position: "absolute",
            top: 0,
            left: 0,
          }}
        />
      </div>

      {/* Legend */}
      <div className="flex-shrink-0 flex items-center justify-center gap-6 px-4 py-1.5 border-t border-white/5 bg-black/20">
        <div className="flex items-center gap-1.5">
          <div
            className="w-2.5 h-3 rounded-sm"
            style={{ backgroundColor: "#26C6DA" }}
          />
          <span className="text-[9px] text-white/40 uppercase">Bull</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div
            className="w-2.5 h-3 rounded-sm"
            style={{ backgroundColor: "#EC0000" }}
          />
          <span className="text-[9px] text-white/40 uppercase">Bear</span>
        </div>
      </div>
    </div>
  );
}
