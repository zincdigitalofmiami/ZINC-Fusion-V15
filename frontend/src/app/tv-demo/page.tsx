/**
 * TV Components Demo Page
 * 
 * Showcases all TradingView-grade chart components with mock data
 */
'use client';

import React from 'react';
import { 
  ForecastCone, 
  TechnicalGauge, 
  SeasonalsChart,
  PerformanceGrid,
  ForwardCurve,
  RangeBar,
  ContractHighlights,
  RelatedCommodities,
  MiniTechnicalGauge,
} from '@/components/charts';

// Mock data
const mockHistorical = Array.from({ length: 60 }, (_, i) => ({
  date: `Day ${i + 1}`,
  price: 48 + Math.sin(i / 10) * 3 + Math.random() * 2,
}));

const mockForecast = {
  horizon: '1Y',
  p90: 58.50,
  p50: 52.40,
  p10: 44.20,
  p90Pct: 17.29,
  p50Pct: 5.07,
  p10Pct: -11.38,
};

const mockSeasonals = [
  {
    year: 2026,
    ytdReturn: 5.83,
    data: [
      { month: 'Jan', value: 2.1 },
      { month: 'Feb', value: 3.5 },
      { month: 'Mar', value: 5.8 },
      { month: 'Apr', value: 4.2 },
      { month: 'May', value: 1.8 },
      { month: 'Jun', value: -2.1 },
      { month: 'Jul', value: -4.5 },
      { month: 'Aug', value: -3.2 },
      { month: 'Sep', value: 1.1 },
      { month: 'Oct', value: 4.8 },
      { month: 'Nov', value: 6.2 },
      { month: 'Dec', value: 5.5 },
    ],
  },
  {
    year: 2025,
    ytdReturn: -9.88,
    data: [
      { month: 'Jan', value: -1.2 },
      { month: 'Feb', value: 1.8 },
      { month: 'Mar', value: 3.2 },
      { month: 'Apr', value: -2.4 },
      { month: 'May', value: -5.8 },
      { month: 'Jun', value: -8.2 },
      { month: 'Jul', value: -10.5 },
      { month: 'Aug', value: -12.1 },
      { month: 'Sep', value: -9.8 },
      { month: 'Oct', value: -7.2 },
      { month: 'Nov', value: -5.8 },
      { month: 'Dec', value: -3.2 },
    ],
  },
  {
    year: 2024,
    ytdReturn: -9.28,
    data: [
      { month: 'Jan', value: 4.5 },
      { month: 'Feb', value: 6.2 },
      { month: 'Mar', value: 8.1 },
      { month: 'Apr', value: 5.4 },
      { month: 'May', value: 2.1 },
      { month: 'Jun', value: -3.5 },
      { month: 'Jul', value: -7.8 },
      { month: 'Aug', value: -11.2 },
      { month: 'Sep', value: -8.5 },
      { month: 'Oct', value: -5.2 },
      { month: 'Nov', value: -2.8 },
      { month: 'Dec', value: -1.1 },
    ],
  },
];

const mockForwardCurve = [
  { contract: 'ZLH2026', month: 'Mar 26', price: 51.70, year: 2026 },
  { contract: 'ZLK2026', month: 'May 26', price: 51.45, year: 2026 },
  { contract: 'ZLN2026', month: 'Jul 26', price: 50.82, year: 2026 },
  { contract: 'ZLU2026', month: 'Sep 26', price: 49.95, year: 2026 },
  { contract: 'ZLZ2026', month: 'Dec 26', price: 49.12, year: 2026 },
  { contract: 'ZLH2027', month: 'Mar 27', price: 48.45, year: 2027 },
  { contract: 'ZLK2027', month: 'May 27', price: 47.98, year: 2027 },
  { contract: 'ZLN2027', month: 'Jul 27', price: 47.62, year: 2027 },
];

const mockPerformance = [
  { period: '1W' as const, value: 4.66 },
  { period: '1M' as const, value: 3.28 },
  { period: '3M' as const, value: 1.75 },
  { period: '6M' as const, value: -7.97 },
  { period: 'YTD' as const, value: 6.64 },
  { period: '1Y' as const, value: 12.64 },
];

const mockRelated = [
  { symbol: 'ZS', name: 'Soybean Futures', price: 1048.4, change: 0.94 },
  { symbol: 'ZC', name: 'Corn Futures', price: 424.6, change: 1.19 },
  { symbol: 'ZW', name: 'Chicago SRW Wheat', price: 514.0, change: 0.69 },
  { symbol: 'ZM', name: 'Soybean Meal', price: 293.4, change: 0.62 },
];

