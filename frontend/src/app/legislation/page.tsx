import { PolicyService } from "@/lib/services/policy-service";
import type { PolicyNewsItem } from "@/lib/services/policy-service";
import {
  RegimeState,
  LegislationEvent,
  ExecutiveEvent,
  TariffDeadline,
  AgencyActivity,
} from "@/components/policy/types";
import { PolicyAiBriefing } from "@/components/policy/PolicyAiBriefing";
import { PolicyNewsFeed } from "@/components/policy/PolicyNewsFeed";
import {
  Gavel,
  FileSignature,
  TrendingUp,
  Building2,
  CalendarClock,
  ExternalLink,
  ShieldAlert,
  Activity,
  Siren,
  Radio,
  Newspaper,
  type LucideIcon,
} from "lucide-react";

export const revalidate = 3600; // ISR: revalidate every 1 hour

// ============================================================================
// UI COMPONENTS
// ============================================================================

// Dashboard risk-card palette (copied 1:1 from `frontend/src/components/ChrisTop4Drivers.tsx`)
function getScoreColor(score: number): { stroke: string; glow: string } {
  const s = Math.max(0, Math.min(100, score));
  if (s <= 25) return { stroke: "#22C55E", glow: "rgba(34, 197, 94, 0.5)" };
  if (s <= 40) {
    const t = (s - 25) / 15;
    return {
      stroke: `rgb(${Math.round(34 + (234 - 34) * t)}, ${Math.round(
        197 - (197 - 179) * t,
      )}, ${Math.round(94 - (94 - 8) * t)})`,
      glow: `rgba(${Math.round(34 + (234 - 34) * t)}, ${Math.round(
        197 - (197 - 179) * t,
      )}, ${Math.round(94 - (94 - 8) * t)}, 0.5)`,
    };
  }
  if (s <= 55) return { stroke: "#EAB308", glow: "rgba(234, 179, 8, 0.5)" };
  if (s <= 70) {
    const t = (s - 55) / 15;
    return {
      stroke: `rgb(${Math.round(234 + (239 - 234) * t)}, ${Math.round(
        179 - (179 - 115) * t,
      )}, ${Math.round(8 + (0 - 8) * t)})`,
      glow: `rgba(${Math.round(234 + (239 - 234) * t)}, ${Math.round(
        179 - (179 - 115) * t,
      )}, ${Math.round(8 + (0 - 8) * t)}, 0.5)`,
    };
  }
  if (s <= 85) return { stroke: "#EF7300", glow: "rgba(239, 115, 0, 0.5)" };
  return { stroke: "#EF4444", glow: "rgba(239, 68, 68, 0.6)" };
}

function getScoreTextColor(score: number): string {
  if (score >= 70) return "text-red-400";
  if (score >= 55) return "text-orange-400";
  if (score >= 40) return "text-amber-400";
  return "text-green-400";
}

function HorizontalMeter({ score }: { score: number }) {
  const percentage = Math.min(Math.max(score, 0), 100);
  const colors = getScoreColor(score);

  return (
    <div className="flex items-center gap-4 w-full">
      <div className="flex-1 h-3 bg-slate-800 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-700 ease-out"
          style={{
            width: `${percentage}%`,
            backgroundColor: colors.stroke,
            boxShadow: `0 0 8px ${colors.glow}`,
          }}
        />
      </div>
      <span
        className="text-3xl font-bold tabular-nums min-w-[3ch] text-right"
        style={{ color: colors.stroke }}
      >
        {Math.round(score)}
      </span>
    </div>
  );
}

