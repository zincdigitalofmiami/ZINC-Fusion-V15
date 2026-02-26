import { PolicyService } from "@/lib/services/policy-service";
import {
  RegimeState,
  LegislationEvent,
  ExecutiveEvent,
  TariffDeadline,
  AgencyActivity,
} from "@/components/policy/types";
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

  return (
    <div
      className="bg-[#0a0a0a] border rounded-2xl p-6 md:p-7 flex flex-col items-end"
      style={borderStyle}
    >
      <div className="text-xs uppercase tracking-widest text-slate-500 mb-2">
        Threat Level
      </div>

      <div className="w-full mb-3">
        <HorizontalMeter score={score} />
      </div>

      <div className={`text-lg font-medium ${getScoreTextColor(score)}`}>
        {regime.label}
      </div>

      {regime.headline && (
        <div className="text-xs text-slate-500 mt-1 italic max-w-[280px] text-right">
          {regime.headline}
        </div>
      )}

      <div className="text-xs font-mono mt-1 opacity-50">
        {regime.tariff_components ? (
          <>
            TPU: {regime.tariff_components.tpu_score} | EMV:{" "}
            {regime.tariff_components.emv_score} | LEGIS:{" "}
            {regime.tariff_components.legislation_count} | NEWS:{" "}
            {regime.tariff_components.soy_tariff_news_count}
          </>
        ) : (
          <>
            SCORE: {Math.round(regime.score)}/100 | TPU:{" "}
            {Math.round(regime.components.tpu)}
          </>
        )}
      </div>
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
    <div className="bg-[#0a0a0a] border border-white/5 rounded-2xl p-6 hover:border-white/20 transition-all duration-300">
      <div className="flex justify-between items-start mb-2">
        <div className="p-2 bg-slate-800 rounded-lg text-slate-400">
          <Icon className="w-5 h-5" />
        </div>
        {trend != null && (
          <span
            className={`text-xs font-medium px-2 py-1 rounded-full border ${
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
      <div className="text-2xl font-bold text-white mb-1">{value}</div>
      <div className="text-sm font-medium text-slate-400">{title}</div>
      {subtext && <div className="text-xs text-slate-500 mt-1">{subtext}</div>}
    </div>
  );
}

function AgencyHeatmap({ agencies }: { agencies: AgencyActivity[] }) {
  const maxCount = Math.max(...agencies.map((a) => a.count), 1);

  return (
    <div className="bg-[#0a0a0a] border border-white/5 rounded-2xl p-6 md:p-8 h-full">
      <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
        <Building2 className="w-5 h-5" />
        Enforcement Radar
      </h3>
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
        Shockwave Events
      </h3>
      <div className="space-y-4 max-h-[300px] overflow-y-auto pr-2 custom-scrollbar">
        {events.slice(0, 6).map((evt) => (
          <div
            key={evt.id}
            className="relative pl-4 border-l-2 border-slate-800 hover:border-slate-500 transition-colors"
          >
            <div className="absolute -left-[5px] top-1.5 w-2 h-2 rounded-full bg-slate-700 ring-2 ring-slate-900" />
            <div className="flex justify-between items-start">
              <span className="text-xs text-slate-500 font-mono">
                {evt.event_date}
              </span>
              {Math.abs(evt.price_return_1d || 0) > 0.01 && (
                <span className="text-xs bg-slate-700 text-slate-300 px-1.5 py-0.5 rounded ml-2">
                  Impact: {(evt.price_return_1d! * 100).toFixed(1)}%
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

  // Fetch everything in parallel
  const [
    regime,
    legislation,
    executive,
    deadlines,
    agencies,
    trumpMetrics,
    shockwaves,
    summaryCounts,
  ] = await Promise.all([
    withFallback("getRegimeStatus", () => PolicyService.getRegimeStatus(), defaultRegime),
    withFallback("getLegislationEvents", () => PolicyService.getLegislationEvents(30), []),
    withFallback("getExecutiveEvents", () => PolicyService.getExecutiveEvents(30), []),
    withFallback("getTariffDeadlines", () => PolicyService.getTariffDeadlines(), []),
    withFallback("getAgencyHeatmap", () => PolicyService.getAgencyHeatmap(), []),
    withFallback("getTrumpEffectMetrics", () => PolicyService.getTrumpEffectMetrics(), []),
    withFallback("getShockwaveEvents", () => PolicyService.getShockwaveEvents(), []),
    withFallback("getSummaryCounts", () => PolicyService.getSummaryCounts(), { uniqueAgencies: 0, activeEvents: 0 }),
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

        {/* METRICS ROW */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <MetricCard
            title="Bureaucracy Velocity"
            value={currentMetric?.velocity?.toFixed(1) || "N/A"}
            subtext={
              currentMetric?.neural_signal != null
                ? `Signal: ${currentMetric.neural_signal.toFixed(3)} | Conf: ${((currentMetric.neural_confidence ?? 0) * 100).toFixed(0)}%`
                : currentMetric
                  ? "Actions per Week"
                  : "No Data"
            }
            icon={TrendingUp}
            trend={velocityTrend}
          />
          <MetricCard
            title="Active Deadlines"
            value={deadlines.filter((d) => d.is_active).length}
            subtext="Next 90 Days"
            icon={CalendarClock}
          />
          <MetricCard
            title="Trade Uncertainty"
            value={Math.round(regime.components.tpu)}
            subtext={
              currentMetric?.epu_7d != null
                ? `FRED EPU Index | 7d Avg: ${currentMetric.epu_7d.toFixed(0)}`
                : "FRED EPU Index"
            }
            icon={ShieldAlert}
          />
          <MetricCard
            title="Market Impact"
            value={`${shockwaves.filter((s) => Math.abs(s.price_return_1d || 0) > 0.01).length}`}
            subtext="High Volatility Events"
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

        {/* FEED COLUMNS */}
        <div>
          <h2 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
            <FileSignature className="w-5 h-5" />
            Live Policy Feeds
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
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
  );
}
