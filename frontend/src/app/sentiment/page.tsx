"use client";

import React, { useEffect, useState, useCallback } from "react";
import { Newspaper, TrendingUp, Activity } from "lucide-react";
import { computeNetSentimentScore } from "@/lib/sentiment-news";

/* ─── Types ─── */

interface Headline {
  id: string;
  event_date: string;
  headline: string;
  summary: string | null;
  source: string;
  lane?: string | null;
  sentiment: "bullish" | "bearish" | "neutral";
  tags: string[];
}

interface NewsData {
  headlines: Headline[];
  stats: { total: number; bullish: number; bearish: number; neutral: number };
}

interface CotCategory {
  long: number;
  short: number;
  net: number;
  net_pct_oi: number;
}

interface CotData {
  as_of_date: string;
  symbol: string;
  latest: {
    open_interest: number;
    managed_money: CotCategory;
    producers: CotCategory;
    swaps: CotCategory;
  };
  history: {
    event_date: string;
    managed_money_net: number;
    prod_merc_net: number;
    swap_net: number;
  }[];
}

interface CrudeCrossData {
  as_of: string | null;
  close: number | null;
  ret_5d: number | null;
  correlation_63d: number | null;
  direction: string;
  implication: string;
  lookback_days: number;
}

interface FearGreedComponent {
  score: number | null;
  weight: number;
  raw: number | null;
}

interface FearGreedData {
  score: number;
  zone: string;
  label: string;
  interpretation: string;
  components: {
    vix: FearGreedComponent;
    oil: FearGreedComponent;
    uncertainty: FearGreedComponent;
    inflation: FearGreedComponent;
    iranWar: FearGreedComponent;
    news: FearGreedComponent;
    positioning: FearGreedComponent;
    sentiment: FearGreedComponent;
  };
}

interface TrumpEffectData {
  title: "Impact on Soybean Oil Futures";
  policy_window: {
    anchor_date: string;
    start_date_7d: string | null;
    selected_feature_mode: "latest_valid" | "latest_fallback";
  };
  zl_response: {
    anchor_price_date: string | null;
    anchor_window_start_date: string | null;
    zl_return_7d_pct: number | null;
    zl_response_1d_pct: number | null;
    zl_response_5d_pct: number | null;
    realized_vol_21d_pct: number | null;
    response_signal: "muted" | "active" | "elevated" | null;
    abnormal_move_ratio: number | null;
  };
  policy_activity: {
    executive_orders_7d: number | null;
    total_presidential_actions_7d: number | null;
    other_presidential_actions_7d: number | null;
    action_velocity: number | null;
    action_acceleration: number | null;
    weighted_action_score: number | null;
    avg_sentiment_7d: number | null;
    avg_sentiment_30d: number | null;
  };
  procurement_outlook: {
    signal: "limited_impact" | "watch" | "elevated_risk" | "confirmed_pressure";
    label: string;
    summary: string;
    corroboration: {
      supporting_policy_items_7d: number;
      market_news_items_7d: number;
      regulatory_follow_through_7d: number;
      corroboration_score: number;
      corroboration_band: "low" | "mixed" | "strong";
    };
  };

  // Legacy compatibility fields still returned by the API.
  weighted_action_score: number | null;
  action_velocity: number | null;
  action_acceleration: number | null;
  total_actions_7d: number | null;
  total_actions_30d: number | null;
  eo_count_7d: number | null;
  other_actions_7d: number | null;
  avg_sentiment_7d: number | null;
  avg_sentiment_30d: number | null;
}

interface TrumpEffectStatus {
  selected_as_of: string;
  latest_any_as_of: string;
  selection_mode: "latest_valid" | "latest_fallback";
  selected_age_days: number | null;
  latest_any_age_days: number | null;
  selected_is_stale: boolean;
  latest_row_missing_score: boolean;
  latest_row_missing_velocity: boolean;
}

interface MetricsData {
  as_of: string | null;
  price: {
    close: number | null;
    open: number | null;
    high: number | null;
    low: number | null;
    volume: number | null;
    open_interest: number | null;
  };
  returns: {
    ret_5d: number | null;
    ret_21d: number | null;
    ret_63d: number | null;
  };
  volatility: {
    realized_21d: number | null;
    vix: number | null;
    vix_avg_1y: number | null;
    vix_z: number | null;
    ovx: number | null;
  };
  technicals: {
    rsi_14: number | null;
    sma20: number | null;
    sma50: number | null;
    sma200: number | null;
    trend: string;
    above_sma20: boolean;
    above_sma50: boolean;
    above_sma200: boolean;
  };
  positioning: {
    mm_net: number | null;
    mm_avg: number | null;
    mm_std: number | null;
    mm_zscore: number | null;
    mm_percentile: number | null;
    mm_pct_oi: number | null;
    prod_net: number | null;
    swap_net: number | null;
    history_weeks: number | null;
  };
  crush: {
    board_crush: number | null;
    crush_zscore: number | null;
    oil_share: number | null;
    oil_share_zscore: number | null;
    sample_size: number | null;
  };
  specialists: {
    bucket: string;
    signal: number;
    signal_2: number | null;
    confidence: number;
    model_type: string;
    as_of: string;
  }[];
  composite: {
    signal: number;
    contributing_models: number;
    interpretation: string;
  };
  fearGreed?: FearGreedData | null;
  trumpEffect?: TrumpEffectData | null;
  trumpEffectStatus?: TrumpEffectStatus | null;
  cot: CotData | null;
  crudeCross: CrudeCrossData | null;
}

interface AnalysisData {
  fearGreedNarrative: string | null;
  trumpEffectNarrative: string | null;
  volatilityNarrative: string | null;
  source: "ai" | "deterministic";
  model: string | null;
}

/* ─── Helpers ─── */

function formatNumber(n: number): string {
  if (Math.abs(n) >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return n.toLocaleString();
}

const chicagoTimestampFormatter = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
  timeZone: "America/Chicago",
});

