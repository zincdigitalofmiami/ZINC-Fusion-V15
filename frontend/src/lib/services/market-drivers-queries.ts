/**
 * Market Drivers Data Access Layer
 *
 * All 23 parallel DB queries for the market-drivers API endpoint,
 * plus data extraction, missing-data guards, and freshness computation.
 */

import { query } from "@/lib/db";
import type { MarketData } from "@/lib/ai-intelligence";

// =============================================================================
// TYPES
// =============================================================================

export interface MarketDriversRawData {
  // VIX
  vix: number | null;
  vixDate: string | null;
  vix3m: number | null;
  ovx: number | null;
  realizedVol: number | null;
  vixZlCorr: number | null;
  hedgeCount: number;
  volSignal: number | null;
  // Crush
  crush: number | null;
  crushDate: string | null;
  oilShare: number | null;
  oilShare5dAgo: number | null;
  crushSignal: number | null;
  crushNewsCount: number;
  soybeanMealNewsCount: number;
  cornNewsCount: number;
  // China
  cnyRate: number | null;
  cnyDate: string | null;
  cnyChange20d: number | null;
  hgChange20d: number;
  hgChange5d: number;
  bdiyChange20d: number | null;
  soyChinaNews: number;
  totalNews: number;
  chinaSignal: number | null;
  // Tariff
  tpu: number | null;
  tpuDate: string | null;
  emv: number | null;
  legislationCount: number;
  soyTariffNews: number;
  tariffSignal: number | null;
  // ZL Price
  zlPrice: number | null;
  zlChange5d: number | null;
  zlChange20d: number | null;
  // Energy (CL crude oil)
  clPrice: number | null;
  clChange5d: number | null;
  clChange20d: number | null;
  clDate: string | null;
  energyNewsCount: number;
  // News
  recentNews: string[];
}

// =============================================================================
// FETCH ALL DATA
// =============================================================================

