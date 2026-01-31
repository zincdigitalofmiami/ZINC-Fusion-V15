import { NextResponse } from 'next/server'
import { query } from '@/lib/db'
import { generateAIIntelligence, type MarketData } from '@/lib/ai-intelligence'
import { generateDriverIntel, generateFallbackDriverIntel } from '@/lib/ai-driver-intel'

export const dynamic = 'force-dynamic'

// =============================================================================
// DOMAIN-SPECIFIC THRESHOLDS
// These match the Python pressure calculators exactly
// =============================================================================

const VIX = { COMPLACENT: 12, LOW: 15, NORMAL: 20, ELEVATED: 25, HIGH: 30, EXTREME: 40 }
const OVX = { LOW: 25, NORMAL: 35, ELEVATED: 50, HIGH: 70 }  // Oil Volatility - biodiesel link
const CRUSH = { DANGER: 0.75, SEVERE: 1.00, TIGHT: 1.25, NEUTRAL: 1.50, HEALTHY: 1.75, STRONG: 2.00, EXCEPTIONAL: 2.50 }
const CNY = { STRONG: 7.00, NORMAL: 7.15, WEAK: 7.30, STRESS: 7.45, CRISIS: 7.60 }
const TPU = { CALM: 40, NORMAL: 100, ELEVATED: 200, HIGH: 400, EXTREME: 700 }

// =============================================================================
// SCORING FUNCTIONS
// =============================================================================

function scoreVixStress(vix: number, ovx: number | null): { score: number; level: string; regime: string; headline: string } {
  let score: number, level: string, regime: string

  // VIX Level scoring (primary - 70% weight)
  if (vix <= VIX.COMPLACENT) { score = 15; level = 'Complacent'; regime = 'complacent' }
  else if (vix <= VIX.LOW) { score = 25; level = 'Low Vol'; regime = 'low_vol' }
  else if (vix <= VIX.NORMAL) { score = 40; level = 'Normal'; regime = 'normal' }
  else if (vix <= VIX.ELEVATED) { score = 55; level = 'Elevated'; regime = 'elevated' }
  else if (vix <= VIX.HIGH) { score = 70; level = 'High Vol'; regime = 'high_vol' }
  else if (vix <= VIX.EXTREME) { score = 85; level = 'Fear'; regime = 'fear' }
  else { score = 95; level = 'Extreme Fear'; regime = 'extreme_fear' }

  // OVX adjustment (30% weight) - oil volatility → biodiesel margin uncertainty → ZL
  if (ovx !== null) {
    if (ovx >= OVX.HIGH) score += 12        // Energy panic → ZL follows
    else if (ovx >= OVX.ELEVATED) score += 6 // Elevated oil vol
    else if (ovx >= OVX.NORMAL) score += 0   // Normal
    else if (ovx < OVX.LOW) score -= 5       // Calm energy = stable ZL
  }
  score = Math.max(0, Math.min(100, score))

  // Soy-centric headlines - VIX/OVX transmission to ZL via risk-off flows
  // NO "hedge" language - this is about FUND FLOWS and LIQUIDITY
  const headline = score >= 80 ? 'ZL Gap Risk - Risk-Off Panic'
    : score >= 65 ? 'Fund Liquidation Risk - ZL Selling Pressure'
    : score >= 50 ? 'Elevated Vol - Watch ZL Spreads'
    : score >= 35 ? 'Normal Vol - ZL on Fundamentals'
    : 'Low Vol - Stable ZL Trading'

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

  // Soy-centric headlines - Crush margin impact on ZL
  const headline = score >= 75 ? 'ZL Mixed - Crush Plants Idling'
    : score >= 55 ? 'ZL Cautious - Processor Margins Squeezed'
    : score >= 40 ? 'ZL Neutral - Balanced Crush Economics'
    : score >= 25 ? 'ZL Supportive - Healthy Crush Margins'
    : 'ZL Watch Demand - Max Crush Running'

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

  // Soy-centric headlines - China export demand for US soy
  const headline = score >= 75 ? 'ZL Bearish - Soy Export Demand Cliff'
    : score >= 60 ? 'ZL Cautious - Trade War Risk Elevated'
    : score >= 45 ? 'Watch USDA Export Sales Closely'
    : score >= 30 ? 'China Buying - Soy Exports Healthy'
    : 'Strong China Demand for US Soy'

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

  // Soy-centric headlines - Tariff impact on soy exports
  const headline = score >= 80 ? 'ZL Bearish - Soy Tariffs Active'
    : score >= 65 ? 'ZL Cautious - Retaliatory Tariff Risk'
    : score >= 50 ? 'Soy Export Sales Pace Uncertain'
    : score >= 35 ? 'Normal Soy Trade Policy Noise'
    : 'Soy Trade Policy Calm - Bullish Backdrop'

  return { score: Math.round(score * 10) / 10, level, regime, headline }
}