function formatAsOf(dateStr: string | null): string {
  if (!dateStr) return "";
  if (/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) return dateStr;

  const parsed = new Date(dateStr);
  if (Number.isNaN(parsed.getTime())) return dateStr;

  return `${chicagoTimestampFormatter.format(parsed)} CT`;
}

function parseDisplayDate(dateStr: string): Date | null {
  if (/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) {
    const [year, month, day] = dateStr.split("-").map(Number);
    return new Date(Date.UTC(year, month - 1, day, 0, 0, 0, 0));
  }

  const parsed = new Date(dateStr);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function timeAgo(dateStr: string): string {
  const parsed = parseDisplayDate(dateStr);
  if (!parsed) return "";

  const diff = Date.now() - parsed.getTime();
  const hours = Math.floor(diff / 3600000);
  if (hours < 1) return "Just now";
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days === 1) return "1d ago";
  return `${days}d ago`;
}

function getTrendBadge(trend: string): {
  text: string;
  color: string;
  bg: string;
} | null {
  switch (trend) {
    case "strong_uptrend":
      return {
        text: "▲ Prices Trending Up",
        color: "text-emerald-400",
        bg: "bg-emerald-500/10 border-emerald-500/20",
      };
    case "uptrend":
      return {
        text: "▲ Prices Rising",
        color: "text-emerald-400",
        bg: "bg-emerald-500/10 border-emerald-500/20",
      };
    case "mixed":
      return {
        text: "◆ Mixed Signals",
        color: "text-amber-400",
        bg: "bg-amber-500/10 border-amber-500/20",
      };
    case "unknown":
      return null;
    default:
      return {
        text: "▼ Prices Trending Down",
        color: "text-red-400",
        bg: "bg-red-500/10 border-red-500/20",
      };
  }
}

function zoneColor(zone: string): string {
  switch (zone) {
    case "extreme_fear":
      return "text-red-500";
    case "fear":
      return "text-orange-400";
    case "neutral":
      return "text-yellow-400";
    case "greed":
      return "text-lime-400";
    case "extreme_greed":
      return "text-emerald-400";
    default:
      return "text-slate-400";
  }
}

function volLabel(
  value: number,
  thresholds: [number, number],
): { text: string; color: string } {
  if (value > thresholds[1]) return { text: "Elevated", color: "text-red-400" };
  if (value > thresholds[0])
    return { text: "Moderate", color: "text-amber-400" };
  return { text: "Calm", color: "text-emerald-400" };
}

function corroborationBandStyle(
  band: "low" | "mixed" | "strong",
): { text: string; chip: string } {
  if (band === "strong") {
    return {
      text: "Strong corroboration",
      chip: "text-emerald-300 bg-emerald-500/10 border-emerald-500/30",
    };
  }
  if (band === "mixed") {
    return {
      text: "Mixed corroboration",
      chip: "text-amber-300 bg-amber-500/10 border-amber-500/30",
    };
  }
  return {
    text: "Low corroboration",
    chip: "text-slate-300 bg-slate-500/10 border-slate-500/30",
  };
}

function responseSignalStyle(
  signal: "muted" | "active" | "elevated" | null,
): { text: string; chip: string } {
  if (signal === "elevated") {
    return {
      text: "Elevated ZL response",
      chip: "text-red-300 bg-red-500/10 border-red-500/30",
    };
  }
  if (signal === "active") {
    return {
      text: "Active ZL response",
      chip: "text-amber-300 bg-amber-500/10 border-amber-500/30",
    };
  }
  return {
    text: "Muted ZL response",
    chip: "text-slate-300 bg-slate-500/10 border-slate-500/30",
  };
}

function buildNarrativePayload(metrics: MetricsData) {
  return {
    fearGreed: metrics.fearGreed
      ? {
          score: metrics.fearGreed.score,
          zone: metrics.fearGreed.zone,
          label: metrics.fearGreed.label,
        }
      : undefined,
    trumpEffect: metrics.trumpEffect
      ? {
          title: metrics.trumpEffect.title,
          zl_return_7d_pct: metrics.trumpEffect.zl_response.zl_return_7d_pct,
          zl_response_1d_pct: metrics.trumpEffect.zl_response.zl_response_1d_pct,
          zl_response_5d_pct: metrics.trumpEffect.zl_response.zl_response_5d_pct,
          response_signal: metrics.trumpEffect.zl_response.response_signal,
          weighted_action_score:
            metrics.trumpEffect.policy_activity.weighted_action_score,
          total_actions_7d:
            metrics.trumpEffect.policy_activity.total_presidential_actions_7d,
          executive_orders_7d:
            metrics.trumpEffect.policy_activity.executive_orders_7d,
          other_actions_7d:
            metrics.trumpEffect.policy_activity.other_presidential_actions_7d,
          action_velocity: metrics.trumpEffect.policy_activity.action_velocity,
          corroboration_score:
            metrics.trumpEffect.procurement_outlook.corroboration.corroboration_score,
          corroboration_band:
            metrics.trumpEffect.procurement_outlook.corroboration.corroboration_band,
          supporting_policy_items_7d:
            metrics.trumpEffect.procurement_outlook.corroboration.supporting_policy_items_7d,
          market_news_items_7d:
            metrics.trumpEffect.procurement_outlook.corroboration.market_news_items_7d,
          regulatory_follow_through_7d:
            metrics.trumpEffect.procurement_outlook.corroboration.regulatory_follow_through_7d,
          procurement_signal: metrics.trumpEffect.procurement_outlook.signal,
          procurement_label: metrics.trumpEffect.procurement_outlook.label,
        }
      : undefined,
    volatility: {
      vix: metrics.volatility.vix,
      ovx: metrics.volatility.ovx,
      realized_21d: metrics.volatility.realized_21d,
    },
  };
}

/* ─── Page ─── */

