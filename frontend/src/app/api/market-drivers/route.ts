import { NextResponse } from 'next/server'
import { query } from '@/lib/db'

export const dynamic = 'force-dynamic'

// =============================================================================
// DOMAIN-SPECIFIC THRESHOLDS
// These match the Python pressure calculators exactly
// =============================================================================

// VIX Thresholds (absolute levels, not percentiles)
const VIX = {
  COMPLACENT: 12,
  LOW: 15,
  NORMAL: 20,
  ELEVATED: 25,
  HIGH: 30,
  EXTREME: 40,
}

// Board Crush Economics ($/bushel thresholds)
const CRUSH = {
  DANGER: 0.75,      // Margin collapse - processors losing money
  SEVERE: 1.00,      // Severe stress
  TIGHT: 1.25,       // Tight margins
  NEUTRAL: 1.50,     // Breakeven zone
  HEALTHY: 1.75,     // Healthy margins
  STRONG: 2.00,      // Strong margins
  EXCEPTIONAL: 2.50, // Exceptional
}

// CNY/USD Thresholds
const CNY = {
  STRONG: 7.00,  // Psychologically important level
  NORMAL: 7.15,
  WEAK: 7.30,
  STRESS: 7.45,
  CRISIS: 7.60,
}

// Trade Policy Uncertainty (Baker-Bloom-Davis)
const TPU = {
  CALM: 40,
  NORMAL: 100,
  ELEVATED: 200,
  HIGH: 400,
  EXTREME: 700,
}

// =============================================================================
// SCORING FUNCTIONS
// =============================================================================

function scoreVixStress(vix: number, vix3m: number | null): {
  score: number
  level: string
  regime: string
  headline: string
} {
  // Term structure: VIX/VIX3M ratio
  const termRatio = vix3m && vix3m > 0 ? vix / vix3m : 1.0

  let baseScore: number
  let level: string
  let regime: string

  if (vix <= VIX.COMPLACENT) {
    baseScore = 15
    level = 'Complacent'
    regime = 'complacent'
  } else if (vix <= VIX.LOW) {
    baseScore = 25
    level = 'Low Vol'
    regime = 'low_vol'
  } else if (vix <= VIX.NORMAL) {
    baseScore = 40
    level = 'Normal'
    regime = 'normal'
  } else if (vix <= VIX.ELEVATED) {
    baseScore = 55
    level = 'Elevated'
    regime = 'elevated'
  } else if (vix <= VIX.HIGH) {
    baseScore = 70
    level = 'High Vol'
    regime = 'high_vol'
  } else if (vix <= VIX.EXTREME) {
    baseScore = 85
    level = 'Fear'
    regime = 'fear'
  } else {
    baseScore = 95
    level = 'Extreme Fear'
    regime = 'extreme_fear'
  }

  // Adjust for term structure (backwardation = stress)
  let termAdj = 0
  if (termRatio > 1.05) {
    termAdj = 15  // Backwardation - acute stress
  } else if (termRatio > 1.0) {
    termAdj = 8   // Slight inversion
  } else if (termRatio < 0.85) {
    termAdj = -10 // Healthy contango
  }

  const score = Math.max(0, Math.min(100, baseScore + termAdj))

  let headline: string
  if (score >= 80) headline = 'Extreme Volatility Alert'
  else if (score >= 65) headline = 'Elevated Market Stress'
  else if (score >= 50) headline = 'Above-Normal Volatility'
  else if (score >= 35) headline = 'Normal Volatility Conditions'
  else headline = 'Low Volatility Environment'

  return { score: Math.round(score * 10) / 10, level, regime, headline }
}

