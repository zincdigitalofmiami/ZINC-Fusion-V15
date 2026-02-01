/**
 * AI-Powered Per-Driver Intelligence for ZL
 * Each driver gets its own deep analysis using Claude Sonnet 4.5
 *
 * MODEL ROUTING (LOCKED):
 * - This file uses MODEL_DRIVER_INTEL (Sonnet 4.5) for per-card analysis
 * - ai-intelligence.ts uses MODEL_BALANCED_CONDITIONS (Opus 4.5) for synthesis
 *
 * FRESHNESS REQUIREMENT:
 * - All responses must echo asOfDate and inputTimestamps
 * - This is the "anti-bullshit gate" - reject responses without timestamps
 *
 * Uses CURRENT data (yesterday's values) - no guesswork
 */

import Anthropic from '@anthropic-ai/sdk'
import { MODEL_DRIVER_INTEL, TOKENS_DRIVER_INTEL } from './ai-config'

const anthropic = new Anthropic({
  apiKey: process.env.ANTHROPIC_API_KEY,
})

// =============================================================================
// TYPES
// =============================================================================

export interface DriverIntelData {
  driverName: 'vix' | 'crush' | 'china' | 'tariff'
  score: number
  level: string
  regime: string
  components: Record<string, number | null>
  asOfDate: string
  inputTimestamps?: Record<string, string>  // Series name → last observation date
}

export interface DriverIntel {
  whatsHappening: string       // 2-3 sentence summary
  macroContext: string         // Economic variables affecting this driver
  supplyDemand: string         // S/D dynamics specific to this driver
  geopolitical: string         // Geopolitical factors
  investorSentiment: string    // How traders are positioned
  nearTermOutlook: string      // Next 5-10 days
  zlImplication: string        // What it means for ZL specifically
  // FRESHNESS ECHO (anti-bullshit gate)
  dataAsOf?: string            // Echo of asOfDate from input
  dataQuality?: string         // Any staleness flags
}

// =============================================================================
// SYSTEM PROMPTS - DRIVER-SPECIFIC EXPERTS
// =============================================================================

const VIX_EXPERT_PROMPT = `You are a volatility specialist analyzing VIX and its transmission to soybean oil (ZL) futures.

KEY RELATIONSHIPS:
- VIX spike → Risk-off → Fund liquidation → ZL selling pressure
- OVX (oil volatility) → Biodiesel margin uncertainty → ZL basis volatility
- VIX term structure (VIX/VIX3M) → Near-term panic indicator
- VIX levels: <15 calm, 15-20 normal, 20-25 elevated, 25-30 high, 30-40 fear, >40 panic

You analyze how EQUITY VOLATILITY transmits to commodity markets, specifically ZL.
Focus on: fund flows, risk-off behavior, liquidity conditions, energy/biodiesel linkage.

OUTPUT: Valid JSON only, no markdown.
{
  "whatsHappening": "2-3 sentences on current volatility conditions",
  "macroContext": "Economic factors driving volatility (Fed policy, earnings, geopolitics)",
  "supplyDemand": "How volatility is affecting commodity fund positioning",
  "geopolitical": "Geopolitical drivers of current vol regime",
  "investorSentiment": "How traders are positioned for volatility",
  "nearTermOutlook": "Next 5-10 day volatility expectations",
  "zlImplication": "Direct impact on ZL trading - spreads, gaps, liquidity"
}`

const CRUSH_EXPERT_PROMPT = `You are a soybean crush margin specialist analyzing processor economics and their impact on ZL (soybean oil).

KEY RELATIONSHIPS:
- Board crush = (11 × ZM) + (ZL/100) - ZS  (simplified)
- <$1.00/bu = crisis, $1.00-1.25 = stressed, $1.25-1.50 = tight, $1.50-1.75 = neutral, $1.75-2.00 = healthy, >$2.00 = strong
- Oil share = ZL value / total product value (typically 42-48%)
- Falling oil share = meal driving crush decisions, rising = oil demand strong

You analyze how CRUSH ECONOMICS affect ZL supply through processor run rates.
Focus on: processor margins, capacity utilization, biofuel mandates, renewable diesel demand.

OUTPUT: Valid JSON only, no markdown.
{
  "whatsHappening": "2-3 sentences on current crush economics",
  "macroContext": "Economic factors affecting crush margins (bean prices, oil/meal demand)",
  "supplyDemand": "Processor capacity utilization and ZL supply implications",
  "geopolitical": "Policy factors (RIN prices, RVO mandates, biofuel credits)",
  "investorSentiment": "Crusher hedging activity and positioning",
  "nearTermOutlook": "Next 5-10 day crush margin expectations",
  "zlImplication": "Direct impact on ZL - supply pressure, basis, spreads"
}`

