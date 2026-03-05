'use client';

import React, { useEffect, useState, useCallback, useRef } from 'react';
import { FusionBrain } from '@/components/viz/FusionBrain';
import { RegimeAnalysisChart } from '@/components/RegimeAnalysisChart';
import { ContractImpactCalculator } from '@/components/tools/ContractImpactCalculator';
import { FactorWaterfall } from '@/components/quant/FactorWaterfall';
import { ProbabilityHeatmap } from '@/components/quant/ProbabilityHeatmap';
import { WeatherRiskArray } from '@/components/viz/WeatherRiskArray';
import { Target, Shield, Zap, AlertTriangle, RefreshCw, Loader2, TrendingUp, TrendingDown, Minus, Brain } from 'lucide-react';

// Brief API types
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
  targetLow: number | null;
  targetMid: number | null;
  targetHigh: number | null;
  expectedChange: string;
  expectedChangePct: string;
  direction: 'UP' | 'DOWN' | 'FLAT' | 'NO DATA';
  source: 'model' | 'unavailable';
}

interface DriverSummary {
  name: string;
  score: number;
  status: string;
  impact: string;
  rawValue: number | null;
  unit: string;
  asOfDate: string | null;
  source: 'live' | 'stale' | 'unavailable';
}

interface CorrelationSummary {
  asset: string;
  correlation: number | null;
  direction: string;
  implication: string;
  lookbackDays: number;
  source: 'calculated' | 'unavailable';
}

interface EventPulseEvent {
  headline: string;
  source: string;
  event_date: string;
  sentiment: 'bullish' | 'bearish' | 'neutral';
  confidence: number;
  tags: string[];
  hoursAgo: number;
}

interface EventPulse {
  recentEvents: EventPulseEvent[];
  velocity: {
    last24h: number;
    last48h: number;
    last72h: number;
    baseline7d: number;
    velocityRatio: number;
  };
  netSentiment: {
    bullish: number;
    bearish: number;
    neutral: number;
    netScore: number;
    signal: 'STRONGLY_BULLISH' | 'BULLISH' | 'NEUTRAL' | 'BEARISH' | 'STRONGLY_BEARISH';
  };
}

interface BriefData {
  generatedAt: string;
  asOfDate: string;
  tldr: string;
  recommendation: 'BUY NOW' | 'WAIT' | 'NORMAL SCHEDULE' | 'LOCK IN COVERAGE' | 'CHECK DATA';
  recommendationColor: string;
  price: PriceSummary;
  forecasts: ForecastHorizon[];
  forecastsAvailable: boolean;
  drivers: DriverSummary[];
  driversSummary: string;
  correlations: CorrelationSummary[];
  keyRisks: string[];
  keyPositives: string[];
  eventPulse: EventPulse;
  overrideReason?: string;
  dataIssues: string[];
  stalenessWarnings: string[];
  dataQuality: 'good' | 'partial' | 'poor';
  dataStaleness?: {
    allFresh: boolean;
    staleSources: Array<{ driver: string; daysStale: number | null; sla: number }>;
  };
}

// Map recommendation to posture display
// When overrideReason is set, LOCK IN COVERAGE = urgent (red). Without override = favorable (green).
const POSTURE_MAP: Record<string, { label: string; color: string; gradient: string }> = {
  'LOCK IN COVERAGE': { label: 'ACCUMULATE', color: 'text-emerald-400', gradient: 'from-emerald-500/5' },
  'LOCK IN COVERAGE:OVERRIDE': { label: 'LOCK IN NOW', color: 'text-red-400', gradient: 'from-red-500/5' },
  'BUY NOW': { label: 'BUY NOW', color: 'text-emerald-400', gradient: 'from-emerald-500/5' },
  'NORMAL SCHEDULE': { label: 'HOLD', color: 'text-amber-400', gradient: 'from-amber-500/5' },
  'WAIT': { label: 'WAIT', color: 'text-red-400', gradient: 'from-red-500/5' },
  'WAIT:OVERRIDE': { label: 'WAIT — VOLATILE', color: 'text-amber-400', gradient: 'from-amber-500/5' },
  'CHECK DATA': { label: 'CHECK DATA', color: 'text-slate-400', gradient: 'from-slate-500/5' },
};