function RegimeBadge({ regime }: { regime: RegimeState }) {
  const score = regime.score ?? 0;
  const colors = getScoreColor(score);
  const borderStyle =
    score >= 65
      ? { borderColor: colors.stroke, boxShadow: `0 0 20px ${colors.glow}` }
      : { borderColor: "rgba(255,255,255,0.08)" };

  const tc = regime.tariff_components;

  return (
    <div
      className="bg-[#0a0a0a] border rounded-2xl p-6 md:p-7 min-w-[340px]"
      style={borderStyle}
    >
      <div className="flex items-center justify-between mb-2">
        <div className="text-xs uppercase tracking-widest text-slate-500">
          Threat Level
        </div>
        {regime.freshness?.tpu_date && (
          <span className="text-[9px] text-slate-600 font-mono">
            TPU as of {regime.freshness.tpu_date}
          </span>
        )}
      </div>

      <div className="w-full mb-3">
        <HorizontalMeter score={score} />
      </div>

      <div className={`text-lg font-medium ${getScoreTextColor(score)}`}>
        {regime.label}
      </div>

      {regime.headline && (
        <div className="text-xs text-slate-500 mt-1 italic">
          {regime.headline}
        </div>
      )}

      {/* Component breakdown */}
      {tc && (
        <div className="mt-4 pt-3 border-t border-white/5 space-y-1.5">
          <div className="text-[10px] text-slate-600 uppercase tracking-wider font-bold mb-2">
            Score Components
          </div>
          <ComponentBar label="TPU (35%)" value={tc.tpu_score} detail={`Index: ${tc.tpu_value}`} />
          <ComponentBar label="EMV (20%)" value={tc.emv_score} detail={tc.emv_value ? `Index: ${tc.emv_value}` : "N/A"} />
          <ComponentBar label="Legislation (10%)" value={50 + tc.legislation_adj} detail={`${tc.legislation_count} filings/14d`} />
          <ComponentBar label="Specialist (15%)" value={50 + tc.specialist_adj} detail={tc.specialist_signal !== null ? `Signal: ${tc.specialist_signal.toFixed(2)}` : "N/A"} />
          <ComponentBar label="News (20%)" value={50 + tc.soy_tariff_news_adj} detail={`${tc.soy_tariff_news_count} articles/7d`} />
        </div>
      )}
    </div>
  );
}

function ComponentBar({ label, value, detail }: { label: string; value: number; detail: string }) {
  const pct = Math.min(100, Math.max(0, value));
  const c = getScoreColor(pct);
  return (
    <div className="flex items-center gap-2">
      <span className="text-[10px] text-slate-500 w-24 shrink-0 truncate">{label}</span>
      <div className="flex-1 h-1.5 bg-slate-800 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, backgroundColor: c.stroke }}
        />
      </div>
      <span className="text-[10px] font-mono text-slate-600 w-20 text-right truncate" title={detail}>
        {detail}
      </span>
    </div>
  );
}

interface MetricCardProps {
  title: string;
  value: string | number;
  subtext?: string;
  icon: LucideIcon;
  trend?: number | null;
}

function MetricCard({
  title,
  value,
  subtext,
  icon: Icon,
  trend,
}: MetricCardProps) {
  return (
    <div className="bg-[#0a0a0a] border border-white/5 rounded-2xl p-5 hover:border-white/20 transition-all duration-300">
      <div className="flex justify-between items-start mb-2">
        <div className="p-2 bg-slate-800 rounded-lg text-slate-400">
          <Icon className="w-4 h-4" />
        </div>
        {trend != null && (
          <span
            className={`text-[10px] font-medium px-1.5 py-0.5 rounded-full border ${
              trend > 0
                ? "bg-red-500/10 text-red-400 border-red-500/20"
                : "bg-green-500/10 text-green-400 border-green-500/20"
            }`}
          >
            {trend > 0 ? "+" : ""}
            {trend}%
          </span>
        )}
      </div>
      <div className="text-2xl font-bold text-white mb-0.5">{value}</div>
      <div className="text-xs font-medium text-slate-400">{title}</div>
      {subtext && <div className="text-[10px] text-slate-500 mt-1 leading-tight">{subtext}</div>}
    </div>
  );
}

