'use client';

import React from 'react';
import { FusionBrain } from '@/components/viz/FusionBrain';
import { Target, Shield, Zap, TrendingUp, AlertTriangle } from 'lucide-react';
import { motion } from 'framer-motion';

export default function StrategyPage() {
  return (
    <div className="min-h-screen bg-[#0a0a0a] text-slate-200 p-6 pb-20 animate-in fade-in duration-700">
      
      {/* Header */}
      <div className="flex items-center justify-between mb-8 pb-4 border-b border-white/5">
        <div>
          <h1 className="text-3xl font-bold text-white tracking-tight">STRATEGY ENGINE</h1>
          <p className="text-slate-400 text-sm font-mono mt-1">XAI OBJECTIVE FORECASTS // MULTI-HORIZON ANALYSIS</p>
        </div>
        <div className="flex items-center gap-4">
            <div className="px-3 py-1 bg-emerald-500/10 border border-emerald-500/20 rounded-full text-xs font-mono text-emerald-400 flex items-center gap-2">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                </span>
                XAI WEIGHTS ACTIVE
            </div>
        </div>
      </div>

      {/* Top HUD: The "Buy" Signal */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        {/* Main Posture */}
        <div className="col-span-2 relative group overflow-hidden bg-[#0a0a0a] border border-white/5 rounded-2xl p-8 flex items-center justify-between shadow-2xl">
            <div className="absolute inset-0 bg-gradient-to-r from-white/5 to-transparent pointer-events-none" />
            
            <div>
                <div className="flex items-center gap-2 text-blue-400 font-mono text-sm mb-2 uppercase tracking-wider">
                    <Target size={16} />
                    Current Posture (1W - 6M)
                </div>
                <h2 className="text-6xl font-bold text-white tracking-tighter mb-2">
                    ACCUMULATE
                </h2>
                <p className="text-slate-400 max-w-md text-sm leading-relaxed">
                    Forecast weighted heavily by <span className="text-white">Technical Momentum (35%)</span> and <span className="text-white">China Demand Flows (25%)</span>.
                    Satellite crop health indicators suggest tightening supply.
                </p>
            </div>

            <div className="flex flex-col items-end gap-4 p-4 bg-[#0a0a0a]/50 backdrop-blur rounded-xl border border-white/5">
                <div className="text-right">
                    <div className="text-3xl font-bold text-emerald-400">87%</div>
                    <div className="text-[10px] text-slate-500 uppercase tracking-widest">Explainable Conf</div>
                </div>
                <div className="text-right">
                    <div className="text-3xl font-bold text-blue-400">+2.4%</div>
                    <div className="text-[10px] text-slate-500 uppercase tracking-widest">Exp Return</div>
                </div>
            </div>
        </div>

        {/* Action Card */}
        <div className="bg-[#0a0a0a] border border-white/5 rounded-2xl p-6 flex flex-col justify-center gap-4 relative overflow-hidden">
            <div className="absolute top-0 right-0 p-4 opacity-10">
                <Zap size={64} className="text-amber-400" />
            </div>
            <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-2">Primary Directive</h3>
            <div className="space-y-3">
                <div className="flex items-center gap-3 p-3 bg-blue-500/10 border-l-2 border-blue-500 rounded-sm">
                    <span className="text-lg font-bold text-blue-400">01</span>
                    <div>
                        <div className="text-sm font-bold text-white">Cover Q1 Needs</div>
                        <div className="text-xs text-slate-400">Lock 60% @ Market</div>
                    </div>
                </div>
                <div className="flex items-center gap-3 p-3 bg-white/5 border-l-2 border-slate-600 rounded-sm">
                    <span className="text-lg font-bold text-slate-500">02</span>
                    <div>
                        <div className="text-sm font-bold text-slate-300">Defer H2</div>
                        <div className="text-xs text-slate-500">Wait for WASDE</div>
                    </div>
                </div>
            </div>
        </div>
      </div>

      {/* The Brain - L3 Fusion Visualization */}
      <div className="mb-8">
        <div className="flex items-center justify-between mb-4 px-2">
            <h3 className="text-lg font-bold text-white flex items-center gap-2">
                <TrendingUp size={18} className="text-blue-400" />
                Driver Attribution (XAI Weights)
            </h3>
            <div className="text-xs text-slate-500 font-mono">
                MODEL: FUSION-V15-XAI
            </div>
        </div>
        
        {/* This creates a "glass" container for the D3 Viz */}
        <div className="relative w-full h-[600px] bg-[#0a0a0a] border border-white/5 rounded-2xl overflow-hidden shadow-2xl">
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(59,130,246,0.03),transparent_70%)]" />
            <FusionBrain />
            
            {/* Overlay UI inside the viz */}
            <div className="absolute bottom-6 left-6 pointer-events-none">
                <div className="p-4 bg-black/40 backdrop-blur-md border border-white/10 rounded-xl max-w-xs">
                    <h4 className="text-xs font-bold text-white mb-2 uppercase">Explainable Drivers (Real-time)</h4>
                    <div className="flex flex-wrap gap-2">
                        <span className="px-2 py-1 bg-red-500/20 text-red-400 text-[10px] rounded uppercase border border-red-500/30">Trade Policy</span>
                        <span className="px-2 py-1 bg-blue-500/20 text-blue-400 text-[10px] rounded uppercase border border-blue-500/30">Technicals</span>
                        <span className="px-2 py-1 bg-emerald-500/20 text-emerald-400 text-[10px] rounded uppercase border border-emerald-500/30">Supply Flows</span>
                    </div>
                </div>
            </div>
        </div>
      </div>

      {/* Risks Footer */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="p-4 rounded-xl border border-red-500/20 bg-red-500/5">
            <div className="flex items-center gap-2 mb-2">
                <AlertTriangle size={16} className="text-red-400" />
                <span className="text-sm font-bold text-red-400">TRUMP TARIFFS</span>
            </div>
            <p className="text-xs text-red-300/70">EPU index &gt; 175. High probability of retaliatory impacts on soy complex.</p>
        </div>
        <div className="p-4 rounded-xl border border-amber-500/20 bg-amber-500/5">
            <div className="flex items-center gap-2 mb-2">
                <Shield size={16} className="text-amber-400" />
                <span className="text-sm font-bold text-amber-400">BRAZIL HARVEST</span>
            </div>
            <p className="text-xs text-amber-300/70">Early harvest reports suggest record yield. Potential price dampener in Q2.</p>
        </div>
        <div className="p-4 rounded-xl border border-blue-500/20 bg-blue-500/5">
            <div className="flex items-center gap-2 mb-2">
                <Zap size={16} className="text-blue-400" />
                <span className="text-sm font-bold text-blue-400">BIOFUEL POLICY</span>
            </div>
            <p className="text-xs text-blue-300/70">EPA waiver decision expected next week. Variance: +/- 4%.</p>
        </div>
      </div>

    </div>
  );
}