export default function TVDemoPage() {
  return (
    <div className="min-h-screen bg-[#131722] text-[#d1d4dc] p-6 pb-20">
      {/* Header */}
      <div className="mb-8 pb-4 border-b border-[rgba(255,255,255,0.1)]">
        <h1 className="text-2xl font-bold text-white">TradingView Components</h1>
        <p className="text-[#787b86] text-sm mt-1">
          Institutional-grade visualizations • No recharts garbage
        </p>
      </div>

      <div className="space-y-12">
        
        {/* Section 1: Forecast Cone */}
        <section>
          <h2 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
            <span className="w-1 h-6 bg-[#2962ff] rounded" />
            Forecast Cone (Price Targets)
          </h2>
          <div className="bg-[#1e222d] rounded-lg border border-[rgba(255,255,255,0.05)] p-6">
            <ForecastCone
              historicalData={mockHistorical}
              currentPrice={49.87}
              forecast={mockForecast}
              height={350}
            />
          </div>
        </section>

        {/* Section 2: Technical Gauges */}
        <section>
          <h2 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
            <span className="w-1 h-6 bg-[#26a69a] rounded" />
            Technical Gauges
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="bg-[#1e222d] rounded-lg border border-[rgba(255,255,255,0.05)] p-6">
              <TechnicalGauge
                value={80}
                signal="strong_buy"
                title="Summary"
                sellCount={0}
                neutralCount={9}
                buyCount={17}
              />
            </div>
            <div className="bg-[#1e222d] rounded-lg border border-[rgba(255,255,255,0.05)] p-6">
              <TechnicalGauge
                value={60}
                signal="buy"
                title="Oscillators"
                sellCount={0}
                neutralCount={8}
                buyCount={3}
              />
            </div>
            <div className="bg-[#1e222d] rounded-lg border border-[rgba(255,255,255,0.05)] p-6">
              <TechnicalGauge
                value={85}
                signal="strong_buy"
                title="Moving Averages"
                sellCount={0}
                neutralCount={1}
                buyCount={14}
              />
            </div>
          </div>

          {/* Mini gauges */}
          <div className="mt-4 flex items-center gap-6">
            <MiniTechnicalGauge value={80} signal="strong_buy" label="1 Day" />
            <MiniTechnicalGauge value={45} signal="neutral" label="1 Week" />
            <MiniTechnicalGauge value={30} signal="sell" label="1 Month" />
          </div>
        </section>

        {/* Section 3: Seasonals */}
        <section>
          <h2 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
            <span className="w-1 h-6 bg-[#ff9800] rounded" />
            Seasonals (Multi-Year Overlay)
          </h2>
          <div className="bg-[#1e222d] rounded-lg border border-[rgba(255,255,255,0.05)] p-6">
            <SeasonalsChart years={mockSeasonals} height={250} />
          </div>
        </section>

        {/* Section 4: Forward Curve */}
        <section>
          <h2 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
            <span className="w-1 h-6 bg-[#ef5350] rounded" />
            Forward Curve (Term Structure)
          </h2>
          <div className="bg-[#1e222d] rounded-lg border border-[rgba(255,255,255,0.05)] p-6">
            <ForwardCurve data={mockForwardCurve} spotPrice={51.70} height={220} />
          </div>
        </section>

        {/* Section 5: Performance Grid + Range */}
        <section>
          <h2 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
            <span className="w-1 h-6 bg-[#9c27b0] rounded" />
            Performance & Range
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="bg-[#1e222d] rounded-lg border border-[rgba(255,255,255,0.05)] p-6">
              <div className="text-sm text-[#787b86] uppercase tracking-wider mb-4">Performance</div>
              <PerformanceGrid data={mockPerformance} columns={3} />
            </div>
            <div className="bg-[#1e222d] rounded-lg border border-[rgba(255,255,255,0.05)] p-6">
              <RangeBar low={41.08} high={57.20} current={51.70} />
            </div>
          </div>
        </section>

        {/* Section 6: Contract Info */}
        <section>
          <h2 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
            <span className="w-1 h-6 bg-[#00bcd4] rounded" />
            Contract Details
          </h2>
          <div className="bg-[#1e222d] rounded-lg border border-[rgba(255,255,255,0.05)] p-6 space-y-6">
            <ContractHighlights
              volume={15350}
              openInterest={270250}
              contractSize={60000}
              frontMonth="ZLH2026"
            />
            <div className="border-t border-[rgba(255,255,255,0.05)] pt-6">
              <RelatedCommodities commodities={mockRelated} />
            </div>
          </div>
        </section>

      </div>
    </div>
  );
}