function scoreCrushPressure(crush: number, oilShare: number | null): {
  score: number
  level: string
  regime: string
  headline: string
} {
  // Lower crush = MORE pressure (inverted scoring)
  let baseScore: number
  let level: string
  let regime: string

  if (crush >= CRUSH.EXCEPTIONAL) {
    baseScore = 10
    level = 'Exceptional Margins'
    regime = 'exceptional_margins'
  } else if (crush >= CRUSH.STRONG) {
    baseScore = 20
    level = 'Strong Margins'
    regime = 'strong_margins'
  } else if (crush >= CRUSH.HEALTHY) {
    baseScore = 30
    level = 'Healthy Margins'
    regime = 'healthy_margins'
  } else if (crush >= CRUSH.NEUTRAL) {
    baseScore = 45
    level = 'Neutral'
    regime = 'neutral'
  } else if (crush >= CRUSH.TIGHT) {
    baseScore = 60
    level = 'Tight Margins'
    regime = 'tight_margins'
  } else if (crush >= CRUSH.SEVERE) {
    baseScore = 75
    level = 'Severe Stress'
    regime = 'severe_stress'
  } else if (crush >= CRUSH.DANGER) {
    baseScore = 88
    level = 'Margin Collapse'
    regime = 'margin_collapse'
  } else {
    baseScore = 95
    level = 'Crisis'
    regime = 'crisis'
  }

  // Oil share adjustment (lower oil share = bearish for soyoil)
  let oilAdj = 0
  if (oilShare !== null) {
    if (oilShare < 0.42) oilAdj = 10       // Very low oil share - bearish
    else if (oilShare < 0.46) oilAdj = 5   // Below normal
    else if (oilShare > 0.52) oilAdj = -8  // High oil share - bullish
    else if (oilShare > 0.48) oilAdj = -3  // Above normal
  }

  const score = Math.max(0, Math.min(100, baseScore + oilAdj))

  let headline: string
  if (score >= 75) headline = 'Crush Economics Under Severe Stress'
  else if (score >= 55) headline = 'Processor Margins Tightening'
  else if (score >= 40) headline = 'Neutral Crush Economics'
  else if (score >= 25) headline = 'Healthy Processor Margins'
  else headline = 'Strong Crush Economics'

  return { score: Math.round(score * 10) / 10, level, regime, headline }
}

function scoreChinaTension(
  cny: number,
  fxiChange20d: number,
  fxiChange5d: number,
  bdryChange20d: number | null
): {
  score: number
  level: string
  regime: string
  headline: string
} {
  let score = 50  // Start neutral

  // CNY component (30%) - weak CNY = tension
  if (cny > CNY.CRISIS) score += 18
  else if (cny > CNY.STRESS) score += 12
  else if (cny > CNY.WEAK) score += 6
  else if (cny > CNY.NORMAL) score += 0
  else if (cny > CNY.STRONG) score -= 5
  else score -= 12  // Strong CNY = constructive

  // FXI 20-day component (35%) - China equity sentiment
  if (fxiChange20d < -0.15) score += 22
  else if (fxiChange20d < -0.10) score += 15
  else if (fxiChange20d < -0.05) score += 8
  else if (fxiChange20d < 0) score += 3
  else if (fxiChange20d > 0.10) score -= 15
  else if (fxiChange20d > 0.05) score -= 10
  else if (fxiChange20d > 0) score -= 5

  // FXI 5-day momentum (15%) - recent trend
  if (fxiChange5d < -0.05) score += 8
  else if (fxiChange5d < -0.02) score += 4
  else if (fxiChange5d > 0.05) score -= 8
  else if (fxiChange5d > 0.02) score -= 4

  // BDRY shipping (20%) - trade flow proxy
  if (bdryChange20d !== null) {
    if (bdryChange20d < -0.20) score += 12
    else if (bdryChange20d < -0.10) score += 6
    else if (bdryChange20d > 0.20) score -= 8
    else if (bdryChange20d > 0.10) score -= 4
  }

  score = Math.max(0, Math.min(100, score))

  let level: string
  let regime: string
  if (score >= 75) {
    level = 'High Tension'
    regime = 'high_tension'
  } else if (score >= 60) {
    level = 'Elevated'
    regime = 'elevated'
  } else if (score >= 45) {
    level = 'Watchful'
    regime = 'watchful'
  } else if (score >= 30) {
    level = 'Constructive'
    regime = 'constructive'
  } else {
    level = 'Optimistic'
    regime = 'optimistic'
  }

  let headline: string
  if (score >= 75) headline = 'China Trade Relations Strained'
  else if (score >= 60) headline = 'Elevated China Risk'
  else if (score >= 45) headline = 'Monitoring China Developments'
  else if (score >= 30) headline = 'Constructive China Outlook'
  else headline = 'China Trade Relations Stable'

  return { score: Math.round(score * 10) / 10, level, regime, headline }
}

