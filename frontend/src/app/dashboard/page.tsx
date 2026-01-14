'use client';

import React, { useState } from 'react';
import { ZLCandlestickChart } from '@/components/ZLCandlestickChart';
import { ChrisTop4Drivers } from '@/components/ChrisTop4Drivers';
import { SignalGauge } from '@/components/ui/SignalGauge';
import { MarketCommentary } from '@/components/ui/MarketCommentary';
import { QuantAdminSidebar } from '@/components/layout/QuantAdminSidebar';
import { AlertTriangle, Menu, TrendingUp, TrendingDown } from 'lucide-react';

export default function DashboardPage() {
  const [isAdminOpen, setIsAdminOpen] = useState(false);

  return (
    <div className="min-h-screen animate-in fade-in duration-500 p-6 space-y-6 pb-20 bg-[#0a0a0a]">
      
      <QuantAdminSidebar isOpen={isAdminOpen} onClose={() => setIsAdminOpen(false)} />

      {/* Header */}
      <div className="flex items-center justify-between border-b border-white/5 pb-6">
        <div>
          <h1 className="text-3xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-white to-slate-400">
            STRATEGY COMMAND
          </h1>
          <p className="text-slate-500 mt-1 font-mono text-xs tracking-wider">
            SOYBEAN OIL FUTURES • MULTI-HORIZON INTELLIGENCE
          </p>
        </div>
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-4 text-xs font-mono text-slate-500">
            <div className="flex items-center gap-2">
              <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
              LIVE
            </div>
            <div className="text-slate-600">|</div>
            <div>ZL1! • $51.70</div>
          </div>
          
          <button 
            onClick={() => setIsAdminOpen(true)}
            className="p-2 hover:bg-white/5 rounded-lg text-slate-500 hover:text-white transition-colors"
          >
            <Menu size={18} />
          </button>
        </div>
      </div>

      {/* SECTION 1: Chris's TOP 4 Key Drivers */}
      <ChrisTop4Drivers />

      {/* SECTION 2: Main Price Chart with Probability Bands */}
      <div className="space-y-2">
        <div className="flex items-center gap-2 pl-1 border-l-4 border-emerald-500">
          <h3 className="text-sm font-bold text-white uppercase tracking-wider">
            Price Action
          </h3>
        </div>
        <ZLCandlestickChart height={450} showBands={true} />
      </div>

      {/* SECTION 3: Multi-Horizon Signals */}
      <div className="space-y-4">
        <div className="flex items-center gap-2 pl-1 border-l-4 border-blue-500">
          <h3 className="text-sm font-bold text-white uppercase tracking-wider">
            Multi-Horizon Signals
          </h3>
          <span className="px-2 py-0.5 rounded text-[9px] font-bold bg-blue-500/10 text-blue-400 border border-blue-500/20">
            4 HORIZONS
          </span>
        </div>
        
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
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

      {/* SECTION 4: Bottom Row - Risks + Commentary */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        
        {/* Active Risks */}
        <div className="bg-[#0a0a0a] border border-white/5 rounded-xl p-5">
          <h3 className="text-xs font-bold text-slate-400 mb-4 uppercase tracking-wider flex items-center gap-2">
            <AlertTriangle size={14} className="text-amber-400" />
            Active Market Risks
          </h3>
          <div className="space-y-3">
            <div className="p-3 bg-red-500/5 border border-red-500/10 rounded-lg group hover:bg-red-500/10 transition-colors">
              <div className="flex justify-between items-center mb-1">
                <span className="text-red-400 text-xs font-bold flex items-center gap-1.5">
                  <TrendingDown size={12} />
                  TRUMP TARIFFS
                </span>
                <span className="text-red-400/70 text-[10px] font-mono">HIGH PROB</span>
              </div>
              <p className="text-slate-500 text-[11px] leading-relaxed">
                EPU index &gt; 175. China retaliation scenarios pricing in.
              </p>
            </div>
            
            <div className="p-3 bg-blue-500/5 border border-blue-500/10 rounded-lg group hover:bg-blue-500/10 transition-colors">
              <div className="flex justify-between items-center mb-1">
                <span className="text-blue-400 text-xs font-bold flex items-center gap-1.5">
                  <TrendingUp size={12} />
                  BIOFUEL MANDATE
                </span>
                <span className="text-blue-400/70 text-[10px] font-mono">MED IMPACT</span>
              </div>
              <p className="text-slate-500 text-[11px] leading-relaxed">
                EPA RVO decision pending. Upside surprise priced at 35%.
              </p>
            </div>

            <div className="p-3 bg-amber-500/5 border border-amber-500/10 rounded-lg group hover:bg-amber-500/10 transition-colors">
              <div className="flex justify-between items-center mb-1">
                <span className="text-amber-400 text-xs font-bold flex items-center gap-1.5">
                  <AlertTriangle size={12} />
                  BRAZIL WEATHER
                </span>
                <span className="text-amber-400/70 text-[10px] font-mono">MONITORING</span>
              </div>
              <p className="text-slate-500 text-[11px] leading-relaxed">
                La Niña conditions developing. Crop stress indicators elevated.
              </p>
            </div>
          </div>
        </div>

        {/* Market Commentary */}
        <MarketCommentary />
      </div>

    </div>
  );
}