export async function fetchMarketDriversData(): Promise<MarketDriversRawData> {
  const [
    vixRows,
    vix3mRows,
    ovxRows,
    realizedVolRows,
    vixZlCorrRows,
    hedgeNewsRows,
    crushRows,
    oilShare5dRows,
    crushNewsRows,
    soybeanMealNewsRows,
    cornNewsRows,
    cnyRows,
    cnyChangeRows,
    hgRows,
    bdiyRows,
    soyChinaNewsRows,
    totalNewsRows,
    tpuRows,
    legislationRows,
    soyTariffNewsRows,
    volSignalRows,
    crushSignalRows,
    chinaSignalRows,
    tariffSignalRows,
    zlPriceRows,
    clPriceRows,
    energyNewsRows,
    recentNewsRows,
  ] = await Promise.all([
    // === VIX STRESS DATA ===
    query<{ vix: number; event_date: string }>(`
      SELECT value::float8 as vix, event_date::text FROM econ.vol_indices_1d
      WHERE series_id = 'VIXCLS' AND value IS NOT NULL
      ORDER BY event_date DESC LIMIT 1
    `),
    query<{ vix3m: number }>(`
      SELECT value::float8 as vix3m FROM econ.vol_indices_1d
      WHERE series_id = 'VXVCLS' AND value IS NOT NULL
      ORDER BY event_date DESC LIMIT 1
    `),
    query<{ ovx: number }>(`
      SELECT value::float8 as ovx FROM econ.vol_indices_1d
      WHERE series_id = 'OVXCLS' AND value IS NOT NULL
      ORDER BY event_date DESC LIMIT 1
    `),
    // Realized ZL Volatility (63-day annualized)
    query<{ realized_vol: number }>(`
      WITH returns AS (
        SELECT (close - LAG(close) OVER (ORDER BY event_date)) /
               NULLIF(LAG(close) OVER (ORDER BY event_date), 0) as ret
        FROM analytics.price_1d
        ORDER BY event_date DESC LIMIT 63
      )
      SELECT STDDEV(ret) * SQRT(252) as realized_vol FROM returns WHERE ret IS NOT NULL
    `),
    // VIX-ZL Correlation (KEY SOY METRIC - 20-day rolling)
    query<{ vix_zl_corr: number }>(`
      WITH vix_changes AS (
        SELECT event_date, value - LAG(value) OVER (ORDER BY event_date) as vix_change
        FROM econ.vol_indices_1d WHERE series_id = 'VIXCLS'
        ORDER BY event_date DESC LIMIT 25
      ),
      zl_changes AS (
        SELECT event_date, (close - LAG(close) OVER (ORDER BY event_date)) /
               NULLIF(LAG(close) OVER (ORDER BY event_date), 0) as zl_ret
        FROM analytics.price_1d ORDER BY event_date DESC LIMIT 25
      )
      SELECT CORR(v.vix_change, z.zl_ret) as vix_zl_corr
      FROM vix_changes v JOIN zl_changes z ON v.event_date = z.event_date
      WHERE v.vix_change IS NOT NULL AND z.zl_ret IS NOT NULL
    `),
    // Hedge/volatility news signal (7 days) across policy/econ/alt sources
    query<{ count: number }>(`
      WITH candidate_news AS (
        SELECT headline, content, specialist_tags
        FROM alt.profarmer_news_event
        WHERE event_date >= CURRENT_DATE - INTERVAL '7 days'

        UNION ALL

        SELECT headline, content, specialist_tags
        FROM alt.policy_news_event
        WHERE event_date >= CURRENT_DATE - INTERVAL '7 days'

        UNION ALL

        SELECT headline, content, specialist_tags
        FROM alt.econ_news_event
        WHERE event_date >= CURRENT_DATE - INTERVAL '7 days'
      )
      SELECT COUNT(DISTINCT md5(COALESCE(headline, '') || '|' || COALESCE(content, '')))::int as count
      FROM candidate_news
      WHERE (
        content ILIKE '%hedge%' OR content ILIKE '%hedging%' OR content ILIKE '%volatility%'
        OR content ILIKE '%options%' OR content ILIKE '%protection%' OR content ILIKE '%risk management%'
        OR headline ILIKE '%volatility%' OR headline ILIKE '%risk-off%'
        OR specialist_tags && ARRAY['volatility']::text[]
      )
    `),

    // === CRUSH PRESSURE DATA ===
    query<{ crush: number; oil_share: number | null; trade_date: string }>(`
      SELECT board_crush::float8 as crush, oil_share::float8 as oil_share, trade_date::text
      FROM analytics.board_crush_1d WHERE board_crush IS NOT NULL
      ORDER BY trade_date DESC LIMIT 1
    `),
    // Oil Share 5 days ago (for trend)
    query<{ oil_share_5d: number }>(`
      SELECT oil_share::float8 as oil_share_5d FROM analytics.board_crush_1d
      WHERE oil_share IS NOT NULL ORDER BY trade_date DESC OFFSET 5 LIMIT 1
    `),

    // Crush-focused news (7 days) tied to ZL crush economics
    query<{ count: number }>(`
      WITH candidate_news AS (
        SELECT headline, content, NULL::text AS source, specialist_tags
        FROM alt.profarmer_news_event
        WHERE event_date >= CURRENT_DATE - INTERVAL '7 days'

        UNION ALL

        SELECT headline, content, source, specialist_tags
        FROM alt.policy_news_event
        WHERE event_date >= CURRENT_DATE - INTERVAL '7 days'

        UNION ALL

        SELECT headline, content, source, specialist_tags
        FROM alt.econ_news_event
        WHERE event_date >= CURRENT_DATE - INTERVAL '7 days'
      )
      SELECT COUNT(DISTINCT md5(COALESCE(headline, '') || '|' || COALESCE(content, '')))::int as count
      FROM candidate_news
      WHERE (
        headline ILIKE '%crush margin%' OR headline ILIKE '%crusher%' OR headline ILIKE '%soy crush%'
        OR headline ILIKE '%processing margin%' OR content ILIKE '%board crush%'
        OR content ILIKE '%soybean crush%' OR content ILIKE '%soy oil share%'
        OR specialist_tags && ARRAY['crush', 'lane_soybean_agriculture']::text[]
        OR source LIKE 'google_news/soybean_agriculture/%'
      )
    `),

    // Soybean meal news (7 days) tied to ZL spread/crush context
    query<{ count: number }>(`
      WITH candidate_news AS (
        SELECT headline, content, NULL::text AS source, specialist_tags
        FROM alt.profarmer_news_event
        WHERE event_date >= CURRENT_DATE - INTERVAL '7 days'

        UNION ALL

        SELECT headline, content, source, specialist_tags
        FROM alt.policy_news_event
        WHERE event_date >= CURRENT_DATE - INTERVAL '7 days'

        UNION ALL

        SELECT headline, content, source, specialist_tags
        FROM alt.econ_news_event
        WHERE event_date >= CURRENT_DATE - INTERVAL '7 days'
      )
      SELECT COUNT(DISTINCT md5(COALESCE(headline, '') || '|' || COALESCE(content, '')))::int as count
      FROM candidate_news
      WHERE (
        headline ILIKE '%soybean meal%' OR headline ILIKE '%soy meal%' OR headline ILIKE '%meal export%'
        OR content ILIKE '%soybean meal%' OR content ILIKE '%soy meal demand%'
        OR content ILIKE '%meal basis%' OR content ILIKE '%meal spread%'
        OR specialist_tags && ARRAY['crush', 'lane_soybean_agriculture']::text[]
        OR source LIKE 'google_news/soybean_agriculture/%'
      )
    `),

    // Corn news (7 days) tied to ZL/biofuel feedstock competition
    query<{ count: number }>(`
      WITH candidate_news AS (
        SELECT headline, content, NULL::text AS source, specialist_tags
        FROM alt.profarmer_news_event
        WHERE event_date >= CURRENT_DATE - INTERVAL '7 days'

        UNION ALL

        SELECT headline, content, source, specialist_tags
        FROM alt.policy_news_event
        WHERE event_date >= CURRENT_DATE - INTERVAL '7 days'

        UNION ALL

        SELECT headline, content, source, specialist_tags
        FROM alt.econ_news_event
        WHERE event_date >= CURRENT_DATE - INTERVAL '7 days'
      )
      SELECT COUNT(DISTINCT md5(COALESCE(headline, '') || '|' || COALESCE(content, '')))::int as count
      FROM candidate_news
      WHERE (
        headline ILIKE '%corn%' OR headline ILIKE '%maize%' OR headline ILIKE '%ethanol%'
        OR content ILIKE '%corn feedstock%' OR content ILIKE '%corn ethanol%'
        OR content ILIKE '%biofuel blend%' OR content ILIKE '%renewable fuel%'
        OR specialist_tags && ARRAY['biofuel', 'energy', 'lane_biofuel']::text[]
        OR source LIKE 'google_news/biofuel/%'
      )
    `),

    // === CHINA TENSION DATA ===
    query<{ rate: number; event_date: string }>(`
      SELECT rate::float8 as rate, event_date::text FROM mkt.fx_1d
      WHERE pair IN ('USD/CNY', 'USDCNY') AND rate IS NOT NULL
      ORDER BY event_date DESC LIMIT 1
    `),
    // CNY 20-day change
    query<{ rate_20d: number }>(`
      SELECT rate::float8 as rate_20d FROM mkt.fx_1d
      WHERE pair IN ('USD/CNY', 'USDCNY') AND rate IS NOT NULL
      ORDER BY event_date DESC OFFSET 20 LIMIT 1
    `),
    // HG Futures 20-day and 5-day change (China demand proxy)
    query<{ close: number; change_20d: number; change_5d: number }>(`
      WITH hg AS (
        SELECT close::float8 as close, ROW_NUMBER() OVER (ORDER BY event_date DESC) as rn
        FROM mkt.futures_1d
        WHERE symbol = 'HG' AND close IS NOT NULL
        LIMIT 21
      )
      SELECT
        (SELECT close FROM hg WHERE rn = 1)::float8 as close,
        CASE WHEN (SELECT close FROM hg WHERE rn = 21) > 0
             THEN ((SELECT close FROM hg WHERE rn = 1) - (SELECT close FROM hg WHERE rn = 21)) / (SELECT close FROM hg WHERE rn = 21)
             ELSE 0 END::float8 as change_20d,
        CASE WHEN (SELECT close FROM hg WHERE rn = 6) > 0
             THEN ((SELECT close FROM hg WHERE rn = 1) - (SELECT close FROM hg WHERE rn = 6)) / (SELECT close FROM hg WHERE rn = 6)
             ELSE 0 END::float8 as change_5d
    `),
    // BDIY 20-day change (shipping demand proxy)
    query<{ value: number; change_20d: number | null }>(`
      WITH bdiy AS (
        SELECT value::float8 as value, ROW_NUMBER() OVER (ORDER BY event_date DESC) as rn
        FROM econ.commodities_1d
        WHERE series_id = 'BDIY' AND value IS NOT NULL
        LIMIT 21
      )
      SELECT
        (SELECT value FROM bdiy WHERE rn = 1)::float8 as value,
        CASE WHEN (SELECT value FROM bdiy WHERE rn = 21) > 0
             THEN ((SELECT value FROM bdiy WHERE rn = 1) - (SELECT value FROM bdiy WHERE rn = 21)) / (SELECT value FROM bdiy WHERE rn = 21)
             ELSE NULL END::float8 as change_20d
    `),
    // China demand/news feed (7 days) — intentionally separated from tariff and energy feeds
    query<{ count: number }>(`
      WITH candidate_news AS (
        SELECT headline, content, NULL::text AS source, specialist_tags
        FROM alt.profarmer_news_event
        WHERE event_date >= CURRENT_DATE - INTERVAL '7 days'

        UNION ALL

        SELECT headline, content, source, specialist_tags
        FROM alt.policy_news_event
        WHERE event_date >= CURRENT_DATE - INTERVAL '7 days'

        UNION ALL

        SELECT headline, content, source, specialist_tags
        FROM alt.econ_news_event
        WHERE event_date >= CURRENT_DATE - INTERVAL '7 days'
      )
      SELECT COUNT(DISTINCT md5(COALESCE(headline, '') || '|' || COALESCE(content, '')))::int as count
      FROM candidate_news
      WHERE (
        ((headline ILIKE '%china%' OR headline ILIKE '%chinese%' OR headline ILIKE '%beijing%')
          AND (headline ILIKE '%soy%' OR headline ILIKE '%bean%' OR headline ILIKE '%export%' OR headline ILIKE '%import%'))
        OR content ILIKE '%china soy%' OR content ILIKE '%soybean export%' OR content ILIKE '%chinese import%'
        OR specialist_tags && ARRAY[
          'china',
          'lane_soybean_agriculture'
        ]::text[]
        OR source LIKE 'google_news/soybean_agriculture/%'
      )
      AND NOT (
        specialist_tags && ARRAY['tariff', 'lane_legislation', 'lane_trump_actions', 'lane_ice_immigration']::text[]
        OR source LIKE 'google_news/legislation/%'
        OR source LIKE 'google_news/trump_actions/%'
        OR source LIKE 'google_news/ice_immigration/%'
      )
    `),
    // Total deduped policy/econ/ag news pool (for concentration)
    query<{ count: number }>(`
      WITH candidate_news AS (
        SELECT headline, content
        FROM alt.profarmer_news_event
        WHERE event_date >= CURRENT_DATE - INTERVAL '7 days'

        UNION ALL

        SELECT headline, content
        FROM alt.policy_news_event
        WHERE event_date >= CURRENT_DATE - INTERVAL '7 days'

        UNION ALL

        SELECT headline, content
        FROM alt.econ_news_event
        WHERE event_date >= CURRENT_DATE - INTERVAL '7 days'
      )
      SELECT COUNT(DISTINCT md5(COALESCE(headline, '') || '|' || COALESCE(content, '')))::int as count
      FROM candidate_news
      WHERE headline IS NOT NULL OR content IS NOT NULL
    `),

    // === TARIFF THREAT DATA ===
    // NOTE: Using USEPUINDXM (main EPU) instead of EPUTRADE - EPUTRADE is stale (Dec 2025)
    query<{ tpu: number; tpu_date: string; emv: number | null }>(`
      SELECT
        (SELECT value FROM econ.vol_indices_1d WHERE series_id = 'USEPUINDXM' AND value IS NOT NULL ORDER BY event_date DESC LIMIT 1)::float8 as tpu,
        (SELECT event_date::text FROM econ.vol_indices_1d WHERE series_id = 'USEPUINDXM' AND value IS NOT NULL ORDER BY event_date DESC LIMIT 1) as tpu_date,
        (SELECT value FROM econ.vol_indices_1d WHERE series_id = 'EMVTRADEPOLEMV' AND value IS NOT NULL ORDER BY event_date DESC LIMIT 1)::float8 as emv
    `),
    // Legislation Velocity (14 days)
    query<{ count: number }>(`
      SELECT COUNT(*)::int as count FROM alt.legislation_1d
      WHERE event_date >= CURRENT_DATE - INTERVAL '14 days'
      AND (title ILIKE '%trade%' OR title ILIKE '%tariff%' OR title ILIKE '%import%' OR title ILIKE '%export%')
    `).catch(() => [{ count: 0 }]), // Table might not exist
    // Tariff/trade policy feed (7 days) — intentionally separated from China and Energy feeds
    query<{ count: number }>(`
      WITH candidate_news AS (
        SELECT headline, content, NULL::text AS source, specialist_tags
        FROM alt.profarmer_news_event
        WHERE event_date >= CURRENT_DATE - INTERVAL '7 days'

        UNION ALL

        SELECT headline, content, source, specialist_tags
        FROM alt.policy_news_event
        WHERE event_date >= CURRENT_DATE - INTERVAL '7 days'

        UNION ALL

        SELECT headline, content, source, specialist_tags
        FROM alt.econ_news_event
        WHERE event_date >= CURRENT_DATE - INTERVAL '7 days'
      )
      SELECT COUNT(DISTINCT md5(COALESCE(headline, '') || '|' || COALESCE(content, '')))::int as count
      FROM candidate_news
      WHERE (
        headline ILIKE '%tariff%' OR headline ILIKE '%trade war%' OR headline ILIKE '%retaliatory%'
        OR (headline ILIKE '%soy%' AND headline ILIKE '%duty%')
        OR (headline ILIKE '%china%' AND headline ILIKE '%tariff%')
        OR content ILIKE '%soy tariff%' OR content ILIKE '%soybean tariff%' OR content ILIKE '%25 percent%'
        OR specialist_tags && ARRAY[
          'tariff',
          'lane_legislation',
          'lane_trump_actions',
          'lane_ice_immigration'
        ]::text[]
        OR source LIKE 'google_news/legislation/%'
        OR source LIKE 'google_news/trump_actions/%'
        OR source LIKE 'google_news/ice_immigration/%'
      )
      AND NOT (
        specialist_tags && ARRAY['energy', 'biofuel', 'lane_biofuel', 'lane_war_military']::text[]
        OR source LIKE 'google_news/biofuel/%'
        OR source LIKE 'google_news/war_military/%'
      )
    `),

    // === SPECIALIST SIGNALS ===
    query<{ signal: number }>(`
      SELECT signal_1::float8 as signal
      FROM training.specialist_signals_1d
      WHERE bucket = 'volatility'
        AND as_of_date >= CURRENT_DATE - INTERVAL '45 days'
        AND abstained = false
        AND confidence > 0
      ORDER BY as_of_date DESC
      LIMIT 1
    `),
    query<{ signal: number }>(`
      SELECT signal_1::float8 as signal
      FROM training.specialist_signals_1d
      WHERE bucket = 'crush'
        AND as_of_date >= CURRENT_DATE - INTERVAL '45 days'
        AND abstained = false
        AND confidence > 0
      ORDER BY as_of_date DESC
      LIMIT 1
    `),
    query<{ signal: number }>(`
      SELECT signal_1::float8 as signal
      FROM training.specialist_signals_1d
      WHERE bucket = 'china'
        AND as_of_date >= CURRENT_DATE - INTERVAL '45 days'
        AND abstained = false
        AND confidence > 0
      ORDER BY as_of_date DESC
      LIMIT 1
    `),
    query<{ signal: number }>(`
      SELECT signal_1::float8 as signal
      FROM training.specialist_signals_1d
      WHERE bucket = 'tariff'
        AND as_of_date >= CURRENT_DATE - INTERVAL '45 days'
        AND abstained = false
        AND confidence > 0
      ORDER BY as_of_date DESC
      LIMIT 1
    `),

    // === ZL PRICE DATA (for comprehensive reports) ===
    query<{ close: number; change_5d: number; change_20d: number }>(`
      WITH zl AS (
        SELECT close, ROW_NUMBER() OVER (ORDER BY event_date DESC) as rn
        FROM analytics.price_1d WHERE close IS NOT NULL LIMIT 21
      )
      SELECT
        (SELECT close FROM zl WHERE rn = 1)::float8 as close,
        CASE WHEN (SELECT close FROM zl WHERE rn = 6) > 0
             THEN ((SELECT close FROM zl WHERE rn = 1) - (SELECT close FROM zl WHERE rn = 6)) / (SELECT close FROM zl WHERE rn = 6)
             ELSE 0 END::float8 as change_5d,
        CASE WHEN (SELECT close FROM zl WHERE rn = 21) > 0
             THEN ((SELECT close FROM zl WHERE rn = 1) - (SELECT close FROM zl WHERE rn = 21)) / (SELECT close FROM zl WHERE rn = 21)
             ELSE 0 END::float8 as change_20d
    `),

    // === CL CRUDE OIL DATA (Energy Stress driver) ===
    query<{ close: number; change_5d: number; change_20d: number; event_date: string }>(`
      WITH cl AS (
        SELECT close, event_date, ROW_NUMBER() OVER (ORDER BY event_date DESC) as rn
        FROM mkt.futures_1d WHERE symbol = 'CL' AND close IS NOT NULL LIMIT 21
      )
      SELECT
        (SELECT close FROM cl WHERE rn = 1)::float8 as close,
        (SELECT event_date::text FROM cl WHERE rn = 1) as event_date,
        CASE WHEN (SELECT close FROM cl WHERE rn = 6) > 0
             THEN ((SELECT close FROM cl WHERE rn = 1) - (SELECT close FROM cl WHERE rn = 6)) / (SELECT close FROM cl WHERE rn = 6)
             ELSE 0 END::float8 as change_5d,
        CASE WHEN (SELECT close FROM cl WHERE rn = 21) > 0
             THEN ((SELECT close FROM cl WHERE rn = 1) - (SELECT close FROM cl WHERE rn = 21)) / (SELECT close FROM cl WHERE rn = 21)
             ELSE 0 END::float8 as change_20d
    `).catch(() => [] as { close: number; change_5d: number; change_20d: number; event_date: string }[]),

    // Energy/oil feed (7 days) — intentionally separated from China and Tariff feeds
    query<{ count: number }>(`
      WITH candidate_news AS (
        SELECT headline, content, NULL::text AS source, specialist_tags
        FROM alt.profarmer_news_event
        WHERE event_date >= CURRENT_DATE - INTERVAL '7 days'

        UNION ALL

        SELECT headline, content, source, specialist_tags
        FROM alt.policy_news_event
        WHERE event_date >= CURRENT_DATE - INTERVAL '7 days'

        UNION ALL

        SELECT headline, content, source, specialist_tags
        FROM alt.econ_news_event
        WHERE event_date >= CURRENT_DATE - INTERVAL '7 days'
      )
      SELECT COUNT(DISTINCT md5(COALESCE(headline, '') || '|' || COALESCE(content, '')))::int as count
      FROM candidate_news
      WHERE (
        headline ILIKE '%crude%' OR headline ILIKE '%oil price%' OR headline ILIKE '%energy%'
        OR headline ILIKE '%iran%' OR headline ILIKE '%hormuz%' OR headline ILIKE '%opec%'
        OR headline ILIKE '%petroleum%' OR headline ILIKE '%biofuel%' OR headline ILIKE '%biodiesel%'
        OR headline ILIKE '%renewable diesel%' OR headline ILIKE '%strait%'
        OR content ILIKE '%crude oil%' OR content ILIKE '%oil spike%' OR content ILIKE '%energy crisis%'
        OR specialist_tags && ARRAY[
          'energy',
          'biofuel',
          'lane_biofuel',
          'lane_war_military',
          'lane_soybean_oil'
        ]::text[]
        OR source LIKE 'google_news/biofuel/%'
        OR source LIKE 'google_news/war_military/%'
        OR source LIKE 'google_news/soybean_oil/%'
      )
      AND NOT (
        specialist_tags && ARRAY['tariff', 'lane_legislation', 'lane_trump_actions', 'lane_ice_immigration']::text[]
        OR source LIKE 'google_news/legislation/%'
        OR source LIKE 'google_news/trump_actions/%'
        OR source LIKE 'google_news/ice_immigration/%'
      )
    `).catch(() => [{ count: 0 }]),

    // === RECENT NEWS HEADLINES (for comprehensive reports) ===
    query<{ headline: string }>(`
      WITH combined AS (
        SELECT event_date, headline
        FROM alt.profarmer_news_event
        WHERE event_date >= CURRENT_DATE - INTERVAL '7 days'

        UNION ALL

        SELECT event_date, headline
        FROM alt.policy_news_event
        WHERE event_date >= CURRENT_DATE - INTERVAL '7 days'

        UNION ALL

        SELECT event_date, headline
        FROM alt.econ_news_event
        WHERE event_date >= CURRENT_DATE - INTERVAL '7 days'
      ),
      dedup AS (
        SELECT headline, MAX(event_date) AS latest_date
        FROM combined
        WHERE headline IS NOT NULL
        GROUP BY headline
      )
      SELECT headline
      FROM dedup
      ORDER BY latest_date DESC
      LIMIT 10
    `).catch(() => [] as { headline: string }[]),
  ]);

  // Extract values — NO FALLBACKS. If primary data is missing, we fail honestly.
  const cnyRate = cnyRows[0]?.rate ?? null;
  const cnyRate20d = cnyChangeRows[0]?.rate_20d ?? null;
  const cnyChange20d =
    cnyRate20d && cnyRate && cnyRate20d > 0
      ? (cnyRate - cnyRate20d) / cnyRate20d
      : null;

  return {
    vix: vixRows[0]?.vix ?? null,
    vixDate: vixRows[0]?.event_date ?? null,
    vix3m: vix3mRows[0]?.vix3m ?? null,
    ovx: ovxRows[0]?.ovx ?? null,
    realizedVol: realizedVolRows[0]?.realized_vol ?? null,
    vixZlCorr: vixZlCorrRows[0]?.vix_zl_corr ?? null,
    hedgeCount: hedgeNewsRows[0]?.count ?? 0,
    volSignal: volSignalRows[0]?.signal ?? null,

    crush: crushRows[0]?.crush ?? null,
    crushDate: crushRows[0]?.trade_date ?? null,
    oilShare: crushRows[0]?.oil_share ?? null,
    oilShare5dAgo: oilShare5dRows[0]?.oil_share_5d ?? null,
    crushSignal: crushSignalRows[0]?.signal ?? null,
    crushNewsCount: crushNewsRows[0]?.count ?? 0,
    soybeanMealNewsCount: soybeanMealNewsRows[0]?.count ?? 0,
    cornNewsCount: cornNewsRows[0]?.count ?? 0,

    cnyRate,
    cnyDate: cnyRows[0]?.event_date ?? null,
    cnyChange20d,
    hgChange20d: hgRows[0]?.change_20d ?? 0,
    hgChange5d: hgRows[0]?.change_5d ?? 0,
    bdiyChange20d: bdiyRows[0]?.change_20d ?? null,
    soyChinaNews: soyChinaNewsRows[0]?.count ?? 0,
    totalNews: totalNewsRows[0]?.count ?? 1,
    chinaSignal: chinaSignalRows[0]?.signal ?? null,

    tpu: tpuRows[0]?.tpu ?? null,
    tpuDate: tpuRows[0]?.tpu_date ?? null,
    emv: tpuRows[0]?.emv ?? null,
    legislationCount: legislationRows[0]?.count ?? 0,
    soyTariffNews: soyTariffNewsRows[0]?.count ?? 0,
    tariffSignal: tariffSignalRows[0]?.signal ?? null,

    zlPrice: zlPriceRows[0]?.close ?? null,
    zlChange5d: zlPriceRows[0]?.change_5d ?? null,
    zlChange20d: zlPriceRows[0]?.change_20d ?? null,

    clPrice: clPriceRows[0]?.close ?? null,
    clChange5d: clPriceRows[0]?.change_5d ?? null,
    clChange20d: clPriceRows[0]?.change_20d ?? null,
    clDate: clPriceRows[0]?.event_date ?? null,
    energyNewsCount: energyNewsRows[0]?.count ?? 0,

    recentNews: recentNewsRows?.map((r) => r.headline) ?? [],
  };
}

