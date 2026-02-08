"use client";

import React, { useEffect, useState, useCallback } from "react";
import {
  OrganicTopicCloud,
  type TopicNode,
} from "@/components/viz/OrganicTopicCloud";
import {
  MessageSquare,
  TrendingUp,
  AlertOctagon,
  Scale,
  RefreshCw,
  Newspaper,
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

/* ─── Page ─── */

export default function SentimentPage() {
  const [news, setNews] = useState<NewsData | null>(null);
  const [cot, setCot] = useState<CotData | null>(null);
  const [topics, setTopics] = useState<TopicsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [newsRes, cotRes, topicsRes] = await Promise.all([
        fetch("/api/sentiment/news"),
        fetch("/api/sentiment/cot"),
        fetch("/api/sentiment/topics"),
      ]);

      const [newsData, cotData, topicsData] = await Promise.all([
        newsRes.ok ? newsRes.json() : null,
        cotRes.ok ? cotRes.json() : null,
        topicsRes.ok ? topicsRes.json() : null,
      ]);

      setNews(newsData);
      setCot(cotData);
      setTopics(topicsData);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 5 * 60 * 1000); // Refresh every 5 min
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

  return (
    <div className="min-h-screen bg-[#0a0a0a] text-slate-200 p-6 pt-36 pb-20 animate-in fade-in duration-700">
      {/* Header */}
      <div className="flex items-center justify-between mb-8 pb-4 border-b border-white/5">
        <div>
          <h1 className="text-5xl font-bold text-white tracking-tight">
            Market Psychology
          </h1>
          <p className="text-slate-400 text-sm font-mono mt-1">
            Narrative clustering // Unstructured data fusion
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
              <AlertOctagon className="w-6 h-6 text-amber-400 mx-auto mb-2" />
              <div className="text-2xl font-bold text-amber-400">
                {loading && !news
                  ? "—"
                  : news && news.stats.bearish > news.stats.bullish
                    ? "Elevated"
                    : news && news.stats.bearish === news.stats.bullish
                      ? "Neutral"
                      : "Low"}
              </div>
              <div className="text-xs text-slate-500 uppercase">Fear Index</div>
            </div>
          </div>

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
