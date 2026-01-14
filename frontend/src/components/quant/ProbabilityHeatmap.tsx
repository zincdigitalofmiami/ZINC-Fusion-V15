'use client';

import React from 'react';

export function ProbabilityHeatmap() {
  return (
    <div className="w-full bg-[#0a0a0a] border border-white/5 rounded-xl p-6 shadow-sm overflow-hidden">
        <div className="flex items-center justify-between mb-2">
            <div>
                 <h3 className="text-sm font-semibold text-white uppercase tracking-wider">L3 Probability Surface</h3>
                 <p className="text-xs text-slate-500">No data available (real-data-only mode)</p>
            </div>
        </div>

        <div className="mt-6 text-sm text-slate-400">
            Populate the probability surface by running L3 (Monte Carlo / risk engine). This widget renders only real distributions.
        </div>
    </div>
  );
}
