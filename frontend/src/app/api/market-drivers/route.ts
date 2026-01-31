import { NextResponse } from 'next/server'
import { query } from '@/lib/db'

export const dynamic = 'force-dynamic'

// =============================================================================
// DOMAIN-SPECIFIC THRESHOLDS
// These match the Python pressure calculators exactly
// =============================================================================

const VIX = { COMPLACENT: 12, LOW: 15, NORMAL: 20, ELEVATED: 25, HIGH: 30, EXTREME: 40 }
const CRUSH = { DANGER: 0.75, SEVERE: 1.00, TIGHT: 1.25, NEUTRAL: 1.50, HEALTHY: 1.75, STRONG: 2.00, EXCEPTIONAL: 2.50 }
const CNY = { STRONG: 7.00, NORMAL: 7.15, WEAK: 7.30, STRESS: 7.45, CRISIS: 7.60 }
const TPU = { CALM: 40, NORMAL: 100, ELEVATED: 200, HIGH: 400, EXTREME: 700 }

// =============================================================================
// SCORING FUNCTIONS
// =============================================================================

function scoreVixStress(vix: number): { score: number; level: string; regime: string; headline: string } {
  let score: number, level: string, regime: string

  if (vix <= VIX.COMPLACENT) { score = 15; level = 'Complacent'; regime = 'complacent' }
  else if (vix <= VIX.LOW) { score = 25; level = 'Low Vol'; regime = 'low_vol' }
  else if (vix <= VIX.NORMAL) { score = 40; level = 'Normal'; regime = 'normal' }
  else if (vix <= VIX.ELEVATED) { score = 55; level = 'Elevated'; regime = 'elevated' }
  else if (vix <= VIX.HIGH) { score = 70; level = 'High Vol'; regime = 'high_vol' }
  else if (vix <= VIX.EXTREME) { score = 85; level = 'Fear'; regime = 'fear' }
  else { score = 95; level = 'Extreme Fear'; regime = 'extreme_fear' }

  const headline = score >= 80 ? 'Extreme Volatility Alert'
    : score >= 65 ? 'Elevated Market Stress'
    : score >= 50 ? 'Above-Normal Volatility'
    : score >= 35 ? 'Normal Volatility Conditions'
    : 'Low Volatility Environment'

  return { score: Math.round(score * 10) / 10, level, regime, headline }
}

function scoreCrushPressure(crush: number, oilShare: number | null): { score: number; level: string; regime: string; headline: string } {
  let score: number, level: string, regime: string

  if (crush >= CRUSH.EXCEPTIONAL) { score = 10; level = 'Exceptional'; regime = 'exceptional_margins' }
  else if (crush >= CRUSH.STRONG) { score = 20; level = 'Strong'; regime = 'strong_margins' }
  else if (crush >= CRUSH.HEALTHY) { score = 30; level = 'Healthy'; regime = 'healthy_margins' }
  else if (crush >= CRUSH.NEUTRAL) { score = 45; level = 'Neutral'; regime = 'neutral' }
  else if (crush >= CRUSH.TIGHT) { score = 60; level = 'Tight'; regime = 'tight_margins' }
  else if (crush >= CRUSH.SEVERE) { score = 75; level = 'Severe'; regime = 'severe_stress' }
  else if (crush >= CRUSH.DANGER) { score = 88; level = 'Collapse'; regime = 'margin_collapse' }
  else { score = 95; level = 'Crisis'; regime = 'crisis' }

  // Oil share adjustment
  if (oilShare !== null) {
    if (oilShare < 0.42) score += 10
    else if (oilShare < 0.46) score += 5
    else if (oilShare > 0.52) score -= 8
    else if (oilShare > 0.48) score -= 3
  }
  score = Math.max(0, Math.min(100, score))

  const headline = score >= 75 ? 'Crush Economics Under Severe Stress'
    : score >= 55 ? 'Processor Margins Tightening'
    : score >= 40 ? 'Neutral Crush Economics'
    : score >= 25 ? 'Healthy Processor Margins'
    : 'Strong Crush Economics'

  return { score: Math.round(score * 10) / 10, level, regime, headline }
}

