'use client';

import React from 'react';
import { CloudRain, Wind, Thermometer, Droplets, Zap, Sun } from 'lucide-react';

const WEATHER_STATIONS = [
    { id: 'USW00014820', name: 'Cleveland', state: 'OH', region: 'Midwest', precip: 0.2, temp: 45, anomaly: 'high' },
    { id: 'USW00094846', name: 'Chicago', state: 'IL', region: 'Midwest', precip: 0.0, temp: 42, anomaly: 'neutral' },
    { id: 'USW00014923', name: 'Waterloo', state: 'IA', region: 'Midwest', precip: 1.2, temp: 38, anomaly: 'high' }, // heavy rain
    { id: 'USW00013967', name: 'Oklahoma City', state: 'OK', region: 'Plains', precip: 0.0, temp: 55, anomaly: 'low' },
    { id: 'USW00093814', name: 'Cincinnati', state: 'OH', region: 'Midwest', precip: 0.1, temp: 48, anomaly: 'neutral' },
    { id: 'USW00014936', name: 'Sioux Falls', state: 'SD', region: 'Plains', precip: 0.0, temp: 30, anomaly: 'neutral' },
    { id: 'USW00014735', name: 'Albany', state: 'NY', region: 'East', precip: 0.3, temp: 40, anomaly: 'high' },
    { id: 'USW00014839', name: 'Toledo', state: 'OH', region: 'Midwest', precip: 0.0, temp: 44, anomaly: 'neutral' },
    { id: 'USW00014933', name: 'Des Moines', state: 'IA', region: 'Midwest', precip: 0.8, temp: 39, anomaly: 'high' },
    { id: 'USW00014848', name: 'South Bend', state: 'IN', region: 'Midwest', precip: 0.4, temp: 41, anomaly: 'high' },
];

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
                    57 Stations // 10 Variables // T+5d Forecast
                 </p>
            </div>
            <div className="flex items-center gap-2">
                <span className="text-[10px] font-mono text-slate-500">AVG SOIL MOISTURE</span>
                <span className="text-xs font-bold text-emerald-400">82%</span>
            </div>
        </div>

        {/* The Matrix */}
        <div className="grid grid-cols-10 gap-1 mb-4 relative z-10">
            {/* Generate a grid of 57 cells to represent the stations */}
            {Array.from({ length: 57 }).map((_, i) => {
                // Mock data simulation based on index
                const isMidwest = i > 10 && i < 40;
                const hasPrecip = isMidwest && i % 3 === 0;
                const isSnow = i > 50;
                
                return (
                    <div 
                        key={i} 
                        className={`
                            h-6 w-full rounded-sm border cursor-help transition-all duration-300
                            ${hasPrecip 
                                ? 'bg-blue-500/20 border-blue-500/40 hover:bg-blue-500/40' 
                                : isSnow 
                                    ? 'bg-slate-200/20 border-slate-200/40 hover:bg-white/40'
                                    : 'bg-emerald-900/10 border-emerald-900/20 hover:bg-emerald-900/30'
                            }
                        `}
                        title={`Station ID: USW000${14000+i} \nPrecip: ${hasPrecip ? '0.8mm' : '0.0mm'}`}
                    />
                )
            })}
        </div>

        {/* Legend */}
        <div className="flex justify-between items-center text-[10px] text-slate-500 font-mono border-t border-white/5 pt-3">
             <div className="flex items-center gap-4">
                <div className="flex items-center gap-1">
                    <div className="w-2 h-2 bg-emerald-900/20 border border-emerald-900/30 rounded-sm"></div>
                    <span>DRY</span>
                </div>
                <div className="flex items-center gap-1">
                    <div className="w-2 h-2 bg-blue-500/20 border border-blue-500/40 rounded-sm"></div>
                    <span>RAIN</span>
                </div>
                <div className="flex items-center gap-1">
                    <div className="w-2 h-2 bg-slate-200/20 border border-slate-200/40 rounded-sm"></div>
                    <span>SNOW</span>
                </div>
             </div>
             
             <div>
                DATA: NOAA CDO (Daily)
             </div>
        </div>
    </div>
  );
}
