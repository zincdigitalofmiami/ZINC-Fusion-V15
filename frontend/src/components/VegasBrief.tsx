'use client';

import React, { useEffect, useState } from 'react';

// =============================================================================
// TYPES (matching API response)
// =============================================================================

interface PriceSummary {
  current: number;
  previousClose: number;
  change: number;
  changePct: number;
  weekHigh: number;
  weekLow: number;
  asOf: string;
}

interface ForecastHorizon {
  label: string;
  days: number;
  targetLow: number;
  targetMid: number;
  targetHigh: number;
  expectedChange: string;
  expectedChangePct: string;
  direction: 'UP' | 'DOWN' | 'FLAT';
}

interface DriverSummary {
  name: string;
  score: number;
  status: string;
  impact: string;
}

interface CorrelationSummary {
  asset: string;
  correlation: number;
  direction: string;
  implication: string;
}

interface VegasBriefData {
  generatedAt: string;
  asOfDate: string;
  tldr: string;
  recommendation: string;
  recommendationColor: string;
  price: PriceSummary;
  forecasts: ForecastHorizon[];
  drivers: DriverSummary[];
  driversSummary: string;
  correlations: CorrelationSummary[];
  policyContext: string;
  keyRisks: string[];
  keyPositives: string[];
}

// =============================================================================
// COMPONENT
// =============================================================================