export default function SentimentPage() {
  const [news, setNews] = useState<NewsData | null>(null);
  const [metrics, setMetrics] = useState<MetricsData | null>(null);
  const [analysis, setAnalysis] = useState<AnalysisData | null>(null);
  const [loading, setLoading] = useState(true);

  const parseEndpoint = useCallback(async <T,>(
    res: Response,
    label: string,
  ): Promise<T | null> => {
    if (!res.ok) {
      console.error(`[sentiment] ${label} failed (${res.status})`);
      return null;
    }

    try {
      return (await res.json()) as T;
    } catch (e) {
      console.error(`[sentiment] ${label} returned invalid JSON`, e);
      return null;
    }
  }, []);

  const fetchAnalysis = useCallback(async (metricsData: MetricsData) => {
    try {
      const analysisRes = await fetch("/api/sentiment/narrative", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        cache: "no-store",
        body: JSON.stringify(buildNarrativePayload(metricsData)),
      });
      const analysisData = await parseEndpoint<AnalysisData>(
        analysisRes,
        "narrative",
      );
      if (analysisData) setAnalysis(analysisData);
    } catch (e) {
      console.error("[sentiment] narrative refresh failed", e);
    }
  }, [parseEndpoint]);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    setAnalysis(null);
    try {
      const [metricsRes, newsRes] = await Promise.all([
        fetch("/api/sentiment/metrics", { cache: "no-store" }),
        fetch("/api/sentiment/news"),
      ]);
      const [metricsData, newsData] = await Promise.all([
        parseEndpoint<MetricsData>(metricsRes, "metrics"),
        parseEndpoint<NewsData>(newsRes, "news"),
      ]);

      if (metricsData) {
        setMetrics(metricsData);
        await fetchAnalysis(metricsData);
      }
      if (newsData) {
        setNews(newsData);
      }
    } finally {
      setLoading(false);
    }
  }, [fetchAnalysis, parseEndpoint]);

  useEffect(() => {
    void fetchAll();
  }, [fetchAll]);

  // Sentiment bias for header
  const biasLabel = (() => {
    if (!news?.stats) return null;
    const netScore = computeNetSentimentScore(news.stats);
    if (netScore == null) return null;
    const direction =
      netScore > 0 ? "Bullish" : netScore < 0 ? "Bearish" : "Neutral";
    return {
      score: `${netScore > 0 ? "+" : ""}${netScore}`,
      direction,
      color:
        netScore > 0
          ? "text-emerald-400"
          : netScore < 0
            ? "text-red-400"
            : "text-slate-400",
    };
  })();

  const fg = metrics?.fearGreed ?? null;
  const trump = metrics?.trumpEffect ?? null;
  const cot = metrics?.cot ?? null;
  const crudeCross = metrics?.crudeCross ?? null;
  const trendBadge = metrics ? getTrendBadge(metrics.technicals.trend) : null;

  return (
    <div className="min-h-screen bg-[#0a0a0a] text-slate-200 p-3 pt-24 md:p-6 md:pt-36 pb-20 animate-in fade-in duration-700">
      {/* Header — KEPT AS-IS */}
      <div className="flex items-center justify-between mb-8 pb-4 border-b border-white/5">
        <div>
          <h1 className="text-5xl font-bold text-white tracking-tight">
            Market Psychology
          </h1>
          <p className="text-slate-400 text-sm font-mono mt-1">
            Quantitative signals // Narrative clustering // Positioning analysis
          </p>
        </div>
        <div className="flex items-center gap-6">
              {biasLabel && (
                <div className="text-right">
                  <div className={`text-2xl font-bold ${biasLabel.color}`}>
                    {biasLabel.score}
                  </div>
                  <div className="text-[10px] text-slate-500 uppercase tracking-widest">
                    {biasLabel.direction} News Bias
                  </div>
                </div>
              )}
        </div>
      </div>

      {/* ═══════════ FEAR & GREED INDEX ═══════════ */}
      <div className="mb-8">
        <div className="bg-[#0a0a0a] border border-white/10 rounded-2xl p-8 md:p-10 hover:border-white/20 transition-all duration-300">
          <div className="text-sm font-semibold text-slate-400 uppercase tracking-widest border-l-2 border-blue-500 pl-3 mb-8">
            Fear &amp; Greed Composite
          </div>

          {loading && !metrics ? (
            <div className="flex flex-col items-center py-12">
              <div className="w-64 h-32 bg-white/5 rounded-full animate-pulse mb-6" />
              <div className="h-12 w-24 bg-white/5 rounded animate-pulse mb-3" />
              <div className="h-6 w-32 bg-white/5 rounded animate-pulse" />
            </div>
          ) : fg ? (
            <>
              <div className="flex flex-col items-center mb-8">
                <FearGreedGauge score={fg.score} />
                <div className="text-6xl font-bold text-white mt-4">
                  {fg.score}
                </div>
                <div
                  className={`text-2xl font-semibold mt-2 ${zoneColor(fg.zone)}`}
                >
                  {fg.label}
                </div>
                <div className="text-lg text-slate-300 mt-2 text-center max-w-lg">
                  {fg.interpretation}
                </div>
              </div>

              {/* AI Narrative */}
              {analysis?.fearGreedNarrative && (
                <div className="bg-white/[0.02] border border-white/5 rounded-xl p-5 mb-8">
                  <div className="text-xs text-slate-500 uppercase tracking-widest font-bold mb-2">
                    Analysis
                  </div>
                  <p className="text-base text-slate-300 leading-relaxed">
                    {analysis.fearGreedNarrative}
                  </p>
                </div>
              )}

              {/* Component breakdown */}
              <div className="border-t border-white/5 pt-6">
                <div className="text-xs text-slate-500 uppercase tracking-widest font-bold mb-4">
                  What&apos;s Driving This
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                  {(
                    [
                      { label: "Market Stress", data: fg.components.vix },
                      { label: "Oil Shock", data: fg.components.oil },
                      { label: "Uncertainty", data: fg.components.uncertainty },
                      { label: "Inflation", data: fg.components.inflation },
                      { label: "Iran War", data: fg.components.iranWar },
                      { label: "Macro News", data: fg.components.news },
                      {
                        label: "Fund Positioning",
                        data: fg.components.positioning,
                      },
                      {
                        label: "News Sentiment",
                        data: fg.components.sentiment,
                      },
                    ] as const
                  ).map((c) => (
                    <div key={c.label} className="flex items-center gap-3">
                      <div className="w-28 text-sm text-slate-400 shrink-0">
                        {c.label}
                      </div>
                      <div className="flex-1 h-2.5 bg-slate-800 rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full transition-all duration-700 ${
                            c.data.score == null
                              ? "bg-slate-700"
                              : "bg-gradient-to-r from-red-500 via-amber-500 to-emerald-500"
                          }`}
                          style={{ width: `${c.data.score ?? 0}%` }}
                        />
                      </div>
                      <div className="text-sm font-mono text-slate-300 w-8 text-right">
                        {c.data.score ?? "Pending"}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </>
          ) : (
            <div className="text-center text-slate-500 py-12">
              No current signal
            </div>
          )}
        </div>
      </div>

      {/* ═══════════ HERO PRICE STRIP ═══════════ */}
      <div className="mb-8">
        <div className="bg-[#0a0a0a] border border-white/10 rounded-2xl p-8 hover:border-white/20 transition-all duration-300">
          {loading && !metrics ? (
            <div className="flex items-center gap-8">
              <div className="h-16 w-48 bg-white/5 rounded animate-pulse" />
              <div className="h-10 w-32 bg-white/5 rounded animate-pulse" />
            </div>
          ) : metrics?.price.close != null ? (
            <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-6">
              <div>
                <div className="text-xs text-slate-500 uppercase tracking-widest font-bold mb-2">
                  ZL Soybean Oil — Front Month
                </div>
                <div className="flex items-baseline gap-4">
                  <span className="text-5xl md:text-6xl font-bold text-white font-mono">
                    ${metrics.price.close != null ? metrics.price.close.toFixed(2) : "—"}
                  </span>
                  {metrics.as_of && (
                    <span className="text-sm text-slate-500">
                      as of {formatAsOf(metrics.as_of)}
                    </span>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-8">
                {metrics.price.high != null && metrics.price.low != null && (
                  <div>
                    <div className="text-xs text-slate-500 uppercase tracking-widest font-bold mb-1">
                      Session Range
                    </div>
                    <div className="text-lg font-mono text-slate-300">
                      ${metrics.price.low != null ? metrics.price.low.toFixed(2) : "—"} — $
                      {metrics.price.high != null ? metrics.price.high.toFixed(2) : "—"}
                    </div>
                    {metrics.price.volume != null && (
                      <div className="text-xs text-slate-500 mt-0.5">
                        Volume: {formatNumber(metrics.price.volume)}
                      </div>
                    )}
                  </div>
                )}
                {trendBadge && (
                  <div
                    className={`px-4 py-2 rounded-full text-base font-bold border ${trendBadge.bg} ${trendBadge.color}`}
                  >
                    {trendBadge.text}
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="text-center text-slate-500 py-6">
              No current signal
            </div>
          )}
        </div>
      </div>

      {/* ═══════════ IMPACT ON SOYBEAN OIL FUTURES ═══════════ */}
      <div className="mb-8">
        <div className="bg-[#0a0a0a] border border-white/10 rounded-2xl p-8 hover:border-white/20 transition-all duration-300">
          <div className="flex items-center justify-between mb-6">
            <div>
              <div className="text-sm font-semibold text-slate-400 uppercase tracking-widest border-l-2 border-amber-500 pl-3">
                {trump?.title ?? "Impact on Soybean Oil Futures"}
              </div>
              <div className="text-xs text-slate-500 mt-1 pl-5">
                ZL-anchored policy pressure for soybean oil procurement
              </div>
            </div>
            {trump?.policy_activity.weighted_action_score != null && (
              <div className="text-4xl font-bold text-white font-mono">
                {trump.policy_activity.weighted_action_score.toFixed(1)}
              </div>
            )}
          </div>

          {loading && !metrics ? (
            <div className="space-y-4">
              <div className="h-3 bg-white/5 rounded-full animate-pulse" />
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {[...Array(4)].map((_, i) => (
                  <div
                    key={i}
                    className="h-16 bg-white/5 rounded-xl animate-pulse"
                  />
                ))}
              </div>
            </div>
          ) : trump ? (
            <>
              {/* 1) ZL response */}
              <div className="mb-6 border border-white/5 rounded-xl p-4 bg-white/[0.02]">
                <div className="flex items-center justify-between gap-4 mb-4">
                  <div className="text-xs text-slate-500 uppercase tracking-widest font-bold">
                    1) ZL Response
                  </div>
                  <div
                    className={`text-xs px-2.5 py-1 rounded-full border ${
                      responseSignalStyle(trump.zl_response.response_signal).chip
                    }`}
                  >
                    {responseSignalStyle(trump.zl_response.response_signal).text}
                  </div>
                </div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div className="bg-white/[0.02] rounded-xl p-4">
                    <div className="text-2xl font-bold text-white font-mono">
                      {trump.zl_response.zl_return_7d_pct != null
                        ? `${trump.zl_response.zl_return_7d_pct > 0 ? "+" : ""}${trump.zl_response.zl_return_7d_pct.toFixed(2)}%`
                        : "Pending"}
                    </div>
                    <div className="text-xs text-slate-500 uppercase">
                      ZL Return (7d window)
                    </div>
                  </div>
                  <div className="bg-white/[0.02] rounded-xl p-4">
                    <div className="text-2xl font-bold text-white font-mono">
                      {trump.zl_response.zl_response_1d_pct != null
                        ? `${trump.zl_response.zl_response_1d_pct > 0 ? "+" : ""}${trump.zl_response.zl_response_1d_pct.toFixed(2)}%`
                        : "Pending"}
                    </div>
                    <div className="text-xs text-slate-500 uppercase">
                      ZL Response (1d)
                    </div>
                  </div>
                  <div className="bg-white/[0.02] rounded-xl p-4">
                    <div className="text-2xl font-bold text-white font-mono">
                      {trump.zl_response.zl_response_5d_pct != null
                        ? `${trump.zl_response.zl_response_5d_pct > 0 ? "+" : ""}${trump.zl_response.zl_response_5d_pct.toFixed(2)}%`
                        : "Pending"}
                    </div>
                    <div className="text-xs text-slate-500 uppercase">
                      ZL Response (5d)
                    </div>
                  </div>
                  <div className="bg-white/[0.02] rounded-xl p-4">
                    <div className="text-2xl font-bold text-white font-mono">
                      {trump.zl_response.realized_vol_21d_pct != null
                        ? `${trump.zl_response.realized_vol_21d_pct.toFixed(1)}%`
                        : "Pending"}
                    </div>
                    <div className="text-xs text-slate-500 uppercase">
                      Realized Vol (21d)
                    </div>
                  </div>
                </div>
              </div>

              {/* 2) Policy activity */}
              <div className="mb-6 border border-white/5 rounded-xl p-4 bg-white/[0.02]">
                <div className="text-xs text-slate-500 uppercase tracking-widest font-bold mb-4">
                  2) Policy Activity
                </div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-3">
                  <div className="bg-white/[0.02] rounded-xl p-4">
                    <div className="text-2xl font-bold text-white font-mono">
                      {trump.policy_activity.executive_orders_7d ?? 0}
                    </div>
                    <div className="text-xs text-slate-500 uppercase">
                      Executive Orders (7d)
                    </div>
                  </div>
                  <div className="bg-white/[0.02] rounded-xl p-4">
                    <div className="text-2xl font-bold text-white font-mono">
                      {trump.policy_activity.total_presidential_actions_7d ?? 0}
                    </div>
                    <div className="text-xs text-slate-500 uppercase">
                      Total Presidential Actions (7d)
                    </div>
                  </div>
                  <div className="bg-white/[0.02] rounded-xl p-4">
                    <div className="text-2xl font-bold text-white font-mono">
                      {trump.policy_activity.other_presidential_actions_7d ?? 0}
                    </div>
                    <div className="text-xs text-slate-500 uppercase">
                      Other Presidential Actions (7d)
                    </div>
                  </div>
                  <div className="bg-white/[0.02] rounded-xl p-4">
                    <div className="text-2xl font-bold text-white font-mono">
                      {trump.policy_activity.action_velocity != null
                        ? trump.policy_activity.action_velocity.toFixed(1)
                        : "Pending"}
                    </div>
                    <div className="text-xs text-slate-500 uppercase">
                      Action Velocity (/day)
                    </div>
                  </div>
                </div>
                <div className="text-sm text-slate-400">
                  Weighted policy pressure:{" "}
                  <span className="font-mono text-white">
                    {trump.policy_activity.weighted_action_score != null
                      ? trump.policy_activity.weighted_action_score.toFixed(2)
                      : "Pending"}
                  </span>{" "}
                  | Acceleration:{" "}
                  <span className="font-mono text-white">
                    {trump.policy_activity.action_acceleration != null
                      ? `${trump.policy_activity.action_acceleration > 0 ? "+" : ""}${trump.policy_activity.action_acceleration.toFixed(2)}`
                      : "Pending"}
                  </span>
                </div>
              </div>

              {/* 3) Procurement outlook (includes corroboration context) */}
              <div className="mb-6 border rounded-xl p-5 bg-white/[0.02] border-cyan-500/30">
                <div className="flex items-center justify-between gap-4 mb-4">
                  <div className="text-xs text-cyan-300 uppercase tracking-widest font-bold">
                    3) Procurement Outlook
                  </div>
                  <div
                    className={`text-xs px-2.5 py-1 rounded-full border ${
                      corroborationBandStyle(
                        trump.procurement_outlook.corroboration.corroboration_band,
                      ).chip
                    }`}
                  >
                    {
                      corroborationBandStyle(
                        trump.procurement_outlook.corroboration.corroboration_band,
                      ).text
                    }{" "}
                    ({trump.procurement_outlook.corroboration.corroboration_score}/100)
                  </div>
                </div>
                <div className="text-xl font-semibold text-white mb-2">
                  {trump.procurement_outlook.label}
                </div>
                <p className="text-sm text-slate-300 leading-relaxed mb-4">
                  {trump.procurement_outlook.summary}
                </p>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div className="bg-white/[0.02] rounded-xl p-4">
                    <div className="text-2xl font-bold text-white font-mono">
                      {trump.procurement_outlook.corroboration.supporting_policy_items_7d}
                    </div>
                    <div className="text-xs text-slate-500 uppercase">
                      Supporting Policy Coverage (7d)
                    </div>
                  </div>
                  <div className="bg-white/[0.02] rounded-xl p-4">
                    <div className="text-2xl font-bold text-white font-mono">
                      {trump.procurement_outlook.corroboration.market_news_items_7d}
                    </div>
                    <div className="text-xs text-slate-500 uppercase">
                      Market Coverage (7d)
                    </div>
                  </div>
                  <div className="bg-white/[0.02] rounded-xl p-4">
                    <div className="text-2xl font-bold text-white font-mono">
                      {trump.procurement_outlook.corroboration.regulatory_follow_through_7d}
                    </div>
                    <div className="text-xs text-slate-500 uppercase">
                      Regulatory Follow-through (7d)
                    </div>
                  </div>
                </div>
              </div>

              {/* AI Narrative */}
              {analysis?.trumpEffectNarrative && (
                <div className="bg-white/[0.02] border border-white/5 rounded-xl p-5">
                  <div className="text-xs text-slate-500 uppercase tracking-widest font-bold mb-2">
                    Analysis
                  </div>
                  <p className="text-base text-slate-300 leading-relaxed">
                    {analysis.trumpEffectNarrative}
                  </p>
                </div>
              )}
            </>
          ) : (
            <div className="text-center text-slate-500 py-6">
              No current signal
            </div>
          )}
        </div>
      </div>

      {/* ═══════════ MARKET SNAPSHOT ═══════════ */}
      <div className="mb-8">
        <h3 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
          <Activity size={18} className="text-cyan-400" />
          Market Snapshot
          {metrics?.as_of && (
            <span className="text-xs text-slate-500 font-normal ml-2">
              as of {formatAsOf(metrics.as_of)}
            </span>
          )}
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
          <SnapshotCard
            label="5 Trading Days"
            value={
              metrics?.returns.ret_5d != null
                ? `${metrics.returns.ret_5d > 0 ? "+" : ""}${metrics.returns.ret_5d}%`
                : "Pending"
            }
            color={
              metrics?.returns.ret_5d != null
                ? metrics.returns.ret_5d > 0
                  ? "text-emerald-400"
                  : "text-red-400"
                : undefined
            }
            loading={loading && !metrics}
          />
          <SnapshotCard
            label="21 Trading Days"
            value={
              metrics?.returns.ret_21d != null
                ? `${metrics.returns.ret_21d > 0 ? "+" : ""}${metrics.returns.ret_21d}%`
                : "Pending"
            }
            color={
              metrics?.returns.ret_21d != null
                ? metrics.returns.ret_21d > 0
                  ? "text-emerald-400"
                  : "text-red-400"
                : undefined
            }
            loading={loading && !metrics}
          />
          <SnapshotCard
            label="63 Trading Days"
            value={
              metrics?.returns.ret_63d != null
                ? `${metrics.returns.ret_63d > 0 ? "+" : ""}${metrics.returns.ret_63d}%`
                : "Pending"
            }
            color={
              metrics?.returns.ret_63d != null
                ? metrics.returns.ret_63d > 0
                  ? "text-emerald-400"
                  : "text-red-400"
                : undefined
            }
            loading={loading && !metrics}
          />
          <SnapshotCard
            label="Crush Margin"
            value={
              metrics?.crush.board_crush != null
                ? `$${metrics.crush.board_crush.toFixed(2)}/bu`
                : "Pending"
            }
            loading={loading && !metrics}
          />
          <SnapshotCard
            label="Soybean Oil Share"
            value={
              metrics?.crush.oil_share != null
                ? `${(metrics.crush.oil_share * 100).toFixed(1)}%`
                : "Pending"
            }
            loading={loading && !metrics}
          />
          <SnapshotCard
            label="Price Swings"
            value={
              metrics?.volatility.realized_21d != null
                ? `${metrics.volatility.realized_21d}%`
                : "Pending"
            }
            sub="21d annualized"
            loading={loading && !metrics}
          />
        </div>

        {crudeCross && (
          <div className="mt-6 bg-[#0a0a0a] border border-white/10 rounded-2xl p-6 hover:border-white/20 transition-colors">
            <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3 mb-5">
              <div>
                <div className="text-sm font-semibold text-slate-400 uppercase tracking-widest border-l-2 border-amber-500 pl-3">
                  Crude Oil / Soybean Oil Cross
                </div>
                <div className="text-xs text-slate-500 mt-1 pl-5">
                  Real 63-trading-day log-return correlation for the biofuel channel
                </div>
              </div>
              {crudeCross.as_of && (
                <div className="text-xs text-slate-500">
                  crude as of {formatAsOf(crudeCross.as_of)}
                </div>
              )}
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
              <SnapshotCard
                label="CL Front Month"
                value={
                  crudeCross.close != null
                    ? `$${crudeCross.close.toFixed(2)}`
                    : "Pending"
                }
              />
              <SnapshotCard
                label="CL 5 Trading Days"
                value={
                  crudeCross.ret_5d != null
                    ? `${crudeCross.ret_5d > 0 ? "+" : ""}${crudeCross.ret_5d}%`
                    : "Pending"
                }
                color={
                  crudeCross.ret_5d != null
                    ? crudeCross.ret_5d > 0
                      ? "text-red-400"
                      : "text-emerald-400"
                    : undefined
                }
              />
              <SnapshotCard
                label={`${crudeCross.lookback_days}d Corr`}
                value={
                  crudeCross.correlation_63d != null
                    ? crudeCross.correlation_63d.toFixed(3)
                    : "Pending"
                }
                sub={crudeCross.direction}
              />
            </div>

            <p className="text-sm text-slate-300 leading-relaxed">
              {crudeCross.implication}
            </p>
          </div>
        )}
      </div>

      {/* ═══════════ VOLATILITY ═══════════ */}
      <div className="mb-8">
        <div className="bg-[#0a0a0a] border border-white/10 rounded-2xl p-8 hover:border-white/20 transition-all duration-300">
          <div className="text-sm font-semibold text-slate-400 uppercase tracking-widest border-l-2 border-purple-500 pl-3 mb-8">
            Market Volatility
          </div>

          {loading && !metrics ? (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {[...Array(3)].map((_, i) => (
                <div
                  key={i}
                  className="h-28 bg-white/5 rounded-xl animate-pulse"
                />
              ))}
            </div>
          ) : metrics ? (
            <>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <VolGauge
                  label="VIX"
                  value={metrics.volatility.vix}
                  max={50}
                  status={
                    metrics.volatility.vix != null
                      ? volLabel(metrics.volatility.vix, [20, 30])
                      : null
                  }
                />
                <VolGauge
                  label="OVX"
                  value={metrics.volatility.ovx}
                  max={60}
                  status={
                    metrics.volatility.ovx != null
                      ? volLabel(metrics.volatility.ovx, [30, 45])
                      : null
                  }
                />
                <VolGauge
                  label="Price Swings"
                  value={metrics.volatility.realized_21d}
                  max={50}
                  status={
                    metrics.volatility.realized_21d != null
                      ? volLabel(metrics.volatility.realized_21d, [20, 35])
                      : null
                  }
                  suffix="%"
                />
              </div>

              {/* AI Narrative */}
              {analysis?.volatilityNarrative && (
                <div className="bg-white/[0.02] border border-white/5 rounded-xl p-5 mt-6">
                  <div className="text-xs text-slate-500 uppercase tracking-widest font-bold mb-2">
                    Analysis
                  </div>
                  <p className="text-base text-slate-300 leading-relaxed">
                    {analysis.volatilityNarrative}
                  </p>
                </div>
              )}
            </>
          ) : (
            <div className="text-center text-slate-500 py-6">
              No current signal
            </div>
          )}
        </div>
      </div>

      {/* ═══════════ MARKET PARTICIPANTS ═══════════ */}
      <div className="mb-8">
        <h3 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
          <TrendingUp size={18} className="text-slate-400" />
          Market Participants
          {cot && (
            <span className="text-xs text-slate-500 font-normal ml-2">
              COT as of {cot.as_of_date}
            </span>
          )}
        </h3>

        {loading && !cot ? (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {[...Array(3)].map((_, i) => (
              <div
                key={i}
                className="h-40 bg-white/5 rounded-2xl animate-pulse"
              />
            ))}
          </div>
        ) : cot ? (
          <>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-6">
              <ParticipantCard
                title="Fund Managers"
                subtitle="Hedge funds & speculators"
                data={cot.latest.managed_money}
              />
              <ParticipantCard
                title="Commercial Buyers"
                subtitle="Producers & processors"
                data={cot.latest.producers}
              />
              <ParticipantCard
                title="Swap Dealers"
                subtitle="Banks & dealers"
                data={cot.latest.swaps}
              />
            </div>

            {/* Fund Percentile Bar */}
            {metrics?.positioning.mm_percentile != null && (
              <div className="bg-[#0a0a0a] border border-white/10 rounded-2xl p-6">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-base font-bold text-white">
                    How Bullish Are Funds?
                  </span>
                  <span className="text-lg font-bold font-mono text-slate-300">
                    P{metrics.positioning.mm_percentile.toFixed(0)}
                  </span>
                </div>
                <div className="h-3 bg-slate-800 rounded-full overflow-hidden mb-2">
                  <div
                    className="h-full bg-gradient-to-r from-red-500 via-amber-500 to-emerald-500 rounded-full transition-all duration-700"
                    style={{
                      width: `${metrics.positioning.mm_percentile}%`,
                    }}
                  />
                </div>
                <div className="flex justify-between text-xs text-slate-500">
                  <span>Most Bearish</span>
                  <span className="text-slate-400 text-center">
                    {metrics.positioning.mm_percentile <= 25
                      ? "Funds are very bearish — potential buying opportunity"
                      : metrics.positioning.mm_percentile <= 50
                        ? "Funds leaning bearish"
                        : metrics.positioning.mm_percentile <= 75
                          ? "Funds leaning bullish"
                          : "Funds are very bullish — prices may be elevated"}
                  </span>
                  <span>Most Bullish</span>
                </div>
              </div>
            )}
          </>
        ) : (
          <div className="text-sm text-slate-500 text-center py-8">
            No positioning data available.
          </div>
        )}
      </div>

      {/* ═══════════ HEADLINES ═══════════ */}
      <div>
        <h3 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
          <Newspaper size={18} className="text-blue-400" />
          Segmented Policy News Lanes
          {news && (
            <span className="text-xs text-slate-500 font-normal ml-2">
              {news.stats.total} recent articles
            </span>
          )}
        </h3>

        {/* Sentiment summary bar */}
        {news && news.stats.total > 0 && (
          <div className="mb-6 bg-[#0a0a0a] border border-white/10 rounded-xl p-4">
            <div className="flex gap-1 h-3 rounded-full overflow-hidden mb-3">
              {news.stats.bullish > 0 && (
                <div
                  className="bg-emerald-500 transition-all"
                  style={{
                    width: `${(news.stats.bullish / news.stats.total) * 100}%`,
                  }}
                />
              )}
              {news.stats.neutral > 0 && (
                <div
                  className="bg-slate-600 transition-all"
                  style={{
                    width: `${(news.stats.neutral / news.stats.total) * 100}%`,
                  }}
                />
              )}
              {news.stats.bearish > 0 && (
                <div
                  className="bg-red-500 transition-all"
                  style={{
                    width: `${(news.stats.bearish / news.stats.total) * 100}%`,
                  }}
                />
              )}
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-emerald-400 font-medium">
                {news.stats.bullish} bullish
              </span>
              <span className="text-slate-500">
                {news.stats.neutral} neutral
              </span>
              <span className="text-red-400 font-medium">
                {news.stats.bearish} bearish
              </span>
            </div>
          </div>
        )}

        {loading && !news && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {[...Array(4)].map((_, i) => (
              <div
                key={i}
                className="bg-white/[0.02] border border-white/5 rounded-2xl p-6 animate-pulse h-36"
              />
            ))}
          </div>
        )}
        {news && news.headlines.length === 0 && (
          <div className="text-sm text-slate-500 py-8 text-center">
            No recent headlines found.
          </div>
        )}
        {news && news.headlines.length > 0 && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {news.headlines.slice(0, 12).map((h) => (
              <HeadlineCard
                key={h.id}
                sentiment={h.sentiment}
                source={h.source}
                lane={h.lane ?? null}
                time={timeAgo(h.event_date)}
                title={h.headline}
                summary={h.summary || ""}
                tags={h.tags}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/* ─── Sub-components ─── */

function FearGreedGauge({ score }: { score: number }) {
  const angle = Math.PI - (score / 100) * Math.PI;
  const needleLen = 95;
  const tipX = 150 + needleLen * Math.cos(angle);
  const tipY = 150 - needleLen * Math.sin(angle);

  return (
    <svg viewBox="0 0 300 170" className="w-full max-w-md mx-auto">
      <defs>
        <linearGradient id="fg-grad" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#ef4444" />
          <stop offset="25%" stopColor="#f97316" />
          <stop offset="50%" stopColor="#eab308" />
          <stop offset="75%" stopColor="#84cc16" />
          <stop offset="100%" stopColor="#22c55e" />
        </linearGradient>
      </defs>
      <path
        d="M 30 150 A 120 120 0 0 1 270 150"
        fill="none"
        stroke="url(#fg-grad)"
        strokeWidth="24"
        strokeLinecap="round"
      />
      <line
        x1="150"
        y1="150"
        x2={tipX}
        y2={tipY}
        stroke="white"
        strokeWidth="3"
        strokeLinecap="round"
      />
      <circle cx="150" cy="150" r="8" fill="white" />
    </svg>
  );
}

function SnapshotCard({
  label,
  value,
  sub,
  color,
  loading,
}: {
  label: string;
  value: string;
  sub?: string;
  color?: string;
  loading?: boolean;
}) {
  if (loading) {
    return (
      <div className="bg-[#0a0a0a] border border-white/10 rounded-xl p-6 animate-pulse">
        <div className="h-3 bg-white/5 rounded w-20 mb-3" />
        <div className="h-8 bg-white/5 rounded w-16" />
      </div>
    );
  }
  return (
    <div className="bg-[#0a0a0a] border border-white/10 rounded-xl p-6 hover:border-white/20 transition-colors">
      <div className="text-xs text-slate-500 uppercase tracking-widest font-bold mb-2">
        {label}
      </div>
      <div className={`text-3xl font-bold font-mono ${color ?? "text-white"}`}>
        {value}
      </div>
      {sub && <div className="text-xs text-slate-500 mt-1">{sub}</div>}
    </div>
  );
}

function VolGauge({
  label,
  value,
  max,
  status,
  suffix,
}: {
  label: string;
  value: number | null;
  max: number;
  status: { text: string; color: string } | null;
  suffix?: string;
}) {
  return (
    <div className="text-center">
      <div className="text-sm text-slate-400 font-bold mb-2">{label}</div>
      <div className="text-3xl font-bold font-mono text-white mb-2">
        {value != null ? `${value.toFixed(1)}${suffix ?? ""}` : "Pending"}
      </div>
      {value != null && (
        <>
          <div className="h-2.5 bg-slate-800 rounded-full overflow-hidden mx-auto max-w-[200px] mb-2">
            <div
              className={`h-full rounded-full transition-all duration-700 ${
                status?.color === "text-red-400"
                  ? "bg-red-500"
                  : status?.color === "text-amber-400"
                    ? "bg-amber-500"
                    : "bg-emerald-500"
              }`}
              style={{ width: `${Math.min(100, (value / max) * 100)}%` }}
            />
          </div>
          {status && (
            <div className={`text-sm font-medium ${status.color}`}>
              {status.text}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function ParticipantCard({
  title,
  subtitle,
  data,
}: {
  title: string;
  subtitle: string;
  data: CotCategory;
}) {
  const isNet = data.net > 0;
  const absLong = Math.abs(data.long);
  const absShort = Math.abs(data.short);
  const total = absLong + absShort;
  const longPct = total > 0 ? (absLong / total) * 100 : 50;

  return (
    <div className="bg-[#0a0a0a] border border-white/10 rounded-2xl p-6 hover:border-white/20 transition-colors">
      <div className="mb-4">
        <div className="text-base font-bold text-white">{title}</div>
        <div className="text-xs text-slate-500">{subtitle}</div>
      </div>
      <div
        className={`text-2xl font-bold mb-1 ${isNet ? "text-emerald-400" : "text-red-400"}`}
      >
        {isNet ? "Net Bullish" : "Net Bearish"}
      </div>
      <div className="text-lg font-mono text-slate-300 mb-3">
        {formatNumber(Math.abs(data.net))} contracts
      </div>
      <div className="h-3 bg-slate-800 rounded-full overflow-hidden mb-2">
        <div
          className="h-full bg-emerald-500 rounded-l-full transition-all duration-700"
          style={{ width: `${longPct}%` }}
        />
      </div>
      <div className="flex justify-between text-sm text-slate-400">
        <span>Long: {formatNumber(absLong)}</span>
        <span>Short: {formatNumber(absShort)}</span>
      </div>
    </div>
  );
}

interface HeadlineCardProps {
  sentiment: "bullish" | "bearish" | "neutral";
  source: string;
  lane?: string | null;
  time: string;
  title: string;
  summary: string;
  tags: string[];
}

function HeadlineCard({
  sentiment,
  source,
  lane,
  time,
  title,
  summary,
  tags,
}: HeadlineCardProps) {
  const pillColor =
    sentiment === "bullish"
      ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
      : sentiment === "bearish"
        ? "bg-red-500/10 text-red-400 border-red-500/20"
        : "bg-slate-500/10 text-slate-400 border-slate-500/20";

  return (
    <div className="bg-[#0a0a0a] border border-white/10 rounded-2xl p-6 hover:border-white/20 transition-colors">
      <div className="flex justify-between items-start mb-3">
        <div className="flex items-center gap-2">
          <span
            className={`px-3 py-1 rounded-full text-xs font-bold border ${pillColor}`}
          >
            {sentiment}
          </span>
          {lane && (
            <span className="px-2 py-0.5 rounded bg-cyan-500/10 text-cyan-300 text-xs border border-cyan-500/20">
              {lane}
            </span>
          )}
          <span className="text-sm text-slate-500">{source}</span>
        </div>
        <span className="text-xs text-slate-600 font-mono">{time}</span>
      </div>
      <h4 className="text-base font-bold text-white mb-2 leading-snug">
        {title}
      </h4>
      {summary && (
        <p className="text-sm text-slate-400 mb-3 leading-relaxed line-clamp-3">
          {summary}
        </p>
      )}
      {tags.length > 0 && (
        <div className="flex gap-2 flex-wrap">
          {tags.map((t: string) => (
            <span
              key={t}
              className="px-2 py-0.5 rounded bg-white/5 text-xs text-slate-400 font-mono border border-white/5"
            >
              {t}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