function scoreChinaTension(cny: number, fxiChange20d: number, fxiChange5d: number, bdryChange20d: number | null): { score: number; level: string; regime: string; headline: string } {
  let score = 50

  // CNY component
  if (cny > CNY.CRISIS) score += 18
  else if (cny > CNY.STRESS) score += 12
  else if (cny > CNY.WEAK) score += 6
  else if (cny > CNY.NORMAL) score += 0
  else if (cny > CNY.STRONG) score -= 5
  else score -= 12

  // FXI 20-day
  if (fxiChange20d < -0.15) score += 22
  else if (fxiChange20d < -0.10) score += 15
  else if (fxiChange20d < -0.05) score += 8
  else if (fxiChange20d < 0) score += 3
  else if (fxiChange20d > 0.10) score -= 15
  else if (fxiChange20d > 0.05) score -= 10
  else if (fxiChange20d > 0) score -= 5

  // FXI 5-day momentum
  if (fxiChange5d < -0.05) score += 8
  else if (fxiChange5d < -0.02) score += 4
  else if (fxiChange5d > 0.05) score -= 8
  else if (fxiChange5d > 0.02) score -= 4

  // BDRY shipping
  if (bdryChange20d !== null) {
    if (bdryChange20d < -0.20) score += 12
    else if (bdryChange20d < -0.10) score += 6
    else if (bdryChange20d > 0.20) score -= 8
    else if (bdryChange20d > 0.10) score -= 4
  }

  score = Math.max(0, Math.min(100, score))

  let level: string, regime: string
  if (score >= 75) { level = 'High Tension'; regime = 'high_tension' }
  else if (score >= 60) { level = 'Elevated'; regime = 'elevated' }
  else if (score >= 45) { level = 'Watchful'; regime = 'watchful' }
  else if (score >= 30) { level = 'Constructive'; regime = 'constructive' }
  else { level = 'Optimistic'; regime = 'optimistic' }

  const headline = score >= 75 ? 'China Trade Relations Strained'
    : score >= 60 ? 'Elevated China Risk'
    : score >= 45 ? 'Monitoring China Developments'
    : score >= 30 ? 'Constructive China Outlook'
    : 'China Trade Relations Stable'

  return { score: Math.round(score * 10) / 10, level, regime, headline }
}

function scoreTariffThreat(tpu: number, emv: number | null): { score: number; level: string; regime: string; headline: string } {
  let score: number, level: string, regime: string

  if (tpu < TPU.CALM) { score = 15; level = 'Trade Calm'; regime = 'trade_calm' }
  else if (tpu < TPU.NORMAL) { score = 15 + ((tpu - TPU.CALM) / (TPU.NORMAL - TPU.CALM)) * 25; level = 'Normal'; regime = 'normal_uncertainty' }
  else if (tpu < TPU.ELEVATED) { score = 40 + ((tpu - TPU.NORMAL) / (TPU.ELEVATED - TPU.NORMAL)) * 20; level = 'Elevated'; regime = 'tariff_threats' }
  else if (tpu < TPU.HIGH) { score = 60 + ((tpu - TPU.ELEVATED) / (TPU.HIGH - TPU.ELEVATED)) * 20; level = 'High'; regime = 'tariff_war' }
  else if (tpu < TPU.EXTREME) { score = 80 + ((tpu - TPU.HIGH) / (TPU.EXTREME - TPU.HIGH)) * 12; level = 'Extreme'; regime = 'extreme_disruption' }
  else { score = 95; level = 'Trade War'; regime = 'extreme_disruption' }

  if (emv !== null) {
    if (emv > 400) score += 10
    else if (emv > 200) score += 5
    else if (emv < 50) score -= 5
  }
  score = Math.max(0, Math.min(100, score))

  const headline = score >= 80 ? 'Trade War Escalating'
    : score >= 65 ? 'Tariff Threats Active'
    : score >= 50 ? 'Tariff Uncertainty Elevated'
    : score >= 35 ? 'Moderate Trade Policy Noise'
    : 'Trade Policy Calm'

  return { score: Math.round(score * 10) / 10, level, regime, headline }
}

// =============================================================================
// MAIN API HANDLER - Uses correct table names
// =============================================================================