export function VegasBrief() {
  const [brief, setBrief] = useState<VegasBriefData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    async function fetchBrief() {
      try {
        const res = await fetch('/api/vegas/brief');
        if (!res.ok) throw new Error('Failed to fetch brief');
        const data = await res.json();
        setBrief(data);
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to load brief');
      } finally {
        setLoading(false);
      }
    }
    fetchBrief();
  }, []);

  if (loading) {
    return (
      <div className="bg-slate-900/80 rounded-xl border border-slate-700 p-6 animate-pulse">
        <div className="h-6 bg-slate-700 rounded w-1/3 mb-4" />
        <div className="h-4 bg-slate-700 rounded w-full mb-2" />
        <div className="h-4 bg-slate-700 rounded w-2/3" />
      </div>
    );
  }

  if (error || !brief) {
    return (
      <div className="bg-red-900/20 border border-red-500/30 rounded-xl p-4 text-red-400">
        {error || 'Brief unavailable'}
      </div>
    );
  }

  return (
    <div className="bg-gradient-to-br from-slate-900 via-slate-900 to-slate-800 rounded-xl border border-slate-700 shadow-2xl">
      {/* Header */}
      <div className="p-4 border-b border-slate-700 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="text-2xl">📧</div>
          <div>
            <h2 className="text-lg font-bold text-white">Daily Brief</h2>
            <p className="text-xs text-slate-400">
              {new Date(brief.generatedAt).toLocaleString()}
            </p>
          </div>
        </div>
        <div
          className="px-4 py-2 rounded-lg font-bold text-sm"
          style={{
            backgroundColor: brief.recommendationColor + '20',
            color: brief.recommendationColor,
            border: `1px solid ${brief.recommendationColor}50`
          }}
        >
          {brief.recommendation}
        </div>
      </div>

      {/* TL;DR */}
      <div className="p-4 bg-slate-800/50 border-b border-slate-700">
        <div className="text-xs font-bold text-yellow-400 mb-2 uppercase tracking-wider">
          TL;DR
        </div>
        <p className="text-slate-200 leading-relaxed">{brief.tldr}</p>
      </div>

      {/* Price & Forecasts */}
      <div className="p-4 border-b border-slate-700">
        <div className="flex items-center gap-2 mb-3">
          <span className="text-3xl font-bold text-white">
            {brief.price.current.toFixed(2)}¢
          </span>
          <span
            className={`text-lg font-semibold ${
              brief.price.changePct >= 0 ? 'text-green-400' : 'text-red-400'
            }`}
          >
            {brief.price.changePct >= 0 ? '+' : ''}{brief.price.changePct.toFixed(2)}%
          </span>
          <span className="text-slate-500 text-sm">today</span>
        </div>

        <div className="text-xs font-bold text-slate-400 mb-2 uppercase tracking-wider">
          Forecasts
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {brief.forecasts.map((f) => (
            <div
              key={f.days}
              className="bg-slate-800/80 rounded-lg p-3 border border-slate-700"
            >
              <div className="text-xs text-slate-400 mb-1">{f.label}</div>
              <div className="flex items-baseline gap-2">
                <span className="text-lg font-bold text-white">
                  {f.targetMid.toFixed(1)}¢
                </span>
                <span
                  className={`text-sm font-semibold ${
                    f.direction === 'UP' ? 'text-green-400' :
                    f.direction === 'DOWN' ? 'text-red-400' : 'text-slate-400'
                  }`}
                >
                  {f.expectedChangePct}
                </span>
              </div>
              <div className="text-[10px] text-slate-500 mt-1">
                Range: {f.targetLow.toFixed(1)} - {f.targetHigh.toFixed(1)}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Drivers Quick View */}
      <div className="p-4 border-b border-slate-700">
        <div className="text-xs font-bold text-slate-400 mb-2 uppercase tracking-wider">
          Key Drivers
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          {brief.drivers.map((d) => (
            <div key={d.name} className="flex items-center gap-2 bg-slate-800/50 rounded-lg p-2">
              <div
                className="w-2 h-2 rounded-full"
                style={{
                  backgroundColor: d.score >= 65 ? '#EF4444' :
                                   d.score >= 50 ? '#F97316' :
                                   d.score <= 35 ? '#22C55E' : '#EAB308'
                }}
              />
              <div>
                <div className="text-xs font-semibold text-white">{d.name}</div>
                <div className="text-[10px] text-slate-400">{d.status}</div>
              </div>
            </div>
          ))}
        </div>
        <p className="text-sm text-slate-400 mt-2 italic">{brief.driversSummary}</p>
      </div>

      {/* Expand/Collapse for more details */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full p-3 text-sm text-slate-400 hover:text-white hover:bg-slate-800/50 transition-colors flex items-center justify-center gap-2"
      >
        {expanded ? 'Show Less' : 'Show More Details'}
        <svg
          className={`w-4 h-4 transition-transform ${expanded ? 'rotate-180' : ''}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* Expanded Content */}
      {expanded && (
        <div className="border-t border-slate-700">
          {/* Correlations */}
          <div className="p-4 border-b border-slate-700">
            <div className="text-xs font-bold text-slate-400 mb-2 uppercase tracking-wider">
              Key Correlations
            </div>
            <div className="space-y-2">
              {brief.correlations.map((c) => (
                <div key={c.asset} className="flex items-center justify-between bg-slate-800/30 rounded-lg p-2">
                  <div className="flex items-center gap-3">
                    <div
                      className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold"
                      style={{
                        backgroundColor: c.correlation > 0 ? '#22C55E20' : '#EF444420',
                        color: c.correlation > 0 ? '#22C55E' : '#EF4444'
                      }}
                    >
                      {c.correlation > 0 ? '+' : ''}{(c.correlation * 100).toFixed(0)}%
                    </div>
                    <div>
                      <div className="text-sm font-semibold text-white">{c.asset}</div>
                      <div className="text-xs text-slate-400">{c.direction}</div>
                    </div>
                  </div>
                  <div className="text-xs text-slate-500 text-right max-w-[200px]">
                    {c.implication}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Policy Context */}
          <div className="p-4 border-b border-slate-700">
            <div className="text-xs font-bold text-slate-400 mb-2 uppercase tracking-wider">
              Policy & Legislation
            </div>
            <p className="text-sm text-slate-300 leading-relaxed">{brief.policyContext}</p>
          </div>

          {/* Risks & Positives */}
          <div className="grid md:grid-cols-2 gap-0">
            <div className="p-4 border-r border-slate-700">
              <div className="text-xs font-bold text-red-400 mb-2 uppercase tracking-wider">
                Key Risks
              </div>
              <ul className="space-y-1">
                {brief.keyRisks.map((risk, i) => (
                  <li key={i} className="text-sm text-slate-300 flex items-start gap-2">
                    <span className="text-red-400 mt-1">•</span>
                    <span>{risk}</span>
                  </li>
                ))}
              </ul>
            </div>
            <div className="p-4">
              <div className="text-xs font-bold text-green-400 mb-2 uppercase tracking-wider">
                Key Positives
              </div>
              <ul className="space-y-1">
                {brief.keyPositives.map((pos, i) => (
                  <li key={i} className="text-sm text-slate-300 flex items-start gap-2">
                    <span className="text-green-400 mt-1">•</span>
                    <span>{pos}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
