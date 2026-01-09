'use client';

import React, { useMemo } from 'react';
import { motion } from 'framer-motion';

// Types
interface AttributionFactor {
  id: string;
  label: string;
  value: number; // impact in cents/lb
  type: 'positive' | 'negative';
  category: 'cell' | 'macro' | 'technical' | 'noise';
}

interface WaterfallProps {
  prevPrice: number;
  currentPrice: number;
  factors?: AttributionFactor[];
}

export function FactorWaterfall({ prevPrice, currentPrice, factors }: WaterfallProps) {
  // Data aligned with "Big 11" Specialist Taxonomy
  const data: AttributionFactor[] = factors || [
    { id: '1', label: 'Crush (USDA)', value: 0.35, type: 'positive', category: 'cell' },
    { id: '2', label: 'China (Imports)', value: 0.22, type: 'positive', category: 'cell' },
    { id: '3', label: 'Energy (RVO)', value: -0.15, type: 'negative', category: 'cell' },
    { id: '4', label: 'Trump (Tariff)', value: 0.08, type: 'positive', category: 'macro' },
    { id: '5', label: 'Macro (Rates)', value: -0.05, type: 'negative', category: 'macro' },
  ];

  // Calculate cumulative steps for the waterfall bridge
  const steps = useMemo(() => {
    let runningTotal = prevPrice;
    return data.map(factor => {
      const start = runningTotal;
      const end = runningTotal + factor.value;
      runningTotal = end;
      return { ...factor, start, end };
    });
  }, [data, prevPrice]);

  const maxVal = Math.max(prevPrice, currentPrice, ...steps.map(s => Math.max(s.start, s.end)));
  const minVal = Math.min(prevPrice, currentPrice, ...steps.map(s => Math.min(s.start, s.end)));
  const range = maxVal - minVal;
  const padding = range * 0.1;

  // Scale function
  const scale = (val: number) => {
    return ((val - (minVal - padding)) / (range + padding * 2)) * 100;
  };

  return (
    <div className="w-full bg-[#0a0a0a] border border-white/5 rounded-xl p-6 shadow-sm">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h3 className="text-sm font-semibold text-white uppercase tracking-wider">Factor Attribution</h3>
          <p className="text-xs text-slate-500">Why the forecast moved (Waterfall)</p>
        </div>
        <div className="text-right">
          <div className="text-xs text-slate-500 font-mono mb-1">NET CHANGE</div>
          <div className={`text-lg font-mono font-bold ${(currentPrice - prevPrice) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
            {(currentPrice - prevPrice) > 0 ? '+' : ''}{(currentPrice - prevPrice).toFixed(2)}¢
          </div>
        </div>
      </div>

      <div className="relative h-64 w-full">
        {/* Y-Axis Grid */}
        <div className="absolute inset-0 flex flex-col justify-between text-[10px] text-slate-600 font-mono pointer-events-none">
           {[...Array(5)].map((_, i) => (
             <div key={i} className="border-b border-white/5 w-full h-full relative">
                <span className="absolute -top-2 left-0">
                    {((maxVal + padding) - (i * ((range + padding * 2) / 4))).toFixed(2)}
                </span>
             </div>
           ))}
        </div>

        {/* Bars Container */}
        <div className="absolute inset-0 flex items-end justify-between pl-10 pr-4 pb-0 pt-0 h-full">
            {/* Start Bar */}
            <div className="relative flex flex-col items-center group w-12 h-full">
                 <motion.div 
                    initial={{ height: 0 }}
                    animate={{ height: `${scale(prevPrice)}%` }}
                    className="w-full bg-slate-700/50 rounded-t-sm border border-slate-600 absolute bottom-0"
                 />
                 <div className="absolute -bottom-6 text-[10px] text-slate-400 font-mono">Yesterday</div>
                 <div className="absolute -top-6 text-xs text-white font-mono opacity-0 group-hover:opacity-100 transition-opacity">
                     {prevPrice.toFixed(2)}
                 </div>
            </div>

            {/* Factor Steps */}
            {steps.map((step, i) => (
                <div key={step.id} className="relative flex flex-col items-center group flex-1 mx-1 h-full">
                    {/* The Bar */}
                    <motion.div 
                         initial={{ opacity: 0, scaleY: 0 }}
                         animate={{ opacity: 1, scaleY: 1 }}
                         transition={{ delay: i * 0.1 }}
                         style={{
                             bottom: `${scale(Math.min(step.start, step.end))}%`,
                             height: `${Math.abs(scale(step.end) - scale(step.start))}%`
                         }}
                         className={`w-full absolute rounded-sm border ${
                             step.type === 'positive' 
                                ? 'bg-emerald-500/20 border-emerald-500' 
                                : 'bg-red-500/20 border-red-500'
                         }`}
                    />
                    {/* Connector Line */}
                    {i < steps.length - 1 && (
                         <div 
                            className="absolute bg-white/10 h-[1px] w-[200%] right-[-100%] z-0 border-t border-dashed border-white/20"
                            style={{ bottom: `${scale(step.end)}%` }}
                         />
                    )}
                    
                    {/* Label */}
                    <div className="absolute -bottom-6 text-[10px] text-slate-500 font-mono truncate max-w-full text-center opacity-70">
                        {step.label.split(' ')[0]}
                    </div>
                    {/* Tooltip Value */}
                    <div className={`absolute -top-8 text-[10px] font-mono font-bold opacity-0 group-hover:opacity-100 transition-opacity ${
                        step.type === 'positive' ? 'text-emerald-400' : 'text-red-400'
                    }`}>
                        {step.type === 'positive' ? '+' : ''}{step.value.toFixed(2)}
                    </div>
                </div>
            ))}

            {/* End Bar */}
            <div className="relative flex flex-col items-center group w-12 h-full">
                 <motion.div 
                    initial={{ height: 0 }}
                    animate={{ height: `${scale(currentPrice)}%` }}
                    className="w-full bg-blue-600/50 rounded-t-sm border border-blue-500 absolute bottom-0"
                 />
                 <div className="absolute -bottom-6 text-[10px] text-blue-400 font-bold font-mono">Today</div>
                 <div className="absolute -top-6 text-xs text-white font-mono opacity-0 group-hover:opacity-100 transition-opacity">
                     {currentPrice.toFixed(2)}
                 </div>
            </div>
        </div>
      </div>
    </div>
  );
}
