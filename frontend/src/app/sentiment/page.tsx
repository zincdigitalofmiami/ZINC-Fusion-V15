"use client";

import React, { useEffect, useState, useCallback } from "react";
import {
  OrganicTopicCloud,
  type TopicNode,
} from "@/components/viz/OrganicTopicCloud";
import {
  MessageSquare,
  TrendingUp,
  Scale,
  RefreshCw,
  Newspaper,
  Activity,
  BarChart3,
  Gauge,
  Zap,
} from "lucide-react";

/* ─── Types ─── */

interface Headline {
  id: string;
  event_date: string;
  headline: string;
  summary: string | null;
  source: string;
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

interface TopicsData {
  topics: TopicNode[];
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
}

/* ─── Helpers ─── */

function formatNumber(n: number): string {
  if (Math.abs(n) >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return n.toLocaleString();
}

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const hours = Math.floor(diff / 3600000);
  if (hours < 1) return "Just now";
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days === 1) return "1d ago";
  return `${days}d ago`;
}

function zColor(z: number | null): string {
  if (z === null) return "text-slate-500";
  if (z > 1.5) return "text-emerald-400";
  if (z > 0.5) return "text-emerald-500/80";
  if (z > -0.5) return "text-slate-400";
  if (z > -1.5) return "text-red-400/80";
  return "text-red-400";
}

function signalColor(s: number): string {
  if (s > 0.5) return "text-emerald-400";
  if (s > 0.1) return "text-emerald-500/70";
  if (s > -0.1) return "text-slate-400";
  if (s > -0.5) return "text-red-400/70";
  return "text-red-400";
}

function signalBg(s: number): string {
  if (s > 0.5) return "bg-emerald-500/20 border-emerald-500/30";
  if (s > 0.1) return "bg-emerald-500/10 border-emerald-500/20";
  if (s > -0.1) return "bg-slate-500/10 border-slate-500/20";
  if (s > -0.5) return "bg-red-500/10 border-red-500/20";
  return "bg-red-500/20 border-red-500/30";
}

function trendLabel(trend: string): { text: string; color: string } {
  switch (trend) {
    case "strong_uptrend":
      return { text: "STRONG UPTREND", color: "text-emerald-400" };
    case "uptrend":
      return { text: "UPTREND", color: "text-emerald-500/80" };
    case "mixed":
      return { text: "MIXED", color: "text-amber-400" };
    default:
      return { text: "DOWNTREND", color: "text-red-400" };
  }
}

function rsiLabel(rsi: number | null): { text: string; color: string } {
  if (rsi === null) return { text: "—", color: "text-slate-500" };
  if (rsi >= 70) return { text: "OVERBOUGHT", color: "text-red-400" };
  if (rsi >= 60) return { text: "STRONG", color: "text-emerald-400" };
  if (rsi >= 40) return { text: "NEUTRAL", color: "text-slate-400" };
  if (rsi >= 30) return { text: "WEAK", color: "text-red-400/80" };
  return { text: "OVERSOLD", color: "text-emerald-400" };
}

/* ─── Page ─── */

