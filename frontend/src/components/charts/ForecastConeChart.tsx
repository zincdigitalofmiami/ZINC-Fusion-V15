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
} from 'recharts';

interface ForecastConeProps {
  data?: any[];
}

export function ForecastConeChart({ data }: ForecastConeProps) {
  const chartData = data ?? [];

  if (!chartData.length) {
    return (
      <div className="w-full h-[400px] bg-[#0a0a0a] rounded-xl border border-white/5 p-4 flex items-center justify-center">
        <div className="text-sm text-slate-400">No forecast data available.</div>
      </div>
    );
  }

  return (
    <div className="w-full h-[400px] bg-[#0a0a0a] rounded-xl border border-white/5 p-4 relative">
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
