'use client';

import React from 'react';
import { motion } from 'framer-motion';

interface PriceOutlookCardProps {
  horizon: string;
  currentPrice: number;
  forecastPrice: number;
  rangeLow: number;
  rangeHigh: number;
  confidence: string;
}

function getVerdict(currentPrice: number, forecastPrice: number) {
  if (!currentPrice || !forecastPrice) return { text: 'Forecast Unavailable', color: 'text-slate-400' };
  const changePct = ((forecastPrice - currentPrice) / currentPrice) * 100;
  if (changePct >= 5) return { text: 'Prices Expected to Rise Significantly', color: 'text-emerald-400' };
  if (changePct >= 2) return { text: 'Prices Expected to Rise', color: 'text-emerald-400' };
  if (changePct >= -2) return { text: 'Prices Expected to Hold Steady', color: 'text-slate-400' };
  if (changePct >= -5) return { text: 'Prices May Ease Lower', color: 'text-amber-400' };
  return { text: 'Prices Expected to Fall', color: 'text-red-400' };
}

function getChangeColor(changePct: number) {
  if (changePct >= 2) return 'text-emerald-400';
  if (changePct >= -2) return 'text-slate-400';
  return 'text-red-400';
}

export function PriceOutlookCard({
  horizon,
  currentPrice,
  forecastPrice,
  rangeLow,
  rangeHigh,
  confidence,
}: PriceOutlookCardProps) {
  const changePct = currentPrice ? ((forecastPrice - currentPrice) / currentPrice) * 100 : 0;
  const verdict = getVerdict(currentPrice, forecastPrice);

  // Range bar positioning: map current price within the range
  const rangeSpan = rangeHigh - rangeLow;
  const currentPosPercent = rangeSpan > 0
    ? Math.min(100, Math.max(0, ((currentPrice - rangeLow) / rangeSpan) * 100))
    : 50;

  const confidenceBadge = confidence === 'High'
    ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
    : confidence === 'Medium'
    ? 'bg-blue-500/10 text-blue-400 border-blue-500/20'
    : 'bg-slate-500/10 text-slate-400 border-slate-500/20';

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className="bg-[#0a0a0a] border border-white/10 rounded-2xl p-6 md:p-8 shadow-lg w-full hover:border-white/20 transition-all duration-300"
    >
      {/* Header: horizon + confidence */}
      <div className="flex justify-between items-center mb-6">
        <div className="text-sm font-semibold text-slate-400 uppercase tracking-widest border-l-2 border-blue-500 pl-3">
          {horizon} Outlook
        </div>
        {confidence && (
          <div className={`text-xs uppercase font-bold px-3 py-1 rounded-full border ${confidenceBadge}`}>
            {confidence}
          </div>
        )}
      </div>

      {/* Forecast price — the hero number */}
      <div className="mb-1">
        <span className="text-4xl md:text-5xl font-bold text-white tracking-tight font-mono">
          ${forecastPrice.toFixed(2)}
        </span>
      </div>

      {/* Change from current */}
      <div className={`text-lg font-medium mb-6 ${getChangeColor(changePct)}`}>
        {changePct >= 0 ? '▲' : '▼'} {changePct >= 0 ? '+' : ''}{changePct.toFixed(1)}% from today
      </div>

      {/* Separator */}
      <div className="border-t border-white/5 my-5" />

      {/* Expected Price Range */}
      {rangeLow > 0 && rangeHigh > 0 ? (
        <div>
          <div className="text-sm text-slate-400 mb-3">Expected Price Range</div>

          {/* Range bar */}
          <div className="relative h-3 bg-slate-800 rounded-full w-full overflow-hidden">
            <div className="absolute inset-y-0 left-0 right-0 bg-gradient-to-r from-blue-600/30 to-blue-500/30 rounded-full" />
            {/* Current price marker */}
            <div
              className="absolute top-0 bottom-0 w-0.5 bg-white shadow-[0_0_6px_rgba(255,255,255,0.8)] z-10"
              style={{ left: `${currentPosPercent}%` }}
            />
          </div>

          {/* Range labels */}
          <div className="flex justify-between text-base font-mono text-slate-300 mt-2">
            <span>${rangeLow.toFixed(2)}</span>
            <span className="text-xs text-slate-500">▲ current (${currentPrice.toFixed(2)})</span>
            <span>${rangeHigh.toFixed(2)}</span>
          </div>
        </div>
      ) : (
        <div className="text-sm text-slate-500">Range data unavailable</div>
      )}

      {/* Verdict */}
      <div className="mt-5 text-center">
        <span className={`text-base font-medium ${verdict.color}`}>
          {verdict.text}
        </span>
      </div>
    </motion.div>
  );
}

// Keep backward-compatible export for any other consumers
export { PriceOutlookCard as SignalGauge };