function scoreTariffThreat(tpu: number, emv: number | null): {
  score: number
  level: string
  regime: string
  headline: string
} {
  let baseScore: number
  let level: string
  let regime: string

  if (tpu < TPU.CALM) {
    baseScore = 15
    level = 'Trade Calm'
    regime = 'trade_calm'
  } else if (tpu < TPU.NORMAL) {
    const pct = (tpu - TPU.CALM) / (TPU.NORMAL - TPU.CALM)
    baseScore = 15 + pct * 25
    level = 'Normal'
    regime = 'normal_uncertainty'
  } else if (tpu < TPU.ELEVATED) {
    const pct = (tpu - TPU.NORMAL) / (TPU.ELEVATED - TPU.NORMAL)
    baseScore = 40 + pct * 20
    level = 'Elevated'
    regime = 'tariff_threats'
  } else if (tpu < TPU.HIGH) {
    const pct = (tpu - TPU.ELEVATED) / (TPU.HIGH - TPU.ELEVATED)
    baseScore = 60 + pct * 20
    level = 'High'
    regime = 'tariff_war'
  } else if (tpu < TPU.EXTREME) {
    const pct = (tpu - TPU.HIGH) / (TPU.EXTREME - TPU.HIGH)
    baseScore = 80 + pct * 12
    level = 'Extreme'
    regime = 'extreme_disruption'
  } else {
    baseScore = 95
    level = 'Trade War'
    regime = 'extreme_disruption'
  }

  // EMV trade component adjustment
  let emvAdj = 0
  if (emv !== null) {
    if (emv > 400) emvAdj = 10
    else if (emv > 200) emvAdj = 5
    else if (emv < 50) emvAdj = -5
  }

  const score = Math.max(0, Math.min(100, baseScore + emvAdj))

  let headline: string
  if (score >= 80) headline = 'Trade War Escalating'
  else if (score >= 65) headline = 'Tariff Threats Active'
  else if (score >= 50) headline = 'Tariff Uncertainty Elevated'
  else if (score >= 35) headline = 'Moderate Trade Policy Noise'
  else headline = 'Trade Policy Calm'

  return { score: Math.round(score * 10) / 10, level, regime, headline }
}

// =============================================================================
// MAIN API HANDLER
// =============================================================================

type VixRow = { vix: number; vix3m: number | null }
type CrushRow = { crush: number; oil_share: number | null }
type CnyRow = { rate: number }
type FxiRow = { change_20d: number; change_5d: number; price: number }
type BdryRow = { change_20d: number }
type TpuRow = { tpu: number; emv: number | null }

