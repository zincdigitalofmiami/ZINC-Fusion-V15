'use client';

import React from 'react';
import { FusionBrain } from '@/components/viz/FusionBrain';
import { RegimeAnalysisChart } from '@/components/RegimeAnalysisChart';
import { ContractImpactCalculator } from '@/components/tools/ContractImpactCalculator';
import { FactorWaterfall } from '@/components/quant/FactorWaterfall';
import { ProbabilityHeatmap } from '@/components/quant/ProbabilityHeatmap';
import { WeatherRiskArray } from '@/components/viz/WeatherRiskArray';
import { Target, Shield, Zap, AlertTriangle } from 'lucide-react';

export default function StrategyPage() {
  return (
    <div className="min-h-screen bg-[#0a0a0a] text-slate-200 p-6 pt-36 pb-20">

      {/* Top HUD: Current Posture */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        {/* Main Posture Card */}
        <div className="col-span-2 relative group overflow-hidden bg-[#0a0a0a] border border-white/5 rounded-xl p-6">
          <div className="absolute inset-0 bg-gradient-to-r from-cyan-500/5 to-transparent pointer-events-none" />

          <div className="flex items-start justify-between">
            <div>
              <div className="flex items-center gap-2 text-cyan-400 font-mono text-xs mb-2 uppercase tracking-wider">
                <Target size={14} />
                Current Posture (1W - 6M)
              </div>
              <h2 className="text-5xl font-bold text-white tracking-tight mb-2">
                ACCUMULATE
              </h2>
              <p className="text-slate-500 max-w-md text-sm leading-relaxed">
                Forecast driven by <span className="text-white">Technical Momentum</span> and{' '}
                <span className="text-white">China Demand Flows</span>.
                Satellite crop health suggests tightening supply.
              </p>
            </div>

            <div className="flex flex-col items-end gap-3 p-4 bg-black/30 rounded-lg border border-white/5">
              <div className="text-right">
                <div className="text-2xl font-bold text-emerald-400">87%</div>
                <div className="text-[9px] text-slate-500 uppercase tracking-widest">Confidence</div>
              </div>
              <div className="text-right">
                <div className="text-2xl font-bold text-cyan-400">+2.4%</div>
                <div className="text-[9px] text-slate-500 uppercase tracking-widest">Exp Return</div>
              </div>
            </div>
          </div>
        </div>

        {/* Action Card */}
        <div className="bg-[#0a0a0a] border border-white/5 rounded-xl p-5 relative overflow-hidden">
          <div className="absolute top-0 right-0 p-4 opacity-5">
            <Zap size={48} className="text-amber-400" />
          </div>
          <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-4">
            Primary Directive
          </h3>
          <div className="space-y-2">
            <div className="flex items-center gap-3 p-2.5 bg-cyan-500/10 border-l-2 border-cyan-500 rounded-r">
              <span className="text-sm font-bold text-cyan-400">01</span>
              <div>
                <div className="text-sm font-bold text-white">Cover Q1 Needs</div>
                <div className="text-[10px] text-slate-500">Lock 60% @ Market</div>
              </div>
            </div>
            <div className="flex items-center gap-3 p-2.5 bg-white/5 border-l-2 border-slate-600 rounded-r">
              <span className="text-sm font-bold text-slate-500">02</span>
              <div>
                <div className="text-sm font-bold text-slate-300">Defer H2</div>
                <div className="text-[10px] text-slate-500">Wait for WASDE</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Regime Analysis Chart */}
      <div className="mb-8">
        <div className="flex items-center gap-2 mb-4 pl-1 border-l-4 border-purple-500">
          <h3 className="text-sm font-bold text-white uppercase tracking-wider">
            Regime Analysis
          </h3>
        </div>
        <RegimeAnalysisChart height={300} />
      </div>

      {/* Driver Attribution - FusionBrain Bubbles */}
      <div className="mb-8">
        <div className="flex items-center gap-2 mb-4 pl-1 border-l-4 border-cyan-500">
          <h3 className="text-sm font-bold text-white uppercase tracking-wider">
            Driver Attribution
          </h3>
        </div>

        <div className="relative w-full h-[500px] bg-[#0a0a0a] border border-white/5 rounded-xl overflow-hidden">
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(0,212,255,0.02),transparent_70%)]" />
          <FusionBrain />
        </div>
      </div>

      {/* Analysis Tools Grid */}
      <div className="grid grid-cols-12 gap-6 mb-8">
        <div className="col-span-12 lg:col-span-8 space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <ContractImpactCalculator />
            <FactorWaterfall prevPrice={49.20} currentPrice={49.65} />
          </div>
          <ProbabilityHeatmap />
        </div>

        <div className="col-span-12 lg:col-span-4">
          <WeatherRiskArray />
        </div>
      </div>

      {/* Risk Footer */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="p-4 rounded-xl border border-red-500/20 bg-red-500/5">
          <div className="flex items-center gap-2 mb-2">
            <AlertTriangle size={14} className="text-red-400" />
            <span className="text-xs font-bold text-red-400">TRUMP TARIFFS</span>
          </div>
          <p className="text-[11px] text-red-300/60 leading-relaxed">
            EPU index &gt; 175. High probability of retaliatory impacts on soy complex.
          </p>
        </div>
        <div className="p-4 rounded-xl border border-amber-500/20 bg-amber-500/5">
          <div className="flex items-center gap-2 mb-2">
            <Shield size={14} className="text-amber-400" />
            <span className="text-xs font-bold text-amber-400">BRAZIL HARVEST</span>
          </div>
          <p className="text-[11px] text-amber-300/60 leading-relaxed">
            Early harvest reports suggest record yield. Potential price dampener in Q2.
          </p>
        </div>
        <div className="p-4 rounded-xl border border-cyan-500/20 bg-cyan-500/5">
          <div className="flex items-center gap-2 mb-2">
            <Zap size={14} className="text-cyan-400" />
            <span className="text-xs font-bold text-cyan-400">BIOFUEL POLICY</span>
          </div>
          <p className="text-[11px] text-cyan-300/60 leading-relaxed">
            EPA waiver decision expected next week. Variance: +/- 4%.
          </p>
        </div>
      </div>

    </div>
  );
}
