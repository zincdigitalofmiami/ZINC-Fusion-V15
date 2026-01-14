/**
 * RangeBar - TradingView-style 52-Week Range Indicator
 * 
 * Shows current price position within 52-week high/low range
 */
'use client';

import React from 'react';
import TV from '@/lib/colors';

interface RangeBarProps {
  low: number;
  high: number;
  current: number;
  label?: string;
}

export function RangeBar({ low, high, current, label = '52WK RANGE' }: RangeBarProps) {
  // Calculate position percentage (0-100)
  const range = high - low;
  const position = range > 0 ? ((current - low) / range) * 100 : 50;

  return (
    <div className="w-full">
      {/* Label */}
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-[10px] text-[#787b86] uppercase tracking-wider">{label}</span>
      </div>

      {/* Bar container */}
      <div className="relative h-2 w-full">
        {/* Background track */}
        <div className="absolute inset-0 rounded-full bg-[#2a2e39]" />

        {/* Filled portion (gradient from left) */}
        <div
          className="absolute left-0 top-0 h-full rounded-full"
          style={{
            width: `${position}%`,
            background: `linear-gradient(90deg, ${TV.bull.primary}40 0%, ${TV.bull.primary} 100%)`,
          }}
        />

        {/* Current position marker (triangle) */}
        <div
          className="absolute top-full"
          style={{
            left: `${position}%`,
            transform: 'translateX(-50%)',
          }}
        >
          <div 
            className="w-0 h-0 mt-1"
            style={{
              borderLeft: '4px solid transparent',
              borderRight: '4px solid transparent',
              borderBottom: `6px solid ${TV.text.primary}`,
            }}
          />
        </div>
      </div>

      {/* Labels */}
      <div className="flex items-center justify-between mt-3 text-xs">
        <span className="text-[#787b86]">{low.toFixed(2)}</span>
        <span className="text-[#d1d4dc] font-medium">{current.toFixed(2)}</span>
        <span className="text-[#787b86]">{high.toFixed(2)}</span>
      </div>
    </div>
  );
}

// =============================================================================
// Day's Range variant
// =============================================================================

interface DayRangeProps {
  low: number;
  high: number;
  current: number;
  bid?: number;
  ask?: number;
}

export function DayRange({ low, high, current, bid, ask }: DayRangeProps) {
  const range = high - low;
  const position = range > 0 ? ((current - low) / range) * 100 : 50;

  return (
    <div className="flex items-center gap-3">
      <span className="text-xs text-[#787b86]">{low.toFixed(2)}</span>
      
      <div className="flex-1 relative h-1.5">
        <div className="absolute inset-0 rounded-full bg-[#2a2e39]" />
        <div
          className="absolute left-0 top-0 h-full rounded-full bg-[#26a69a]"
          style={{ width: `${position}%` }}
        />
        
        {/* Current marker */}
        <div
          className="absolute top-1/2 w-2 h-2 -translate-y-1/2 rounded-full bg-[#d1d4dc] border border-[#131722]"
          style={{ left: `${position}%`, transform: 'translate(-50%, -50%)' }}
        />
      </div>

      <span className="text-xs text-[#787b86]">{high.toFixed(2)}</span>

      {/* Bid/Ask pills */}
      {bid && ask && (
        <div className="flex items-center gap-1 ml-2">
          <span className="px-1.5 py-0.5 rounded text-[10px] bg-[#2962ff]/20 text-[#2962ff]">
            {bid.toFixed(2)}
          </span>
          <span className="text-[10px] text-[#434651]">×</span>
          <span className="px-1.5 py-0.5 rounded text-[10px] bg-[#ef5350]/20 text-[#ef5350]">
            {ask.toFixed(2)}
          </span>
        </div>
      )}
    </div>
  );
}

export default RangeBar;
