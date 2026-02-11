import { NextResponse } from "next/server";
import { query } from "@/lib/db";
import { classifySentiment } from "@/lib/sentiment-scorer";

export const dynamic = "force-dynamic";

interface NewsRow {
  id: number;
  event_date: string;
  headline: string;
  summary: string | null;
  content: string | null;
  source: string | null;
  zl_sentiment: string | null;
  specialist_tags: string[];
  table_source: string;
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

    // Compute sentiment classification — keyword-based when zl_sentiment is NULL
    const headlines = rows.map((r) => {
      const sentiment = classifySentiment(
        r.headline,
        r.summary || r.content,
      );
      return {
        id: `${r.table_source}-${r.id}`,
        event_date: r.event_date,
        headline: r.headline,
        summary: r.summary || r.content || null,
        source: r.source || r.table_source,
        sentiment,
        tags: (r.specialist_tags || []).slice(0, 4),
      };
    });

    // Summary stats
    const bullish = headlines.filter((h) => h.sentiment === "bullish").length;
    const bearish = headlines.filter((h) => h.sentiment === "bearish").length;
    const total = headlines.length;

    return NextResponse.json(
      {
        headlines,
        stats: { total, bullish, bearish, neutral: total - bullish - bearish },
      },
      {
        headers: {
          "Cache-Control": "s-maxage=300, stale-while-revalidate=600",
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
