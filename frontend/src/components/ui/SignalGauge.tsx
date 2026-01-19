'use client';

import React from 'react';
import { motion } from 'framer-motion';

interface SignalGaugeProps {
  value: number; // 0 to 100
  horizon: string;
  trend?: string;
  p10?: number;
  p90?: number;
  confidence?: string;
}

export function SignalGauge({ value, horizon, p10, p90, confidence }: SignalGaugeProps) {
  // Normalize value (0-100) to rotation (-90 to 90)
  // 0 = -90deg, 50 = 0deg, 100 = 90deg
  const rotation = (value / 100) * 180 - 90;

  const getSignalText = (val: number) => {
    if (val >= 80) return { text: 'STRONG BUY', color: '#3b82f6' }; // blue-500
    if (val >= 60) return { text: 'BUY', color: '#60a5fa' };       // blue-400
    if (val >= 40) return { text: 'NEUTRAL', color: '#94a3b8' };   // slate-400
    if (val >= 20) return { text: 'SELL', color: '#f87171' };      // red-400
    return { text: 'STRONG SELL', color: '#ef4444' };              // red-500
  };

  const signal = getSignalText(value);
  // Use p10 and p90 for range visualization if needed
  void p10;
  void p90;
  
  return (
    <div className="relative flex flex-col items-center justify-center p-5 bg-[#0a0a0a] border border-white/5 rounded-xl w-full shadow-lg">
      <div className="flex justify-between w-full mb-6 items-center">
          <div className="text-xs font-mono text-slate-400 uppercase tracking-widest border-l-2 border-blue-500 pl-2">{horizon}</div>
          {confidence && (
              <div className={`text-[9px] uppercase font-bold px-2 py-0.5 rounded border ${
                  confidence === 'High' ? 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20' :
                  confidence === 'Med' ? 'bg-blue-500/10 text-blue-500 border-blue-500/20' :
                  'bg-slate-500/10 text-slate-500 border-slate-500/20'
              }`}>
                  CONF: {confidence}
              </div>
          )}
      </div>
      
      {/* TradingView Style Gauge */}
      <div className="relative w-48 h-24 mb-6">
        {/* SVG Arc */}
        <svg viewBox="0 0 200 100" className="w-full h-full overflow-visible">
            {/* Defs for Gradients */}
            <defs>
                <linearGradient id="gaugeGradient" x1="0%" y1="0%" x2="100%" y2="0%">
                    <stop offset="0%" stopColor="#ef4444" />       {/* Red (Sell) */}
                    <stop offset="45%" stopColor="#94a3b8" />      {/* Slate (Neutral) */}
                    <stop offset="55%" stopColor="#94a3b8" />
                    <stop offset="100%" stopColor="#3b82f6" />     {/* Blue (Buy) */}
                </linearGradient>
            </defs>

            {/* Background Track */}
            <path d="M 20 100 A 80 80 0 0 1 180 100" fill="none" stroke="#1e293b" strokeWidth="12" strokeLinecap="round" />
            
            {/* Active Gradient Track */}
            <path d="M 20 100 A 80 80 0 0 1 180 100" fill="none" stroke="url(#gaugeGradient)" strokeWidth="12" strokeLinecap="round" strokeOpacity="0.8" />
            
            {/* Segments Dividers (White Lines) */}
            {/* Center (Neutral) */}
            <line x1="100" y1="20" x2="100" y2="30" stroke="#0a0a0a" strokeWidth="2" />
            {/* Left (Sell/Strong Sell split) */}
            <line x1="43.5" y1="43.5" x2="50.6" y2="50.6" stroke="#0a0a0a" strokeWidth="2" />
            {/* Right (Buy/Strong Buy split) */}
            <line x1="156.5" y1="43.5" x2="149.4" y2="50.6" stroke="#0a0a0a" strokeWidth="2" />
        </svg>

        {/* Needle */}
        <motion.div 
            className="absolute bottom-0 left-[50%] w-[2px] h-[85px] bg-white origin-bottom z-10"
            style={{ 
                x: '-50%',
                borderRadius: '4px',
                boxShadow: '0 0 10px rgba(255,255,255,0.5)'
            }}
            initial={{ rotate: -90 }}
            animate={{ rotate: rotation }}
            transition={{ type: 'spring', damping: 15, stiffness: 60 }}
        >
            {/* Needle Head Circle */}
            <div className="absolute -top-1 -left-1.5 w-4 h-4 bg-white rounded-full border-2 border-[#0a0a0a]" />
        </motion.div>
        
        {/* Pivot Hub */}
        <div className="absolute bottom-[-10px] left-1/2 -translate-x-1/2 w-8 h-4 bg-[#0a0a0a] border-t border-white/10 rounded-t-full z-20 flex items-center justify-center">
             <div className="w-1.5 h-1.5 bg-slate-500 rounded-full mt-1"></div>
        </div>
      </div>

      <div className="text-center mb-6 relative z-10">
         <motion.div 
            initial={{ opacity: 0, y: 5 }}
            animate={{ opacity: 1, y: 0 }}
            className="text-2xl font-bold tracking-tight"
            style={{ color: signal.color }}
         >
             {signal.text}
         </motion.div>
         
         <div className="text-[10px] font-mono text-slate-500 mt-1 flex justify-center gap-4 uppercase tracking-widest">
             <span>Sell</span>
             <span className="text-slate-700">|</span>
             <span>Neutral</span>
             <span className="text-slate-700">|</span>
             <span>Buy</span>
         </div>
         
         {/* Value Indicator */}
         <div className="mt-1 font-mono text-xs text-slate-600">
             SCORE: <span className="text-white">{value}</span>/100
         </div>
      </div>

      {/* Prominent P10/P90 Visualization */}
      {(p10 && p90) && (
        <div className="w-full bg-zinc-900/50 rounded-lg p-3 border border-white/5 relative overflow-hidden group">
            {/* Label */}
            <div className="flex justify-between items-end mb-2 text-[10px] font-mono text-slate-500 uppercase">
                <span>Confidence Band (90%)</span>
                <span>Spread: <span className="text-white">${(p90 - p10).toFixed(2)}</span></span>
            </div>

            {/* The Bar */}
            <div className="relative h-2 bg-slate-800 rounded-full w-full overflow-hidden">
                {/* P10 Marker Line (Left) */}
                <div className="absolute left-0 top-0 bottom-0 w-[15%] bg-indigo-500/20" /> 
                {/* P90 Marker Line (Right) */}
                <div className="absolute right-0 top-0 bottom-0 w-[15%] bg-indigo-500/20" />
                
                {/* Center Range (The "Meat") */}
                <div className="absolute left-[15%] right-[15%] top-0 bottom-0 bg-blue-600/30 border-x border-blue-500/50"></div>
                
                {/* Current Price Marker (Assumed roughly center for viz unless exact passed) */}
                <div className="absolute left-1/2 top-0 bottom-0 w-0.5 bg-white shadow-[0_0_8px_white] z-10" />
            </div>
            
            {/* Ticks */}
            <div className="flex justify-between text-xs font-bold font-mono mt-1.5 px-0 text-slate-300">
                <div className="text-left">
                    <span className="text-[9px] text-slate-600 block leading-none mb-0.5">P10</span>
                    ${p10.toFixed(2)}
                </div>
                <div className="text-right">
                    <span className="text-[9px] text-slate-600 block leading-none mb-0.5">P90</span>
                    ${p90.toFixed(2)}
                </div>
            </div>
        </div>
      )}
    </div>
  );
}
