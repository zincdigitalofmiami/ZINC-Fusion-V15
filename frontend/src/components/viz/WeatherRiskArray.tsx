'use client';

import React from 'react';
import { CloudRain, Wind, Thermometer, Droplets, Zap, Sun } from 'lucide-react';

export function WeatherRiskArray() {
  return (
    <div className="bg-[#0a0a0a] border border-white/5 rounded-xl p-6 relative overflow-hidden group">
        <div className="flex items-center justify-between mb-4 relative z-10">
            <div>
                 <h3 className="text-sm font-semibold text-white uppercase tracking-wider flex items-center gap-2">
                    <CloudRain size={16} className="text-blue-400" />
                    NOAA Precip Matrix
                 </h3>
                 <p className="text-[10px] text-slate-500 font-mono mt-1">
                    No data available (real-data-only mode)
                 </p>
            </div>
        </div>

        <div className="text-sm text-slate-400">
            Wire this widget to real NOAA-derived metrics (no synthetic grids).
        </div>
    </div>
  );
}
