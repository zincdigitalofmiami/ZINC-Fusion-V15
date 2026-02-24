"use client";

import React, { useState, useMemo } from "react";
import { motion } from "framer-motion";
import { Scale } from "lucide-react";

type Horizon = "5d" | "21d" | "63d" | "126d";

interface ForecastInput {
  label: string;
  days: number;
  targetLow: number | null;
  targetMid: number | null;
  targetHigh: number | null;
  source: 'model' | 'unavailable';
}

interface ContractImpactProps {
  currentPrice?: number;
  forecasts?: ForecastInput[];
}

const HORIZON_DAYS: Record<Horizon, number> = {
  "5d": 5,
  "21d": 21,
  "63d": 63,
  "126d": 126,
};

export function ContractImpactCalculator({ currentPrice = 0, forecasts = [] }: ContractImpactProps) {
  const [contracts, setContracts] = useState(1);
  const [horizon, setHorizon] = useState<Horizon>("63d");
  const POUNDS_PER_CONTRACT = 60000;

  // Map forecasts by days for quick lookup
  const forecastByDays = useMemo(() => {
    const map: Record<number, ForecastInput> = {};
    for (const fc of forecasts) {
      map[fc.days] = fc;
    }
    return map;
  }, [forecasts]);

  const targetDays = HORIZON_DAYS[horizon];
  const fc = forecastByDays[targetDays];

  const hasData = fc && fc.source === 'model' && fc.targetMid !== null && currentPrice > 0;

  const p30 = fc?.targetLow ?? 0;
  const p50 = fc?.targetMid ?? 0;
  const p70 = fc?.targetHigh ?? 0;

  const calculatePnL = (forecastPrice: number) => {
    const diff = forecastPrice - currentPrice; // diff in cents/lb (ZL quoted in cents)
    const diffDollars = diff / 100; // convert to dollars/lb for P&L
    return diffDollars * (contracts * POUNDS_PER_CONTRACT);
  };

  const pnlP70 = calculatePnL(p70);
  const pnlP50 = calculatePnL(p50);
  const pnlP30 = calculatePnL(p30);

  const formatCurrency = (val: number) => {
    const sign = val >= 0 ? "+" : "";
    return `${sign}${new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
      maximumFractionDigits: 0,
    }).format(val)}`;
  };

  const getPnlColor = (val: number) => {
    if (val > 0) return "text-emerald-400";
    if (val < 0) return "text-red-400";
    return "text-slate-400";
  };

  return (
    <div className="w-full bg-[#0a0a0a] border border-white/5 rounded-xl p-6 shadow-sm">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-zinc-800 rounded-lg text-zinc-100 border border-zinc-700">
            <Scale size={20} />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-white uppercase tracking-wider">
              Scenario Analysis
            </h3>
            <p className="text-xs text-slate-500">
              PnL Simulation — P30 / P50 / P70
            </p>
          </div>
        </div>

        {/* Horizon Selector */}
        <div className="flex bg-zinc-900 rounded-lg p-1 border border-white/5 relative">
          {(["5d", "21d", "63d", "126d"] as Horizon[]).map((h) => (
            <button
              key={h}
              onClick={() => setHorizon(h)}
              className={`relative px-3 py-1 text-[10px] font-mono rounded-md transition-all z-10 ${
                horizon === h
                  ? "bg-blue-600 text-white shadow-lg"
                  : "text-slate-500 hover:text-slate-300"
              }`}
            >
              {h.toUpperCase()}
              {h === "63d" && (
                <div
                  className="absolute -top-1 -right-1 w-2 h-2 bg-emerald-500 rounded-full animate-pulse border border-[#0a0a0a]"
                  title="Optimal Risk/Reward"
                />
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Current price context */}
      <div className="mb-4">
        <div className="flex justify-between items-center text-[10px] text-slate-500 font-mono bg-white/5 p-2 rounded border border-white/5">
          <span>CURRENT ZL:</span>
          <span className="text-blue-400">
            {currentPrice > 0 ? `$${currentPrice.toFixed(2)}` : '—'}
          </span>
        </div>
      </div>

      {/* Input */}
      <div className="mb-8">
        <div className="flex justify-between text-sm mb-2">
          <span className="text-slate-400">Position Size</span>
          <span className="text-white font-mono text-lg">
            {contracts} Lot{contracts > 1 ? "s" : ""}{" "}
            <span className="text-slate-500 text-xs">
              ({(contracts * 0.6).toFixed(1)}M lbs)
            </span>
          </span>
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
      {hasData ? (
        <div className="space-y-3">
          {/* P70 Upside */}
          <motion.div
            key={`${horizon}-p70`}
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            className="flex items-center justify-between p-3 rounded-lg bg-emerald-500/5 border border-emerald-500/10"
          >
            <div>
              <div className="text-xs text-emerald-500 font-bold uppercase tracking-wider">
                Upside (P70)
              </div>
              <div className="text-[10px] text-emerald-500/60">
                Price hits ${p70.toFixed(2)}
              </div>
            </div>
            <div className={`text-lg font-mono font-bold ${getPnlColor(pnlP70)}`}>
              {formatCurrency(pnlP70)}
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
              <div className="text-xs text-blue-400 font-bold uppercase tracking-wider">
                Base Case (P50)
              </div>
              <div className="text-[10px] text-blue-400/60">
                Price hits ${p50.toFixed(2)}
              </div>
            </div>
            <div className={`text-lg font-mono font-bold ${getPnlColor(pnlP50)}`}>
              {formatCurrency(pnlP50)}
            </div>
          </motion.div>

          {/* P30 Downside */}
          <motion.div
            key={`${horizon}-p30`}
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.2 }}
            className="flex items-center justify-between p-3 rounded-lg bg-red-500/5 border border-red-500/10"
          >
            <div>
              <div className="text-xs text-red-400 font-bold uppercase tracking-wider">
                Downside (P30)
              </div>
              <div className="text-[10px] text-red-400/60">
                Price hits ${p30.toFixed(2)}
              </div>
            </div>
            <div className={`text-lg font-mono font-bold ${getPnlColor(pnlP30)}`}>
              {formatCurrency(pnlP30)}
            </div>
          </motion.div>
        </div>
      ) : (
        <div className="flex items-center justify-center py-8 text-sm text-slate-500">
          No forecast data for {horizon.toUpperCase()} horizon
        </div>
      )}
    </div>
  );
}