function AgencyHeatmap({ agencies }: { agencies: AgencyActivity[] }) {
  const maxCount = Math.max(...agencies.map((a) => a.count), 1);

  return (
    <div className="bg-[#0a0a0a] border border-white/5 rounded-2xl p-6 md:p-8 h-full">
      <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
        <Building2 className="w-5 h-5" />
        ZL-Relevant Agency Activity
      </h3>
      <p className="text-[10px] text-slate-600 -mt-3 mb-3">Trade, biofuel, energy, agriculture filings (90d)</p>
      <div className="space-y-3 max-h-[300px] overflow-y-auto pr-2 custom-scrollbar">
        {agencies.slice(0, 8).map((agency) => (
          <div key={agency.agency} className="group">
            <div className="flex justify-between text-sm mb-1">
              <span
                className="text-slate-300 font-medium truncate w-3/4"
                title={agency.agency}
              >
                {agency.agency}
              </span>
              <span className="text-slate-400 font-mono">{agency.count}</span>
            </div>
            <div className="h-2 bg-slate-800 rounded-full overflow-hidden">
              <div
                className="h-full rounded-full transition-all duration-700 ease-out"
                style={{
                  width: `${(agency.count / maxCount) * 100}%`,
                  backgroundColor: getScoreColor(
                    (agency.count / maxCount) * 100,
                  ).stroke,
                  boxShadow: `0 0 8px ${getScoreColor((agency.count / maxCount) * 100).glow}`,
                }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function ShockwaveList({ events }: { events: ExecutiveEvent[] }) {
  return (
    <div className="bg-[#0a0a0a] border border-white/5 rounded-2xl p-6 md:p-8 h-full">
      <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
        <Activity className="w-5 h-5" />
        Executive Actions
      </h3>
      <p className="text-[10px] text-slate-600 -mt-3 mb-3">Recent orders & memoranda with ZL price impact</p>
      <div className="space-y-4 max-h-[280px] overflow-y-auto pr-2 custom-scrollbar">
        {events.length === 0 ? (
          <p className="text-xs text-slate-600 italic">No executive actions in the last 90 days.</p>
        ) : events.slice(0, 6).map((evt) => (
          <div
            key={evt.id}
            className="relative pl-4 border-l-2 border-slate-800 hover:border-slate-500 transition-colors"
          >
            <div className="absolute -left-[5px] top-1.5 w-2 h-2 rounded-full bg-slate-700 ring-2 ring-slate-900" />
            <div className="flex justify-between items-start">
              <span className="text-xs text-slate-500 font-mono">
                {evt.event_date}
              </span>
              {Math.abs(evt.price_return_1d || 0) > 0.005 && (
                <span className={`text-xs px-1.5 py-0.5 rounded ml-2 ${
                  (evt.price_return_1d || 0) > 0
                    ? "bg-green-500/10 text-green-400 border border-green-500/20"
                    : "bg-red-500/10 text-red-400 border border-red-500/20"
                }`}>
                  ZL {(evt.price_return_1d! * 100) > 0 ? "+" : ""}{(evt.price_return_1d! * 100).toFixed(1)}%
                </span>
              )}
            </div>
            <a
              href={evt.url || "#"}
              target="_blank"
              className="block text-sm text-slate-300 mt-1 hover:text-white transition-colors line-clamp-2"
            >
              {evt.headline}
            </a>
          </div>
        ))}
      </div>
    </div>
  );
}

type FeedItem = LegislationEvent | ExecutiveEvent | TariffDeadline;

interface FeedColumnProps {
  title: string;
  icon: LucideIcon;
  items: FeedItem[];
  type: "legislation" | "executive" | "deadline";
}

function FeedColumn({ title, icon: Icon, items, type }: FeedColumnProps) {
  return (
    <div className="col-span-1 bg-[#0a0a0a] border border-white/5 rounded-2xl overflow-hidden flex flex-col h-[600px]">
      <div className="p-4 border-b border-white/5 bg-[#0a0a0a]/80 backdrop-blur sticky top-0 z-10">
        <h3 className="font-semibold text-slate-200 flex items-center gap-2">
          <Icon className="w-4 h-4 text-slate-400" />
          {title}
        </h3>
      </div>
      <div className="overflow-y-auto p-4 space-y-4 flex-1 custom-scrollbar">
        {items.map((item) => {
          // Helper to safely extract common fields
          const titleText =
            "title" in item
              ? item.title
              : "headline" in item
                ? item.headline
                : item.deadline_name;
          const dateText =
            "event_date" in item ? item.event_date : item.deadline_date;
          const tags = "specialist_tags" in item ? (item.specialist_tags ?? []) : [];
          const url = "url" in item ? item.url : undefined;
          const docType =
            "document_type" in item ? item.document_type : undefined;
          const daysToExpiry =
            "days_to_expiry" in item ? item.days_to_expiry : undefined;

          return (
            <div
              key={item.id}
              className="group p-4 bg-slate-950 border border-white/5 rounded-xl hover:border-white/20 transition-all"
            >
              <div className="flex justify-between items-start mb-2">
                <span
                  className={`text-[10px] font-bold px-2 py-0.5 rounded-full uppercase tracking-wider bg-slate-700 text-slate-300`}
                >
                  {type === "deadline"
                    ? `${daysToExpiry} DAYS`
                    : docType || "RULE"}
                </span>
                <span className="text-xs text-slate-500 font-mono">
                  {dateText}
                </span>
              </div>

              <h4 className="text-sm font-medium text-slate-200 leading-snug mb-2 group-hover:text-white">
                {titleText}
              </h4>

              {type === "deadline" && daysToExpiry !== undefined && (
                <div className="w-full bg-slate-900 h-1.5 rounded-full mt-2 overflow-hidden">
                  {(() => {
                    const urgencyScore = Math.max(
                      0,
                      Math.min(100, 100 - (daysToExpiry / 365) * 100),
                    );
                    const c = getScoreColor(urgencyScore);
                    return (
                      <div
                        className="h-full rounded-full transition-all duration-700 ease-out"
                        style={{
                          width: `${Math.max(5, urgencyScore)}%`,
                          backgroundColor: c.stroke,
                          boxShadow: `0 0 8px ${c.glow}`,
                        }}
                      />
                    );
                  })()}
                </div>
              )}

              {/* Tags for legislation/executive */}
              {tags.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-3">
                  {tags.slice(0, 3).map((tag: string) => (
                    <span
                      key={tag}
                      className="text-[10px] bg-slate-900 text-slate-500 px-1.5 py-0.5 rounded border border-slate-800"
                    >
                      #{tag}
                    </span>
                  ))}
                </div>
              )}

              {url && (
                <a
                  href={url}
                  target="_blank"
                  className="flex items-center gap-1 text-xs text-cyan-400 mt-3 opacity-0 group-hover:opacity-100 transition-opacity"
                >
                  Source <ExternalLink className="w-3 h-3" />
                </a>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ============================================================================
// MAIN PAGE
// ============================================================================

export default async function PolicyPage() {
  // Fetch everything in parallel, but never let one failed query blank the page.
  const withFallback = async <T,>(
    label: string,
    task: () => Promise<T>,
    fallback: T,
  ): Promise<T> => {
    try {
      return await task();
    } catch (error) {
      console.error(`[PolicyPage] ${label} failed:`, error);
      return fallback;
    }
  };

  const defaultRegime: RegimeState = {
    score: 35,
    label: "Background Noise",
    components: {
      tpu: 100,
      emv: 0,
      news_velocity: 0,
      legis_velocity: 0,
    },
  };

  // Fetch everything in parallel (including news)
  const [
    regime,
    legislation,
    executive,
    deadlines,
    agencies,
    trumpMetrics,
    shockwaves,
    summaryCounts,
    policyNews,
  ] = await Promise.all([
    withFallback("getRegimeStatus", () => PolicyService.getRegimeStatus(), defaultRegime),
    withFallback("getLegislationEvents", () => PolicyService.getLegislationEvents(30), []),
    withFallback("getExecutiveEvents", () => PolicyService.getExecutiveEvents(30), []),
    withFallback("getTariffDeadlines", () => PolicyService.getTariffDeadlines(), []),
    withFallback("getAgencyHeatmap", () => PolicyService.getAgencyHeatmap(), []),
    withFallback("getTrumpEffectMetrics", () => PolicyService.getTrumpEffectMetrics(), []),
    withFallback("getShockwaveEvents", () => PolicyService.getShockwaveEvents(), []),
    withFallback("getSummaryCounts", () => PolicyService.getSummaryCounts(), { uniqueAgencies: 0, activeEvents: 0 }),
    withFallback("getPolicyNews", () => PolicyService.getPolicyNews(50, 7), [] as PolicyNewsItem[]),
  ]);

  // Extract metric for Bureaucracy Velocity
  const currentMetric = trumpMetrics[0];
  const prevMetric = trumpMetrics[1];

  // Calculate trend if we have previous data (avoid division by zero)
  const velocityTrend =
    currentMetric?.velocity && prevMetric?.velocity && prevMetric.velocity > 0
      ? Math.round(
          ((currentMetric.velocity - prevMetric.velocity) /
            prevMetric.velocity) *
            100,
        )
      : null;

  // News pulse: how active is the news feed?
  const now = new Date();
  const newsLast24h = policyNews.filter((n) => {
    const d = new Date(n.published_at || n.event_date);
    return (now.getTime() - d.getTime()) / (1000 * 60 * 60) <= 24;
  }).length;
  const newsLast48h = policyNews.filter((n) => {
    const d = new Date(n.published_at || n.event_date);
    return (now.getTime() - d.getTime()) / (1000 * 60 * 60) <= 48;
  }).length;
  const newsBaseline = policyNews.length > 0 ? policyNews.length / 7 : 0;
  const newsVelocityRatio = newsBaseline > 0 ? newsLast24h / newsBaseline : 0;

  // Prepare AI briefing props (serialized for client component)
  const briefingProps = {
    regime: {
      score: regime.score,
      label: regime.label,
      headline: regime.headline,
      tpu: regime.components.tpu,
      emv: regime.components.emv,
    },
    metrics: {
      velocity: currentMetric?.velocity ?? null,
      deadlinesActive: deadlines.filter((d) => d.is_active).length,
      shockwaveCount: shockwaves.filter((s) => Math.abs(s.price_return_1d || 0) > 0.01).length,
      agencyCount: summaryCounts.uniqueAgencies,
      activeEvents: summaryCounts.activeEvents,
    },
    topAgencies: agencies.slice(0, 5).map((a) => ({ agency: a.agency, count: a.count })),
    recentLegislation: legislation.slice(0, 5).map((l) => ({
      title: l.title || "Untitled",
      agency: l.agency || "Unknown",
      date: l.event_date,
    })),
    recentExecutive: executive.slice(0, 5).map((e) => ({
      headline: e.headline,
      date: e.event_date,
      impact: e.price_return_1d ?? null,
    })),
    recentNews: policyNews.slice(0, 10).map((n) => ({
      headline: n.headline,
      source: n.source || "unknown",
      date: n.event_date,
      tags: n.specialist_tags,
    })),
  };

  return (
    <div className="min-h-screen bg-[#0a0a0a] text-slate-200 pt-36 pb-20">
      <div className="max-w-[1600px] mx-auto px-4 sm:px-6 lg:px-8 space-y-8">
        {/* HEADER */}
        <header className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
          <div>
            <div className="flex items-center gap-3 mb-1">
              <Gavel className="w-8 h-8" />
              <h1 className="text-5xl font-bold tracking-tight text-white">
                Policy Intelligence
              </h1>
            </div>
            <p className="text-slate-400 text-sm font-mono">
              Monitoring {summaryCounts.uniqueAgencies} agencies and{" "}
              {summaryCounts.activeEvents} active regulatory events
            </p>
          </div>

          <RegimeBadge regime={regime} />
        </header>

        {/* AI BRIEFING — Claude-powered policy analysis */}
        <PolicyAiBriefing {...briefingProps} />

        {/* EVENT PULSE INDICATOR — shows when news velocity is elevated */}
        {newsVelocityRatio >= 1.5 && (
          <div className={`p-3 rounded-xl border flex items-center gap-3 ${
            newsVelocityRatio > 3 ? "bg-red-500/5 border-red-500/20" :
            newsVelocityRatio > 2 ? "bg-amber-500/5 border-amber-500/20" :
            "bg-blue-500/5 border-blue-500/20"
          }`}>
            <div className={`relative flex h-2.5 w-2.5 ${
              newsVelocityRatio > 3 ? "text-red-400" :
              newsVelocityRatio > 2 ? "text-amber-400" :
              "text-blue-400"
            }`}>
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-current opacity-75" />
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-current" />
            </div>
            <Radio size={12} className={
              newsVelocityRatio > 3 ? "text-red-400" :
              newsVelocityRatio > 2 ? "text-amber-400" :
              "text-blue-400"
            } />
            <span className={`text-xs font-bold uppercase tracking-wider ${
              newsVelocityRatio > 3 ? "text-red-400" :
              newsVelocityRatio > 2 ? "text-amber-400" :
              "text-blue-400"
            }`}>
              News Pulse: {newsVelocityRatio.toFixed(1)}x normal
            </span>
            <span className="text-xs text-slate-500">
              {newsLast24h} articles in 24h · {newsLast48h} in 48h
            </span>
          </div>
        )}

        {/* METRICS ROW */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
          <MetricCard
            title="Bureaucracy Velocity"
            value={
              currentMetric?.velocity != null
                ? currentMetric.velocity.toFixed(1)
                : regime.components.legis_velocity > 0
                  ? `${(regime.components.legis_velocity / 2).toFixed(0)}/wk`
                  : "N/A"
            }
            subtext={
              currentMetric?.neural_signal != null
                ? `Signal: ${currentMetric.neural_signal.toFixed(3)} | Conf: ${((currentMetric.neural_confidence ?? 0) * 100).toFixed(0)}%`
                : currentMetric?.velocity != null
                  ? `Actions/Week · as of ${currentMetric.date}`
                  : regime.components.legis_velocity > 0
                    ? `${regime.components.legis_velocity} filings/14d from Federal Register`
                    : "No specialist data"
            }
            icon={TrendingUp}
            trend={velocityTrend}
          />
          {(() => {
            const upcoming = deadlines.filter((d) => d.days_to_expiry >= 0);
            const expired = deadlines.filter((d) => d.days_to_expiry < 0);
            const next = upcoming[0]; // already sorted ASC by days_to_expiry
            return (
              <MetricCard
                title="Active Deadlines"
                value={upcoming.length > 0 ? upcoming.length : `${deadlines.length} expired`}
                subtext={
                  next
                    ? `Next: ${next.deadline_name.slice(0, 28)} (${next.days_to_expiry}d)`
                    : expired.length > 0
                      ? `All ${expired.length} deadlines have passed — needs refresh`
                      : "No deadlines tracked"
                }
                icon={CalendarClock}
              />
            );
          })()}
          <MetricCard
            title="Trade Uncertainty"
            value={Math.round(regime.components.tpu)}
            subtext={
              regime.freshness?.tpu_date
                ? `FRED EPU Index · as of ${regime.freshness.tpu_date}`
                : "FRED EPU Index"
            }
            icon={ShieldAlert}
          />
          <MetricCard
            title="News Velocity"
            value={regime.components.news_velocity}
            subtext={`Policy-relevant articles (7d) · ${policyNews.length} total`}
            icon={Newspaper}
          />
          <MetricCard
            title="Market Impact"
            value={`${shockwaves.filter((s) => Math.abs(s.price_return_1d || 0) > 0.01).length}`}
            subtext={`of ${shockwaves.length} exec actions moved ZL >1% (90d)`}
            icon={Activity}
          />
        </div>

        {/* ANALYTICS ROW */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 h-[400px]">
          <div className="lg:col-span-2 h-full">
            <AgencyHeatmap agencies={agencies} />
          </div>
          <div className="lg:col-span-1 h-full">
            <ShockwaveList events={shockwaves} />
          </div>
        </div>

        {/* NEWS INTELLIGENCE + FEED COLUMNS */}
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          {/* News Intelligence Feed — Google News + ProFarmer */}
          <div className="lg:col-span-1">
            <PolicyNewsFeed articles={policyNews} />
          </div>

          {/* Live Policy Feeds */}
          <div className="lg:col-span-3">
            <h2 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
              <FileSignature className="w-5 h-5" />
              Live Policy Feeds
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <FeedColumn
                title="Federal Register"
                icon={Building2}
                items={legislation}
                type="legislation"
              />
              <FeedColumn
                title="Executive Actions"
                icon={Siren}
                items={executive}
                type="executive"
              />
              <FeedColumn
                title="Tariff Deadlines"
                icon={CalendarClock}
                items={deadlines}
                type="deadline"
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