// =============================================================================
// NARRATIVE GENERATOR - AI-style market intelligence
// =============================================================================

interface DriverResult {
  score: number
  level: string
  regime: string
  headline: string
}

function generateMarketIntelligence(
  vix: DriverResult, vixValue: number,
  crush: DriverResult, crushValue: number, oilShare: number | null,
  china: DriverResult, cnyRate: number, fxiChange20d: number,
  tariff: DriverResult, tpuValue: number
): {
  headline: string
  summary: string
  drivers: { label: string; outlook: string; detail: string }[]
  zlOutlook: 'BULLISH' | 'NEUTRAL' | 'CAUTIOUS' | 'BEARISH'
  zlColor: string
} {
  const avgScore = (vix.score + crush.score + china.score + tariff.score) / 4
  const highPressureCount = [vix.score, crush.score, china.score, tariff.score].filter(s => s >= 65).length

  // Determine overall ZL outlook
  let zlOutlook: 'BULLISH' | 'NEUTRAL' | 'CAUTIOUS' | 'BEARISH'
  let zlColor: string
  let headline: string

  if (avgScore >= 70 || highPressureCount >= 3) {
    zlOutlook = 'BEARISH'
    zlColor = '#EF4444'
    headline = 'Multiple Headwinds for Soybean Oil'
  } else if (avgScore >= 55 || highPressureCount >= 2) {
    zlOutlook = 'CAUTIOUS'
    zlColor = '#F97316'
    headline = 'Mixed Signals for ZL - Proceed Carefully'
  } else if (avgScore >= 40) {
    zlOutlook = 'NEUTRAL'
    zlColor = '#EAB308'
    headline = 'Balanced Conditions for Soybean Oil'
  } else {
    zlOutlook = 'BULLISH'
    zlColor = '#22C55E'
    headline = 'Supportive Environment for ZL'
  }

  // Generate summary paragraph
  const summaryParts: string[] = []

  if (vix.score >= 65) {
    summaryParts.push(`VIX at ${vixValue.toFixed(1)} signals risk-off mode - fund liquidation pressure on ZL, wider spreads, potential gap risk.`)
  } else if (vix.score <= 30) {
    summaryParts.push(`Low VIX at ${vixValue.toFixed(1)} - stable ZL trading, fundamentals driving price action.`)
  }

  if (crush.score >= 65) {
    summaryParts.push(`Crush margins at $${crushValue.toFixed(2)}/bu are under severe pressure, which may force processor capacity cuts.`)
  } else if (crush.score <= 30) {
    summaryParts.push(`Strong crush economics at $${crushValue.toFixed(2)}/bu are driving high utilization rates.`)
  }

  if (china.score >= 65) {
    summaryParts.push(`China trade tensions are elevated with CNY at ${cnyRate.toFixed(2)} and FXI ${fxiChange20d >= 0 ? 'up' : 'down'} ${Math.abs(fxiChange20d * 100).toFixed(1)}% over 20 days, threatening soy export demand.`)
  } else if (china.score <= 30) {
    summaryParts.push(`China demand outlook is constructive with stable trade flows.`)
  }

  if (tariff.score >= 65) {
    summaryParts.push(`Trade Policy Uncertainty at ${tpuValue.toFixed(0)} signals active tariff risk to soy exports.`)
  } else if (tariff.score <= 30) {
    summaryParts.push(`Trade policy is calm, supporting normal soy export flows.`)
  }

  if (summaryParts.length === 0) {
    summaryParts.push(`Market conditions are balanced across all four key drivers. ZL is trading primarily on fundamentals.`)
  }

  // Generate driver-specific bullets
  const drivers = [
    {
      label: 'Volatility',
      outlook: vix.score >= 65 ? 'PRESSURE' : vix.score <= 35 ? 'SUPPORTIVE' : 'NEUTRAL',
      detail: vix.score >= 65
        ? `VIX at ${vixValue.toFixed(1)} - risk-off flows pressuring ZL, watch for liquidation`
        : vix.score <= 35
        ? `VIX at ${vixValue.toFixed(1)} - stable conditions, ZL trading on fundamentals`
        : `VIX at ${vixValue.toFixed(1)} - normal volatility, standard trading conditions`
    },
    {
      label: 'Crush',
      outlook: crush.score >= 65 ? 'MIXED' : crush.score <= 35 ? 'WATCH SUPPLY' : 'NEUTRAL',
      detail: crush.score >= 65
        ? `Board crush $${crushValue.toFixed(2)} - margins squeezed, processor slowdowns possible`
        : crush.score <= 35
        ? `Board crush $${crushValue.toFixed(2)} - max crush running, heavy oil supply`
        : `Board crush $${crushValue.toFixed(2)} - balanced processor economics`
    },
    {
      label: 'China',
      outlook: china.score >= 65 ? 'BEARISH' : china.score <= 35 ? 'BULLISH' : 'MONITOR',
      detail: china.score >= 65
        ? `CNY ${cnyRate.toFixed(2)}, FXI ${fxiChange20d >= 0 ? '+' : ''}${(fxiChange20d * 100).toFixed(1)}% - export demand at risk`
        : china.score <= 35
        ? `CNY ${cnyRate.toFixed(2)} - China buying actively, strong export pace`
        : `CNY ${cnyRate.toFixed(2)} - watching trade headlines, normal export flow`
    },
    {
      label: 'Tariff',
      outlook: tariff.score >= 65 ? 'BEARISH' : tariff.score <= 35 ? 'CALM' : 'NOISE',
      detail: tariff.score >= 65
        ? `TPU ${tpuValue.toFixed(0)} - tariff war risk, Gulf basis vulnerable`
        : tariff.score <= 35
        ? `TPU ${tpuValue.toFixed(0)} - trade policy calm, bullish backdrop`
        : `TPU ${tpuValue.toFixed(0)} - normal policy noise, no immediate threat`
    }
  ]

  return {
    headline,
    summary: summaryParts.join(' '),
    drivers,
    zlOutlook,
    zlColor
  }
}

