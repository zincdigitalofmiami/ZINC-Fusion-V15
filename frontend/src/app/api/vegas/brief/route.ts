/**
 * Vegas Procurement Brief - Consolidated Email Summary
 *
 * Combines: Live ZL price, 4 driver scores, forecasts at multiple horizons,
 * correlations, and actionable recommendations - all in plain English.
 *
 * For Chris - major Las Vegas soybean oil procurement buyer
 */

import { NextResponse } from 'next/server'
import { query } from '@/lib/db'

export const dynamic = 'force-dynamic'

// =============================================================================
// TYPES
// =============================================================================

interface PriceSummary {
  current: number
  previousClose: number
  change: number
  changePct: number
  weekHigh: number
  weekLow: number
  asOf: string
}

interface ForecastHorizon {
  label: string
  days: number
  targetLow: number | null   // p30
  targetMid: number | null   // p50
  targetHigh: number | null  // p70
  expectedChange: string
  expectedChangePct: string
  direction: 'UP' | 'DOWN' | 'FLAT' | 'NO DATA'
  source: 'model' | 'unavailable'
}

interface DriverSummary {
  name: string
  score: number
  status: string
  impact: string
  rawValue: number | null  // The actual underlying value (VIX level, crush margin, etc.)
  unit: string             // e.g., 'VIX points', '$/bu', 'CNY/$', 'index'
  asOfDate: string | null  // When this data was last updated
  source: 'live' | 'stale' | 'unavailable'
}

interface CorrelationSummary {
  asset: string
  correlation: number | null
  direction: string
  implication: string
  lookbackDays: number
  source: 'calculated' | 'unavailable'
}

interface VegasBrief {
  generatedAt: string
  asOfDate: string

  // Quick read
  tldr: string
  recommendation: 'BUY NOW' | 'WAIT' | 'NORMAL SCHEDULE' | 'LOCK IN COVERAGE' | 'CHECK DATA'
  recommendationColor: string

  // Price
  price: PriceSummary

  // Forecasts
  forecasts: ForecastHorizon[]
  forecastsAvailable: boolean

  // Drivers (simplified)
  drivers: DriverSummary[]
  driversSummary: string

  // Correlations
  correlations: CorrelationSummary[]

  // Policy/context
  policyContext: string

  // Risk factors
  keyRisks: string[]
  keyPositives: string[]

  // Data quality
  dataIssues: string[]
  dataQuality: 'good' | 'partial' | 'poor'
}

// =============================================================================
// DATA FETCHERS
// =============================================================================

async function getCurrentPrice(): Promise<PriceSummary | null> {
  try {
    // Get latest price
    const latest = await query<{price: number, timestamp: string}>(`
      SELECT price, timestamp FROM analytics.zl_latest WHERE id = 1
    `)

    // Get recent daily closes for week range
    const dailyCloses = await query<{close: number, event_date: string}>(`
      SELECT close, event_date FROM analytics.zl_price_1d
      ORDER BY event_date DESC LIMIT 6
    `)

    if (!latest.length || !dailyCloses.length) return null

    const current = latest[0].price
    const previousClose = dailyCloses[1]?.close ?? dailyCloses[0].close
    const weekPrices = dailyCloses.map(r => r.close)

    return {
      current,
      previousClose,
      change: current - previousClose,
      changePct: ((current - previousClose) / previousClose) * 100,
      weekHigh: Math.max(...weekPrices, current),
      weekLow: Math.min(...weekPrices, current),
      asOf: latest[0].timestamp
    }
  } catch (e) {
    console.error('Price fetch error:', e)
    return null
  }
}

