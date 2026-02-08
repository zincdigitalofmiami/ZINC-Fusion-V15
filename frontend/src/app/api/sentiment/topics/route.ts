import { NextResponse } from "next/server";
import { query } from "@/lib/db";

export const dynamic = "force-dynamic";

interface TagRow {
  tag: string;
  cnt: number;
  bullish: number;
  bearish: number;
}

/**
 * GET /api/sentiment/topics
 * Aggregates specialist_tags across all news tables from the last 14 days
 * to build topic clusters for the bubble visualization.
 * Returns tag name, mention count, and net sentiment.
 */
export async function GET() {
  try {
    const rows = await query<TagRow>(`
      WITH all_tags AS (
        -- ProFarmer
        SELECT unnest(specialist_tags) AS tag, NULL AS zl_sentiment
        FROM alt.profarmer_news
        WHERE event_date >= NOW() - INTERVAL '14 days'
          AND specialist_tags IS NOT NULL

        UNION ALL

        -- Policy
        SELECT unnest(specialist_tags), zl_sentiment
        FROM alt.policy_news
        WHERE event_date >= NOW() - INTERVAL '14 days'
          AND specialist_tags IS NOT NULL

        UNION ALL

        -- Executive actions
        SELECT unnest(specialist_tags), zl_sentiment
        FROM alt.executive_actions
        WHERE event_date >= NOW() - INTERVAL '14 days'
          AND specialist_tags IS NOT NULL

        UNION ALL

        -- Econ news
        SELECT unnest(specialist_tags), NULL
        FROM alt.econ_news
        WHERE event_date >= NOW() - INTERVAL '14 days'
          AND specialist_tags IS NOT NULL

        UNION ALL

        -- News events
        SELECT unnest(specialist_tags), zl_sentiment
        FROM econ.news_event
        WHERE event_date >= NOW() - INTERVAL '14 days'
          AND specialist_tags IS NOT NULL
      )
      SELECT
        tag,
        COUNT(*)::int AS cnt,
        COUNT(*) FILTER (WHERE LOWER(zl_sentiment) LIKE '%bull%' OR LOWER(zl_sentiment) LIKE '%positive%')::int AS bullish,
        COUNT(*) FILTER (WHERE LOWER(zl_sentiment) LIKE '%bear%' OR LOWER(zl_sentiment) LIKE '%negative%')::int AS bearish
      FROM all_tags
      WHERE tag IS NOT NULL AND LENGTH(TRIM(tag)) > 0
      GROUP BY tag
      ORDER BY cnt DESC
      LIMIT 25
    `);

    // Convert to bubble nodes: volume proportional to mention count,
    // sentiment = (bullish - bearish) / total scaled to -1..1
    const maxCount = Math.max(...rows.map((r) => r.cnt), 1);
    const topics = rows.map((r) => {
      const total = r.bullish + r.bearish || 1;
      const sentiment = (r.bullish - r.bearish) / total;
      return {
        id: r.tag.toLowerCase().replace(/\s+/g, "-"),
        topic: r.tag,
        volume: Math.max(30, Math.round((r.cnt / maxCount) * 100)),
        sentiment: Math.round(sentiment * 100) / 100,
        mentions: r.cnt,
      };
    });

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
