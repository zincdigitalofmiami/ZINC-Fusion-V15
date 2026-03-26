"use client";

import React from "react";
import { LightweightZlCandlestickChart } from "@/components/LightweightZlCandlestickChart";
import { RegimeAnalysisChart } from "@/components/RegimeAnalysisChart";
import { ProbabilityHeatmap } from "@/components/quant/ProbabilityHeatmap";
import {
  ChrisTop4Drivers,
  MarketIntelligenceRow,
} from "@/components/ChrisTop4Drivers";

export default function DashboardPage() {
  return (
    <div className="min-h-screen bg-[#0a0a0a] text-slate-200 p-3 pt-24 md:p-6 md:pt-36 pb-20 space-y-8">
      {/* SECTION 1: HERO CHART */}
      <div>
        <LightweightZlCandlestickChart height="80vh" />
      </div>

      {/* SECTION 2: L3 Probability Surface - Full Width Row (directly under chart) */}
      <div className="w-full">
        <ProbabilityHeatmap />
      </div>

      {/* SECTION 3: Regime Analysis - Full Width Row */}
      <div className="w-full">
        <RegimeAnalysisChart height={350} timeRange="1Y" />
      </div>

      {/* SECTION 4: AI Market Intelligence - Full Width Row */}
      <div className="w-full">
        <div className="flex items-center gap-2 pl-1 border-l-4 border-violet-500 mb-4">
          <h3 className="text-base font-bold text-white uppercase tracking-wider">
            AI Market Intelligence
          </h3>
          <span className="px-2 py-0.5 rounded text-xs font-bold bg-violet-500/10 text-violet-400 border border-violet-500/20">
            FULL WIDTH
          </span>
        </div>
        <MarketIntelligenceRow />
      </div>

      {/* SECTION 5: Market Risk Factors */}
      <ChrisTop4Drivers />
    </div>
  );
}
