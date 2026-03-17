import { NextResponse } from "next/server";
import { query } from "@/lib/db";
import {
  resolveZlSentimentForAggregation,
  summarizeSentiments,
} from "@/lib/sentiment-news";
import type { Sentiment } from "@/lib/sentiment-scorer";

export const dynamic = "force-dynamic";

interface NewsRow {
  id: number;
  event_date: string;
  headline: string;
  summary: string | null;
  content: string | null;
  source: string | null;
  zl_sentiment: string | null;
  specialist_tags: string[] | null;
  table_source: string;
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

function laneSlugFromSource(source: string | null): string | null {
  if (!source) return null;
  if (!source.startsWith("google_news/")) return null;

  const parts = source.split("/");
  if (parts.length < 3) return null;
  const lane = parts[1] || null;
  if (!lane || !GOOGLE_NEWS_LANE_SLUGS.has(lane)) return null;
  return lane;
}

function laneSlugsFromTags(tags: string[] | null | undefined): string[] {
  if (!tags || tags.length === 0) return [];
  const seen = new Set<string>();
  const slugs: string[] = [];
  for (const tag of tags) {
    if (!tag.startsWith("lane_")) continue;
    const lane = tag.slice(5);
    if (!GOOGLE_NEWS_LANE_SLUGS.has(lane) || seen.has(lane)) continue;
    seen.add(lane);
    slugs.push(lane);
  }
  return slugs;
}

export function laneLabelsFromRow(
  source: string | null,
  specialistTags: string[] | null | undefined,
): string[] {
  const labels: string[] = [];
  const seen = new Set<string>();

  for (const lane of laneSlugsFromTags(specialistTags)) {
    const label = laneLabelFromSlug(lane);
    if (label && !seen.has(label)) {
      labels.push(label);
      seen.add(label);
    }
  }

  const sourceLane = laneSlugFromSource(source);
  if (sourceLane) {
    const label = laneLabelFromSlug(sourceLane);
    if (label && !seen.has(label)) {
      labels.push(label);
      seen.add(label);
    }
  }

  return labels;
}

function laneLabelFromSlug(slug: string | null): string | null {
  if (!slug) return null;
  return slug
    .split("_")
    .filter((part) => part.length > 0)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function buildSentimentNewsPayload(rows: readonly NewsRow[]) {
  const countableSentiments: Sentiment[] = [];

  const headlines = rows.map((row) => {
    const resolved = resolveZlSentimentForAggregation(
      row.zl_sentiment,
      row.headline,
      row.summary || row.content,
      row.source,
      row.specialist_tags,
    );
    if (resolved.includeInCounts) {
      countableSentiments.push(resolved.sentiment);
    }

    const laneLabels = laneLabelsFromRow(row.source, row.specialist_tags);
    return {
      id: `${row.table_source}-${row.id}`,
      event_date: row.event_date,
      headline: row.headline,
      summary: row.summary || row.content || null,
      source: row.source || row.table_source,
      lane: laneLabels[0] ?? null,
      lanes: laneLabels,
      sentiment: resolved.sentiment,
      tags: (row.specialist_tags || []).slice(0, 4),
    };
  });

  return {
    headlines,
    stats: summarizeSentiments(countableSentiments),
  };
}

/**
 * GET /api/sentiment/news
 * Aggregates recent headlines across all news tables (alt.profarmer_news_event,
 * alt.policy_news_event, alt.executive_actions_event, alt.econ_news_event, econ.news_event)
 * and returns them sorted by date descending.
 */
export async function GET() {
  try {
    const rows = await query<NewsRow>(`
      WITH combined AS (
        -- ProFarmer (no zl_sentiment column — derive from specialist_tags)
        SELECT
          id,
          event_date::text AS event_date,
          headline,
          summary,
          LEFT(content, 300) AS content,
          'ProFarmer' AS source,
          NULL AS zl_sentiment,
          specialist_tags,
          'profarmer' AS table_source
        FROM alt.profarmer_news_event
        WHERE event_date >= NOW() - INTERVAL '30 days'

        UNION ALL

        -- Federal Register legislation (2,900+ rows, actively ingested)
        SELECT
          id,
          event_date::text,
          title AS headline,
          CONCAT(document_type, ' — ', agency) AS summary,
          NULL AS content,
          COALESCE(source, 'Federal Register') AS source,
          NULL AS zl_sentiment,
          specialist_tags,
          'legislation' AS table_source
        FROM alt.legislation_1d
        WHERE event_date >= NOW() - INTERVAL '30 days'

        UNION ALL

        -- Policy news
        SELECT
          id,
          event_date::text,
          headline,
          NULL AS summary,
          LEFT(content, 300),
          source,
          zl_sentiment,
          specialist_tags,
          'policy' AS table_source
        FROM alt.policy_news_event
        WHERE event_date >= NOW() - INTERVAL '30 days'

        UNION ALL

        -- Executive actions
        SELECT
          id,
          event_date::text,
          headline,
          NULL AS summary,
          LEFT(content, 300),
          source,
          zl_sentiment,
          specialist_tags,
          'executive' AS table_source
        FROM alt.executive_actions_event
        WHERE event_date >= NOW() - INTERVAL '30 days'

        UNION ALL

        -- Econ news
        SELECT
          id,
          event_date::text,
          headline,
          summary,
          LEFT(content, 300),
          source,
          NULL AS zl_sentiment,
          specialist_tags,
          'econ' AS table_source
        FROM alt.econ_news_event
        WHERE event_date >= NOW() - INTERVAL '30 days'

        UNION ALL

        -- News events
        SELECT
          id,
          event_date::text,
          headline,
          NULL AS summary,
          LEFT(content, 300),
          source,
          zl_sentiment,
          specialist_tags,
          'news_event' AS table_source
        FROM econ.news_event
        WHERE event_date >= NOW() - INTERVAL '30 days'
      )
      SELECT *
      FROM combined
      ORDER BY event_date DESC
      LIMIT 50
    `);

    const { headlines, stats } = buildSentimentNewsPayload(rows);

    return NextResponse.json(
      {
        headlines,
        stats,
      },
      {
        headers: {
          "Cache-Control": "s-maxage=3600, stale-while-revalidate=3600",
        },
      },
    );
  } catch (error) {
    console.error("[/api/sentiment/news] Error:", error);
    return NextResponse.json(
      { error: "Failed to fetch news", details: String(error) },
      { status: 500, headers: { "Cache-Control": "no-store" } },
    );
  }
}
