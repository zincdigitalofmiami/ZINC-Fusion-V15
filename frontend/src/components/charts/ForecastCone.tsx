/**
 * ForecastCone - TradingView-style Price Target Visualization
 *
 * Shows historical price + forecast cone with P10/P50/P90 targets
 * Exactly like TradingView's "Price Target" chart with gradient fills
 */
'use client';

import React, { useMemo } from 'react';
import {
  ComposedChart,
  Area,
  Line,
  XAxis,
  YAxis,
  ResponsiveContainer,
  ReferenceDot,
  Tooltip,
} from 'recharts';

interface ForecastConeProps {
  historicalData: Array<{ date: string; price: number }>;
  currentPrice: number;
  forecast: {
    horizon: string;        // "1Y", "6M", etc
    p90: number;            // Max/ceiling
    p50: number;            // Expected/avg
    p10: number;            // Min/floor
    p90Pct: number;         // +35.01%
    p50Pct: number;         // +12.89%
    p10Pct: number;         // -17.07%
  };
  height?: number;
}

export function ForecastCone({
  historicalData,
  currentPrice,
  forecast,
  height = 300
}: ForecastConeProps) {

  // Build the combined data with cone projection
  const chartData = useMemo(() => {
    const historical = historicalData.map(d => ({
      date: d.date,
      price: d.price,
      isHistorical: true,
    }));

    // Current point (transition from history to forecast)
    const currentDate = historical[historical.length - 1]?.date || 'Now';

    // Forecast point (end of cone)
    const forecastDate = forecast.horizon;

    // Create cone data points
    const coneData = [
      {
        date: currentDate,
        price: currentPrice,
        p90: currentPrice,
        p50: currentPrice,
        p10: currentPrice,
        isCurrent: true,
      },
      {
        date: forecastDate,
        p90: forecast.p90,
        p50: forecast.p50,
        p10: forecast.p10,
        isForecast: true,
      },
    ];

    return { historical, coneData };
  }, [historicalData, currentPrice, forecast]);

  // Custom gradient definitions
  const bullGradientId = 'bullConeGradient';
  const bearGradientId = 'bearConeGradient';

  return (
    <div className="w-full" style={{ height }}>
      {/* Labels */}
      <div className="flex items-center justify-between mb-4 px-2">
        <div>
          <div className="text-xs text-[#787b86] uppercase tracking-wider">Price Target</div>
          <div className="text-2xl font-bold text-white">
            {currentPrice.toFixed(2)}
            <span className="text-sm ml-2 text-[#787b86]">USD</span>
            <span className={`text-sm ml-2 ${forecast.p50Pct >= 0 ? 'text-[#26a69a]' : 'text-[#ef5350]'}`}>
              {forecast.p50Pct >= 0 ? '+' : ''}{forecast.p50Pct.toFixed(2)}%
            </span>
          </div>
        </div>

        {/* Target labels - right side */}
        <div className="flex flex-col gap-1 text-right text-xs">
          <div className="flex items-center gap-2">
            <span className="text-[#787b86]">Max +{forecast.p90Pct.toFixed(2)}%</span>
            <span className="px-2 py-0.5 rounded bg-[#22ab94]/20 text-[#22ab94] font-mono">
              {forecast.p90.toFixed(2)}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[#787b86]">Avg +{forecast.p50Pct.toFixed(2)}%</span>
            <span className="px-2 py-0.5 rounded bg-[#ffb74d]/20 text-[#ffb74d] font-mono">
              {forecast.p50.toFixed(2)}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[#787b86]">Min {forecast.p10Pct.toFixed(2)}%</span>
            <span className="px-2 py-0.5 rounded bg-[#f06292]/20 text-[#f06292] font-mono">
              {forecast.p10.toFixed(2)}
            </span>
          </div>
        </div>
      </div>

      <ResponsiveContainer width="100%" height={height - 80}>
        <ComposedChart margin={{ top: 20, right: 80, bottom: 20, left: 20 }}>
          <defs>
            {/* Bull gradient (green fade) for upper cone */}
            <linearGradient id={bullGradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#22ab94" stopOpacity={0.3} />
              <stop offset="100%" stopColor="#22ab94" stopOpacity={0.05} />
            </linearGradient>

            {/* Bear gradient (red fade) for lower cone */}
            <linearGradient id={bearGradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#f06292" stopOpacity={0.05} />
              <stop offset="100%" stopColor="#f06292" stopOpacity={0.3} />
            </linearGradient>
          </defs>

          <XAxis
            dataKey="date"
            axisLine={{ stroke: 'rgba(255,255,255,0.1)' }}
            tickLine={false}
            tick={{ fill: '#787b86', fontSize: 11 }}
          />

          <YAxis
            domain={['auto', 'auto']}
            axisLine={false}
            tickLine={false}
            tick={{ fill: '#787b86', fontSize: 11 }}
            orientation="right"
            tickFormatter={(v) => v.toFixed(2)}
          />

          {/* Historical price line */}
          <Line
            data={chartData.historical}
            type="monotone"
            dataKey="price"
            stroke="#2962ff"
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />

          {/* Forecast cone - upper bound (P90) */}
          <Area
            data={chartData.coneData}
            type="linear"
            dataKey="p90"
            stroke="#22ab94"
            strokeWidth={1}
            strokeDasharray="4 2"
            fill={`url(#${bullGradientId})`}
            isAnimationActive={false}
          />

          {/* Forecast cone - lower bound (P10) */}
          <Area
            data={chartData.coneData}
            type="linear"
            dataKey="p10"
            stroke="#f06292"
            strokeWidth={1}
            strokeDasharray="4 2"
            fill={`url(#${bearGradientId})`}
            isAnimationActive={false}
          />

          {/* Expected path (P50) - dotted line */}
          <Line
            data={chartData.coneData}
            type="linear"
            dataKey="p50"
            stroke="#787b86"
            strokeWidth={1}
            strokeDasharray="4 2"
            dot={false}
            isAnimationActive={false}
          />

          {/* Current price dot */}
          <ReferenceDot
            x={chartData.historical[chartData.historical.length - 1]?.date}
            y={currentPrice}
            r={6}
            fill="#26a69a"
            stroke="#131722"
            strokeWidth={2}
          />

          <Tooltip
            contentStyle={{
              backgroundColor: '#1e222d',
              border: '1px solid rgba(255,255,255,0.1)',
              borderRadius: '4px',
            }}
            labelStyle={{ color: '#d1d4dc' }}
            formatter={(value) => [typeof value === 'number' ? value.toFixed(2) : '', 'Price']}
          />
        </ComposedChart>
      </ResponsiveContainer>

      {/* Time range buttons */}
      <div className="flex items-center gap-2 mt-2 px-2">
        <button className="px-3 py-1 rounded text-xs font-medium bg-[#2a2e39] text-[#787b86] hover:bg-[#363a45] transition-colors">
          PAST 2Y
        </button>
        <button className="px-3 py-1 rounded text-xs font-medium bg-[#2962ff]/20 text-[#2962ff] border border-[#2962ff]/30">
          {forecast.horizon} FORECAST
        </button>
      </div>
    </div>
  );
}

// =============================================================================
// Simplified version for dashboard cards
// =============================================================================

interface MiniConeProps {
  p90: number;
  p50: number;
  p10: number;
  horizon: string;
}

export function MiniForecastCone({ p90, p50, p10, horizon }: MiniConeProps) {
  return (
    <div className="relative h-32 w-full flex items-end">
      {/* Cone shape using CSS */}
      <div className="absolute inset-0 flex items-center justify-center">
        <svg viewBox="0 0 100 80" className="w-full h-full">
          {/* Gradient defs */}
          <defs>
            <linearGradient id="miniConeGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#22ab94" stopOpacity="0.3" />
              <stop offset="50%" stopColor="#787b86" stopOpacity="0.1" />
              <stop offset="100%" stopColor="#f06292" stopOpacity="0.3" />
            </linearGradient>
          </defs>

          {/* Cone triangle */}
          <polygon
            points="20,40 80,10 80,70"
            fill="url(#miniConeGrad)"
            stroke="rgba(255,255,255,0.1)"
            strokeWidth="0.5"
          />

          {/* P90 line */}
          <line x1="20" y1="40" x2="80" y2="10" stroke="#22ab94" strokeWidth="1" strokeDasharray="2 2" />

          {/* P50 line */}
          <line x1="20" y1="40" x2="80" y2="40" stroke="#787b86" strokeWidth="1" strokeDasharray="2 2" />

          {/* P10 line */}
          <line x1="20" y1="40" x2="80" y2="70" stroke="#f06292" strokeWidth="1" strokeDasharray="2 2" />

          {/* Current dot */}
          <circle cx="20" cy="40" r="4" fill="#26a69a" stroke="#131722" strokeWidth="1" />
        </svg>
      </div>

      {/* Labels */}
      <div className="absolute right-0 top-0 text-[10px] space-y-1">
        <div className="text-[#22ab94]">P90: {p90.toFixed(2)}</div>
        <div className="text-[#ffb74d]">P50: {p50.toFixed(2)}</div>
        <div className="text-[#f06292]">P10: {p10.toFixed(2)}</div>
      </div>

      <div className="absolute left-0 bottom-0 text-[10px] text-[#787b86]">
        {horizon}
      </div>
    </div>
  );
}

export default ForecastCone;
