'use client';

import React from 'react';
import { LightweightZlCandlestickChart } from '@/components/LightweightZlCandlestickChart';
import { ChrisTop4Drivers } from '@/components/ChrisTop4Drivers';
import { SignalGauge } from '@/components/ui/SignalGauge';
import { VegasBrief } from '@/components/VegasBrief';

export default function DashboardPage() {
  return (
    <div className="min-h-screen bg-[#0a0a0a] text-slate-200 px-4 pt-20 pb-8 space-y-6">

      {/* SECTION 0: VEGAS BRIEF - Executive Summary */}
      <VegasBrief />

      {/* SECTION 1: HERO CHART */}
      <div>
        <LightweightZlCandlestickChart height="80vh" />
      </div>
      
      {/* SECTION 2: Multi-Horizon Signals - 4 Big Cards */}
      <div className="space-y-3">
        <div className="flex items-center gap-2 pl-1 border-l-4 border-blue-500">
          <h3 className="text-sm font-bold text-white uppercase tracking-wider">
            Forecast Horizons
          </h3>
          <span className="px-2 py-0.5 rounded text-[9px] font-bold bg-blue-500/10 text-blue-400 border border-blue-500/20">
            4 HORIZONS
          </span>
        </div>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <SignalGauge horizon="1 Week" value={65} trend="bullish" p10={46.20} p90={48.90} confidence="High" />
          <SignalGauge horizon="1 Month" value={45} trend="neutral" p10={44.50} p90={50.10} confidence="Med" />
          <SignalGauge horizon="3 Months" value={30} trend="bearish" p10={40.20} p90={49.50} confidence="Low" />
          <SignalGauge horizon="6 Months" value={25} trend="bearish" p10={38.10} p90={47.80} confidence="Low" />
        </div>
      </div>
      
      {/* SECTION 3: Chris's TOP 4 Key Drivers */}
      <ChrisTop4Drivers />
    </div>
  );
}
