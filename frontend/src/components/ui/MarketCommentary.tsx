'use client';

import React from 'react';
import { Sparkles, ArrowRight, BookOpen } from 'lucide-react';

export function MarketCommentary() {
  return (
    <div className="bg-[#0a0a0a] border border-white/5 rounded-xl p-6 relative overflow-hidden">
      <div className="absolute top-0 right-0 p-4 opacity-5">
        <BookOpen size={64} className="text-white" />
      </div>

      <div className="flex items-center gap-2 mb-6">
        <Sparkles size={16} className="text-purple-400" />
        <h3 className="text-sm font-semibold text-white uppercase tracking-wider">
            AI Market Narrative
        </h3>
        <span className="text-[10px] bg-purple-500/10 text-purple-400 px-2 py-0.5 rounded border border-purple-500/20">
            GENERATED 14:05 CST
        </span>
      </div>

      <div className="space-y-6 relative z-10">
        <div>
            <h4 className="text-xs font-bold text-slate-300 uppercase tracking-wide mb-2 flex items-center gap-2">
                <div className="w-1 h-1 bg-blue-500 rounded-full"></div>
                Executive Summary
            </h4>
            <p className="text-slate-400 text-sm leading-relaxed">
                The ZL complex remains in an <span className="text-slate-200 font-semibold">Accumulate</span> regime. 
                Despite short-term volatility from EPA discussions, the 3-month outlook is supported by robust 
                China demand signals and tightening South American supply lines. 
                Our models suggest a <span className="text-emerald-400">65% probability</span> of upside breakout above 50c/lb by mid-Q1.
            </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="p-4 bg-emerald-500/5 border border-emerald-500/10 rounded-lg">
                <h4 className="text-xs font-bold text-emerald-400 uppercase tracking-wide mb-3 flex items-center justify-between">
                    Bullish Drivers
                    <span className="text-[10px] text-emerald-500/50">Combined Impact: +2.1σ</span>
                </h4>
                <ul className="space-y-4">
                    <li className="relative pl-4 border-l-2 border-emerald-500/20">
                        <div className="flex items-center gap-2 mb-1">
                            <span className="text-[9px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400 uppercase border border-white/5">Alternative Data</span>
                            <span className="text-[9px] font-mono text-emerald-400">+1.4σ</span>
                        </div>
                        <p className="text-xs text-slate-300 leading-relaxed">
                            <strong className="text-white">China Inventory Drawdown:</strong> Satellite imagery confirms vessel congestion easing, correlating with a <span className="text-white">-2.4% WoW</span> stock depletion in major ports.
                        </p>
                    </li>
                    <li className="relative pl-4 border-l-2 border-emerald-500/20">
                        <div className="flex items-center gap-2 mb-1">
                            <span className="text-[9px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400 uppercase border border-white/5">Technicals</span>
                            <span className="text-[9px] font-mono text-emerald-400">+0.7σ</span>
                        </div>
                        <p className="text-xs text-slate-300 leading-relaxed">
                            <strong className="text-white">Momentum Divergence:</strong> RSI on the 4H timeframe is making higher lows while price consolidates, often preceding a breakout.
                        </p>
                    </li>
                </ul>
            </div>

            <div className="p-4 bg-red-500/5 border border-red-500/10 rounded-lg">
                <h4 className="text-xs font-bold text-red-400 uppercase tracking-wide mb-3 flex items-center justify-between">
                    Bearish Drivers
                    <span className="text-[10px] text-red-500/50">Combined Impact: -0.9σ</span>
                </h4>
                <ul className="space-y-4">
                    <li className="relative pl-4 border-l-2 border-red-500/20">
                         <div className="flex items-center gap-2 mb-1">
                            <span className="text-[9px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400 uppercase border border-white/5">Policy / Reg</span>
                            <span className="text-[9px] font-mono text-red-400">-0.6σ</span>
                        </div>
                        <p className="text-xs text-slate-300 leading-relaxed">
                             <strong className="text-white">EPA RVO Uncertainty:</strong> Regulatory noise regarding renewable volume obligations is capping speculative long positioning.
                        </p>
                    </li>
                    <li className="relative pl-4 border-l-2 border-red-500/20">
                         <div className="flex items-center gap-2 mb-1">
                            <span className="text-[9px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400 uppercase border border-white/5">Macro</span>
                            <span className="text-[9px] font-mono text-red-400">-0.3σ</span>
                        </div>
                        <p className="text-xs text-slate-300 leading-relaxed">
                             <strong className="text-white">Broad Commodities:</strong> Crude weakness (-1.2%) implies lower biofuel feedstock demand in the short term.
                        </p>
                    </li>
                </ul>
            </div>
        </div>
      </div>
    </div>
  );
}