async function getForecasts(currentPrice: number): Promise<ForecastHorizon[]> {
  try {
    // Try production forecasts first
    const fcRows = await query<{
      horizon_days: number, price_p30: number, price_p50: number, price_p70: number
    }>(`
      WITH latest_5d AS (
        SELECT 5 as horizon_days, price_p30::float, price_p50::float, price_p70::float
        FROM forecasts.production_5d_1d ORDER BY as_of_date DESC LIMIT 1
      ),
      latest_21d AS (
        SELECT 21 as horizon_days, price_p30::float, price_p50::float, price_p70::float
        FROM forecasts.production_21d_1d ORDER BY as_of_date DESC LIMIT 1
      ),
      latest_63d AS (
        SELECT 63 as horizon_days, price_p30::float, price_p50::float, price_p70::float
        FROM forecasts.production_63d_1d ORDER BY as_of_date DESC LIMIT 1
      ),
      latest_126d AS (
        SELECT 126 as horizon_days, price_p30::float, price_p50::float, price_p70::float
        FROM forecasts.production_126d_1d ORDER BY as_of_date DESC LIMIT 1
      )
      SELECT * FROM latest_5d
      UNION ALL SELECT * FROM latest_21d
      UNION ALL SELECT * FROM latest_63d
      UNION ALL SELECT * FROM latest_126d
      ORDER BY horizon_days
    `)

    if (fcRows.length > 0) {
      return fcRows.map(f => formatForecast(f, currentPrice))
    }

    // No model forecasts available - return empty (NO FAKE DATA)
    return getEmptyForecasts()
  } catch (e) {
    console.error('Forecast fetch error:', e)
    return getEmptyForecasts()
  }
}

function formatForecast(f: {horizon_days: number, price_p30: number, price_p50: number, price_p70: number}, currentPrice: number): ForecastHorizon {
  const labels: Record<number, string> = {
    5: '1 Week',
    21: '1 Month',
    63: '1 Quarter',
    126: '6 Months'
  }

  const change = f.price_p50 - currentPrice
  const changePct = (change / currentPrice) * 100

  return {
    label: labels[f.horizon_days] || `${f.horizon_days}d`,
    days: f.horizon_days,
    targetLow: f.price_p30,
    targetMid: f.price_p50,
    targetHigh: f.price_p70,
    expectedChange: (change >= 0 ? '+' : '') + change.toFixed(2) + '¢',
    expectedChangePct: (changePct >= 0 ? '+' : '') + changePct.toFixed(1) + '%',
    direction: changePct > 2 ? 'UP' : changePct < -2 ? 'DOWN' : 'FLAT',
    source: 'model'
  }
}

// NO FAKE FORECASTS - return placeholders that clearly indicate no model data
function getEmptyForecasts(): ForecastHorizon[] {
  return [
    { label: '1 Week', days: 5, targetLow: null, targetMid: null, targetHigh: null,
      expectedChange: '--', expectedChangePct: '--', direction: 'NO DATA', source: 'unavailable' },
    { label: '1 Month', days: 21, targetLow: null, targetMid: null, targetHigh: null,
      expectedChange: '--', expectedChangePct: '--', direction: 'NO DATA', source: 'unavailable' },
    { label: '1 Quarter', days: 63, targetLow: null, targetMid: null, targetHigh: null,
      expectedChange: '--', expectedChangePct: '--', direction: 'NO DATA', source: 'unavailable' },
    { label: '6 Months', days: 126, targetLow: null, targetMid: null, targetHigh: null,
      expectedChange: '--', expectedChangePct: '--', direction: 'NO DATA', source: 'unavailable' }
  ]
}

