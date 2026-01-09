'use client';

import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { Calculator, DollarSign, Scale } from 'lucide-react';

type Horizon = '5d' | '21d' | '63d' | '126d';

export function ContractImpactCalculator() {
  const [contracts, setContracts] = useState(1);
  const [horizon, setHorizon] = useState<Horizon>('63d');
  const POUNDS_PER_CONTRACT = 60000;
  
  // Data sourced from COMPLETE_DATA_INVENTORY.md (Horizons & Models)
  const SCENARIOS = {
      '5d': { 
          label: '1 Week',
          model: 'Ensemble (Chronos2 + DeepAR)',
          current: 48.25, p10: 47.90, p50: 48.40, p90: 48.95, trend: 'Neutral' 
      },
      '21d': { 
          label: '1 Month',
          model: 'WeightedEnsemble (L1)',
          current: 48.25, p10: 46.50, p50: 49.10, p90: 51.20, trend: 'Bullish' 
      },
      '63d': { 
          label: '3 Months',
          model: 'DirectTabular (Quarterly)',
          current: 48.25, p10: 45.00, p50: 49.80, p90: 53.10, trend: 'Bullish' 
      },
      '126d': { 
          label: '6 Months',
          model: 'Chronos2SmallFineTuned',
          current: 48.25, p10: 42.00, p50: 47.50, p90: 55.00, trend: 'High Vol' 
      }
  };

  const currentScenario = SCENARIOS[horizon];
  const { current, p10, p50, p90 } = currentScenario;

  const calculatePnL = (forecastPrice: number) => {
    const diff = forecastPrice - current; // cents/lb
    const diffDollars = diff / 100; // dollars/lb
    return diffDollars * (contracts * POUNDS_PER_CONTRACT);
  };

  const pnlP10 = calculatePnL(p10);
  const pnlP50 = calculatePnL(p50);
  const pnlP90 = calculatePnL(p90);

  const formatCurrency = (val: number) => {
    const sign = val >= 0 ? '+' : '';
    return `${sign}${new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(val)}`;
  };
  
  const getPnlColor = (val: number) => {
      if (val > 0) return 'text-emerald-400';
      if (val < 0) return 'text-red-400';
      return 'text-slate-400';
  };

  return (
    <div className="w-full bg-[#0a0a0a] border border-white/5 rounded-xl p-6 shadow-sm">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
            <div className="p-2 bg-zinc-800 rounded-lg text-zinc-100 border border-zinc-700">
                <Scale size={20} />
            </div>
            <div>
                <h3 className="text-sm font-semibold text-white uppercase tracking-wider">Scenario Analysis</h3>
                <p className="text-xs text-slate-500">PnL Simulation vs Confidence Bands</p>
            </div>
        </div>
        
        {/* Horizon Selector */}
        <div className="flex bg-zinc-900 rounded-lg p-1 border border-white/5 relative">
            {(['5d', '21d', '63d', '126d'] as Horizon[]).map((h) => (
                <button
                    key={h}
                    onClick={() => setHorizon(h)}
                    className={`relative px-3 py-1 text-[10px] font-mono rounded-md transition-all z-10 ${
                        horizon === h 
                        ? 'bg-blue-600 text-white shadow-lg' 
                        : 'text-slate-500 hover:text-slate-300'
                    }`}
                >
                    {h.toUpperCase()}
                    {h === '63d' && (
                        <div className="absolute -top-1 -right-1 w-2 h-2 bg-emerald-500 rounded-full animate-pulse border border-[#0a0a0a]" title="Optimal Risk/Reward" />
                    )}
                </button>
            ))}
        </div>
      </div>

      <div className="mb-4">
         <div className="flex justify-between items-center text-[10px] text-slate-500 font-mono bg-white/5 p-2 rounded border border-white/5">
            <span>ACTIVE MODEL:</span>
            <span className="text-blue-400">{SCENARIOS[horizon].model}</span>
         </div>
      </div>

      {/* Input */}
      <div className="mb-8">
        <div className="flex justify-between text-sm mb-2">
            <span className="text-slate-400">Position Size</span>
            <span className="text-white font-mono text-lg">{contracts} Lot{contracts > 1 ? 's' : ''} <span className="text-slate-500 text-xs">({(contracts * 0.6).toFixed(1)}M lbs)</span></span>
        </div>
        <input 
            type="range" 
            min="1" 
            max="50" 
            value={contracts} 
            onChange={(e) => setContracts(Number(e.target.value))}
            className="w-full h-2 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-blue-600"
        />
        <div className="flex justify-between text-[10px] text-slate-600 mt-2 font-mono">
            <span>MIN (1)</span>
            <span>MAX (50)</span>
        </div>
      </div>

      {/* Scenarios */}
      <div className="space-y-3">
         {/* P90 Upside */}
         <motion.div 
            key={`${horizon}-p90`}
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            className="flex items-center justify-between p-3 rounded-lg bg-emerald-500/5 border border-emerald-500/10"
         >
             <div>
                 <div className="text-xs text-emerald-500 font-bold uppercase tracking-wider">Blue Sky (P90)</div>
                 <div className="text-[10px] text-emerald-500/60">Price hits {p90.toFixed(2)}</div>
             </div>
             <div className={`text-lg font-mono font-bold ${getPnlColor(pnlP90)}`}>
                 {formatCurrency(pnlP90)}
             </div>
         </motion.div>

         {/* P50 Base */}
         <motion.div 
            key={`${horizon}-p50`}
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.1 }}
            className="flex items-center justify-between p-3 rounded-lg bg-blue-500/5 border border-blue-500/10"
         >
             <div>
                 <div className="text-xs text-blue-400 font-bold uppercase tracking-wider">Base Case (P50)</div>
                 <div className="text-[10px] text-blue-400/60">Price hits {p50.toFixed(2)}</div>
             </div>
             <div className={`text-lg font-mono font-bold ${getPnlColor(pnlP50)}`}>
                 {formatCurrency(pnlP50)}
             </div>
         </motion.div>

         {/* P10 Downside */}
         <motion.div 
            key={`${horizon}-p10`}
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.2 }}
            className="flex items-center justify-between p-3 rounded-lg bg-red-500/5 border border-red-500/10"
         >
             <div>
                 <div className="text-xs text-red-400 font-bold uppercase tracking-wider">Downside Risk (P10)</div>
                 <div className="text-[10px] text-red-400/60">Price hits {p10.toFixed(2)}</div>
             </div>
             <div className={`text-lg font-mono font-bold ${getPnlColor(pnlP10)}`}>
                 {formatCurrency(pnlP10)}
             </div>
         </motion.div>
      </div>
    </div>
  );
}
