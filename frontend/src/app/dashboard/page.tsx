'use client';

import React from 'react';
import { LightweightZlCandlestickChart } from '@/components/LightweightZlCandlestickChart';
import { ChrisTop4Drivers } from '@/components/ChrisTop4Drivers';

export default function DashboardPage() {
  return (
    <div className="min-h-screen bg-[#0a0a0a] text-slate-200 px-4 pt-20 pb-8 space-y-8">
      {/* SECTION 1: HERO CHART */}
      <div>
        <LightweightZlCandlestickChart height="80vh" />
      </div>

      {/* SECTION 2: Market Risk Factors */}
      <ChrisTop4Drivers />
    </div>
  );
}