async function getDriverScores(): Promise<{drivers: DriverSummary[], avgScore: number, summary: string, dataIssues: string[]}> {
  const dataIssues: string[] = []

  try {
    // VIX data - from econ.vol_indices_1d (with date for freshness check)
    const vixData = await query<{value: number, event_date: string}>(`
      SELECT value::float8, event_date::text FROM econ.vol_indices_1d WHERE series_id = 'VIXCLS'
      AND value IS NOT NULL ORDER BY event_date DESC LIMIT 1
    `)

    // Crush margin - from analytics.board_crush_1d
    const crushData = await query<{board_crush: number, oil_share: number, trade_date: string}>(`
      SELECT board_crush::float8 as board_crush, oil_share::float8 as oil_share, trade_date::text
      FROM analytics.board_crush_1d WHERE board_crush IS NOT NULL
      ORDER BY trade_date DESC LIMIT 1
    `)

    // CNY rate - from mkt.fx_1d
    const cnyData = await query<{rate: number, event_date: string}>(`
      SELECT rate::float8, event_date::text FROM mkt.fx_1d WHERE pair IN ('USD/CNY', 'USDCNY')
      AND rate IS NOT NULL ORDER BY event_date DESC LIMIT 1
    `)

    // Trade policy uncertainty - from econ.vol_indices_1d
    const tpuData = await query<{value: number, event_date: string}>(`
      SELECT value::float8, event_date::text FROM econ.vol_indices_1d WHERE series_id = 'USEPUINDXM'
      AND value IS NOT NULL ORDER BY event_date DESC LIMIT 1
    `)

    // Extract values - track what's missing
    const vix = vixData[0]?.value ?? null
    const vixDate = vixData[0]?.event_date ?? null
    const crush = crushData[0]?.board_crush ?? null
    const crushDate = crushData[0]?.trade_date ?? null
    const cny = cnyData[0]?.rate ?? null
    const cnyDate = cnyData[0]?.event_date ?? null
    const tpu = tpuData[0]?.value ?? null
    const tpuDate = tpuData[0]?.event_date ?? null

    // Track missing data
    if (!vix) dataIssues.push('VIX data unavailable')
    if (!crush) dataIssues.push('Crush margin data unavailable')
    if (!cny) dataIssues.push('CNY/USD rate unavailable')
    if (!tpu) dataIssues.push('Trade policy index unavailable')

    // Check data freshness (warn if > 3 days old)
    const today = new Date()
    const checkFreshness = (dateStr: string | null, name: string): 'live' | 'stale' | 'unavailable' => {
      if (!dateStr) return 'unavailable'
      const dataDate = new Date(dateStr)
      const daysDiff = Math.floor((today.getTime() - dataDate.getTime()) / (1000 * 60 * 60 * 24))
      if (daysDiff > 3) {
        dataIssues.push(`${name} data is ${daysDiff} days old`)
        return 'stale'
      }
      return 'live'
    }

    // Score calculations — null means no data, not neutral
    const vixScore = vix !== null ? Math.min(100, Math.max(0, ((vix - 12) / 28) * 100)) : null
    const crushScore = crush !== null
      ? (crush < 1 ? 90 : crush < 1.25 ? 75 : crush < 1.5 ? 50 : crush < 1.75 ? 35 : 20)
      : null
    const chinaScore = cny !== null
      ? (cny > 7.3 ? 70 : cny > 7.2 ? 55 : cny > 7.0 ? 40 : 30)
      : null
    const tariffScore = tpu !== null
      ? (tpu > 200 ? 80 : tpu > 150 ? 60 : tpu > 100 ? 45 : 30)
      : null

    // Only average scores that actually have data
    const validScores = [vixScore, crushScore, chinaScore, tariffScore].filter((s): s is number => s !== null)
    const avgScore = validScores.length > 0 ? validScores.reduce((a, b) => a + b, 0) / validScores.length : 0

    const drivers: DriverSummary[] = [
      {
        name: 'Markets',
        score: vixScore ?? 0,
        status: vixScore === null ? 'NO DATA' : vixScore >= 65 ? 'PANIC' : vixScore >= 50 ? 'NERVOUS' : vixScore <= 35 ? 'CALM' : 'OK',
        impact: vixScore === null ? 'VIX data unavailable — score excluded from average' :
                vixScore >= 65 ? 'Funds dumping commodities, wild swings' :
                vixScore <= 35 ? 'Stable, fundamentals-driven pricing' : 'Normal volatility',
        rawValue: vix,
        unit: 'VIX points',
        asOfDate: vixDate,
        source: checkFreshness(vixDate, 'VIX')
      },
      {
        name: 'Crush',
        score: crushScore ?? 0,
        status: crushScore === null ? 'NO DATA' : crushScore >= 65 ? 'TIGHT' : crushScore <= 35 ? 'FLUSH' : 'NORMAL',
        impact: crushScore === null ? 'Crush data unavailable — score excluded from average' :
                crushScore >= 65 ? `Plants slowing at $${crush!.toFixed(2)}/bu - supply tightening` :
                crushScore <= 35 ? `Plants running full at $${crush!.toFixed(2)}/bu - plenty of oil` :
                `Normal margins at $${crush!.toFixed(2)}/bu`,
        rawValue: crush,
        unit: '$/bushel',
        asOfDate: crushDate,
        source: checkFreshness(crushDate, 'Crush')
      },
      {
        name: 'China',
        score: chinaScore ?? 0,
        status: chinaScore === null ? 'NO DATA' : chinaScore >= 65 ? 'FROZEN' : 'BRAZIL PREFERRED',
        impact: chinaScore === null ? 'FX data unavailable — score excluded from average' :
                chinaScore >= 65 ? 'Trade disrupted, soy demand weak' :
                `Brazil beats US (CNY at ${cny!.toFixed(2)}) - 13% tariff gap`,
        rawValue: cny,
        unit: 'CNY/USD',
        asOfDate: cnyDate,
        source: checkFreshness(cnyDate, 'CNY')
      },
      {
        name: 'Trade',
        score: tariffScore ?? 0,
        status: tariffScore === null ? 'NO DATA' : tariffScore >= 65 ? 'WAR RISK' : tariffScore >= 50 ? 'NOISY' : 'QUIET',
        impact: tariffScore === null ? 'Policy index unavailable — score excluded from average' :
                tariffScore >= 65 ? `TPU at ${tpu!.toFixed(0)} - escalation risk, stay defensive` :
                tariffScore <= 35 ? 'Policy stable, no new threats' : 'Headlines, no action',
        rawValue: tpu,
        unit: 'index',
        asOfDate: tpuDate,
        source: checkFreshness(tpuDate, 'TPU')
      }
    ]

    const missingCount = 4 - validScores.length
    const summary = missingCount >= 3
      ? `${missingCount} of 4 drivers have no data. Brief is unreliable.`
      : dataIssues.length > 2
      ? `Data issues detected: ${dataIssues.slice(0, 2).join(', ')}. Scores based on ${validScores.length}/4 drivers.`
      : avgScore >= 60
      ? 'Multiple headwinds. Markets nervous, trade uncertain.'
      : avgScore <= 40
      ? 'Favorable conditions. Stable markets, solid crush.'
      : 'Mixed picture. No clear direction.'

    return { drivers, avgScore, summary, dataIssues }
  } catch (e) {
    console.error('Driver fetch error:', e)
    // Return unavailable drivers - NO FAKE SCORES
    return {
      drivers: [
        { name: 'Markets', score: 0, status: 'ERROR', impact: 'Database query failed', rawValue: null, unit: 'VIX points', asOfDate: null, source: 'unavailable' },
        { name: 'Crush', score: 0, status: 'ERROR', impact: 'Database query failed', rawValue: null, unit: '$/bushel', asOfDate: null, source: 'unavailable' },
        { name: 'China', score: 0, status: 'ERROR', impact: 'Database query failed', rawValue: null, unit: 'CNY/USD', asOfDate: null, source: 'unavailable' },
        { name: 'Trade', score: 0, status: 'ERROR', impact: 'Database query failed', rawValue: null, unit: 'index', asOfDate: null, source: 'unavailable' }
      ],
      avgScore: 0,
      summary: 'DATABASE ERROR: Unable to fetch driver data. Do not rely on this brief.',
      dataIssues: ['Database connection failed']
    }
  }
}

