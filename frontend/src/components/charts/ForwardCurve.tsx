/**
 * ForwardCurve - TradingView-style Futures Term Structure
 *
 * Shows price curve across contract months (contango/backwardation)
 * Colored dots: teal for upward slope, red for backwardation sections
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
import TV from '@/lib/colors';

interface ContractPoint {
  contract: string;    // "ZLH2026", "ZLK2026", etc
  month: string;       // "Mar 26", "May 26", etc
  price: number;
  year: number;
}

interface ForwardCurveProps {
  data: ContractPoint[];
  spotPrice?: number;
  height?: number;
}

// Custom dot component to color based on slope
interface CustomDotProps {
  cx?: number;
  cy?: number;
  payload?: ContractPoint;
  index?: number;
  data?: ContractPoint[];
}

function CustomDot(props: CustomDotProps) {
  const { cx, cy, payload, index = 0, data = [] } = props;

  if (!cx || !cy || !payload) return null;

  // Determine if this point is in contango (higher than previous)
  const prevPoint = index > 0 ? data[index - 1] : null;
  const isContango = prevPoint ? payload.price >= prevPoint.price : true;

  return (
    <circle
      cx={cx}
      cy={cy}
      r={4}
      fill={isContango ? TV.bull.primary : TV.bear.primary}
      stroke="#131722"
      strokeWidth={1}
    />
  );
}

export function ForwardCurve({ data, spotPrice, height = 180 }: ForwardCurveProps) {
  // Calculate domain
  const { minPrice, maxPrice } = useMemo(() => {
    const prices = data.map(d => d.price);
    return {
      minPrice: Math.min(...prices) * 0.98,
      maxPrice: Math.max(...prices) * 1.02,
    };
  }, [data]);

  // Determine overall structure
  const isContango = data.length > 1 && data[data.length - 1].price > data[0].price;

  return (
    <div className="w-full">
      {/* Header */}
      <div className="flex items-center justify-between mb-2 px-2">
        <div>
          <div className="text-xs text-[#787b86] uppercase tracking-wider">Forward Curve</div>
          <p className="text-[10px] text-[#434651] mt-0.5">
            What the market thinks the asset will be worth in the future
          </p>
        </div>
        <div
          className="px-2 py-1 rounded text-xs font-medium"
          style={{
            backgroundColor: isContango ? 'rgba(38, 166, 154, 0.1)' : 'rgba(239, 83, 80, 0.1)',
            color: isContango ? TV.bull.primary : TV.bear.primary,
          }}
        >
          {isContango ? 'CONTANGO' : 'BACKWARDATION'}
        </div>
      </div>

      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={data} margin={{ top: 10, right: 10, bottom: 20, left: 10 }}>
          {/* Gradient background based on structure */}
          <defs>
            <linearGradient id="curveGradient" x1="0" y1="0" x2="0" y2="1">
              <stop
                offset="0%"
                stopColor={isContango ? TV.bull.primary : TV.bear.primary}
                stopOpacity={0.1}
              />
              <stop
                offset="100%"
                stopColor={isContango ? TV.bull.primary : TV.bear.primary}
                stopOpacity={0}
              />
            </linearGradient>
          </defs>

          <XAxis
            dataKey="month"
            axisLine={{ stroke: 'rgba(255,255,255,0.1)' }}
            tickLine={false}
            tick={{ fill: '#787b86', fontSize: 9 }}
            interval={0}
            angle={-45}
            textAnchor="end"
            height={40}
          />

          <YAxis
            domain={[minPrice, maxPrice]}
            axisLine={false}
            tickLine={false}
            tick={{ fill: '#787b86', fontSize: 10 }}
            tickFormatter={(v) => v.toFixed(2)}
            width={45}
          />

          {/* Spot price reference */}
          {spotPrice && (
            <ReferenceLine
              y={spotPrice}
              stroke="rgba(255,255,255,0.3)"
              strokeDasharray="3 3"
              label={{
                value: `Spot: ${spotPrice.toFixed(2)}`,
                position: 'right',
                fill: '#787b86',
                fontSize: 9,
              }}
            />
          )}

          {/* The curve line */}
          <Line
            type="monotone"
            dataKey="price"
            stroke="#2962ff"
            strokeWidth={2}
            dot={(props) => <CustomDot {...props} data={data} />}
            activeDot={{ r: 6, stroke: '#131722', strokeWidth: 2 }}
            isAnimationActive={false}
          />

          <Tooltip
            contentStyle={{
              backgroundColor: '#1e222d',
              border: '1px solid rgba(255,255,255,0.1)',
              borderRadius: '4px',
              padding: '8px 12px',
            }}
            labelStyle={{ color: '#d1d4dc', fontWeight: 'bold' }}
            formatter={(value) => [
              <span key="v" className="text-[#2962ff]">{typeof value === 'number' ? value.toFixed(4) : ''}</span>,
              'Price'
            ]}
          />
        </LineChart>
      </ResponsiveContainer>

      {/* More info button */}
      <div className="flex justify-center mt-2">
        <button className="px-4 py-1 rounded border border-[rgba(255,255,255,0.1)] text-xs text-[#787b86] hover:bg-[rgba(255,255,255,0.05)] transition-colors">
          More info
        </button>
      </div>
    </div>
  );
}

// =============================================================================
// Mini forward curve for sidebar
// =============================================================================

export function MiniForwardCurve({ data }: { data: ContractPoint[] }) {
  const isContango = data.length > 1 && data[data.length - 1].price > data[0].price;

  return (
    <div className="w-full h-12">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data}>
          <Line
            type="monotone"
            dataKey="price"
            stroke={isContango ? TV.bull.primary : TV.bear.primary}
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export default ForwardCurve;