// =============================================================================
// VALIDATION HELPERS
// =============================================================================

/** Returns list of missing primary data sources (empty = all present). */
export function findMissingPrimaryData(data: MarketDriversRawData): string[] {
  const missing: string[] = [];
  if (data.vix === null) missing.push("VIX (econ.vol_indices_1d VIXCLS)");
  if (data.crush === null)
    missing.push("Board Crush (analytics.board_crush_1d)");
  if (data.cnyRate === null) missing.push("CNY Rate (mkt.fx_1d USD/CNY)");
  if (data.tpu === null) missing.push("TPU (econ.vol_indices_1d USEPUINDXM)");
  return missing;
}

/** Computes data freshness metadata for response envelope. */
export function computeDataFreshness(
  data: MarketDriversRawData,
): Record<string, unknown> {
  const today = new Date();
  const daysSince = (dateStr: string | null) => {
    if (!dateStr) return null;
    const d = new Date(dateStr);
    return Math.floor(
      (today.getTime() - d.getTime()) / (1000 * 60 * 60 * 24),
    );
  };

  return {
    vix: {
      date: data.vixDate,
      days_old: daysSince(data.vixDate),
      status:
        daysSince(data.vixDate) !== null && daysSince(data.vixDate)! <= 2
          ? "fresh"
          : "stale",
    },
    crush: {
      date: data.crushDate,
      days_old: daysSince(data.crushDate),
      status:
        daysSince(data.crushDate) !== null && daysSince(data.crushDate)! <= 2
          ? "fresh"
          : "stale",
    },
    cny: {
      date: data.cnyDate,
      days_old: daysSince(data.cnyDate),
      status:
        daysSince(data.cnyDate) !== null && daysSince(data.cnyDate)! <= 5
          ? "fresh"
          : "stale",
    },
    tpu: {
      date: data.tpuDate,
      days_old: daysSince(data.tpuDate),
      status:
        daysSince(data.tpuDate) !== null && daysSince(data.tpuDate)! <= 45
          ? "fresh"
          : "stale",
    },
    vix3m: {
      available: data.vix3m !== null,
      note:
        data.vix3m === null
          ? "VXVCLS (VIX 3-month) series not found"
          : "Term structure calc enabled",
    },
    specialist_signals: (() => {
      const hasSignals =
        data.volSignal !== null ||
        data.crushSignal !== null ||
        data.chinaSignal !== null ||
        data.tariffSignal !== null;
      return {
        available: hasSignals,
        buckets: {
          volatility: data.volSignal !== null,
          crush: data.crushSignal !== null,
          china: data.chinaSignal !== null,
          tariff: data.tariffSignal !== null,
        },
        note: hasSignals
          ? "Specialist signals active"
          : "No specialist signal data within 45-day window",
      };
    })(),
  };
}