export async function GET() {
  try {
    const [vixRows, crushRows, cnyRows, fxiRows, bdryRows, tpuRows] = await Promise.all([
      // VIX from econ.vol_indices_1d
      query<{ vix: number }>(`
        SELECT value::float8 as vix FROM econ.vol_indices_1d
        WHERE series_id = 'VIXCLS' AND value IS NOT NULL
        ORDER BY event_date DESC LIMIT 1
      `),

      // Board Crush from analytics.board_crush_1d (correct table!)
      query<{ crush: number; oil_share: number | null }>(`
        SELECT board_crush::float8 as crush, oil_share::float8 as oil_share
        FROM analytics.board_crush_1d
        WHERE board_crush IS NOT NULL
        ORDER BY trade_date DESC LIMIT 1
      `),

      // CNY from mkt.fx_1d (correct table and column!)
      query<{ rate: number }>(`
        SELECT rate::float8 as rate FROM mkt.fx_1d
        WHERE pair IN ('USD/CNY', 'USDCNY') AND rate IS NOT NULL
        ORDER BY event_date DESC LIMIT 1
      `),

      // FXI changes from mkt.etf_1d
      query<{ change_20d: number; change_5d: number; price: number }>(`
        WITH fxi AS (
          SELECT close, ROW_NUMBER() OVER (ORDER BY event_date DESC) as rn
          FROM mkt.etf_1d WHERE symbol = 'FXI' AND close IS NOT NULL
          ORDER BY event_date DESC LIMIT 21
        )
        SELECT
          (SELECT close FROM fxi WHERE rn = 1)::float8 as price,
          CASE WHEN (SELECT close FROM fxi WHERE rn = 21) > 0
               THEN ((SELECT close FROM fxi WHERE rn = 1) - (SELECT close FROM fxi WHERE rn = 21)) / (SELECT close FROM fxi WHERE rn = 21)
               ELSE 0 END::float8 as change_20d,
          CASE WHEN (SELECT close FROM fxi WHERE rn = 6) > 0
               THEN ((SELECT close FROM fxi WHERE rn = 1) - (SELECT close FROM fxi WHERE rn = 6)) / (SELECT close FROM fxi WHERE rn = 6)
               ELSE 0 END::float8 as change_5d
      `),

      // BDRY changes
      query<{ change_20d: number }>(`
        WITH bdry AS (
          SELECT close, ROW_NUMBER() OVER (ORDER BY event_date DESC) as rn
          FROM mkt.etf_1d WHERE symbol = 'BDRY' AND close IS NOT NULL
          ORDER BY event_date DESC LIMIT 21
        )
        SELECT CASE WHEN (SELECT close FROM bdry WHERE rn = 21) > 0
               THEN ((SELECT close FROM bdry WHERE rn = 1) - (SELECT close FROM bdry WHERE rn = 21)) / (SELECT close FROM bdry WHERE rn = 21)
               ELSE 0 END::float8 as change_20d
      `),

      // TPU and EMV from econ.vol_indices_1d
      query<{ tpu: number; emv: number | null }>(`
        SELECT
          (SELECT value FROM econ.vol_indices_1d WHERE series_id = 'EPUTRADE' AND value IS NOT NULL ORDER BY event_date DESC LIMIT 1)::float8 as tpu,
          (SELECT value FROM econ.vol_indices_1d WHERE series_id = 'EMVTRADEPOLEMV' AND value IS NOT NULL ORDER BY event_date DESC LIMIT 1)::float8 as emv
      `),
    ])

    // Extract with defaults
    const vixValue = vixRows[0]?.vix ?? 20
    const crushValue = crushRows[0]?.crush ?? 1.50
    const oilShareValue = crushRows[0]?.oil_share ?? null
    const cnyRate = cnyRows[0]?.rate ?? 7.25
    const fxiChange20d = fxiRows[0]?.change_20d ?? 0
    const fxiChange5d = fxiRows[0]?.change_5d ?? 0
    const fxiPrice = fxiRows[0]?.price ?? 0
    const bdryChange20d = bdryRows[0]?.change_20d ?? null
    const tpuValue = tpuRows[0]?.tpu ?? 100
    const emvValue = tpuRows[0]?.emv ?? null

    // Calculate scores
    const vixResult = scoreVixStress(vixValue)
    const crushResult = scoreCrushPressure(crushValue, oilShareValue)
    const chinaResult = scoreChinaTension(cnyRate, fxiChange20d, fxiChange5d, bdryChange20d)
    const tariffResult = scoreTariffThreat(tpuValue, emvValue)

    return NextResponse.json({
      as_of_date: new Date().toISOString().split('T')[0],
      drivers: {
        vix_stress: {
          name: 'VIX Stress',
          score: vixResult.score,
          level: vixResult.level,
          regime: vixResult.regime,
          headline: vixResult.headline,
          components: { vix_value: Math.round(vixValue * 10) / 10 },
        },
        crush_pressure: {
          name: 'Crush Pressure',
          score: crushResult.score,
          level: crushResult.level,
          regime: crushResult.regime,
          headline: crushResult.headline,
          components: {
            board_crush_value: Math.round(crushValue * 100) / 100,
            oil_share_value: oilShareValue ? Math.round(oilShareValue * 1000) / 1000 : null,
          },
        },
        china_tension: {
          name: 'China Tension',
          score: chinaResult.score,
          level: chinaResult.level,
          regime: chinaResult.regime,
          headline: chinaResult.headline,
          components: {
            cny_rate: Math.round(cnyRate * 100) / 100,
            fxi_change_20d: Math.round(fxiChange20d * 1000) / 10,
            fxi_price: Math.round(fxiPrice * 100) / 100,
          },
        },
        tariff_threat: {
          name: 'Tariff Threat',
          score: tariffResult.score,
          level: tariffResult.level,
          regime: tariffResult.regime,
          headline: tariffResult.headline,
          components: {
            tpu_value: Math.round(tpuValue),
            emv_value: emvValue ? Math.round(emvValue) : null,
          },
        },
      },
      summary: {
        average_pressure: Math.round((vixResult.score + crushResult.score + chinaResult.score + tariffResult.score) / 4 * 10) / 10,
        highest_pressure: [
          { name: 'VIX Stress', score: vixResult.score },
          { name: 'Crush Pressure', score: crushResult.score },
          { name: 'China Tension', score: chinaResult.score },
          { name: 'Tariff Threat', score: tariffResult.score },
        ].sort((a, b) => b.score - a.score)[0],
        alert_count: [vixResult.score, crushResult.score, chinaResult.score, tariffResult.score].filter(s => s >= 65).length,
      },
    })
  } catch (error) {
    console.error('Market drivers query failed:', error)
    return NextResponse.json({ error: 'Market drivers query failed', details: String(error) }, { status: 500 })
  }
}
