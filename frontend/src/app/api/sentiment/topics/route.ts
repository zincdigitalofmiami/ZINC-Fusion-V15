import { NextResponse } from "next/server";
import { query } from "@/lib/db";
import { resolveZlSentimentForAggregation } from "@/lib/sentiment-news";

export const dynamic = "force-dynamic";

interface TagRow {
  tag: string;
  headline: string | null;
  summary: string | null;
  source: string | null;
  zl_sentiment: string | null;
  specialist_tags: string[] | null;
}

export function buildTopicsFromRows(rows: readonly TagRow[]) {
  // Score and aggregate by tag
  const tagMap = new Map<
    string,
    { cnt: number; bullish: number; bearish: number; neutral: number }
  >();

  for (const row of rows) {
    const resolved = resolveZlSentimentForAggregation(
      row.zl_sentiment,
      row.headline,
      row.summary,
      row.source,
      row.specialist_tags,
    );

    const entry = tagMap.get(row.tag) || {
      cnt: 0,
      bullish: 0,
      bearish: 0,
      neutral: 0,
    };

    // Keep mention volume semantics unchanged: every tag mention still counts.
    entry.cnt++;
    if (resolved.includeInCounts) {
      entry[resolved.sentiment]++;
    }
    tagMap.set(row.tag, entry);
  }

  // Sort by count descending, take top 25
  const sorted = [...tagMap.entries()]
    .sort((a, b) => b[1].cnt - a[1].cnt)
    .slice(0, 25);

  // Convert to bubble nodes
  const maxCount = Math.max(...sorted.map(([, value]) => value.cnt), 1);
  return sorted.map(([tag, stats]) => {
    const total = (stats.bullish + stats.bearish) || 1; // explicit: neutral excluded from ratio
    const sentiment = (stats.bullish - stats.bearish) / total;
    return {
      id: tag.toLowerCase().replace(/\s+/g, "-"),
      topic: tag,
      volume: Math.max(30, Math.round((stats.cnt / maxCount) * 100)),
      sentiment: Math.round(sentiment * 100) / 100,
      mentions: stats.cnt,
    };
  });
}

/**
 * GET /api/sentiment/topics
 * Aggregates specialist_tags across all news tables from the last 30 days
 * to build topic clusters for the bubble visualization.
 * Returns tag name, mention count, and net sentiment.
 * Sentiment is derived from keyword analysis of associated headlines.
 */
export async function GET() {
  try {
    // Fetch individual tag+headline rows so we can score sentiment per mention
    const rows = await query<TagRow>(`
      WITH all_tags AS (
        -- ProFarmer
        SELECT unnest(specialist_tags) AS tag,
               headline,
               summary,
               'ProFarmer'::text AS source,
               NULL::text AS zl_sentiment,
               COALESCE(specialist_tags, ARRAY[]::text[]) AS specialist_tags
        FROM alt.profarmer_news_event
        WHERE event_date >= NOW() - INTERVAL '30 days'
          AND specialist_tags IS NOT NULL

        UNION ALL

        -- Policy
        SELECT unnest(specialist_tags) AS tag,
               headline,
               NULL::text AS summary,
               source,
               zl_sentiment,
               COALESCE(specialist_tags, ARRAY[]::text[]) AS specialist_tags
        FROM alt.policy_news_event
        WHERE event_date >= NOW() - INTERVAL '30 days'
          AND specialist_tags IS NOT NULL

        UNION ALL

        -- Executive actions
        SELECT unnest(specialist_tags) AS tag,
               headline,
               NULL::text AS summary,
               source,
               zl_sentiment,
               COALESCE(specialist_tags, ARRAY[]::text[]) AS specialist_tags
        FROM alt.executive_actions_event
        WHERE event_date >= NOW() - INTERVAL '30 days'
          AND specialist_tags IS NOT NULL

        UNION ALL

        -- Econ news
        SELECT unnest(specialist_tags) AS tag,
               headline,
               summary,
               source,
               NULL::text AS zl_sentiment,
               COALESCE(specialist_tags, ARRAY[]::text[]) AS specialist_tags
        FROM alt.econ_news_event
        WHERE event_date >= NOW() - INTERVAL '30 days'
          AND specialist_tags IS NOT NULL

        UNION ALL

        -- News events
        SELECT unnest(specialist_tags) AS tag,
               headline,
               NULL::text AS summary,
               source,
               zl_sentiment,
               COALESCE(specialist_tags, ARRAY[]::text[]) AS specialist_tags
        FROM econ.news_event
        WHERE event_date >= NOW() - INTERVAL '30 days'
          AND specialist_tags IS NOT NULL
      )
      SELECT tag, headline, summary, source, zl_sentiment, specialist_tags
      FROM all_tags
      WHERE tag IS NOT NULL AND LENGTH(TRIM(tag)) > 0
    `);

    const topics = buildTopicsFromRows(rows);

    return NextResponse.json(
      { topics },
      {
        headers: {
          "Cache-Control": "s-maxage=300, stale-while-revalidate=600",
        },
      },
    );
  } catch (error) {
    console.error("[/api/sentiment/topics] Error:", error);
    return NextResponse.json(
      { error: "Failed to fetch topics", details: String(error) },
      { status: 500, headers: { "Cache-Control": "no-store" } },
    );
  }
}