// Calculate REAL correlations from database price data (63-day rolling)
async function getCorrelations(): Promise<CorrelationSummary[]> {
  const LOOKBACK = 63 // 3-month rolling correlation

  try {
    // Calculate correlations between ZL and key assets using actual price data
    const correlationQueries = await Promise.all([
      // ZL vs Soybean Meal (ZM)
      query<{corr: number}>(`
        WITH zl AS (SELECT event_date, close FROM mkt.futures_1d WHERE symbol = 'ZL' ORDER BY event_date DESC LIMIT ${LOOKBACK}),
             zm AS (SELECT event_date, close FROM mkt.futures_1d WHERE symbol = 'ZM' ORDER BY event_date DESC LIMIT ${LOOKBACK})
        SELECT CORR(zl.close, zm.close)::float8 as corr FROM zl JOIN zm ON zl.event_date = zm.event_date
      `).catch(() => [{ corr: null }]),

      // ZL vs Soybeans (ZS)
      query<{corr: number}>(`
        WITH zl AS (SELECT event_date, close FROM mkt.futures_1d WHERE symbol = 'ZL' ORDER BY event_date DESC LIMIT ${LOOKBACK}),
             zs AS (SELECT event_date, close FROM mkt.futures_1d WHERE symbol = 'ZS' ORDER BY event_date DESC LIMIT ${LOOKBACK})
        SELECT CORR(zl.close, zs.close)::float8 as corr FROM zl JOIN zs ON zl.event_date = zs.event_date
      `).catch(() => [{ corr: null }]),

      // ZL vs Crude Oil (CL)
      query<{corr: number}>(`
        WITH zl AS (SELECT event_date, close FROM mkt.futures_1d WHERE symbol = 'ZL' ORDER BY event_date DESC LIMIT ${LOOKBACK}),
             cl AS (SELECT event_date, close FROM mkt.futures_1d WHERE symbol = 'CL' ORDER BY event_date DESC LIMIT ${LOOKBACK})
        SELECT CORR(zl.close, cl.close)::float8 as corr FROM zl JOIN cl ON zl.event_date = cl.event_date
      `).catch(() => [{ corr: null }]),

      // ZL vs VIX (inverse relationship expected)
      query<{corr: number}>(`
        WITH zl AS (SELECT event_date, close FROM analytics.zl_price_1d ORDER BY event_date DESC LIMIT ${LOOKBACK}),
             vix AS (SELECT event_date, value as close FROM econ.vol_indices_1d WHERE series_id = 'VIXCLS' ORDER BY event_date DESC LIMIT ${LOOKBACK})
        SELECT CORR(zl.close, vix.close)::float8 as corr FROM zl JOIN vix ON zl.event_date = vix.event_date
      `).catch(() => [{ corr: null }]),

      // ZL vs Corn (ZC) - competing biofuel feedstock
      query<{corr: number}>(`
        WITH zl AS (SELECT event_date, close FROM mkt.futures_1d WHERE symbol = 'ZL' ORDER BY event_date DESC LIMIT ${LOOKBACK}),
             zc AS (SELECT event_date, close FROM mkt.futures_1d WHERE symbol = 'ZC' ORDER BY event_date DESC LIMIT ${LOOKBACK})
        SELECT CORR(zl.close, zc.close)::float8 as corr FROM zl JOIN zc ON zl.event_date = zc.event_date
      `).catch(() => [{ corr: null }])
    ])

    const [zmCorr, zsCorr, clCorr, vixCorr, zcCorr] = correlationQueries.map(r => r[0]?.corr ?? null)

    const formatDirection = (corr: number | null): string => {
      if (corr === null) return 'No data'
      if (corr >= 0.7) return 'Strong positive'
      if (corr >= 0.4) return 'Moderate positive'
      if (corr >= 0.1) return 'Weak positive'
      if (corr >= -0.1) return 'Uncorrelated'
      if (corr >= -0.4) return 'Weak negative'
      if (corr >= -0.7) return 'Moderate negative'
      return 'Strong negative'
    }

    return [
      {
        asset: 'Soybean Meal (ZM)',
        correlation: zmCorr,
        direction: formatDirection(zmCorr),
        implication: zmCorr !== null && zmCorr > 0.5
          ? 'Crush economics linked. Strong meal supports crush and oil supply.'
          : 'Crush relationship currently weak.',
        lookbackDays: LOOKBACK,
        source: zmCorr !== null ? 'calculated' : 'unavailable'
      },
      {
        asset: 'Soybeans (ZS)',
        correlation: zsCorr,
        direction: formatDirection(zsCorr),
        implication: zsCorr !== null && zsCorr > 0.6
          ? 'Bean prices drive oil. Watch bean fundamentals.'
          : 'Oil trading independently of beans currently.',
        lookbackDays: LOOKBACK,
        source: zsCorr !== null ? 'calculated' : 'unavailable'
      },
      {
        asset: 'Crude Oil (CL)',
        correlation: clCorr,
        direction: formatDirection(clCorr),
        implication: clCorr !== null && clCorr > 0.3
          ? 'Energy complex link via biofuels. Crude rallies support soy oil.'
          : 'Limited energy complex correlation currently.',
        lookbackDays: LOOKBACK,
        source: clCorr !== null ? 'calculated' : 'unavailable'
      },
      {
        asset: 'VIX (Fear Index)',
        correlation: vixCorr,
        direction: formatDirection(vixCorr),
        implication: vixCorr !== null && vixCorr < -0.2
          ? 'Risk-off hurts commodities. Wait out volatility spikes.'
          : 'Limited vol spillover currently - fundamentals driving.',
        lookbackDays: LOOKBACK,
        source: vixCorr !== null ? 'calculated' : 'unavailable'
      },
      {
        asset: 'Corn (ZC)',
        correlation: zcCorr,
        direction: formatDirection(zcCorr),
        implication: zcCorr !== null && zcCorr > 0.4
          ? 'Ag complex moving together. Broad commodity theme.'
          : 'Oil trading on its own fundamentals vs corn.',
        lookbackDays: LOOKBACK,
        source: zcCorr !== null ? 'calculated' : 'unavailable'
      }
    ]
  } catch (e) {
    console.error('Correlation calculation error:', e)
    // Return empty correlations - NO FAKE DATA
    return [
      { asset: 'Soybean Meal (ZM)', correlation: null, direction: 'Data unavailable', implication: 'Unable to calculate', lookbackDays: LOOKBACK, source: 'unavailable' },
      { asset: 'Soybeans (ZS)', correlation: null, direction: 'Data unavailable', implication: 'Unable to calculate', lookbackDays: LOOKBACK, source: 'unavailable' },
      { asset: 'Crude Oil (CL)', correlation: null, direction: 'Data unavailable', implication: 'Unable to calculate', lookbackDays: LOOKBACK, source: 'unavailable' },
      { asset: 'VIX (Fear Index)', correlation: null, direction: 'Data unavailable', implication: 'Unable to calculate', lookbackDays: LOOKBACK, source: 'unavailable' },
      { asset: 'Corn (ZC)', correlation: null, direction: 'Data unavailable', implication: 'Unable to calculate', lookbackDays: LOOKBACK, source: 'unavailable' }
    ]
  }
}

