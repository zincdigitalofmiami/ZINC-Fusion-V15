'use client';

import React from 'react';
import {
  Area,
  ComposedChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine
} from 'recharts';

interface ForecastConeProps {
  data?: any[]; // Allow passing real data later
}

// Generate high-quality mock data for the design preview
const generateMockData = () => {
  const data = [];
  let price = 48.00;
  
  // Historical (Past 30 days)
  for (let i = -30; i <= 0; i++) {
    const date = new Date();
    date.setDate(date.getDate() + i);
    price = price + (Math.random() - 0.5) * 0.5;
    data.push({
      date: date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
      price: Number(price.toFixed(2)),
      p10: null,
      p50: null,
      p90: null,
      type: 'historical'
    });
  }

  // Forecast (Next 21 days)
  let p50 = price;
  let spread = 0.5;
  for (let i = 1; i <= 21; i++) {
    const date = new Date();
    date.setDate(date.getDate() + i);
    p50 = p50 + 0.1; // Gentle uptrend
    spread += 0.15; // Widening cone based on uncertainty
    data.push({
      date: date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
      price: null,
      p50: Number(p50.toFixed(2)),
      p10: Number((p50 - spread).toFixed(2)),
      p90: Number((p50 + spread).toFixed(2)),
      type: 'forecast'
    });
  }
  return data;
};

export function ForecastConeChart({ data }: ForecastConeProps) {
  const chartData = data || generateMockData();

  return (
    <div className="w-full h-[400px] bg-[#0a0a0a] rounded-xl border border-white/5 p-4 relative">
        <div className="absolute top-4 left-4 z-10">
            <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
                <span className="text-xs font-mono text-blue-500 tracking-wider">LIVE FORECAST (L0-L3)</span>
            </div>
            <div className="text-2xl font-bold text-white mt-1">
                48.25 <span className="text-sm font-normal text-emerald-400">+1.2%</span>
            </div>
        </div>

        {/* Legend */}
        <div className="absolute top-4 right-4 z-10 flex flex-col items-end gap-1">
            <div className="flex items-center gap-2">
                <div className="w-3 h-[2px] bg-slate-400"></div>
                <span className="text-[10px] text-slate-400 uppercase tracking-wider">Historical</span>
            </div>
            <div className="flex items-center gap-2">
                <div className="w-3 h-[2px] bg-blue-500 border-dashed border-b"></div>
                <span className="text-[10px] text-blue-400 uppercase tracking-wider">P50 Forecast</span>
            </div>
            <div className="flex items-center gap-2">
                <div className="w-3 h-3 bg-blue-500/10 border border-blue-500/20 rounded-sm"></div>
                <span className="text-[10px] text-blue-400/60 uppercase tracking-wider">Confidence (P10-P90)</span>
            </div>
        </div>

      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={chartData} margin={{ top: 60, right: 30, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="coneGradient" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.1} />
              <stop offset="100%" stopColor="#3b82f6" stopOpacity={0.05} />
            </linearGradient>
            <linearGradient id="lineGradient" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="#94a3b8" />
              <stop offset="100%" stopColor="#3b82f6" />
            </linearGradient>
          </defs>
          
          <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
          
          <XAxis 
            dataKey="date" 
            stroke="#475569" 
            fontSize={12} 
            tickLine={false} 
            axisLine={false}
            interval={6}
          />
          
          <YAxis 
            domain={['auto', 'auto']} 
            stroke="#475569" 
            fontSize={12} 
            tickLine={false} 
            axisLine={false}
            tickFormatter={(val) => `$${val}`}
          />
          
          <Tooltip 
            contentStyle={{ 
                backgroundColor: '#0f172a', 
                borderColor: '#1e293b', 
                borderRadius: '8px', 
                boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.5)' 
            }}
            itemStyle={{ fontSize: '12px' }}
            labelStyle={{ color: '#94a3b8', marginBottom: '8px', fontSize: '11px', textTransform: 'uppercase' }}
          />

          {/* Historical Price */}
          <Line 
            type="monotone" 
            dataKey="price" 
            stroke="url(#lineGradient)" 
            strokeWidth={2} 
            dot={false}
            connectNulls
          />

          {/* Area needs proper implementation in Recharts 2.x, skipping fill for now to be safe, just lines */}
           
          {/* Forecast P50 Line */}
           <Line 
            type="monotone" 
            dataKey="p50" 
            stroke="#3b82f6" 
            strokeDasharray="5 5" 
            strokeWidth={2} 
            dot={false}
            connectNulls
          />
          
          {/* Upper/Lower Bounds Lines */}
          <Line type="monotone" dataKey="p90" stroke="#3b82f6" strokeOpacity={0.2} strokeWidth={1} dot={false} connectNulls />
          <Line type="monotone" dataKey="p10" stroke="#3b82f6" strokeOpacity={0.2} strokeWidth={1} dot={false} connectNulls />
          
          {/* Current Day Line */}
          <ReferenceLine x={new Date().toLocaleDateString('en-US', { month: 'short', day: 'numeric' })} stroke="#fff" strokeDasharray="3 3" />

        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
