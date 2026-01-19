'use client';

import React, { useState } from 'react';
import { ZLCandlestickChart } from '@/components/ZLCandlestickChart';
import { ChrisTop4Drivers } from '@/components/ChrisTop4Drivers';
import { SignalGauge } from '@/components/ui/SignalGauge';
import { MarketCommentary } from '@/components/ui/MarketCommentary';
import { QuantAdminSidebar } from '@/components/layout/QuantAdminSidebar';
import { AlertTriangle, TrendingUp, TrendingDown } from 'lucide-react';

export default function DashboardPage() {
    const [isAdminOpen, setIsAdminOpen] = useState(false);

  return (
        <div className="min-h-screen p-6 pt-28 space-y-6 pb-20 bg-[#0a0a0a]">
              <QuantAdminSidebar isOpen={isAdminOpen} onClose={() => setIsAdminOpen(false)} />
        
          {/* SECTION 1: HERO CHART - Massive, Full Width */}
              <div className="space-y-2">
                      <ZLCandlestickChart height="70vh" />
              </div>
        
          {/* SECTION 2: Multi-Horizon Signals - 4 Big Cards */}
              <div className="space-y-4">
                      <div className="flex items-center gap-2 pl-1 border-l-4 border-blue-500">
                                <h3 className="text-sm font-bold text-white uppercase tracking-wider">
                                            Forecast Horizons
                                </h3>
                                <span className="px-2 py-0.5 rounded text-[9px] font-bold bg-blue-500/10 text-blue-400 border border-blue-500/20">
                                            4 HORIZONS
                                </span>
                      </div>
                      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
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
