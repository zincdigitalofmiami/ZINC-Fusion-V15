import { NextResponse } from "next/server";
import { query } from "@/lib/db";
import { scoreZlSentiment } from "@/lib/sentiment-scorer";

export const dynamic = "force-dynamic";

interface TagRow {
  tag: string;
  headline: string | null;
  summary: string | null;
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
        SELECT unnest(specialist_tags) AS tag, headline, summary
        FROM alt.profarmer_news_event
        WHERE event_date >= NOW() - INTERVAL '30 days'
          AND specialist_tags IS NOT NULL

        UNION ALL

        -- Policy
        SELECT unnest(specialist_tags), headline, NULL
        FROM alt.policy_news_event
        WHERE event_date >= NOW() - INTERVAL '30 days'
          AND specialist_tags IS NOT NULL

        UNION ALL

        -- Executive actions
        SELECT unnest(specialist_tags), headline, NULL
        FROM alt.executive_actions_event
        WHERE event_date >= NOW() - INTERVAL '30 days'
          AND specialist_tags IS NOT NULL

        UNION ALL

        -- Econ news
        SELECT unnest(specialist_tags), headline, summary
        FROM alt.econ_news_event
        WHERE event_date >= NOW() - INTERVAL '30 days'
          AND specialist_tags IS NOT NULL

        UNION ALL

        -- News events
        SELECT unnest(specialist_tags), headline, NULL
        FROM econ.news_event
        WHERE event_date >= NOW() - INTERVAL '30 days'
          AND specialist_tags IS NOT NULL
      )
      SELECT tag, headline, summary
      FROM all_tags
      WHERE tag IS NOT NULL AND LENGTH(TRIM(tag)) > 0
    `);

    // Score and aggregate by tag
    const tagMap = new Map<
      string,
      { cnt: number; bullish: number; bearish: number; neutral: number }
    >();

    for (const r of rows) {
      const { sentiment } = scoreZlSentiment(r.headline, r.summary);
      const entry = tagMap.get(r.tag) || {
        cnt: 0,
        bullish: 0,
        bearish: 0,
        neutral: 0,
      };
      entry.cnt++;
      entry[sentiment]++;
      tagMap.set(r.tag, entry);
    }

    // Sort by count descending, take top 25
    const sorted = [...tagMap.entries()]
      .sort((a, b) => b[1].cnt - a[1].cnt)
      .slice(0, 25);

    // Convert to bubble nodes
    const maxCount = Math.max(...sorted.map(([, v]) => v.cnt), 1);
    const topics = sorted.map(([tag, stats]) => {
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
