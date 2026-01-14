/**
 * ContractHighlights - TradingView-style Contract Info Card
 * 
 * Shows Volume, Open Interest, Contract Size, Front Month
 */
'use client';

import React from 'react';
import TV from '@/lib/colors';

interface ContractHighlightsProps {
  volume: number | string;
  openInterest: number | string;
  contractSize: number | string;
  frontMonth: string;
}

export function ContractHighlights({
  volume,
  openInterest,
  contractSize,
  frontMonth,
}: ContractHighlightsProps) {
  const formatNumber = (n: number | string) => {
    if (typeof n === 'string') return n;
    if (n >= 1000000) return `${(n / 1000000).toFixed(2)}M`;
    if (n >= 1000) return `${(n / 1000).toFixed(2)}K`;
    return n.toString();
  };

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
      <div>
        <div className="text-xs text-[#787b86] uppercase tracking-wider mb-1">Volume</div>
        <div className="text-lg font-bold text-[#d1d4dc]">{formatNumber(volume)}</div>
      </div>
      <div>
        <div className="text-xs text-[#787b86] uppercase tracking-wider mb-1">Open Interest</div>
        <div className="text-lg font-bold text-[#d1d4dc]">{formatNumber(openInterest)}</div>
      </div>
      <div>
        <div className="text-xs text-[#787b86] uppercase tracking-wider mb-1">Contract Size</div>
        <div className="text-lg font-bold text-[#d1d4dc]">
          {formatNumber(contractSize)}
          <span className="text-xs text-[#787b86] ml-1">LBR</span>
        </div>
      </div>
      <div>
        <div className="text-xs text-[#787b86] uppercase tracking-wider mb-1">Front Month</div>
        <div className="text-lg font-bold text-[#d1d4dc]">{frontMonth}</div>
      </div>
    </div>
  );
}

// =============================================================================
// Related Commodities pills (like ZS, ZC, ZW, ZM)
// =============================================================================

interface RelatedCommodity {
  symbol: string;
  name: string;
  price: number;
  change: number;  // percentage
  color?: string;  // icon background color
}

interface RelatedCommoditiesProps {
  commodities: RelatedCommodity[];
}

// Default colors for common symbols
const symbolColors: Record<string, string> = {
  ZS: '#2962ff',   // Soybeans - blue
  ZC: '#ff9800',   // Corn - orange
  ZW: '#4caf50',   // Wheat - green
  ZM: '#9c27b0',   // Soybean Meal - purple
  ZL: '#26a69a',   // Soybean Oil - teal
  CL: '#ff5722',   // Crude Oil - deep orange
  NG: '#00bcd4',   // Natural Gas - cyan
};

export function RelatedCommodities({ commodities }: RelatedCommoditiesProps) {
  return (
    <div className="w-full">
      <div className="text-xs text-[#787b86] uppercase tracking-wider mb-3">
        Related Commodities
      </div>
      <p className="text-[10px] text-[#434651] mb-4">
        Plan your next futures move with related contracts
      </p>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {commodities.map(c => {
          const iconColor = c.color || symbolColors[c.symbol] || '#787b86';
          const isPositive = c.change >= 0;

          return (
            <div
              key={c.symbol}
              className="p-3 rounded-lg border border-[rgba(255,255,255,0.05)] hover:border-[rgba(255,255,255,0.1)] hover:bg-[rgba(255,255,255,0.02)] transition-all cursor-pointer"
            >
              <div className="flex items-center gap-2 mb-2">
                {/* Symbol icon */}
                <div
                  className="w-8 h-8 rounded-full flex items-center justify-center text-white text-xs font-bold"
                  style={{ backgroundColor: iconColor }}
                >
                  {c.symbol.slice(0, 2)}
                </div>
                <div>
                  <div className="text-xs font-medium text-[#d1d4dc]">
                    {c.symbol}1!
                    <span className="text-[#787b86] text-[10px] ml-1">futures price</span>
                  </div>
                  <div className="text-[10px] text-[#787b86]">{c.name}</div>
                </div>
              </div>

              <div className="flex items-baseline gap-2">
                <span className="text-sm font-bold text-[#d1d4dc]">
                  {c.price.toLocaleString()}
                </span>
                <span className="text-[10px] text-[#787b86]">USX/BUA</span>
              </div>

              <div 
                className="text-xs mt-1"
                style={{ color: isPositive ? TV.bull.primary : TV.bear.primary }}
              >
                {isPositive ? '+' : ''}{c.change.toFixed(2)}%
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default ContractHighlights;
