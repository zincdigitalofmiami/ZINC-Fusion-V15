/**
 * PerformanceGrid - TradingView-style Returns Grid
 *
 * Shows 1W | 1M | 3M | 6M | YTD | 1Y performance in a clean grid
 */
'use client';

import React from 'react';
import TV from '@/lib/colors';

interface PerformanceData {
  period: '1W' | '1M' | '3M' | '6M' | 'YTD' | '1Y';
  value: number;  // percentage
}

interface PerformanceGridProps {
  data: PerformanceData[];
  columns?: 3 | 6;
}

const periodOrder = ['1W', '1M', '3M', '6M', 'YTD', '1Y'];

export function PerformanceGrid({ data, columns = 3 }: PerformanceGridProps) {
  // Sort by period order
  const sortedData = [...data].sort(
    (a, b) => periodOrder.indexOf(a.period) - periodOrder.indexOf(b.period)
  );

  return (
    <div
      className="grid gap-2"
      style={{
        gridTemplateColumns: `repeat(${columns}, 1fr)`,
      }}
    >
      {sortedData.map(item => {
        const isPositive = item.value >= 0;
        const bgColor = isPositive
          ? 'rgba(38, 166, 154, 0.1)'
          : 'rgba(239, 83, 80, 0.1)';
        const textColor = isPositive ? TV.bull.primary : TV.bear.primary;

        return (
          <div
            key={item.period}
            className="flex flex-col items-center justify-center p-3 rounded"
            style={{ backgroundColor: bgColor }}
          >
            <div
              className="text-lg font-bold"
              style={{ color: textColor }}
            >
              {isPositive ? '+' : ''}{item.value.toFixed(2)}%
            </div>
            <div className="text-[10px] text-[#787b86] uppercase">
              {item.period}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// =============================================================================
// Inline performance row (for compact displays)
// =============================================================================

export function PerformanceRow({ data }: { data: PerformanceData[] }) {
  const sortedData = [...data].sort(
    (a, b) => periodOrder.indexOf(a.period) - periodOrder.indexOf(b.period)
  );

  return (
    <div className="flex items-center gap-4">
      {sortedData.map(item => {
        const isPositive = item.value >= 0;
        const textColor = isPositive ? TV.bull.primary : TV.bear.primary;

        return (
          <div key={item.period} className="text-center">
            <div
              className="text-sm font-bold"
              style={{ color: textColor }}
            >
              {isPositive ? '+' : ''}{item.value.toFixed(2)}%
            </div>
            <div className="text-[9px] text-[#787b86] uppercase">
              {item.period}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default PerformanceGrid;