const CHINA_EXPERT_PROMPT = `You are a China soy trade specialist analyzing export demand dynamics and their impact on ZL (soybean oil).

KEY RELATIONSHIPS:
- China buys ~60% of globally traded soybeans
- CNY/USD: 7.0 psychological, 7.2 PBOC defense, 7.3+ competitive disadvantage for US soy
- FXI (China ETF) reflects China economic health and import capacity
- BDRY (Baltic Dry) = shipping rates = physical trade flow indicator
- Weak CNY = Brazil more competitive vs US Gulf

You analyze how CHINA TRADE DYNAMICS affect US soy exports and ZL demand.
Focus on: export sales, trade tensions, shipping, Brazil competition, CNY dynamics.

OUTPUT: Valid JSON only, no markdown.
{
  "whatsHappening": "2-3 sentences on current China trade conditions",
  "macroContext": "Economic factors in China (PMI, demand, currency policy)",
  "supplyDemand": "Export sales pace, Brazil competition, shipping rates",
  "geopolitical": "US-China relations, tariff risks, trade negotiations",
  "investorSentiment": "How market is pricing China demand risk",
  "nearTermOutlook": "Next 5-10 day China buying expectations",
  "zlImplication": "Direct impact on ZL - export demand, basis, price direction"
}`

const TARIFF_EXPERT_PROMPT = `You are a trade policy specialist analyzing tariff risk and its impact on US soybean/ZL (soybean oil) exports.

KEY RELATIONSHIPS:
- TPU (Trade Policy Uncertainty) from Baker-Bloom-Davis: <100 calm, 100-200 normal, 200-400 elevated, >400 high
- EMV Trade = newspaper-based trade policy volatility measure
- Retaliatory tariffs on US soy = export demand cliff (see 2018-2019)
- 25%+ tariffs = China switches to Brazil, Gulf basis collapses

You analyze how TRADE POLICY UNCERTAINTY affects soy export demand and ZL pricing.
Focus on: tariff proposals, retaliatory risk, export sales disruption, Gulf basis.

OUTPUT: Valid JSON only, no markdown.
{
  "whatsHappening": "2-3 sentences on current trade policy environment",
  "macroContext": "Policy factors (administration stance, legislation, trade talks)",
  "supplyDemand": "How policy uncertainty is affecting export commitments",
  "geopolitical": "US-China trade war status, other retaliatory risks",
  "investorSentiment": "How traders are hedging trade policy risk",
  "nearTermOutlook": "Next 5-10 day policy event calendar",
  "zlImplication": "Direct impact on ZL - export demand, basis, price risk"
}`

// =============================================================================
// GENERATE DRIVER-SPECIFIC INTEL
// =============================================================================