function getPolicyContext(_avgScore: number): string {
  // Current policy landscape
  return `BIOFUELS DRIVING DEMAND: EPA's 2026 RFS proposals boost biomass-based diesel targets to ~5.6B gallons. ` +
    `45Z tax credit (clean fuel) supports renewable diesel economics. Soy oil now ~40%+ of U.S. production goes to biofuels. ` +
    `CHINA REALITY: U.S. faces permanent 13% tariff vs Brazil's 3%. We only compete when Brazil runs short. ` +
    `Don't count on China surprises - price your coverage on domestic biofuel demand, not exports.`
}

// =============================================================================
// BRIEF GENERATION
// =============================================================================

function generateTLDR(
  price: PriceSummary,
  fcHorizons: ForecastHorizon[],
  driverData: {drivers: DriverSummary[], avgScore: number, dataIssues: string[]}
): string {
  const f1m = fcHorizons.find(f => f.days === 21) || fcHorizons[1]
  const f6m = fcHorizons.find(f => f.days === 126) || fcHorizons[3]

  const priceDesc = `Soybean oil (ZL) at ${price.current.toFixed(2)}¢/lb`
  const change = price.changePct >= 0
    ? `up ${price.changePct.toFixed(1)}% today`
    : `down ${Math.abs(price.changePct).toFixed(1)}% today`

  let outlook: string
  if (driverData.dataIssues.length >= 3) {
    outlook = 'DATA ISSUES - some indicators unavailable, proceed with caution'
  } else if (driverData.avgScore >= 60) {
    outlook = 'CAUTIOUS - multiple headwinds (volatility, trade uncertainty)'
  } else if (driverData.avgScore <= 40) {
    outlook = 'FAVORABLE - stable markets, strong crush economics'
  } else {
    outlook = 'MIXED - no clear direction, normal buying conditions'
  }

  // Build forecast summary only if model data available
  let forecastSummary: string
  if (f1m?.targetMid !== null && f6m?.targetMid !== null) {
    forecastSummary = `1-month target: ${f1m.targetMid.toFixed(1)}¢ (${f1m.expectedChangePct}). ` +
      `6-month target: ${f6m.targetMid.toFixed(1)}¢ (${f6m.expectedChangePct}).`
  } else {
    forecastSummary = `Model forecasts not yet available - prices based on current drivers only.`
  }

  return `${priceDesc}, ${change}. Outlook: ${outlook}. ${forecastSummary} ` +
    `Biofuel demand strong (45Z credit, RFS increases), China buying from Brazil (13% tariff gap). ` +
    `Key watch: VIX, crush margins, trade headlines.`
}

