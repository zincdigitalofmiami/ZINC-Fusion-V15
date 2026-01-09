'use client';

import React from 'react';

export function ProbabilityHeatmap() {
  const horizons = ['5d', '21d', '63d', '126d'];
  const prices = [52.0, 51.5, 51.0, 50.5, 50.0, 49.5, 49.0, 48.5, 48.0, 47.5, 47.0];
  
  // Mock Probability Density Function (PDF) generator
  const getDensity = (price: number, horizonIdx: number) => {
    // Center point drifts up slightly over time
    const center = 49.20 + (horizonIdx * 0.4);
    // Spread increases over time (uncertainty)
    const sigma = 0.5 + (horizonIdx * 0.4);
    
    // Gaussian-ish
    const diff = Math.abs(price - center);
    const density = Math.exp(-(diff * diff) / (2 * sigma * sigma));
    return density;
  };

  return (
    <div className="w-full bg-[#0a0a0a] border border-white/5 rounded-xl p-6 shadow-sm overflow-hidden">
        <div className="flex items-center justify-between mb-2">
            <div>
                 <h3 className="text-sm font-semibold text-white uppercase tracking-wider">L3 Probability Surface</h3>
                 <p className="text-xs text-slate-500">Full distribution density over horizon</p>
            </div>
            <div className="flex items-center gap-2">
                 <div className="flex items-center gap-1 text-[10px] text-slate-500">
                    <div className="w-2 h-2 bg-blue-500/100 rounded-[1px]"></div> High Prob
                 </div>
                 <div className="flex items-center gap-1 text-[10px] text-slate-500">
                    <div className="w-2 h-2 bg-blue-500/10 rounded-[1px]"></div> Low Prob
                 </div>
            </div>
        </div>

        <div className="relative">
             {/* The Heatmap Grid */}
             <div className="grid grid-cols-4 gap-1 mt-6 relative h-[300px]">
                {horizons.map((h, hIdx) => (
                    <div key={h} className="relative h-full border-l border-white/5 mx-1">
                        {/* Horizon Label */}
                        <div className="absolute -bottom-6 w-full text-center text-xs text-slate-500 font-mono">
                            {h}
                        </div>

                        {/* Price Buckets (Vertical) */}
                        <div className="flex flex-col h-full justify-between gap-[1px]">
                            {prices.map((p) => {
                                const density = getDensity(p, hIdx);
                                // Color mapping: Transparent -> Blue -> Bright White/Cyan
                                const opacity = Math.min(density * 1.5, 1); // Boost contrast
                                return (
                                    <div 
                                        key={p} 
                                        className="w-full h-full rounded-[1px] relative group transition-all hover:scale-105 hover:z-10"
                                        style={{
                                            backgroundColor: `rgba(59, 130, 246, ${opacity})`,
                                            boxShadow: density > 0.8 ? '0 0 10px rgba(59, 130, 246, 0.5)' : 'none'
                                        }}
                                    >
                                        {/* Tooltip */}
                                        <div className="absolute right-full top-1/2 -translate-y-1/2 mr-2 px-2 py-1 bg-black/90 border border-white/10 rounded text-[10px] text-white whitespace-nowrap hidden group-hover:block z-50">
                                            ${p.toFixed(2)} | {(density * 100).toFixed(1)}% Density
                                        </div>
                                    </div>
                                )
                            })}
                        </div>
                    </div>
                ))}
                
                {/* Y-Axis Labels (Left) */}
                <div className="absolute -left-8 top-0 bottom-0 flex flex-col justify-between text-[10px] text-slate-600 font-mono py-1">
                    {prices.map(p => <div key={p}>${p.toFixed(2)}</div>)}
                </div>
                
                {/* Current Price Line */}
                <div className="absolute left-0 right-0 top-[55%] border-t border-dashed border-white/30 pointer-events-none">
                     <span className="absolute -left-10 -top-2 text-[10px] text-white font-mono bg-black px-1">NOW</span>
                </div>
             </div>
        </div>
        
        {/* Spacer for bottom labels */}
        <div className="h-4" />
    </div>
  );
}