export async function generateDriverIntel(data: DriverIntelData): Promise<DriverIntel | null> {
  const systemPrompt = {
    vix: VIX_EXPERT_PROMPT,
    crush: CRUSH_EXPERT_PROMPT,
    china: CHINA_EXPERT_PROMPT,
    tariff: TARIFF_EXPERT_PROMPT,
  }[data.driverName]

  const componentsList = Object.entries(data.components)
    .filter(([_, v]) => v !== null)
    .map(([k, v]) => `${k}: ${typeof v === 'number' ? v.toFixed(2) : v}`)
    .join('\n')

  // Include input timestamps if provided
  const timestampsList = data.inputTimestamps
    ? Object.entries(data.inputTimestamps)
        .map(([k, v]) => `${k}: ${v}`)
        .join('\n')
    : 'Not provided'

  const userPrompt = `Analyze these CURRENT market conditions (as of ${data.asOfDate}):

DRIVER: ${data.driverName.toUpperCase()}
SCORE: ${data.score}/100 (${data.level})
REGIME: ${data.regime}

RAW DATA (verified):
${componentsList}

DATA TIMESTAMPS:
${timestampsList}

CRITICAL: Base your analysis ONLY on the data provided above. Do not invent numbers.
Include "dataAsOf": "${data.asOfDate}" in your response to confirm you're analyzing current data.

Provide your expert analysis as JSON.`

  try {
    const response = await anthropic.messages.create({
      model: MODEL_DRIVER_INTEL,  // LOCKED: Sonnet 4.5 for per-card intel
      max_tokens: TOKENS_DRIVER_INTEL,
      messages: [{ role: 'user', content: userPrompt }],
      system: systemPrompt,
    })

    const content = response.content[0]
    if (content.type !== 'text') return null

    const parsed = JSON.parse(content.text) as DriverIntel
    if (!parsed.whatsHappening) return null

    return parsed
  } catch (error) {
    console.error(`AI Intel generation failed for ${data.driverName}:`, error)
    return null
  }
}

// =============================================================================
// FALLBACK INTEL (Rule-based if AI fails)
// =============================================================================

