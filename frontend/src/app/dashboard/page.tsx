'use client';

import React, { useState } from 'react';
import { ZLPriceChart } from '@/components/ZLPriceChart';
import { SignalGauge } from '@/components/ui/SignalGauge';
import { ContractImpactCalculator } from '@/components/tools/ContractImpactCalculator';
import { MarketCommentary } from '@/components/ui/MarketCommentary';
import { FactorWaterfall } from '@/components/quant/FactorWaterfall';
import { ProbabilityHeatmap } from '@/components/quant/ProbabilityHeatmap';
import { FusionBrain } from '@/components/viz/FusionBrain';
import { WeatherRiskArray } from '@/components/viz/WeatherRiskArray';
import { QuantAdminSidebar } from '@/components/layout/QuantAdminSidebar';
import { BrainCircuit, Wind, TrendingUp, AlertTriangle, Menu, Activity } from 'lucide-react';

export default function DashboardPage() {
  const [isAdminOpen, setIsAdminOpen] = useState(false);

  return (
    <div className="min-h-screen animate-in fade-in duration-500 p-6 space-y-8 pb-20 bg-[#0a0a0a]">
      
      <QuantAdminSidebar isOpen={isAdminOpen} onClose={() => setIsAdminOpen(false)} />

      {/* Header */}
      <div className="flex items-center justify-between border-b border-white/5 pb-6">
        <div>
          <h1 className="text-3xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-white to-slate-400">
            STRATEGY COMMAND
          </h1>
          <p className="text-slate-400 mt-1 font-mono text-sm tracking-wide">
             ALTERNATIVE DATA INTELLIGENCE // MULTI-HORIZON XAI
          </p>
        </div>
        <div className="flex items-center gap-6">
            <div className="flex items-center gap-4 text-xs font-mono text-slate-500">
            <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                LIVE FEED
            </div>
            <div>UPDATED: 14:02 CST</div>
            </div>
            
            <button 
                onClick={() => setIsAdminOpen(true)}
                className="p-2 hover:bg-white/10 rounded-md text-slate-400 hover:text-white transition-colors border border-transparent hover:border-white/10"
            >
                <Menu size={20} />
            </button>
        </div>
      </div>

      {/* SECTION 1: ZL PRICE CHART */}
      <div className="bg-[#0a0a0a] border border-white/5 rounded-xl p-1 shadow-2xl shadow-black/50">
          <ZLPriceChart height={700} />
      </div>

      {/* SECTION 1.5: HORIZON SIGNALS (Moved Up) */}
      <div>
        <div className="flex items-center gap-2 mb-4 pl-1 border-l-4 border-blue-500">
            <h3 className="text-xl font-bold text-white">
                Multi-Horizon Signals
            </h3>
            <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-blue-500/10 text-blue-400 border border-blue-500/20">
                ACTIVE
            </span>
        </div>
        
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            <SignalGauge 
                horizon="1 Week" 
                value={65} 
                trend="bullish" 
                p10={46.20} 
                p90={48.90} 
                confidence="High"
            />
            <SignalGauge 
                horizon="1 Month" 
                value={45} 
                trend="neutral" 
                p10={44.50} 
                p90={50.10} 
                confidence="Med"
            />
            <SignalGauge 
                horizon="3 Months" 
                value={30} 
                trend="bearish" 
                p10={40.20} 
                p90={49.50} 
                confidence="Low"
            />
            <SignalGauge 
                horizon="6 Months" 
                value={25} 
                trend="bearish" 
                p10={38.10} 
                p90={47.80} 
                confidence="Low"
            />
        </div>
      </div>

      {/* SECTION 2: QUANT OPERATIONAL LAYER */}
      <div className="grid grid-cols-12 gap-6">
        
        {/* Left Column: Tools & Drivers (8) */}
        <div className="col-span-12 lg:col-span-8 flex flex-col gap-6">
            
            {/* Impact & Waterfall Row */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <ContractImpactCalculator />
                <FactorWaterfall prevPrice={49.20} currentPrice={49.65} />
            </div>

            {/* Heatmap */}
            <ProbabilityHeatmap />

            {/* Brain (Force Graph) */}
            <div className="h-[400px] border border-white/5 rounded-xl overflow-hidden bg-black/20">
                 <div className="p-4 border-b border-white/5 bg-white/5 flex items-center justify-between">
                    <span className="text-xs font-mono text-slate-400 uppercase tracking-widest">Global Causal Network</span>
                    <BrainCircuit size={14} className="text-purple-400" />
                 </div>
                 <FusionBrain />
            </div>
        </div>

        {/* Right Column: Commentary & Risks (4) */}
        <div className="col-span-12 lg:col-span-4 flex flex-col gap-6">
            
            {/* Weather Risk Array (New Hi-Def Component) */}
            <WeatherRiskArray />

            {/* Quick Stats / Active Risks */}
            <div className="bg-[#0a0a0a] border border-white/5 rounded-xl p-6">
                <h3 className="text-sm font-semibold text-white mb-4 uppercase tracking-wider flex items-center gap-2">
                    <AlertTriangle size={16} className="text-amber-400" />
                    Active Risks
                </h3>
                <div className="space-y-3">
                    <div className="p-3 bg-amber-500/10 border border-amber-500/20 rounded-lg">
                        <div className="flex justify-between items-center mb-1">
                            <span className="text-amber-400 text-xs font-bold">TRUMP TARIFFS</span>
                            <span className="text-amber-400 text-xs">HIGH PROB</span>
                        </div>
                        <p className="text-slate-400 text-xs">EPU index &gt; 175. China retaliation likely.</p>
                    </div>
                    <div className="p-3 bg-blue-500/10 border border-blue-500/20 rounded-lg">
                        <div className="flex justify-between items-center mb-1">
                            <span className="text-blue-400 text-xs font-bold">BIOFUEL MANDATE</span>
                            <span className="text-blue-400 text-xs">MED IMPACT</span>
                        </div>
                        <p className="text-slate-400 text-xs">EPA waiver discussions in progress.</p>
                    </div>
                </div>
            </div>

            {/* Market Commentary */}
            <MarketCommentary />
        </div>

      </div>


      {/* Bottom Section: Horizon Gauges (Moved Up) */}
      
    </div>
  );
}