function getRecommendation(avgScore: number, dataIssues: string[]): {text: 'BUY NOW' | 'WAIT' | 'NORMAL SCHEDULE' | 'LOCK IN COVERAGE' | 'CHECK DATA', color: string} {
  // If too many data issues, warn user to check data
  if (dataIssues.length >= 3) {
    return { text: 'CHECK DATA', color: '#6B7280' }
  }
  if (avgScore >= 65) {
    return { text: 'WAIT', color: '#EF4444' }
  } else if (avgScore >= 50) {
    return { text: 'NORMAL SCHEDULE', color: '#F97316' }
  } else if (avgScore >= 35) {
    return { text: 'NORMAL SCHEDULE', color: '#EAB308' }
  } else {
    return { text: 'LOCK IN COVERAGE', color: '#22C55E' }
  }
}

function getKeyRisks(driverData: {drivers: DriverSummary[], avgScore: number}): string[] {
  const risks: string[] = []

  const vix = driverData.drivers.find(d => d.name === 'Markets')
  const tariff = driverData.drivers.find(d => d.name === 'Trade')
  const china = driverData.drivers.find(d => d.name === 'China')
  const crush = driverData.drivers.find(d => d.name === 'Crush')

  if (vix && vix.score >= 50) {
    risks.push('Market volatility elevated - prices could swing on any headline')
  }
  if (tariff && tariff.score >= 50) {
    risks.push('Trade policy noise - China could pull back if tensions escalate')
  }
  if (china && china.score >= 60) {
    risks.push('China demand weak - exports not providing price support')
  }
  if (crush && crush.score >= 60) {
    risks.push('Crush margins tight - some plants may slow, tightening supply')
  }

  // Always include these structural risks
  risks.push('South America (Brazil/Argentina) record crops pressuring global supplies')

  return risks.slice(0, 4)
}

