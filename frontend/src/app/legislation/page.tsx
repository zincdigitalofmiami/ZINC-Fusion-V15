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
  Siren,
  TrendingUp,
  Activity,
  Building2,
  CalendarClock,
  ExternalLink,
  ShieldAlert,
  type LucideIcon,
} from "lucide-react";

// ============================================================================
// UI COMPONENTS
// ============================================================================

function RegimeBadge({ regime }: { regime: RegimeState }) {
  const colors = {
    Minimal: "bg-slate-800 text-slate-400 border-slate-700",
    "Background Noise": "bg-blue-950 text-blue-400 border-blue-800",
    Elevated: "bg-yellow-950 text-yellow-400 border-yellow-800",
    "Retaliation Risk": "bg-orange-950 text-orange-400 border-orange-800",
    "Active War": "bg-red-950 text-red-500 border-red-800 animate-pulse",
  };
  const colorClass = colors[regime.label] || colors["Minimal"];

  return (
    <div
      className={`flex flex-col items-end px-6 py-3 rounded-lg border ${colorClass}`}
    >
      <div className="text-xs uppercase tracking-widest opacity-80 mb-1">
        Threat Level
      </div>
      <div className="text-2xl font-black tracking-tight">
        {regime.label.toUpperCase()}
      </div>
      <div className="text-xs font-mono mt-1 opacity-70">
        SCORE: {Math.round(regime.score)}/100 | TPU:{" "}
        {Math.round(regime.components.tpu)}
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
    <div className="bg-slate-900/50 border border-slate-800 rounded-xl p-5 hover:border-slate-700 transition-colors">
      <div className="flex justify-between items-start mb-2">
        <div className="p-2 bg-slate-800 rounded-lg text-slate-400">
          <Icon className="w-5 h-5" />
        </div>
        {trend && (
          <span
            className={`text-xs font-medium px-2 py-1 rounded-full ${trend > 0 ? "bg-red-950 text-red-400" : "bg-green-950 text-green-400"}`}
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
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 h-full">
      <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
        <Building2 className="w-5 h-5 text-indigo-400" />
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
                className="h-full bg-indigo-500/80 rounded-full group-hover:bg-indigo-400 transition-all"
                style={{ width: `${(agency.count / maxCount) * 100}%` }}
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
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 h-full">
      <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
        <Activity className="w-5 h-5 text-rose-400" />
        Shockwave Events
      </h3>
      <div className="space-y-4 max-h-[300px] overflow-y-auto pr-2 custom-scrollbar">
        {events.slice(0, 6).map((evt) => (
          <div
            key={evt.id}
            className="relative pl-4 border-l-2 border-slate-800 hover:border-rose-500/50 transition-colors"
          >
            <div className="absolute -left-[5px] top-1.5 w-2 h-2 rounded-full bg-slate-700 ring-2 ring-slate-900" />
            <div className="flex justify-between items-start">
              <span className="text-xs text-slate-500 font-mono">
                {evt.event_date}
              </span>
              {Math.abs(evt.price_return_1d || 0) > 0.01 && (
                <span className="text-xs bg-rose-950 text-rose-400 px-1.5 py-0.5 rounded ml-2">
                  Impact: {(evt.price_return_1d! * 100).toFixed(1)}%
                </span>
              )}
            </div>
            <a
              href={evt.url || "#"}
              target="_blank"
              className="block text-sm text-slate-200 mt-1 hover:text-rose-400 transition-colors line-clamp-2"
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
    <div className="col-span-1 bg-slate-900/50 border border-slate-800 rounded-xl overflow-hidden flex flex-col h-[600px]">
      <div className="p-4 border-b border-slate-800 bg-slate-900/80 backdrop-blur sticky top-0 z-10">
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
          const tags = "specialist_tags" in item ? item.specialist_tags : [];
          const url = "url" in item ? item.url : undefined;
          const docType =
            "document_type" in item ? item.document_type : undefined;
          const daysToExpiry =
            "days_to_expiry" in item ? item.days_to_expiry : undefined;

          return (
            <div
              key={item.id}
              className="group p-4 bg-slate-950 border border-slate-800 rounded-lg hover:border-slate-600 transition-all"
            >
              <div className="flex justify-between items-start mb-2">
                <span
                  className={`text-[10px] font-bold px-2 py-0.5 rounded-full uppercase tracking-wider
                  ${
                    type === "deadline"
                      ? "bg-amber-950 text-amber-500"
                      : type === "executive"
                        ? "bg-purple-950 text-purple-400"
                        : "bg-emerald-950 text-emerald-400"
                  }`}
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
                  <div
                    className={`h-full rounded-full ${daysToExpiry < 30 ? "bg-amber-500" : "bg-slate-600"}`}
                    style={{
                      width: `${Math.max(5, 100 - (daysToExpiry / 365) * 100)}%`,
                    }}
                  />
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
                  className="flex items-center gap-1 text-xs text-blue-500 mt-3 opacity-0 group-hover:opacity-100 transition-opacity"
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
  // Fetch everything in parallel
  const [
    regime,
    legislation,
    executive,
    deadlines,
    agencies,
    trumpMetrics,
    shockwaves,
  ] = await Promise.all([
    PolicyService.getRegimeStatus(),
    PolicyService.getLegislationEvents(30),
    PolicyService.getExecutiveEvents(30),
    PolicyService.getTariffDeadlines(),
    PolicyService.getAgencyHeatmap(),
    PolicyService.getTrumpEffectMetrics(),
    PolicyService.getShockwaveEvents(),
  ]);

  // Extract metric for Bureaucracy Velocity
  const currentMetric = trumpMetrics[0] || { velocity: 0, score: 0 };
  const prevMetric = trumpMetrics[1] || { velocity: 0 };

  // Calculate trend if we have previous data (avoid division by zero)
  const velocityTrend =
    currentMetric.velocity && prevMetric.velocity && prevMetric.velocity > 0
      ? Math.round(
          ((currentMetric.velocity - prevMetric.velocity) /
            prevMetric.velocity) *
            100,
        )
      : null;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-200 pb-20">
      <div className="max-w-[1600px] mx-auto p-4 sm:p-6 lg:p-8 space-y-8">
        {/* HEADER */}
        <header className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
          <div>
            <div className="flex items-center gap-3 mb-1">
              <Gavel className="w-8 h-8 text-amber-500" />
              <h1 className="text-3xl font-bold tracking-tight text-white">
                Policy Intelligence
              </h1>
            </div>
            <p className="text-slate-400">
              Monitoring {agencies.length} agencies and{" "}
              {legislation.length + executive.length} active regulatory events
            </p>
          </div>

          <RegimeBadge regime={regime} />
        </header>

        {/* METRICS ROW */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <MetricCard
            title="Bureaucracy Velocity"
            value={currentMetric.velocity?.toFixed(1) || "0.0"}
            subtext="Actions per Week"
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
            subtext="Fred EPU Index"
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
            <FileSignature className="w-5 h-5 text-slate-400" />
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
