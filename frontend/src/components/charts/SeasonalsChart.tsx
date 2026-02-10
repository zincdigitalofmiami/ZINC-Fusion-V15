/**
 * SeasonalsChart - TradingView-style Multi-Year Overlay
 *
 * Shows price movements across years to identify seasonal patterns
 * 2026 (blue), 2025 (green), 2024 (orange) overlaid on same axis
 */
'use client';

import React, { useMemo } from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  ResponsiveContainer,
  Tooltip,
  ReferenceLine,
} from 'recharts';

interface YearData {
  year: number;
  data: Array<{ month: string; value: number }>;
  ytdReturn?: number;
}

interface SeasonalsChartProps {
  years: YearData[];
  height?: number;
  showYTDBadges?: boolean;
}

// Month abbreviations for x-axis
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

// Year colors - TradingView palette
const YEAR_COLORS: Record<number, string> = {
  2026: '#2962ff',  // Blue - current
  2025: '#26a69a',  // Teal/green
  2024: '#ff9800',  // Orange
  2023: '#9c27b0',  // Purple
  2022: '#e91e63',  // Pink
};

export function SeasonalsChart({
  years,
  height = 200,
  showYTDBadges = true,
}: SeasonalsChartProps) {

  // Normalize data - each year's data aligned by month
  const chartData = useMemo(() => {
    const normalizedData: Array<Record<string, number | string>> = MONTHS.map((month, i) => ({
      month,
      monthNum: i,
    }));

    years.forEach(yearData => {
      yearData.data.forEach((point, i) => {
        if (i < normalizedData.length) {
          normalizedData[i][`y${yearData.year}`] = point.value;
        }
      });
    });

    return normalizedData;
  }, [years]);

  // Get current month for reference line
  const currentMonth = new Date().getMonth();

  return (
    <div className="w-full">
      {/* Header with YTD badges */}
      <div className="flex items-center justify-between mb-2 px-2">
        <div className="text-xs text-[#787b86] uppercase tracking-wider">Seasonals</div>

        {showYTDBadges && (
          <div className="flex items-center gap-2">
            {years.map(yearData => {
              const color = YEAR_COLORS[yearData.year] || '#787b86';
              const ytd = yearData.ytdReturn ?? 0;
              return (
                <div
                  key={yearData.year}
                  className="flex items-center gap-1.5 px-2 py-0.5 rounded text-xs"
                  style={{
                    backgroundColor: `${color}20`,
                    borderLeft: `3px solid ${color}`,
                  }}
                >
                  <span style={{ color }}>{yearData.year}</span>
                  <span className={ytd >= 0 ? 'text-[#26a69a]' : 'text-[#ef5350]'}>
                    {ytd >= 0 ? '+' : ''}{ytd.toFixed(2)}%
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={chartData} margin={{ top: 10, right: 10, bottom: 10, left: 10 }}>
          <XAxis
            dataKey="month"
            axisLine={{ stroke: 'rgba(255,255,255,0.1)' }}
            tickLine={false}
            tick={{ fill: '#787b86', fontSize: 10 }}
            interval={0}
          />

          <YAxis
            domain={['auto', 'auto']}
            axisLine={false}
            tickLine={false}
            tick={{ fill: '#787b86', fontSize: 10 }}
            tickFormatter={(v) => `${v.toFixed(0)}%`}
            width={40}
          />

          {/* Reference line at 0% */}
          <ReferenceLine y={0} stroke="rgba(255,255,255,0.2)" strokeDasharray="3 3" />

          {/* Current month indicator */}
          <ReferenceLine
            x={MONTHS[currentMonth]}
            stroke="rgba(255,255,255,0.3)"
            strokeDasharray="3 3"
            label={{
              value: 'Now',
              position: 'top',
              fill: '#787b86',
              fontSize: 10,
            }}
          />

          {/* Year lines */}
          {years.map(yearData => {
            const color = YEAR_COLORS[yearData.year] || '#787b86';
            return (
              <Line
                key={yearData.year}
                type="monotone"
                dataKey={`y${yearData.year}`}
                stroke={color}
                strokeWidth={yearData.year === new Date().getFullYear() ? 2 : 1.5}
                dot={false}
                connectNulls
                isAnimationActive={false}
              />
            );
          })}

          <Tooltip
            contentStyle={{
              backgroundColor: '#1e222d',
              border: '1px solid rgba(255,255,255,0.1)',
              borderRadius: '4px',
              padding: '8px 12px',
            }}
            labelStyle={{ color: '#d1d4dc', marginBottom: 4 }}
            formatter={(value, name) => {
              const year = String(name).replace('y', '');
              const color = YEAR_COLORS[parseInt(year)] || '#787b86';
              return [
                <span key="v" style={{ color }}>{typeof value === 'number' ? value.toFixed(2) : ''}%</span>,
                year,
              ];
            }}
          />
        </LineChart>
      </ResponsiveContainer>

      {/* Description */}
      <p className="text-[10px] text-[#787b86] px-2 mt-1">
        Displays price movements over previous years to identify recurring trends.
      </p>
    </div>
  );
}

// =============================================================================
// Mini seasonals for sidebar widget
// =============================================================================

interface MiniSeasonalsProps {
  years: YearData[];
  height?: number;
}

export function MiniSeasonals({ years, height = 60 }: MiniSeasonalsProps) {
  const chartData = useMemo(() => {
    return MONTHS.map((month, i) => {
      const point: Record<string, number | string> = { month };
      years.forEach(y => {
        if (y.data[i]) {
          point[`y${y.year}`] = y.data[i].value;
        }
      });
      return point;
    });
  }, [years]);

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={chartData} margin={{ top: 5, right: 5, bottom: 5, left: 5 }}>
        {years.map(yearData => (
          <Line
            key={yearData.year}
            type="monotone"
            dataKey={`y${yearData.year}`}
            stroke={YEAR_COLORS[yearData.year] || '#787b86'}
            strokeWidth={1}
            dot={false}
            isAnimationActive={false}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

export default SeasonalsChart;