export async function GET() {
  try {
    // Fetch all data in parallel for performance
    const [vixRows, crushRows, cnyRows, fxiRows, bdryRows, tpuRows] = await Promise.all([
      // VIX and VIX3M
      query<VixRow>(`
        SELECT
          (SELECT value FROM econ.vol_indices_1d WHERE series_id = 'VIXCLS' AND value IS NOT NULL ORDER BY event_date DESC LIMIT 1)::float8 as vix,
          (SELECT value FROM econ.vol_indices_1d WHERE series_id = 'VIX3M' AND value IS NOT NULL ORDER BY event_date DESC LIMIT 1)::float8 as vix3m
      `),

      // Board Crush and Oil Share
      query<CrushRow>(`
        SELECT
          crush::float8 as crush,
          oil_share::float8 as oil_share
        FROM mkt.board_crush_1d
        WHERE crush IS NOT NULL
        ORDER BY event_date DESC
        LIMIT 1
      `),

      // CNY/USD
      query<CnyRow>(`
        SELECT close::float8 as rate
        FROM econ.fx_1d
        WHERE series_id = 'DEXCHUS' AND close IS NOT NULL
        ORDER BY event_date DESC
        LIMIT 1
      `),

      // FXI changes
      query<FxiRow>(`
        WITH fxi AS (
          SELECT close, event_date,
                 ROW_NUMBER() OVER (ORDER BY event_date DESC) as rn
          FROM mkt.etf_1d
          WHERE symbol = 'FXI' AND close IS NOT NULL
          ORDER BY event_date DESC
          LIMIT 21
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

      // BDRY (Baltic Dry Index ETF) change
      query<BdryRow>(`
        WITH bdry AS (
          SELECT close,
                 ROW_NUMBER() OVER (ORDER BY event_date DESC) as rn
          FROM mkt.etf_1d
          WHERE symbol = 'BDRY' AND close IS NOT NULL
          ORDER BY event_date DESC
          LIMIT 21
        )
        SELECT
          CASE WHEN (SELECT close FROM bdry WHERE rn = 21) > 0
               THEN ((SELECT close FROM bdry WHERE rn = 1) - (SELECT close FROM bdry WHERE rn = 21)) / (SELECT close FROM bdry WHERE rn = 21)
               ELSE 0 END::float8 as change_20d
      `),

      // TPU and Trade EMV
      query<TpuRow>(`
        SELECT
          (SELECT value FROM econ.vol_indices_1d WHERE series_id = 'EPUTRADE' AND value IS NOT NULL ORDER BY event_date DESC LIMIT 1)::float8 as tpu,
          (SELECT value FROM econ.vol_indices_1d WHERE series_id = 'EMVTRADEPOLEMV' AND value IS NOT NULL ORDER BY event_date DESC LIMIT 1)::float8 as emv
      `),
    ])

    // Extract values with defaults
    const vixValue = vixRows[0]?.vix ?? 20
    const vix3mValue = vixRows[0]?.vix3m ?? null
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
    const vixResult = scoreVixStress(vixValue, vix3mValue)
    const crushResult = scoreCrushPressure(crushValue, oilShareValue)
    const chinaResult = scoreChinaTension(cnyRate, fxiChange20d, fxiChange5d, bdryChange20d)
    const tariffResult = scoreTariffThreat(tpuValue, emvValue)

    // Build response matching FastAPI format
    const response = {
      as_of_date: new Date().toISOString().split('T')[0],
      drivers: {
        vix_stress: {
          name: 'VIX Stress',
          score: vixResult.score,
          level: vixResult.level,
          regime: vixResult.regime,
          headline: vixResult.headline,
          components: {
            vix_value: Math.round(vixValue * 10) / 10,
            vix3m_value: vix3mValue ? Math.round(vix3mValue * 10) / 10 : null,
            term_ratio: vix3mValue ? Math.round((vixValue / vix3mValue) * 1000) / 1000 : null,
          },
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
            fxi_change_5d: Math.round(fxiChange5d * 1000) / 10,
            fxi_price: Math.round(fxiPrice * 100) / 100,
            bdry_change_20d: bdryChange20d ? Math.round(bdryChange20d * 1000) / 10 : null,
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
        average_pressure: Math.round(
          (vixResult.score + crushResult.score + chinaResult.score + tariffResult.score) / 4 * 10
        ) / 10,
        highest_pressure: [
          { name: 'VIX Stress', score: vixResult.score },
          { name: 'Crush Pressure', score: crushResult.score },
          { name: 'China Tension', score: chinaResult.score },
          { name: 'Tariff Threat', score: tariffResult.score },
        ].sort((a, b) => b.score - a.score)[0],
        alert_count: [vixResult.score, crushResult.score, chinaResult.score, tariffResult.score]
          .filter(s => s >= 65).length,
      },
    }

    return NextResponse.json(response)
  } catch (error) {
    console.error('Market drivers query failed:', error)
    return NextResponse.json(
      { error: 'Market drivers query failed', details: String(error) },
      { status: 500 }
    )
  }
}