// =============================================================================
// STALENESS-AWARE METADATA
// =============================================================================

export interface SourceStaleness {
  source: string;
  date: string | null;
  daysStale: number | null;
  slaMaxDays: number;
  isFresh: boolean;
}

/** Per-source SLA thresholds (calendar days). */
const SOURCE_SLAS: Record<string, number> = {
  vix: 3,    // Daily VIX
  crush: 5,  // Daily crush (business-day cadence)
  cny: 5,    // Daily FX (business-day cadence)
  tpu: 45,   // Monthly EPU series
};

/** Returns per-source staleness info with SLA-aware thresholds. */
export function computeStalenessAwareness(
  data: MarketDriversRawData,
): Record<string, SourceStaleness> {
  const today = new Date();
  const daysSince = (dateStr: string | null): number | null => {
    if (!dateStr) return null;
    return Math.floor(
      (today.getTime() - new Date(dateStr).getTime()) / (1000 * 60 * 60 * 24),
    );
  };

  const assess = (
    source: string,
    date: string | null,
    sla: number,
  ): SourceStaleness => {
    const days = daysSince(date);
    return {
      source,
      date,
      daysStale: days,
      slaMaxDays: sla,
      isFresh: days !== null && days <= sla,
    };
  };

  return {
    vix: assess("econ.vol_indices_1d VIXCLS", data.vixDate, SOURCE_SLAS.vix),
    crush: assess("analytics.board_crush_1d", data.crushDate, SOURCE_SLAS.crush),
    cny: assess("mkt.fx_1d CNY/USD", data.cnyDate, SOURCE_SLAS.cny),
    tpu: assess("econ.vol_indices_1d USEPUINDXM", data.tpuDate, SOURCE_SLAS.tpu),
  };
}

/** Assembles MarketData for AI calls. */
export function buildMarketData(
  data: MarketDriversRawData,
  scores: { vix: number; crush: number; china: number; tariff: number; energy: number },
  asOfDate: string,
): MarketData {
  return {
    vix: data.vix!,
    ovx: data.ovx,
    boardCrush: data.crush!,
    oilShare: data.oilShare,
    cnyRate: data.cnyRate!,
    // Backward-compatible aliases for any older consumers
    fxiChange20d: data.hgChange20d,
    fxiChange5d: data.hgChange5d,
    bdryChange20d: data.bdiyChange20d,
    tpu: data.tpu!,
    emv: data.emv,
    scores,
    zlPrice: data.zlPrice ?? undefined,
    zlChange5d: data.zlChange5d ?? undefined,
    zlChange20d: data.zlChange20d ?? undefined,
    recentNews: data.recentNews.length > 0 ? data.recentNews : undefined,
    asOfDate,
  };
}