// Risk card color rotation
const RISK_COLORS = [
  { border: 'border-red-500/20', bg: 'bg-red-500/5', text: 'text-red-400', textMuted: 'text-red-300/60', icon: AlertTriangle },
  { border: 'border-amber-500/20', bg: 'bg-amber-500/5', text: 'text-amber-400', textMuted: 'text-amber-300/60', icon: Shield },
  { border: 'border-cyan-500/20', bg: 'bg-cyan-500/5', text: 'text-cyan-400', textMuted: 'text-cyan-300/60', icon: Zap },
];

export default function StrategyPage() {
  const [brief, setBrief] = useState<BriefData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchBrief = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/zl/brief');
      if (!res.ok) throw new Error(`Brief API error: ${res.status}`);
      const data = await res.json();
      setBrief(data);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchBrief();
    const interval = setInterval(fetchBrief, 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, [fetchBrief]);

  const [aiContext, setAiContext] = useState<string>('');
  const [aiContextLoading, setAiContextLoading] = useState(false);
  const aiContextFetched = useRef(false);

  // Stream AI context when brief data loads
  useEffect(() => {
    if (!brief || aiContextFetched.current) return;
    aiContextFetched.current = true;
    setAiContextLoading(true);

    fetch('/api/zl/context', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        price: brief.price ? { current: brief.price.current, changePct: brief.price.changePct } : undefined,
        drivers: brief.drivers,
        forecastsAvailable: brief.forecastsAvailable,
        dataIssues: brief.dataIssues,
        stalenessWarnings: brief.stalenessWarnings,
        recentEvents: brief.eventPulse?.recentEvents?.map(e => ({
          headline: e.headline,
          source: e.source,
          hoursAgo: e.hoursAgo,
          sentiment: e.sentiment,
          confidence: e.confidence,
        })),
        eventVelocity: brief.eventPulse?.velocity?.velocityRatio,
        overrideReason: brief.overrideReason,
      }),
    })
      .then(async (res) => {
        if (!res.ok || !res.body) {
          setAiContextLoading(false);
          return;
        }
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let text = '';
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          text += decoder.decode(value, { stream: true });
          setAiContext(text);
        }
        setAiContextLoading(false);
      })
      .catch(() => setAiContextLoading(false));
  }, [brief]);

  // When there's an event-driven override, use the override variant
  const postureKey = brief
    ? (brief.overrideReason
        ? (brief.recommendation === 'LOCK IN COVERAGE' ? 'LOCK IN COVERAGE:OVERRIDE'
           : brief.recommendation === 'WAIT' ? 'WAIT:OVERRIDE'
           : brief.recommendation)
        : brief.recommendation)
    : 'CHECK DATA';
  const posture = brief ? (POSTURE_MAP[postureKey] ?? POSTURE_MAP['CHECK DATA']) : null;

  // Derive confidence from driver data quality — percentage of drivers with live data
  const confidence = brief
    ? (() => {
        const liveDrivers = brief.drivers.filter(d => d.source === 'live').length;
        const totalDrivers = brief.drivers.length;
        const driverPct = totalDrivers > 0 ? (liveDrivers / totalDrivers) * 100 : 0;
        // Weight: 60% driver coverage, 40% forecast availability
        return Math.round(driverPct * 0.6 + (brief.forecastsAvailable ? 40 : 0));
      })()
    : 0;

  // Expected return from 1-month forecast
  const expReturn = brief?.forecasts.find(f => f.days === 21);

  // Generate action items from brief data
  const actionItems = brief
    ? (() => {
        const items: { title: string; detail: string; primary: boolean }[] = [];

        if (brief.recommendation === 'LOCK IN COVERAGE' || brief.recommendation === 'BUY NOW') {
          items.push({ title: 'Lock In Coverage', detail: `Price at $${brief.price.current.toFixed(2)}`, primary: true });
        } else if (brief.recommendation === 'WAIT') {
          items.push({ title: 'Hold Off Buying', detail: 'Headwinds detected', primary: true });
        } else if (brief.recommendation === 'NORMAL SCHEDULE') {
          items.push({ title: 'Normal Schedule', detail: 'No urgency — follow standard plan', primary: true });
        } else {
          items.push({ title: 'Verify Data', detail: 'Some indicators unavailable', primary: true });
        }

        // Secondary action from top driver insight
        const topDriver = brief.drivers.reduce((a, b) => a.score > b.score ? a : b, brief.drivers[0]);
        if (topDriver && topDriver.source !== 'unavailable') {
          items.push({
            title: `Watch ${topDriver.name}`,
            detail: topDriver.impact.split('.')[0],
            primary: false,
          });
        }

        return items;
      })()
    : [];

  // Build risk cards from keyRisks — extract a short label from the first phrase
  const riskCards = brief?.keyRisks.slice(0, 3).map((risk, i) => {
    const colors = RISK_COLORS[i % RISK_COLORS.length];
    // Extract first 2-3 words as label, fallback to first 25 chars
    const words = risk.split(/[\s—\-,]+/).filter(Boolean);
    const label = words.slice(0, 3).join(' ').toUpperCase();
    return { label, text: risk, colors };
  }) ?? [];

  // Build real factor-attribution inputs from live driver scores.
  // This avoids placeholder decomposition and keeps all values data-driven.
  const waterfallFactors = brief
    ? (() => {
        const active = brief.drivers.filter((d) => d.source !== 'unavailable');
        if (active.length === 0) return [];

        const totalDelta = brief.price.current - brief.price.previousClose;
        const centered = active.map((d) => (d.score - 50) / 50);
        const centeredSum = centered.reduce((sum, value) => sum + value, 0);
        const absCenteredSum = centered.reduce((sum, value) => sum + Math.abs(value), 0);

        const inferCategory = (name: string): 'cell' | 'macro' | 'technical' | 'noise' => {
          const normalized = name.toLowerCase();
          if (normalized.includes('crush') || normalized.includes('energy')) return 'cell';
          if (normalized.includes('china') || normalized.includes('tariff')) return 'macro';
          if (normalized.includes('market') || normalized.includes('vix')) return 'technical';
          return 'noise';
        };

        return active.map((driver, idx) => {
          let contribution = 0;
          if (Math.abs(totalDelta) > 0.0001) {
            if (Math.abs(centeredSum) >= 0.05) {
              contribution = totalDelta * (centered[idx] / centeredSum);
            } else {
              const magnitudeWeight =
                absCenteredSum > 0
                  ? Math.abs(centered[idx]) / absCenteredSum
                  : 1 / active.length;
              const sign = Math.sign(totalDelta) || 1;
              contribution = sign * magnitudeWeight * Math.abs(totalDelta);
            }
          } else {
            contribution = centered[idx] * 0.05;
          }

          return {
            id: `${driver.name.toLowerCase().replace(/[^a-z0-9]+/g, '-')}-${idx}`,
            label: driver.name,
            value: Number(contribution.toFixed(4)),
            type: contribution >= 0 ? ('positive' as const) : ('negative' as const),
            category: inferCategory(driver.name),
          };
        });
      })()
    : [];

  return (
    <div className="min-h-screen bg-[#0a0a0a] text-slate-200 p-3 pt-24 md:p-6 md:pt-36 pb-20">

      {/* Error banner */}
      {error && (
        <div className="mb-6 p-4 bg-red-500/10 border border-red-500/20 rounded-xl text-red-400 text-sm flex items-center justify-between">
          <span>Failed to load strategy brief: {error}</span>
          <button onClick={fetchBrief} className="text-red-300 hover:text-white">
            <RefreshCw size={14} />
          </button>
        </div>
      )}

      {/* Data quality banner — only show for truly poor data (most drivers missing) */}
      {brief?.dataQuality === 'poor' && (
        <div className="mb-6 p-4 bg-red-500/10 border border-red-500/20 rounded-xl text-red-400 text-sm">
          Multiple data sources offline — {brief.dataIssues.join(', ')}
        </div>
      )}
      {/* Staleness notice — informational, not blocking */}
      {brief?.dataQuality === 'partial' && brief.stalenessWarnings?.length > 0 && (
        <div className="mb-6 p-3 bg-amber-500/5 border border-amber-500/10 rounded-xl text-amber-500/70 text-xs flex items-center gap-2">
          <AlertTriangle size={12} />
          <span>{brief.stalenessWarnings.length} source{brief.stalenessWarnings.length > 1 ? 's' : ''} past freshness SLA — scores still usable</span>
        </div>
      )}

      {/* Event-Driven Override Banner */}
      {brief?.overrideReason && (
        <div className="mb-4 p-4 bg-red-500/10 border border-red-500/30 rounded-xl relative overflow-hidden">
          <div className="absolute inset-0 bg-gradient-to-r from-red-500/5 to-transparent pointer-events-none" />
          <div className="flex items-start gap-3 relative">
            <div className="p-1.5 rounded bg-red-500/20 text-red-400 shrink-0 mt-0.5">
              <AlertTriangle size={14} />
            </div>
            <div>
              <div className="text-[10px] text-red-400/80 uppercase tracking-widest font-bold mb-1">
                Posture Override
              </div>
              <p className="text-sm text-red-300 leading-relaxed">{brief.overrideReason}</p>
            </div>
          </div>
        </div>
      )}

      {/* AI Context — What's Happening Now */}
      {(aiContext || aiContextLoading) && (
        <div className="mb-6 bg-[#0a0a0a] border border-cyan-500/10 rounded-xl p-4 relative overflow-hidden">
          <div className="absolute inset-0 bg-gradient-to-r from-cyan-500/3 to-transparent pointer-events-none" />
          <div className="flex items-start gap-3 relative">
            <div className="p-1.5 rounded bg-cyan-500/10 text-cyan-400 shrink-0 mt-0.5">
              <Brain size={14} />
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-[10px] text-cyan-500/60 uppercase tracking-widest font-bold mb-1">
                AI Market Context
              </div>
              <p className="text-sm text-slate-300 leading-relaxed">
                {aiContext || (
                  <span className="text-slate-500 animate-pulse">Analyzing market conditions...</span>
                )}
                {aiContextLoading && aiContext && (
                  <span className="inline-block w-1.5 h-3.5 bg-cyan-400/60 ml-0.5 animate-pulse" />
                )}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Top HUD: Current Posture */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        {/* Main Posture Card */}
        <div className="col-span-2 relative group overflow-hidden bg-[#0a0a0a] border border-white/5 rounded-xl p-6">
          <div className={`absolute inset-0 bg-gradient-to-r ${posture?.gradient ?? 'from-cyan-500/5'} to-transparent pointer-events-none`} />

          {loading && !brief ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 size={24} className="animate-spin text-slate-500" />
            </div>
          ) : brief && posture ? (
            <div className="flex items-start justify-between">
              <div>
                <div className="flex items-center gap-2 text-cyan-400 font-mono text-xs mb-2 uppercase tracking-wider">
                  <Target size={14} />
                  Current Posture
                  <span className="text-slate-600">|</span>
                  <span className="text-slate-500">{brief.asOfDate}</span>
                </div>
                <h2 className={`text-5xl font-bold tracking-tight mb-2 ${posture.color}`}>
                  {posture.label}
                </h2>
                <p className={`max-w-md text-sm leading-relaxed ${brief.overrideReason ? 'text-red-400/80 font-medium' : 'text-slate-500'}`}>
                  {brief.overrideReason || brief.driversSummary}
                </p>
                {brief.dataQuality === 'partial' && (
                  <div className="mt-2 text-[10px] text-amber-500/60 uppercase tracking-wider">
                    {brief.dataIssues.length > 0 && `${brief.dataIssues.length} source${brief.dataIssues.length !== 1 ? 's' : ''} offline`}
                    {brief.dataIssues.length > 0 && brief.stalenessWarnings?.length > 0 && ' · '}
                    {brief.stalenessWarnings?.length > 0 && `${brief.stalenessWarnings.length} past SLA`}
                  </div>
                )}
              </div>

              <div className="flex flex-col items-end gap-3 p-4 bg-black/30 rounded-lg border border-white/5">
                <div className="text-right">
                  <div className={`text-2xl font-bold ${confidence >= 60 ? 'text-emerald-400' : confidence >= 40 ? 'text-amber-400' : 'text-red-400'}`}>
                    {confidence}%
                  </div>
                  <div className="text-[9px] text-slate-500 uppercase tracking-widest">Data Conf</div>
                </div>
                <div className="text-right">
                  {expReturn && expReturn.source === 'model' ? (
                    <>
                      <div className={`text-2xl font-bold ${
                        expReturn.direction === 'UP' ? 'text-cyan-400' :
                        expReturn.direction === 'DOWN' ? 'text-red-400' : 'text-slate-400'
                      }`}>
                        {expReturn.expectedChangePct}
                      </div>
                      <div className="text-[9px] text-slate-500 uppercase tracking-widest">1M Forecast</div>
                    </>
                  ) : (
                    <>
                      <div className="text-2xl font-bold text-slate-500">--</div>
                      <div className="text-[9px] text-slate-500 uppercase tracking-widest">No Forecast</div>
                    </>
                  )}
                </div>
              </div>
            </div>
          ) : null}
        </div>

        {/* Action Card */}
        <div className="bg-[#0a0a0a] border border-white/5 rounded-xl p-5 relative overflow-hidden">
          <div className="absolute top-0 right-0 p-4 opacity-5">
            <Zap size={48} className="text-amber-400" />
          </div>
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider">
              Primary Directive
            </h3>
            <button
              onClick={fetchBrief}
              disabled={loading}
              className="p-1.5 rounded border border-white/10 hover:border-white/20 text-slate-500 hover:text-white transition-colors disabled:opacity-30"
              title="Refresh brief"
            >
              <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
            </button>
          </div>
          {loading && !brief ? (
            <div className="space-y-2">
              <div className="h-12 bg-white/5 rounded animate-pulse" />
              <div className="h-12 bg-white/5 rounded animate-pulse" />
            </div>
          ) : (
            <div className="space-y-2">
              {actionItems.map((item, i) => (
                <div
                  key={i}
                  className={`flex items-center gap-3 p-2.5 rounded-r ${
                    item.primary
                      ? 'bg-cyan-500/10 border-l-2 border-cyan-500'
                      : 'bg-white/5 border-l-2 border-slate-600'
                  }`}
                >
                  <span className={`text-sm font-bold ${item.primary ? 'text-cyan-400' : 'text-slate-500'}`}>
                    {String(i + 1).padStart(2, '0')}
                  </span>
                  <div>
                    <div className={`text-sm font-bold ${item.primary ? 'text-white' : 'text-slate-300'}`}>
                      {item.title}
                    </div>
                    <div className="text-[10px] text-slate-500">{item.detail}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Driver Scores Strip */}
      {brief && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-8">
          {brief.drivers.map((driver) => {
            const scoreColor = driver.source === 'unavailable' ? 'text-slate-600'
              : driver.score >= 65 ? 'text-red-400'
              : driver.score >= 50 ? 'text-amber-400'
              : driver.score >= 35 ? 'text-yellow-400'
              : 'text-emerald-400';
            const barColor = driver.source === 'unavailable' ? 'bg-slate-700'
              : driver.score >= 65 ? 'bg-red-500'
              : driver.score >= 50 ? 'bg-amber-500'
              : driver.score >= 35 ? 'bg-yellow-500'
              : 'bg-emerald-500';
            return (
              <div key={driver.name} className="bg-[#0a0a0a] border border-white/5 rounded-xl p-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs text-slate-400 font-bold uppercase tracking-wider">{driver.name}</span>
                  <span className={`text-xs font-mono font-bold px-1.5 py-0.5 rounded ${
                    driver.source === 'stale' ? 'bg-amber-500/10 text-amber-400' :
                    driver.source === 'unavailable' ? 'bg-slate-500/10 text-slate-500' :
                    'bg-white/5 text-slate-400'
                  }`}>
                    {driver.source === 'stale' ? 'STALE' : driver.source === 'unavailable' ? 'N/A' : driver.status}
                  </span>
                </div>
                <div className={`text-2xl font-bold font-mono mb-2 ${scoreColor}`}>
                  {driver.source === 'unavailable' ? '—' : driver.score}
                </div>
                <div className="h-1.5 bg-slate-800 rounded-full overflow-hidden mb-2">
                  <div
                    className={`h-full rounded-full transition-all duration-700 ${barColor}`}
                    style={{ width: `${driver.source === 'unavailable' ? 0 : driver.score}%` }}
                  />
                </div>
                <div className="text-[10px] text-slate-600 leading-tight line-clamp-2">
                  {driver.impact.split('.')[0]}
                </div>
                {driver.source === 'stale' && driver.asOfDate && (
                  <div className="text-[9px] text-amber-500/50 mt-1 font-mono">
                    {Math.floor((Date.now() - new Date(driver.asOfDate).getTime()) / 86400000)}d ago
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Event Timeline */}
      {brief?.eventPulse && brief.eventPulse.recentEvents.length > 0 && (
        <div className="mb-8">
          <div className="flex items-center gap-2 mb-4 pl-1 border-l-4 border-orange-500">
            <h3 className="text-sm font-bold text-white uppercase tracking-wider">
              Recent Events
            </h3>
            <span className="text-[10px] text-slate-500 font-mono">Last 72h</span>
          </div>
          <div className="space-y-1.5">
            {brief.eventPulse.recentEvents.slice(0, 5).map((event, i) => (
              <div key={i} className="flex items-start gap-3 p-3 bg-[#0a0a0a] border border-white/5 rounded-lg hover:border-white/10 transition-colors">
                {/* Sentiment dot */}
                <div className={`mt-1.5 h-2 w-2 rounded-full shrink-0 ${
                  event.sentiment === 'bullish' ? 'bg-emerald-400' :
                  event.sentiment === 'bearish' ? 'bg-red-400' :
                  'bg-slate-500'
                }`} />
                {/* Content */}
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-slate-300 leading-snug line-clamp-1">{event.headline}</p>
                  <div className="flex items-center gap-2 mt-1">
                    <span className="text-[10px] font-mono text-slate-600">
                      {event.hoursAgo <= 24 ? `${event.hoursAgo}h ago` : `${Math.round(event.hoursAgo / 24)}d ago`}
                    </span>
                    <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded ${
                      event.source === 'Federal Register' ? 'bg-blue-500/10 text-blue-400' :
                      event.source === 'ProFarmer' ? 'bg-amber-500/10 text-amber-400' :
                      'bg-slate-500/10 text-slate-400'
                    }`}>
                      {event.source}
                    </span>
                    {event.tags?.slice(0, 2).map((tag, j) => (
                      <span key={j} className="text-[9px] text-slate-600 font-mono">{tag}</span>
                    ))}
                  </div>
                </div>
                {/* Confidence bar */}
                {event.sentiment !== 'neutral' && (
                  <div className="text-right shrink-0">
                    <span className={`text-[10px] font-mono font-bold ${
                      event.sentiment === 'bullish' ? 'text-emerald-400/60' : 'text-red-400/60'
                    }`}>
                      {(event.confidence * 100).toFixed(0)}%
                    </span>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Forecast Targets */}
      {brief && brief.forecastsAvailable && (
        <div className="mb-8">
          <div className="flex items-center gap-2 mb-4 pl-1 border-l-4 border-blue-500">
            <h3 className="text-sm font-bold text-white uppercase tracking-wider">
              Target Zones
            </h3>
            <span className="text-[10px] text-slate-500 font-mono">Model Forecasts</span>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {brief.forecasts.map((fc) => {
              const DirectionIcon = fc.direction === 'UP' ? TrendingUp : fc.direction === 'DOWN' ? TrendingDown : Minus;
              const dirColor = fc.direction === 'UP' ? 'text-emerald-400' : fc.direction === 'DOWN' ? 'text-red-400' : 'text-slate-400';
              return (
                <div key={fc.days} className="bg-[#0a0a0a] border border-white/5 rounded-xl p-4 hover:border-white/10 transition-colors">
                  <div className="text-xs text-slate-500 uppercase tracking-widest font-bold mb-3">{fc.label}</div>
                  {fc.source === 'model' && fc.targetMid !== null ? (
                    <>
                      <div className="text-2xl font-bold text-white font-mono mb-1">
                        ${fc.targetMid.toFixed(2)}
                      </div>
                      <div className="flex items-center gap-1.5 mb-3">
                        <DirectionIcon size={14} className={dirColor} />
                        <span className={`text-sm font-bold font-mono ${dirColor}`}>
                          {fc.expectedChangePct}
                        </span>
                      </div>
                      {fc.targetLow !== null && fc.targetHigh !== null && (
                        <div className="text-[10px] text-slate-600 font-mono">
                          Range: ${fc.targetLow.toFixed(2)} — ${fc.targetHigh.toFixed(2)}
                        </div>
                      )}
                    </>
                  ) : (
                    <div className="text-lg text-slate-600 font-mono">—</div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Regime Analysis Chart */}
      <div className="mb-8">
        <div className="flex items-center gap-2 mb-4 pl-1 border-l-4 border-purple-500">
          <h3 className="text-sm font-bold text-white uppercase tracking-wider">
            Regime Analysis
          </h3>
        </div>
        <RegimeAnalysisChart height={300} />
      </div>

      {/* Driver Attribution - FusionBrain Bubbles */}
      <div className="mb-8">
        <div className="flex items-center gap-2 mb-4 pl-1 border-l-4 border-cyan-500">
          <h3 className="text-sm font-bold text-white uppercase tracking-wider">
            Driver Attribution
          </h3>
        </div>

        <div className="relative w-full h-[300px] md:h-[500px] bg-[#0a0a0a] border border-white/5 rounded-xl overflow-hidden">
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(0,212,255,0.02),transparent_70%)]" />
          <FusionBrain drivers={brief?.drivers} correlations={brief?.correlations} />
        </div>
      </div>

      {/* Analysis Tools Grid */}
      <div className="grid grid-cols-12 gap-6 mb-8">
        <div className="col-span-12 lg:col-span-8 space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <ContractImpactCalculator
              currentPrice={brief?.price.current}
              forecasts={brief?.forecasts}
            />
            <FactorWaterfall
              prevPrice={brief?.price.previousClose ?? 0}
              currentPrice={brief?.price.current ?? 0}
              factors={waterfallFactors}
            />
          </div>
          <ProbabilityHeatmap />
        </div>

        <div className="col-span-12 lg:col-span-4">
          <WeatherRiskArray />
        </div>
      </div>

      {/* Risk & Tailwind Footer */}
      {brief && (riskCards.length > 0 || brief.keyPositives.length > 0) && (
        <div className="space-y-4">
          {/* Section label */}
          <div className="flex items-center gap-2 pl-1 border-l-4 border-red-500">
            <h3 className="text-sm font-bold text-white uppercase tracking-wider">
              Risk & Tailwinds
            </h3>
          </div>

          {/* Combined grid — risks then tailwinds, auto-fit columns */}
          <div className={`grid gap-4 ${
            riskCards.length + Math.min(brief.keyPositives.length, 2) >= 3
              ? 'grid-cols-1 md:grid-cols-2 lg:grid-cols-3'
              : 'grid-cols-1 md:grid-cols-2'
          }`}>
            {/* Risk cards */}
            {riskCards.map((card, i) => {
              const IconComponent = card.colors.icon;
              return (
                <div key={`risk-${i}`} className={`p-4 rounded-xl border ${card.colors.border} ${card.colors.bg}`}>
                  <div className="flex items-center gap-2 mb-2">
                    <IconComponent size={14} className={card.colors.text} />
                    <span className={`text-xs font-bold ${card.colors.text}`}>{card.label}</span>
                  </div>
                  <p className={`text-[11px] ${card.colors.textMuted} leading-relaxed`}>
                    {card.text}
                  </p>
                </div>
              );
            })}

            {/* Tailwind cards — fill remaining grid slots */}
            {brief.keyPositives.slice(0, Math.max(1, 3 - riskCards.length)).map((positive, i) => (
              <div key={`pos-${i}`} className="p-4 rounded-xl border border-emerald-500/20 bg-emerald-500/5">
                <div className="flex items-center gap-2 mb-2">
                  <Shield size={14} className="text-emerald-400" />
                  <span className="text-xs font-bold text-emerald-400">TAILWIND</span>
                </div>
                <p className="text-[11px] text-emerald-300/60 leading-relaxed">
                  {positive}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

    </div>
  );
}
