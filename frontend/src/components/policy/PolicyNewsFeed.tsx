import {
  Newspaper,
  ExternalLink,
  Rss,
} from "lucide-react";

// Specialist tag colors
const TAG_COLORS: Record<string, string> = {
  crush: "bg-amber-900/30 text-amber-400 border-amber-800/30",
  china: "bg-red-900/30 text-red-400 border-red-800/30",
  substitutes: "bg-purple-900/30 text-purple-400 border-purple-800/30",
  fx: "bg-blue-900/30 text-blue-400 border-blue-800/30",
  fed: "bg-emerald-900/30 text-emerald-400 border-emerald-800/30",
  tariff: "bg-orange-900/30 text-orange-400 border-orange-800/30",
  energy: "bg-yellow-900/30 text-yellow-400 border-yellow-800/30",
  biofuel: "bg-lime-900/30 text-lime-400 border-lime-800/30",
  palm: "bg-green-900/30 text-green-400 border-green-800/30",
  volatility: "bg-pink-900/30 text-pink-400 border-pink-800/30",
  trump_effect: "bg-rose-900/30 text-rose-400 border-rose-800/30",
};

function getTagColor(tag: string): string {
  return TAG_COLORS[tag] || "bg-slate-800 text-slate-400 border-slate-700";
}

function getSourceIcon(source: string): string {
  if (source.includes("google_news")) return "GN";
  if (source.includes("profarmer")) return "PF";
  if (source.includes("reuters")) return "RT";
  if (source.includes("bloomberg")) return "BB";
  return source.slice(0, 2).toUpperCase();
}

function getSourceColor(source: string): string {
  if (source.includes("google_news")) return "bg-blue-900/40 text-blue-300";
  if (source.includes("profarmer")) return "bg-green-900/40 text-green-300";
  return "bg-slate-800 text-slate-400";
}

function toTitleCaseFromSnake(text: string): string {
  return text
    .split("_")
    .filter((part) => part.length > 0)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

const GOOGLE_NEWS_LANE_SLUGS = new Set([
  "ice_immigration",
  "war_military",
  "soybean_oil",
  "soybean_agriculture",
  "trump_actions",
  "legislation",
  "biofuel",
]);

function parseGoogleNewsSource(
  source: string | null,
): { lane: string | null; publication: string | null } {
  if (!source || !source.startsWith("google_news/")) {
    return { lane: null, publication: source };
  }

  const parts = source.split("/");
  const laneSlug = parts[1] || null;
  const hasKnownLane = laneSlug ? GOOGLE_NEWS_LANE_SLUGS.has(laneSlug) : false;
  const lane = hasKnownLane && laneSlug ? toTitleCaseFromSnake(laneSlug) : null;
  const publicationRaw = (hasKnownLane ? parts.slice(2) : parts.slice(1)).join("/").trim();
  const publication = publicationRaw.length > 0 ? publicationRaw : "Google News";
  return { lane, publication };
}

function timeAgo(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffHours < 1) return "just now";
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays === 1) return "yesterday";
  return `${diffDays}d ago`;
}

interface PolicyNewsItem {
  id: number;
  event_date: string;
  headline: string;
  url: string | null;
  source: string | null;
  specialist_tags: string[];
  published_at: string | null;
}

interface PolicyNewsFeedProps {
  articles: PolicyNewsItem[];
}

export function PolicyNewsFeed({ articles }: PolicyNewsFeedProps) {
  if (articles.length === 0) {
    return (
      <div className="bg-[#0a0a0a] border border-white/5 rounded-2xl p-8 text-center">
        <Rss className="w-8 h-8 text-slate-600 mx-auto mb-2" />
        <p className="text-slate-500 text-sm">No recent lane-tagged news articles</p>
        <p className="text-slate-600 text-xs mt-1">
          Google News ingestion runs daily at 8 AM CT
        </p>
      </div>
    );
  }

  // Group by date
  const grouped = articles.reduce(
    (acc, article) => {
      const date = article.event_date;
      if (!acc[date]) acc[date] = [];
      acc[date].push(article);
      return acc;
    },
    {} as Record<string, PolicyNewsItem[]>,
  );

  return (
    <div className="bg-[#0a0a0a] border border-white/5 rounded-2xl overflow-hidden">
      <div className="p-4 md:p-6 border-b border-white/5 flex items-center justify-between">
        <h3 className="text-lg font-semibold text-white flex items-center gap-2">
          <Newspaper className="w-5 h-5" />
          Segmented Policy News Lanes
        </h3>
        <span className="text-xs font-mono text-slate-500">
          {articles.length} lane-tagged articles / 7 days
        </span>
      </div>

      <div className="max-h-[600px] overflow-y-auto custom-scrollbar">
        {Object.entries(grouped).map(([date, dayArticles]) => (
          <div key={date}>
            {/* Date divider */}
            <div className="sticky top-0 z-10 bg-[#0a0a0a]/95 backdrop-blur-sm px-4 py-2 border-b border-white/5">
              <span className="text-xs font-mono text-slate-500">{date}</span>
              <span className="text-xs text-slate-600 ml-2">
                ({dayArticles.length} articles)
              </span>
            </div>

            {/* Articles for this date */}
            <div className="divide-y divide-white/[0.03]">
              {dayArticles.map((article) => {
                const parsed = parseGoogleNewsSource(article.source);
                return (
                  <div
                    key={article.id}
                    className="group px-4 py-3 hover:bg-white/[0.02] transition-colors"
                  >
                    <div className="flex items-start gap-3">
                      {/* Source badge */}
                      <div
                        className={`flex-shrink-0 w-8 h-8 rounded-lg flex items-center justify-center text-[10px] font-bold ${getSourceColor(article.source || "")}`}
                      >
                        {getSourceIcon(article.source || "")}
                      </div>

                      <div className="flex-1 min-w-0">
                        {/* Headline */}
                        <div className="flex items-start justify-between gap-2">
                          <h4 className="text-sm text-slate-300 leading-snug group-hover:text-white transition-colors line-clamp-2">
                            {article.headline}
                          </h4>
                          {article.url && (
                            <a
                              href={article.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity p-1"
                            >
                              <ExternalLink className="w-3.5 h-3.5 text-cyan-400" />
                            </a>
                          )}
                        </div>

                        {/* Meta row: time + lane + source + tags */}
                        <div className="flex flex-wrap items-center gap-1.5 mt-1.5">
                          <span className="text-[10px] text-slate-500 font-mono">
                            {article.published_at
                              ? timeAgo(article.published_at)
                              : article.event_date}
                          </span>
                          {parsed.lane && (
                            <span className="text-[10px] px-1.5 py-0.5 rounded border border-cyan-500/20 bg-cyan-500/10 text-cyan-300">
                              {parsed.lane}
                            </span>
                          )}
                          {parsed.publication && (
                            <span className="text-[10px] text-slate-600">
                              via {parsed.publication}
                            </span>
                          )}
                          {article.specialist_tags.map((tag) => (
                            <span
                              key={tag}
                              className={`text-[9px] px-1.5 py-0.5 rounded border ${getTagColor(tag)}`}
                            >
                              {tag}
                            </span>
                          ))}
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