export default function SentimentPage() {
  const [news, setNews] = useState<NewsData | null>(null);
  const [cot, setCot] = useState<CotData | null>(null);
  const [topics, setTopics] = useState<TopicsData | null>(null);
  const [metrics, setMetrics] = useState<MetricsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [newsRes, cotRes, topicsRes, metricsRes] = await Promise.all([
        fetch("/api/sentiment/news"),
        fetch("/api/sentiment/cot"),
        fetch("/api/sentiment/topics"),
        fetch("/api/sentiment/metrics"),
      ]);

      const [newsData, cotData, topicsData, metricsData] = await Promise.all([
        newsRes.ok ? newsRes.json() : null,
        cotRes.ok ? cotRes.json() : null,
        topicsRes.ok ? topicsRes.json() : null,
        metricsRes.ok ? metricsRes.json() : null,
      ]);

      setNews(newsData);
      setCot(cotData);
      setTopics(topicsData);
      setMetrics(metricsData);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, [fetchData]);

  // Sentiment bias calculation
  const biasLabel = (() => {
    if (!news?.stats) return null;
    const { bullish, bearish, total } = news.stats;
    if (total === 0) return null;
    const ratio = (bullish - bearish) / total;
    const sigma = (ratio * 2).toFixed(2);
    const direction = ratio > 0 ? "Bullish" : ratio < 0 ? "Bearish" : "Neutral";
    return {
      sigma: `${ratio > 0 ? "+" : ""}${sigma}σ`,
      direction,
      color:
        ratio > 0
          ? "text-emerald-400"
          : ratio < 0
            ? "text-red-400"
            : "text-slate-400",
    };
  })();

  const trendInfo = metrics ? trendLabel(metrics.technicals.trend) : null;
  const rsiInfo = metrics ? rsiLabel(metrics.technicals.rsi_14) : null;

  return (
    <div className="min-h-screen bg-[#0a0a0a] text-slate-200 p-6 pt-36 pb-20 animate-in fade-in duration-700">
      {/* Header */}
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
          <button
            onClick={fetchData}
            disabled={loading}
            className="p-2 rounded-lg border border-white/10 hover:border-white/20 text-slate-400 hover:text-white transition-colors disabled:opacity-30"
            title="Refresh data"
          >
            <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
          </button>
          {biasLabel && (
            <div className="text-right">
              <div className={`text-2xl font-bold ${biasLabel.color}`}>
                {biasLabel.sigma}
              </div>
              <div className="text-[10px] text-slate-500 uppercase tracking-widest">
                {biasLabel.direction} Bias
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div className="mb-6 p-4 bg-red-500/10 border border-red-500/20 rounded-xl text-red-400 text-sm">
          Failed to load data: {error}
        </div>
      )}

      {/* ═══════════ QUANT PULSE ═══════════ */}
      <div className="mb-8">
        <h3 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
          <Activity size={18} className="text-cyan-400" />
          Quant Pulse
          {metrics?.as_of && (
            <span className="text-xs text-slate-500 font-normal ml-2">
              as of {metrics.as_of}
            </span>
          )}
        </h3>

        {/* Top row — price + returns + vol */}
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3 mb-4">
          <MetricCell
            label="ZL Close"
            value={
              metrics?.price.close != null
                ? `¢${metrics.price.close.toFixed(2)}`
                : "—"
            }
            sub={
              metrics?.price.volume
                ? `Vol ${formatNumber(metrics.price.volume)}`
                : undefined
            }
            loading={loading && !metrics}
          />
          <MetricCell
            label="5d Return"
            value={
              metrics?.returns.ret_5d != null
                ? `${metrics.returns.ret_5d > 0 ? "+" : ""}${metrics.returns.ret_5d}%`
                : "—"
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
          <MetricCell
            label="21d Return"
            value={
              metrics?.returns.ret_21d != null
                ? `${metrics.returns.ret_21d > 0 ? "+" : ""}${metrics.returns.ret_21d}%`
                : "—"
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
          <MetricCell
            label="63d Return"
            value={
              metrics?.returns.ret_63d != null
                ? `${metrics.returns.ret_63d > 0 ? "+" : ""}${metrics.returns.ret_63d}%`
                : "—"
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
          <MetricCell
            label="21d RVol"
            value={
              metrics?.volatility.realized_21d != null
                ? `${metrics.volatility.realized_21d}%`
                : "—"
            }
            sub="annualized"
            loading={loading && !metrics}
          />
          <MetricCell
            label="RSI-14"
            value={
              metrics?.technicals.rsi_14 != null
                ? metrics.technicals.rsi_14.toFixed(1)
                : "—"
            }
            color={rsiInfo?.color}
            sub={rsiInfo?.text}
            loading={loading && !metrics}
          />
        </div>

        {/* Second row — trend + positioning + vol indices + crush */}
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3 mb-4">
          <MetricCell
            label="Trend"
            value={trendInfo?.text ?? "—"}
            color={trendInfo?.color}
            sub={
              metrics
                ? `${[
                    metrics.technicals.above_sma20 ? "▲20" : "▼20",
                    metrics.technicals.above_sma50 ? "▲50" : "▼50",
                    metrics.technicals.above_sma200 ? "▲200" : "▼200",
                  ].join(" ")}`
                : undefined
            }
            loading={loading && !metrics}
          />
          <MetricCell
            label="MM Z-Score"
            value={
              metrics?.positioning.mm_zscore != null
                ? (metrics.positioning.mm_zscore > 0 ? "+" : "") +
                  metrics.positioning.mm_zscore.toFixed(3)
                : "—"
            }
            color={zColor(metrics?.positioning.mm_zscore ?? null)}
            sub={
              metrics?.positioning.mm_percentile != null
                ? `P${metrics.positioning.mm_percentile.toFixed(0)}`
                : undefined
            }
            loading={loading && !metrics}
          />
          <MetricCell
            label="VIX"
            value={
              metrics?.volatility.vix != null
                ? metrics.volatility.vix.toFixed(2)
                : "—"
            }
            color={zColor(metrics?.volatility.vix_z ?? null)}
            sub={
              metrics?.volatility.vix_z != null
                ? `z=${metrics.volatility.vix_z > 0 ? "+" : ""}${metrics.volatility.vix_z.toFixed(2)}`
                : undefined
            }
            loading={loading && !metrics}
          />
          <MetricCell
            label="OVX"
            value={
              metrics?.volatility.ovx != null
                ? metrics.volatility.ovx.toFixed(2)
                : "—"
            }
            sub="Oil Vol Index"
            loading={loading && !metrics}
          />
          <MetricCell
            label="Board Crush"
            value={
              metrics?.crush.board_crush != null
                ? metrics.crush.board_crush.toFixed(3)
                : "—"
            }
            color={zColor(metrics?.crush.crush_zscore ?? null)}
            sub={
              metrics?.crush.crush_zscore != null
                ? `z=${metrics.crush.crush_zscore > 0 ? "+" : ""}${metrics.crush.crush_zscore.toFixed(2)}`
                : undefined
            }
            loading={loading && !metrics}
          />
          <MetricCell
            label="Oil Share"
            value={
              metrics?.crush.oil_share != null
                ? `${(metrics.crush.oil_share * 100).toFixed(1)}%`
                : "—"
            }
            color={zColor(metrics?.crush.oil_share_zscore ?? null)}
            sub={
              metrics?.crush.oil_share_zscore != null
                ? `z=${metrics.crush.oil_share_zscore > 0 ? "+" : ""}${metrics.crush.oil_share_zscore.toFixed(2)}`
                : undefined
            }
            loading={loading && !metrics}
          />
        </div>

        {/* MA visualization */}
        {metrics && (
          <div className="bg-[#0a0a0a] border border-white/5 rounded-xl p-4 mb-4">
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs text-slate-500 uppercase tracking-widest font-bold">
                Moving Average Structure
              </span>
              <span className={`text-xs font-bold ${trendInfo?.color}`}>
                {trendInfo?.text}
              </span>
            </div>
            <div className="flex gap-2 items-end h-16">
              {[
                {
                  label: "SMA200",
                  val: metrics.technicals.sma200,
                  above: metrics.technicals.above_sma200,
                },
                {
                  label: "SMA50",
                  val: metrics.technicals.sma50,
                  above: metrics.technicals.above_sma50,
                },
                {
                  label: "SMA20",
                  val: metrics.technicals.sma20,
                  above: metrics.technicals.above_sma20,
                },
                { label: "PRICE", val: metrics.price.close, above: true },
              ].map((ma) => (
                <div key={ma.label} className="flex-1 text-center">
                  <div
                    className={`text-lg font-bold font-mono ${ma.label === "PRICE" ? "text-white" : ma.above ? "text-emerald-500/70" : "text-red-500/70"}`}
                  >
                    {ma.val?.toFixed(2) ?? "—"}
                  </div>
                  <div
                    className={`text-[10px] mt-1 ${ma.label === "PRICE" ? "text-white font-bold" : "text-slate-500"}`}
                  >
                    {ma.label}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* ═══════════ SPECIALIST SIGNALS ═══════════ */}
      {metrics && metrics.specialists.length > 0 && (
        <div className="mb-8">
          <h3 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
            <Zap size={18} className="text-amber-400" />
            Big 11 Specialist Signals
            <span className="text-xs text-slate-500 font-normal ml-2">
              {metrics.composite.contributing_models} models
            </span>
            <span
              className={`ml-auto text-sm font-bold ${signalColor(metrics.composite.signal)}`}
            >
              Composite: {metrics.composite.signal > 0 ? "+" : ""}
              {metrics.composite.signal.toFixed(3)}
              <span className="text-[10px] text-slate-500 font-normal ml-2 uppercase">
                {metrics.composite.interpretation}
              </span>
            </span>
          </h3>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-2">
            {metrics.specialists
              .sort((a, b) => Math.abs(b.signal) - Math.abs(a.signal))
              .map((s) => (
                <div
                  key={s.bucket}
                  className={`rounded-lg border p-3 ${signalBg(s.signal)} transition-all hover:scale-[1.02]`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-[10px] text-slate-400 uppercase tracking-wider font-bold">
                      {s.bucket.replace("_", " ")}
                    </span>
                    <span className="text-[9px] text-slate-600 font-mono">
                      {s.model_type}
                    </span>
                  </div>
                  <div
                    className={`text-xl font-bold font-mono ${signalColor(s.signal)}`}
                  >
                    {s.signal > 0 ? "+" : ""}
                    {s.signal.toFixed(2)}
                  </div>
                  <div className="flex items-center gap-1 mt-1">
                    <div className="flex-1 h-1 bg-white/5 rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full ${s.confidence > 0.7 ? "bg-emerald-500" : s.confidence > 0.4 ? "bg-amber-500" : "bg-red-500"}`}
                        style={{ width: `${s.confidence * 100}%` }}
                      />
                    </div>
                    <span className="text-[9px] text-slate-600">
                      {(s.confidence * 100).toFixed(0)}%
                    </span>
                  </div>
                </div>
              ))}
          </div>
        </div>
      )}

      {/* Narrative Cloud */}
      <div className="mb-8">
        <h3 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
          <MessageSquare size={18} className="text-blue-400" />
          Active Narrative Clusters
          {topics && topics.topics.length > 0 && (
            <span className="text-xs text-slate-500 font-normal ml-2">
              Last 30 days
            </span>
          )}
        </h3>
        <div className="w-full bg-[#0a0a0a] border border-white/5 rounded-2xl p-1 overflow-hidden shadow-2xl relative">
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(59,130,246,0.05),transparent_60%)] pointer-events-none" />
          <OrganicTopicCloud topics={topics?.topics ?? []} loading={loading} />

          {/* Legend */}
          <div className="absolute bottom-6 left-6 p-4 bg-black/40 backdrop-blur border border-white/10 rounded-xl max-w-xs pointer-events-none">
            <h4 className="text-xs font-bold text-white mb-2 uppercase">
              Size = Mention Volume
            </h4>
            <p className="text-[10px] text-slate-400">
              Bubble size driven by specialist tag mention count across news
              sources.
              <br />
              <span className="text-emerald-400">Green</span> = bullish
              sentiment, <span className="text-rose-400">Red</span> = bearish,{" "}
              <span className="text-slate-400">Gray</span> = neutral.
            </p>
          </div>
        </div>
      </div>

      {/* Lower Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* News Feed */}
        <div>
          <h3 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
            <TrendingUp size={18} className="text-slate-400" />
            Recent Headlines
            {news && (
              <span className="text-xs text-slate-500 font-normal ml-2">
                {news.stats.total} articles
              </span>
            )}
          </h3>
          <div className="space-y-4 max-h-[600px] overflow-y-auto pr-1 custom-scrollbar">
            {loading && !news && (
              <div className="space-y-4">
                {[...Array(3)].map((_, i) => (
                  <div
                    key={i}
                    className="bg-white/[0.02] border border-white/5 rounded-r-xl p-4 animate-pulse h-28"
                  />
                ))}
              </div>
            )}
            {news && news.headlines.length === 0 && (
              <div className="text-sm text-slate-500 py-8 text-center">
                No recent headlines found.
              </div>
            )}
            {news?.headlines.slice(0, 15).map((h) => (
              <HeadlineCard
                key={h.id}
                sentiment={h.sentiment}
                source={h.source}
                time={timeAgo(h.event_date)}
                title={h.headline}
                summary={h.summary || ""}
                tags={h.tags}
              />
            ))}
          </div>
        </div>

        {/* COT & Metrics */}
        <div className="space-y-8">
          {/* COT */}
          <div className="bg-[#0a0a0a] border border-white/5 rounded-xl p-6">
            <div className="flex items-center justify-between mb-6">
              <h3 className="text-lg font-bold text-white flex items-center gap-2">
                <Scale size={18} className="text-slate-400" />
                Smart Money (COT)
              </h3>
              {cot ? (
                <div className="text-right">
                  <span
                    className={`text-xs font-mono ${cot.latest.managed_money.net > 0 ? "text-emerald-400" : "text-red-400"}`}
                  >
                    NET {cot.latest.managed_money.net > 0 ? "LONG" : "SHORT"}{" "}
                    {formatNumber(Math.abs(cot.latest.managed_money.net))}
                  </span>
                  <div className="text-[10px] text-slate-600 mt-0.5">
                    as of {cot.as_of_date}
                  </div>
                </div>
              ) : loading ? (
                <span className="text-xs text-slate-600 animate-pulse">
                  Loading…
                </span>
              ) : null}
            </div>

            {cot ? (
              <div className="space-y-6">
                <CotBar
                  label="Managed Money"
                  value={Math.min(
                    100,
                    Math.max(0, cot.latest.managed_money.net_pct_oi + 50),
                  )}
                  color="bg-emerald-500"
                  valueText={formatNumber(cot.latest.managed_money.net)}
                  type={
                    cot.latest.managed_money.net > 0 ? "bullish" : "bearish"
                  }
                  pctOi={cot.latest.managed_money.net_pct_oi}
                />
                <CotBar
                  label="Producers / Commercials"
                  value={Math.min(
                    100,
                    Math.max(0, cot.latest.producers.net_pct_oi + 50),
                  )}
                  color="bg-red-500"
                  valueText={formatNumber(cot.latest.producers.net)}
                  type={cot.latest.producers.net > 0 ? "bullish" : "bearish"}
                  pctOi={cot.latest.producers.net_pct_oi}
                />
                <CotBar
                  label="Swap Dealers"
                  value={Math.min(
                    100,
                    Math.max(
                      0,
                      50 +
                        (cot.latest.swaps.net /
                          (cot.latest.open_interest || 1)) *
                          100,
                    ),
                  )}
                  color="bg-slate-500"
                  valueText={formatNumber(cot.latest.swaps.net)}
                  type={
                    Math.abs(cot.latest.swaps.net) < 1000
                      ? "neutral"
                      : cot.latest.swaps.net > 0
                        ? "bullish"
                        : "bearish"
                  }
                />
              </div>
            ) : loading ? (
              <div className="space-y-6">
                {[...Array(3)].map((_, i) => (
                  <div
                    key={i}
                    className="h-8 bg-white/[0.02] rounded animate-pulse"
                  />
                ))}
              </div>
            ) : (
              <div className="text-sm text-slate-500 py-4 text-center">
                No COT data available.
              </div>
            )}
          </div>

          {/* Stats cards */}
          <div className="grid grid-cols-2 gap-4">
            <div className="bg-[#0a0a0a] border border-white/5 rounded-xl p-6 text-center shadow-lg shadow-black/50">
              <Newspaper className="w-6 h-6 text-blue-400 mx-auto mb-2" />
              <div className="text-2xl font-bold text-white">
                {loading && !news ? "—" : (news?.stats.total ?? 0)}
              </div>
              <div className="text-xs text-slate-500 uppercase">
                Articles (30d)
              </div>
            </div>
            <div className="bg-[#0a0a0a] border border-white/5 rounded-xl p-6 text-center shadow-lg shadow-black/50">
              <Gauge className="w-6 h-6 text-amber-400 mx-auto mb-2" />
              <div
                className={`text-2xl font-bold ${metrics?.volatility.ovx != null && metrics.volatility.ovx > 50 ? "text-red-400" : metrics?.volatility.ovx != null && metrics.volatility.ovx > 35 ? "text-amber-400" : "text-emerald-400"}`}
              >
                {loading && !metrics
                  ? "—"
                  : metrics?.volatility.ovx != null
                    ? metrics.volatility.ovx.toFixed(1)
                    : news && news.stats.bearish > news.stats.bullish
                      ? "Elevated"
                      : "Low"}
              </div>
              <div className="text-xs text-slate-500 uppercase">OVX Fear</div>
            </div>
          </div>

          {/* Positioning Z-Score Card */}
          {metrics?.positioning.mm_zscore != null && (
            <div className="bg-[#0a0a0a] border border-white/5 rounded-xl p-6">
              <h4 className="text-sm font-bold text-white mb-3 flex items-center gap-2">
                <BarChart3 size={14} className="text-slate-400" />
                Managed Money Positioning
              </h4>
              <div className="flex items-center gap-4 mb-3">
                <div className="text-center">
                  <div
                    className={`text-3xl font-bold font-mono ${zColor(metrics.positioning.mm_zscore)}`}
                  >
                    {metrics.positioning.mm_zscore > 0 ? "+" : ""}
                    {metrics.positioning.mm_zscore.toFixed(2)}σ
                  </div>
                  <div className="text-[10px] text-slate-600 mt-0.5">
                    Z-Score
                  </div>
                </div>
                <div className="flex-1 space-y-1.5">
                  <div className="flex justify-between text-[10px]">
                    <span className="text-slate-600">Percentile</span>
                    <span className="text-slate-400 font-mono">
                      P{metrics.positioning.mm_percentile?.toFixed(0)}
                    </span>
                  </div>
                  <div className="h-2 bg-slate-800 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-gradient-to-r from-red-500 via-amber-500 to-emerald-500 rounded-full transition-all duration-700"
                      style={{
                        width: `${metrics.positioning.mm_percentile ?? 50}%`,
                      }}
                    />
                  </div>
                  <div className="flex justify-between text-[9px] text-slate-600">
                    <span>Bearish extreme</span>
                    <span>Bullish extreme</span>
                  </div>
                </div>
              </div>
              <div className="grid grid-cols-3 gap-2 text-center text-[10px]">
                <div>
                  <div className="text-slate-400 font-mono">
                    {formatNumber(metrics.positioning.mm_net ?? 0)}
                  </div>
                  <div className="text-slate-600">Current</div>
                </div>
                <div>
                  <div className="text-slate-400 font-mono">
                    {formatNumber(metrics.positioning.mm_avg ?? 0)}
                  </div>
                  <div className="text-slate-600">
                    Mean ({metrics.positioning.history_weeks}w)
                  </div>
                </div>
                <div>
                  <div className="text-slate-400 font-mono">
                    ±{formatNumber(metrics.positioning.mm_std ?? 0)}
                  </div>
                  <div className="text-slate-600">Std Dev</div>
                </div>
              </div>
            </div>
          )}

          {/* Sentiment breakdown */}
          {news && news.stats.total > 0 && (
            <div className="bg-[#0a0a0a] border border-white/5 rounded-xl p-6">
              <h4 className="text-sm font-bold text-white mb-4">
                Sentiment Breakdown
              </h4>
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
              <div className="flex justify-between text-xs">
                <span className="text-emerald-400">
                  {news.stats.bullish} bullish
                </span>
                <span className="text-slate-500">
                  {news.stats.neutral} neutral
                </span>
                <span className="text-red-400">
                  {news.stats.bearish} bearish
                </span>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/* ─── Sub-components ─── */

interface HeadlineCardProps {
  sentiment: "bullish" | "bearish" | "neutral";
  source: string;
  time: string;
  title: string;
  summary: string;
  tags: string[];
}

function HeadlineCard({
  sentiment,
  source,
  time,
  title,
  summary,
  tags,
}: HeadlineCardProps) {
  const borderColor =
    sentiment === "bullish"
      ? "border-l-emerald-500"
      : sentiment === "bearish"
        ? "border-l-red-500"
        : "border-l-slate-500";
  const textColor =
    sentiment === "bullish"
      ? "text-emerald-400"
      : sentiment === "bearish"
        ? "text-red-400"
        : "text-slate-400";

  return (
    <div
      className={`bg-[#0a0a0a] border border-white/5 border-l-4 ${borderColor} rounded-r-xl p-4 hover:bg-white/[0.02] transition-colors`}
    >
      <div className="flex justify-between items-start mb-2">
        <div className="flex items-center gap-2">
          <span className={`text-xs font-bold uppercase ${textColor}`}>
            {sentiment}
          </span>
          <span className="text-xs text-slate-600">·</span>
          <span className="text-xs text-slate-500">{source}</span>
        </div>
        <span className="text-xs text-slate-600 font-mono">{time}</span>
      </div>
      <h4 className="text-sm font-bold text-white mb-2 leading-tight">
        {title}
      </h4>
      {summary && (
        <p className="text-xs text-slate-400 mb-3 leading-relaxed line-clamp-2">
          {summary}
        </p>
      )}
      {tags.length > 0 && (
        <div className="flex gap-2 flex-wrap">
          {tags.map((t: string) => (
            <span
              key={t}
              className="px-1.5 py-0.5 rounded bg-white/5 text-[10px] text-slate-400 font-mono border border-white/5"
            >
              {t}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

interface CotBarProps {
  label: string;
  value: number;
  color: string;
  valueText: string;
  type: "bullish" | "bearish" | "neutral";
  pctOi?: number;
}

function CotBar({ label, value, color, valueText, type, pctOi }: CotBarProps) {
  return (
    <div>
      <div className="flex justify-between text-xs mb-2">
        <span className="text-slate-400">{label}</span>
        <div className="flex items-center gap-2">
          {pctOi !== undefined && (
            <span className="text-slate-600 text-[10px]">
              {pctOi > 0 ? "+" : ""}
              {pctOi.toFixed(1)}% OI
            </span>
          )}
          <span
            className={
              type === "bullish"
                ? "text-emerald-400"
                : type === "bearish"
                  ? "text-red-400"
                  : "text-slate-500"
            }
          >
            {valueText}
          </span>
        </div>
      </div>
      <div className="h-2 bg-slate-800 rounded-full overflow-hidden">
        <div
          className={`h-full ${color} transition-all duration-700`}
          style={{ width: `${value}%` }}
        />
      </div>
    </div>
  );
}

/* ─── Metric Cell ─── */

interface MetricCellProps {
  label: string;
  value: string;
  color?: string;
  sub?: string;
  loading?: boolean;
}

function MetricCell({ label, value, color, sub, loading }: MetricCellProps) {
  if (loading) {
    return (
      <div className="bg-[#0a0a0a] border border-white/5 rounded-lg p-3 animate-pulse">
        <div className="h-3 bg-white/5 rounded w-16 mb-2" />
        <div className="h-5 bg-white/5 rounded w-12" />
      </div>
    );
  }
  return (
    <div className="bg-[#0a0a0a] border border-white/5 rounded-lg p-3 hover:border-white/10 transition-colors">
      <div className="text-[10px] text-slate-500 uppercase tracking-wider font-bold mb-1">
        {label}
      </div>
      <div className={`text-lg font-bold font-mono ${color ?? "text-white"}`}>
        {value}
      </div>
      {sub && <div className="text-[9px] text-slate-600 mt-0.5">{sub}</div>}
    </div>
  );
}