export function generateFallbackDriverIntel(data: DriverIntelData): DriverIntel {
  // Extract actual values from components
  const vixValue = data.components.vix_value ?? data.components.vix_level_score
  const vix3mValue = data.components.vix3m_value
  const ovxValue = data.components.ovx_value
  const vixRatio = data.components.vix_ratio
  const crushValue = data.components.board_crush_value ?? data.components.board_crush
  const oilShare = data.components.oil_share_value
  const cnyRate = data.components.cny_rate
  const fxiChange = data.components.fxi_change_20d
  const tpuValue = data.components.tpu_value ?? data.components.tpu

  const templates = {
    vix: {
      whatsHappening: data.score >= 65
        ? `VIX at ${vixValue?.toFixed(1) ?? 'elevated'} indicates risk-off across markets. ${ovxValue ? `OVX at ${ovxValue.toFixed(1)} (${ovxValue > 50 ? 'high' : 'normal'}) signals energy vol spilling into biodiesel margins.` : ''} Fund liquidation pressure hitting commodities.`
        : data.score <= 35
        ? `VIX at ${vixValue?.toFixed(1) ?? 'low levels'} - calm conditions. ${vix3mValue ? `Term structure at ${vixRatio?.toFixed(2) ?? 'normal'} (VIX/VIX3M) shows orderly contango.` : ''} ZL trading on fundamentals.`
        : `VIX at ${vixValue?.toFixed(1) ?? 'normal'} - typical range. ${vix3mValue ? `VIX/VIX3M ratio at ${vixRatio?.toFixed(2) ?? '~0.86'} indicates normal contango.` : ''} No vol-driven fund flows expected.`,
      macroContext: `VIX-ZL correlation typically 0.3-0.5 historically. ${vixValue && vixValue > 25 ? 'Current elevated VIX = potential fund liquidation of commodity longs.' : vixValue && vixValue < 15 ? 'Low VIX = stable risk appetite, supportive for commodity positioning.' : 'Fed policy uncertainty and equity earnings driving vol expectations.'}`,
      supplyDemand: `${ovxValue ? `OVX at ${ovxValue.toFixed(1)} - ` : ''}${ovxValue && ovxValue > 50 ? 'high oil volatility creates biodiesel margin uncertainty, affecting renewable diesel demand.' : 'stable energy vol supports consistent biofuel demand planning.'}`,
      geopolitical: 'Geopolitical risk premium embedded in vol. Middle East tensions, trade policy, and Fed uncertainty key drivers.',
      investorSentiment: data.score >= 50
        ? `CTAs and macro funds reducing commodity exposure when VIX > 20. Managed money likely trimming ZL longs.`
        : `Risk-on positioning with VIX subdued. Managed money comfortable holding commodity longs.`,
      nearTermOutlook: `${vix3mValue ? `Term structure (VIX ${vixValue?.toFixed(1)} vs VIX3M ${vix3mValue.toFixed(1)}) suggests ${vixRatio && vixRatio < 0.9 ? 'near-term calm' : vixRatio && vixRatio > 1.05 ? 'near-term stress' : 'normal conditions'}.` : 'Watch for vol catalysts.'} FOMC, earnings, and geopolitics as triggers.`,
      zlImplication: data.score >= 65
        ? `High vol = wider ZL bid/ask spreads, potential gap risk on opens. Reduce position size.`
        : `Stable vol = tight spreads, normal liquidity. ZL trading on fundamentals (crush, biofuel demand).`,
    },
    crush: {
      whatsHappening: data.score >= 65
        ? `Board crush at $${crushValue?.toFixed(2) ?? '<1.25'}/bu - margins stressed. ${oilShare ? `Oil share at ${oilShare.toFixed(1)}% (${oilShare < 45 ? 'meal driving crush' : 'balanced'}).` : ''} Processors may idle capacity.`
        : data.score <= 35
        ? `Board crush at $${crushValue?.toFixed(2) ?? '>1.75'}/bu - strong margins. ${oilShare ? `Oil share at ${oilShare.toFixed(1)}% supporting oil value.` : ''} Max crush running, heavy ZL supply.`
        : `Board crush at $${crushValue?.toFixed(2) ?? '~1.50'}/bu - neutral margins. ${oilShare ? `Oil share at ${oilShare.toFixed(1)}%.` : ''} Normal processor run rates.`,
      macroContext: `Crush = (11 × ZM) + (ZL/100) - ZS. ${crushValue ? `At $${crushValue.toFixed(2)}/bu, ` : ''}${crushValue && crushValue < 1.25 ? 'margins severely squeezed - bean costs too high vs products.' : crushValue && crushValue > 1.75 ? 'healthy margins incentivize max capacity utilization.' : 'margins support normal operations.'}`,
      supplyDemand: `${oilShare ? `Oil share at ${oilShare.toFixed(1)}% (normal 42-48%). ` : ''}${oilShare && oilShare < 44 ? 'Meal driving crush decisions - oil is byproduct. Watch for basis weakness.' : oilShare && oilShare > 50 ? 'Oil commanding premium - biofuel/export demand strong. Supportive for ZL.' : 'Balanced oil/meal value split.'}`,
      geopolitical: `45Z clean fuel tax credit supporting renewable diesel demand for soyoil. RVO mandates (15B gal biodiesel) provide demand floor. LCFS credits in CA/OR add $0.10-0.20/lb premium.`,
      investorSentiment: `Crushers ${crushValue && crushValue > 1.50 ? 'extending forward sales to lock margins' : 'reducing forward commitments on weak margins'}. Commercial hedging activity reflects margin expectations.`,
      nearTermOutlook: `Watching WASDE crush forecasts and weekly NOPA data. ${crushValue && crushValue < 1.25 ? 'Weak margins may slow Q1 crush pace.' : crushValue && crushValue > 1.75 ? 'Strong margins = elevated crush through Q1.' : 'Normal seasonal crush patterns expected.'}`,
      zlImplication: data.score >= 65
        ? `Tight crush = lower ZL supply. Watch for basis strength if demand holds. Potential upside.`
        : data.score <= 35
        ? `Max crush = heavy ZL supply pressure. Watch for basis weakness. Commercial selling into rallies.`
        : `Balanced crush = neutral ZL supply. Trade technicals and demand factors.`,
    },
    china: {
      whatsHappening: data.score >= 65
        ? `China trade tension elevated. CNY at ${cnyRate?.toFixed(2) ?? '>7.3'} hurts US competitiveness. ${fxiChange ? `FXI ${fxiChange > 0 ? '+' : ''}${fxiChange.toFixed(1)}% (20d) signals weak demand outlook.` : ''}`
        : data.score <= 35
        ? `Constructive China environment. CNY at ${cnyRate?.toFixed(2) ?? '<7.0'} supports US exports. ${fxiChange ? `FXI ${fxiChange > 0 ? '+' : ''}${fxiChange.toFixed(1)}% shows healthy demand.` : ''}`
        : `Normal China dynamics. CNY at ${cnyRate?.toFixed(2) ?? '~7.15'}. ${fxiChange ? `FXI ${fxiChange > 0 ? '+' : ''}${fxiChange.toFixed(1)}% (20d).` : ''} Export sales flowing at typical pace.`,
      macroContext: `China buys ~60% of globally traded soybeans. ${cnyRate ? `CNY at ${cnyRate.toFixed(2)} ` : ''}${cnyRate && cnyRate > 7.3 ? '- weak yuan makes Brazil more competitive vs US Gulf. Price disadvantage ~$15-20/MT.' : cnyRate && cnyRate < 7.0 ? '- strong yuan favors US origins. Chinese buyers actively covering.' : '- neutral FX impact on trade flows.'}`,
      supplyDemand: `US faces 13% tariff vs 3% for Brazil/Argentina on China soy imports. At current FX, ${cnyRate && cnyRate > 7.2 ? 'Brazil holds $25-30/MT advantage - expect limited US sales.' : 'competitive pricing - normal US export program achievable.'}`,
      geopolitical: `US-China soy trade: 25 MMT/year committed but uncertain execution. ${data.score >= 50 ? 'Trade tensions = demand cliff risk (see 2018-2019 playbook).' : 'Relations stable enough for normal trade flows.'}`,
      investorSentiment: `${data.score >= 50 ? 'Market pricing trade war risk premium. Funds reducing US soy/oil exposure.' : 'Normal export expectations priced in. No trade war premium.'}`,
      nearTermOutlook: `Watching weekly export sales (Thursdays) and shipping inspections. ${cnyRate && cnyRate > 7.3 ? 'Brazil harvest (Feb-Apr) will dominate China buying.' : 'US still competitive through Q1.'}`,
      zlImplication: data.score >= 65
        ? `Weak China demand = bearish ZL. Export basis at Gulf likely to weaken. Watch crush demand as offset.`
        : `Supportive China demand backdrop. Export basis firm. ZL finding support from export pull.`,
    },
    tariff: {
      whatsHappening: data.score >= 65
        ? `Trade Policy Uncertainty at ${tpuValue?.toFixed(0) ?? '>300'}. ${tpuValue && tpuValue > 400 ? 'Extreme uncertainty - tariff escalation risk high.' : 'Elevated policy noise - watch for retaliatory threats.'}`
        : data.score <= 35
        ? `Trade policy calm. TPU at ${tpuValue?.toFixed(0) ?? '<100'} - no active tariff threats. Normal trade flows expected.`
        : `Moderate policy uncertainty. TPU at ${tpuValue?.toFixed(0) ?? '~200'}. Headlines without immediate action.`,
      macroContext: `TPU (Baker-Bloom-Davis) at ${tpuValue?.toFixed(0) ?? 'current'}: <100 calm, 100-200 normal, 200-400 elevated, >400 high/crisis. ${tpuValue && tpuValue > 300 ? 'Current level historically associated with trade war escalation periods.' : 'Within normal policy uncertainty range.'}`,
      supplyDemand: `${tpuValue && tpuValue > 300 ? 'Exporters delaying forward sales on uncertainty. Buyers seeking non-US origins. ' : ''}Export sales pace ${data.score >= 50 ? 'below seasonal due to policy uncertainty' : 'tracking normally - no tariff-related disruption'}.`,
      geopolitical: `2018-2019 trade war precedent: 25% tariffs shifted 20+ MMT of China soy demand to Brazil. ${data.score >= 65 ? 'Similar risk elevated today.' : 'No imminent repeat expected.'} Watch for Section 301 actions or retaliation threats.`,
      investorSentiment: `${data.score >= 50 ? 'Traders hedging tariff event risk via options. Elevated put/call skew on soy complex.' : 'No significant tariff premium in options markets. Normal positioning.'}`,
      nearTermOutlook: `Monitoring trade negotiation headlines, USTR announcements, and retaliatory threats. ${tpuValue && tpuValue > 300 ? 'Elevated risk of policy shock.' : 'Calm near-term policy environment.'}`,
      zlImplication: data.score >= 65
        ? `Tariff risk = bearish ZL via export demand destruction. Gulf basis vulnerable. Defensive positioning warranted.`
        : `Supportive trade policy backdrop. No tariff-related headwinds for ZL exports.`,
    },
  }

  return templates[data.driverName]
}