// =============================================================================
// MAIN API HANDLER - Uses correct table names
// =============================================================================

export async function GET() {
  try {
    const [vixRows, ovxRows, crushRows, cnyRows, fxiRows, bdryRows, tpuRows] = await Promise.all([
      // VIX from econ.vol_indices_1d
      query<{ vix: number }>(`
        SELECT value::float8 as vix FROM econ.vol_indices_1d
        WHERE series_id = 'VIXCLS' AND value IS NOT NULL
        ORDER BY event_date DESC LIMIT 1
      `),

      // OVX (Oil Volatility) - critical for biodiesel/ZL link
      query<{ ovx: number }>(`
        SELECT value::float8 as ovx FROM econ.vol_indices_1d
        WHERE series_id = 'OVXCLS' AND value IS NOT NULL
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
    const ovxValue = ovxRows[0]?.ovx ?? null  // Oil Volatility Index
    const crushValue = crushRows[0]?.crush ?? 1.50
    const oilShareValue = crushRows[0]?.oil_share ?? null
    const cnyRate = cnyRows[0]?.rate ?? 7.25
    const fxiChange20d = fxiRows[0]?.change_20d ?? 0
    const fxiChange5d = fxiRows[0]?.change_5d ?? 0
    const fxiPrice = fxiRows[0]?.price ?? 0
    const bdryChange20d = bdryRows[0]?.change_20d ?? null
    const tpuValue = tpuRows[0]?.tpu ?? 100
    const emvValue = tpuRows[0]?.emv ?? null

    // Dashboard date (for freshness tracking)
    const asOfDate = new Date().toISOString().split('T')[0]

    // Calculate scores
    const vixResult = scoreVixStress(vixValue, ovxValue)
    const crushResult = scoreCrushPressure(crushValue, oilShareValue)
    const chinaResult = scoreChinaTension(cnyRate, fxiChange20d, fxiChange5d, bdryChange20d)
    const tariffResult = scoreTariffThreat(tpuValue, emvValue)

    // Generate market intelligence narrative (rule-based fallback)
    const ruleBasedIntelligence = generateMarketIntelligence(
      vixResult, vixValue,
      crushResult, crushValue, oilShareValue,
      chinaResult, cnyRate, fxiChange20d,
      tariffResult, tpuValue
    )

    // Prepare data for AI intelligence
    const marketData: MarketData = {
      vix: vixValue,
      ovx: ovxValue,
      boardCrush: crushValue,
      oilShare: oilShareValue,
      cnyRate: cnyRate,
      fxiChange20d: fxiChange20d,
      fxiChange5d: fxiChange5d,
      bdryChange20d: bdryChange20d,
      tpu: tpuValue,
      emv: emvValue,
      scores: {
        vix: vixResult.score,
        crush: crushResult.score,
        china: chinaResult.score,
        tariff: tariffResult.score,
      },
      asOfDate,  // For freshness tracking
    }

    // Generate AI-powered intelligence (with fallback)
    const aiIntelligence = await generateAIIntelligence(marketData)
      .catch(() => null) // Silent fallback on error

    // Use AI if available, otherwise use rule-based
    const intelligence = aiIntelligence ? {
      headline: aiIntelligence.headline,
      summary: aiIntelligence.reasoning,
      drivers: [
        ...aiIntelligence.keyRisks.map(r => ({ label: 'Risk', outlook: 'PRESSURE' as const, detail: r })),
        ...aiIntelligence.keySupports.map(s => ({ label: 'Support', outlook: 'SUPPORTIVE' as const, detail: s })),
      ],
      zlOutlook: aiIntelligence.zlOutlook,
      zlColor: aiIntelligence.zlOutlook === 'BEARISH' ? '#EF4444' :
               aiIntelligence.zlOutlook === 'CAUTIOUS' ? '#F97316' :
               aiIntelligence.zlOutlook === 'NEUTRAL' ? '#EAB308' : '#22C55E',
      tradingImplication: aiIntelligence.tradingImplication,
      aiPowered: true,
    } : {
      ...ruleBasedIntelligence,
      aiPowered: false,
    }

    // Generate per-driver "What's Happening?" intel (parallel)
    const [vixIntel, crushIntel, chinaIntel, tariffIntel] = await Promise.all([
      generateDriverIntel({
        driverName: 'vix',
        score: vixResult.score,
        level: vixResult.level,
        regime: vixResult.regime,
        components: { vix_value: vixValue, ovx_value: ovxValue },
        asOfDate,
      }).catch(() => null),
      generateDriverIntel({
        driverName: 'crush',
        score: crushResult.score,
        level: crushResult.level,
        regime: crushResult.regime,
        components: { board_crush: crushValue, oil_share: oilShareValue },
        asOfDate,
      }).catch(() => null),
      generateDriverIntel({
        driverName: 'china',
        score: chinaResult.score,
        level: chinaResult.level,
        regime: chinaResult.regime,
        components: { cny_rate: cnyRate, fxi_change_20d: fxiChange20d, bdry_change_20d: bdryChange20d },
        asOfDate,
      }).catch(() => null),
      generateDriverIntel({
        driverName: 'tariff',
        score: tariffResult.score,
        level: tariffResult.level,
        regime: tariffResult.regime,
        components: { tpu: tpuValue, emv: emvValue },
        asOfDate,
      }).catch(() => null),
    ])

    // Use AI intel or fallback
    const vixWhatsHappening = vixIntel ?? generateFallbackDriverIntel({
      driverName: 'vix', score: vixResult.score, level: vixResult.level, regime: vixResult.regime,
      components: { vix_value: vixValue }, asOfDate
    })
    const crushWhatsHappening = crushIntel ?? generateFallbackDriverIntel({
      driverName: 'crush', score: crushResult.score, level: crushResult.level, regime: crushResult.regime,
      components: { board_crush: crushValue }, asOfDate
    })
    const chinaWhatsHappening = chinaIntel ?? generateFallbackDriverIntel({
      driverName: 'china', score: chinaResult.score, level: chinaResult.level, regime: chinaResult.regime,
      components: { cny_rate: cnyRate }, asOfDate
    })
    const tariffWhatsHappening = tariffIntel ?? generateFallbackDriverIntel({
      driverName: 'tariff', score: tariffResult.score, level: tariffResult.level, regime: tariffResult.regime,
      components: { tpu: tpuValue }, asOfDate
    })

    return NextResponse.json({
      as_of_date: asOfDate,  // Use consistent timestamp
      drivers: {
        vix_stress: {
          name: 'VIX Stress',
          score: vixResult.score,
          level: vixResult.level,
          regime: vixResult.regime,
          headline: vixResult.headline,
          components: {
            vix_value: Math.round(vixValue * 10) / 10,
            ovx_value: ovxValue ? Math.round(ovxValue * 10) / 10 : null,
          },
          whatsHappening: vixWhatsHappening,
          aiPowered: vixIntel !== null,
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
          whatsHappening: crushWhatsHappening,
          aiPowered: crushIntel !== null,
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
          whatsHappening: chinaWhatsHappening,
          aiPowered: chinaIntel !== null,
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
          whatsHappening: tariffWhatsHappening,
          aiPowered: tariffIntel !== null,
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
      intelligence,
    })
  } catch (error) {
    console.error('Market drivers query failed:', error)
    return NextResponse.json({ error: 'Market drivers query failed', details: String(error) }, { status: 500 })
  }
}