function getKeyPositives(driverData: {drivers: DriverSummary[], avgScore: number}): string[] {
  const positives: string[] = []

  const vix = driverData.drivers.find(d => d.name === 'Markets')
  const crush = driverData.drivers.find(d => d.name === 'Crush')

  // Always include biofuel tailwind
  positives.push('EPA 2026 RFS increases boost biofuel demand - >50% of soy oil to biodiesel/renewable diesel')
  positives.push('45Z clean fuel tax credit supports renewable diesel economics through 2027')

  if (vix && vix.score <= 40) {
    positives.push('Markets calm - fundamentals-driven pricing, tight spreads')
  }
  if (crush && crush.score <= 40) {
    positives.push('Crush margins strong - plants running full, reliable supply')
  }

  positives.push('Record U.S. crush forecast (~2.57B bushels) keeps domestic supply flowing')

  return positives.slice(0, 4)
}

// =============================================================================
// MAIN HANDLER
// =============================================================================

export async function GET() {
  try {
    const now = new Date()
    const asOfDate = now.toISOString().split('T')[0]

    // Fetch all data
    const price = await getCurrentPrice()

    if (!price) {
      return NextResponse.json({
        error: 'Price data unavailable',
        message: 'Unable to fetch current ZL price'
      }, { status: 503 })
    }

    const [fcHorizons, driverData, correlations] = await Promise.all([
      getForecasts(price.current),
      getDriverScores(),
      getCorrelations()
    ])

    const policyContext = getPolicyContext(driverData.avgScore)
    const recommendation = getRecommendation(driverData.avgScore, driverData.dataIssues)

    // Check if forecasts are available (not all placeholders)
    const forecastsAvailable = fcHorizons.some(f => f.source === 'model')

    // Determine overall data quality
    const unavailableDrivers = driverData.drivers.filter(d => d.source === 'unavailable').length
    const unavailableCorrs = correlations.filter(c => c.source === 'unavailable').length
    let dataQuality: 'good' | 'partial' | 'poor'
    if (unavailableDrivers >= 2 || unavailableCorrs >= 3) {
      dataQuality = 'poor'
    } else if (unavailableDrivers >= 1 || unavailableCorrs >= 2 || !forecastsAvailable) {
      dataQuality = 'partial'
    } else {
      dataQuality = 'good'
    }

    const brief: VegasBrief = {
      generatedAt: now.toISOString(),
      asOfDate,

      tldr: generateTLDR(price, fcHorizons, driverData),
      recommendation: recommendation.text,
      recommendationColor: recommendation.color,

      price,
      forecasts: fcHorizons,
      forecastsAvailable,

      drivers: driverData.drivers,
      driversSummary: driverData.summary,

      correlations,
      policyContext,

      keyRisks: getKeyRisks(driverData),
      keyPositives: getKeyPositives(driverData),

      dataIssues: driverData.dataIssues,
      dataQuality
    }

    return NextResponse.json(brief)

  } catch (error) {
    console.error('Vegas brief generation failed:', error)
    return NextResponse.json({
      error: 'Brief generation failed',
      details: String(error)
    }, { status: 500 })
  }
}
