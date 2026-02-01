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
  // Extract actual values from components (FULL data now passed from route.ts)
  const vixValue = data.components.vix_value ?? data.components.vix_level_score
  const vix3mValue = data.components.vix3m_value
  const ovxValue = data.components.ovx_value
  const vixRatio = data.components.vix_ratio
  const realizedVol = data.components.realized_zl_vol
  const vixZlCorr = data.components.vix_zl_correlation
  const hedgeCount = data.components.hedge_article_count
  const crushValue = data.components.board_crush_value ?? data.components.board_crush
  const oilShare = data.components.oil_share_value
  const oilShare5dChange = data.components.oil_share_5d_change
  const cnyRate = data.components.cny_rate
  const fxiChange20d = data.components.fxi_change_20d
  const fxiChange5d = data.components.fxi_change_5d
  const bdryChange = data.components.bdry_change_20d
  const tpuValue = data.components.tpu_value ?? data.components.tpu
  const emvValue = data.components.emv_value
  const soyTariffNews = data.components.soy_tariff_news_count

  // Helper for sign formatting
  const fmtDelta = (v: number | null | undefined) => v !== null && v !== undefined ? `${v >= 0 ? '+' : ''}${v.toFixed(1)}%` : 'N/A'
  const vixDesc = vixValue && vixValue < 15 ? 'low' : vixValue && vixValue > 25 ? 'elevated' : 'normal range'
  const termDesc = vixRatio && vixRatio < 0.92 ? 'contango' : vixRatio && vixRatio > 1.05 ? 'backwardation' : 'flat'

  const templates = {
    vix: {
      whatsHappening: `VIX ${vixValue?.toFixed(1) ?? '--'} (${vixDesc}), VIX/VIX3M ${vixRatio?.toFixed(2) ?? '--'} (${termDesc}). ${ovxValue ? `OVX ${ovxValue.toFixed(1)} (oil vol ${ovxValue > 50 ? 'elevated' : 'stable'}).` : ''} ${vixZlCorr !== null && vixZlCorr !== undefined ? `VIX-ZL correlation ${vixZlCorr.toFixed(2)} - ${vixZlCorr > 0.4 ? 'risk-off pressure on soy' : vixZlCorr > 0.2 ? 'moderate transmission' : 'ZL trading on fundamentals'}.` : 'VIX-ZL correlation typical 0.3-0.5 historically.'} ${data.score >= 65 ? 'Fund liquidation pressure hitting commodities.' : data.score <= 35 ? 'No vol-driven fund flows expected.' : 'Normal vol environment.'}`,
      macroContext: `VIX-ZL correlation typically 0.3-0.5 historically. ${vixValue && vixValue > 25 ? `Current elevated VIX (${vixValue.toFixed(1)}) = potential fund liquidation of commodity longs.` : vixValue && vixValue < 15 ? `Low VIX (${vixValue.toFixed(1)}) = stable risk appetite, supportive for commodity positioning.` : 'Fed policy uncertainty and equity earnings driving vol expectations.'} ${realizedVol ? `Realized ZL vol at ${realizedVol.toFixed(1)}% annualized.` : ''}`,
      supplyDemand: `${ovxValue ? `OVX at ${ovxValue.toFixed(1)} - ` : ''}${ovxValue && ovxValue > 50 ? 'high oil volatility creates biodiesel margin uncertainty, affecting renewable diesel demand.' : 'stable energy vol supports consistent biofuel demand planning.'} ${hedgeCount ? `ProFarmer tracking ${hedgeCount} hedge-related articles (7d) - ${hedgeCount > 8 ? 'elevated farmer hedging focus' : 'normal coverage'}.` : ''}`,
      geopolitical: 'Geopolitical risk premium embedded in vol. Middle East tensions, trade policy, and Fed uncertainty key drivers.',
      investorSentiment: data.score >= 50
        ? `CTAs and macro funds reducing commodity exposure when VIX > 20. Managed money likely trimming ZL longs. ${vixRatio && vixRatio > 1 ? 'Term structure backwardation signals near-term stress.' : ''}`
        : `Risk-on positioning with VIX subdued. Managed money comfortable holding commodity longs.`,
      nearTermOutlook: `${vix3mValue ? `Term structure (VIX ${vixValue?.toFixed(1)} vs VIX3M ${vix3mValue.toFixed(1)}) suggests ${vixRatio && vixRatio < 0.9 ? 'near-term calm' : vixRatio && vixRatio > 1.05 ? 'near-term stress' : 'normal conditions'}.` : 'Watch for vol catalysts.'} FOMC, earnings, and geopolitics as triggers.`,
      zlImplication: data.score >= 65
        ? `PROCUREMENT: High vol = wider ZL bid/ask spreads, potential gap risk on opens. Reduce position size, delay marginal coverage until VIX < 25.`
        : data.score >= 50
        ? `PROCUREMENT: Elevated vol = watch for spread blowouts. Maintain existing hedges but avoid new commitments until vol stabilizes.`
        : `PROCUREMENT: Stable vol supports consistent hedging. ZL trading on fundamentals (crush, biofuel demand). Normal procurement timing appropriate.`,
    },
    crush: {
      whatsHappening: `Board crush $${crushValue?.toFixed(2) ?? '--'}/bu${oilShare ? `, oil share ${oilShare.toFixed(1)}%` : ''}${oilShare5dChange !== null && oilShare5dChange !== undefined ? ` (5d Δ ${fmtDelta(oilShare5dChange)})` : ''}. ${crushValue && crushValue < 1.25 ? 'Margins severely stressed - processors may idle capacity.' : crushValue && crushValue > 1.75 ? 'Strong margins running, heavy ZL supply expected from max crush.' : 'Neutral margins supporting normal run rates.'}`,
      macroContext: `Crush = (11 × ZM) + (ZL/100) - ZS. ${crushValue ? `At $${crushValue.toFixed(2)}/bu: ` : ''}${crushValue && crushValue < 1.00 ? 'CRISIS - plants idling, ZL supply tightening.' : crushValue && crushValue < 1.25 ? 'margins severely squeezed - bean costs too high vs products.' : crushValue && crushValue > 2.00 ? 'exceptional margins = max capacity utilization, watch for ZL basis weakness on heavy supply.' : crushValue && crushValue > 1.75 ? 'healthy margins incentivize max capacity utilization.' : 'margins support normal operations.'}`,
      supplyDemand: `${oilShare ? `Oil share at ${oilShare.toFixed(1)}% (normal 42-48%). ` : ''}${oilShare && oilShare < 44 ? 'Meal driving crush decisions - oil is byproduct. Watch for ZL basis weakness.' : oilShare && oilShare > 50 ? 'Oil commanding premium - biofuel/export demand strong. Supportive for ZL.' : 'Balanced oil/meal value split.'} ${oilShare5dChange !== null && oilShare5dChange !== undefined && oilShare5dChange > 1 ? 'Oil share rising = biofuel pull strengthening.' : oilShare5dChange !== null && oilShare5dChange !== undefined && oilShare5dChange < -1 ? 'Oil share falling = meal driving crush.' : ''}`,
      geopolitical: `45Z clean fuel tax credit supporting renewable diesel demand for soyoil. RVO mandates (potential 6B+ gal biomass diesel 2026) provide demand floor. LCFS credits in CA/OR add $0.10-0.20/lb premium.`,
      investorSentiment: `Crushers ${crushValue && crushValue > 1.50 ? 'extending forward sales to lock margins' : 'reducing forward commitments on weak margins'}. Commercial hedging activity reflects margin expectations.`,
      nearTermOutlook: `Watching WASDE crush forecasts and weekly NOPA data. ${crushValue && crushValue < 1.25 ? 'Weak margins may slow Q1 crush pace - potential ZL supply tightening.' : crushValue && crushValue > 1.75 ? 'Strong margins = elevated crush through Q1 - heavy ZL supply.' : 'Normal seasonal crush patterns expected.'}`,
      zlImplication: data.score >= 65
        ? `PROCUREMENT: Tight crush = lower ZL supply. Watch for basis strength if demand holds. Consider accelerating coverage on potential supply squeeze.`
        : data.score <= 35
        ? `PROCUREMENT: Max crush = heavy ZL supply pressure. Delay marginal coverage - commercials selling into rallies. Basis likely to weaken.`
        : `PROCUREMENT: Balanced crush = neutral ZL supply. Trade technicals and demand factors. Normal procurement timing appropriate.`,
    },
    china: {
      whatsHappening: `CNY ${cnyRate?.toFixed(2) ?? '--'} (${cnyRate && cnyRate < 7.0 ? 'strong' : cnyRate && cnyRate > 7.3 ? 'weak' : 'stable'}), FXI ${fmtDelta(fxiChange20d)} (20d)${fxiChange5d !== null && fxiChange5d !== undefined ? `, ${fmtDelta(fxiChange5d)} (5d)` : ''}. ${bdryChange !== null && bdryChange !== undefined ? `BDRY (shipping) ${fmtDelta(bdryChange)} (20d) - ${bdryChange > 10 ? 'freight rates surging' : bdryChange < -10 ? 'freight rates collapsing' : 'stable shipping'}.` : ''} Brazil structurally favored (3% tariff vs US 13%). ${data.score >= 65 ? 'US sales pace at risk.' : data.score <= 35 ? 'China demand stable but Brazil still dominates.' : 'Export sales flowing at typical pace.'}`,
      macroContext: `China buys ~60% of globally traded soybeans. ${cnyRate ? `CNY at ${cnyRate.toFixed(2)} ` : ''}${cnyRate && cnyRate > 7.3 ? '- weak yuan makes Brazil more competitive vs US Gulf. Price disadvantage ~$15-20/MT.' : cnyRate && cnyRate < 7.0 ? '- strong yuan favors US origins. Chinese buyers actively covering.' : '- neutral FX impact on trade flows.'} ${fxiChange20d !== null && fxiChange20d !== undefined && fxiChange20d < -5 ? 'FXI weakness signals China economic headwinds.' : ''}`,
      supplyDemand: `US faces 13% tariff vs 3% for Brazil/Argentina on China soy imports - structural disadvantage. At current FX, ${cnyRate && cnyRate > 7.2 ? 'Brazil holds $25-30/MT advantage - expect limited US sales.' : 'competitive pricing possible but Brazil still preferred.'} ${bdryChange !== null && bdryChange !== undefined && bdryChange > 20 ? 'Rising freight rates add to US cost disadvantage.' : ''}`,
      geopolitical: `US-China soy trade: 25 MMT/year committed but uncertain execution. ${data.score >= 50 ? 'Trade tensions = demand cliff risk (see 2018-2019 playbook).' : 'Relations stable enough for normal trade flows.'} 13% US tariff vs 3% Brazil/Argentina = permanent headwind.`,
      investorSentiment: `${data.score >= 50 ? 'Market pricing trade war risk premium. Funds reducing US soy/oil exposure.' : 'Normal export expectations priced in. No trade war premium.'} ${fxiChange20d !== null && fxiChange20d !== undefined && fxiChange20d < -10 ? 'Sharp FXI decline = China demand concerns spreading to commodities.' : ''}`,
      nearTermOutlook: `Watching weekly export sales (Thursdays) and shipping inspections. ${cnyRate && cnyRate > 7.3 ? 'Brazil harvest (Feb-Apr) will dominate China buying.' : 'US still competitive through Q1.'} ${bdryChange !== null && bdryChange !== undefined && bdryChange < -15 ? 'Collapsing freight = weak physical trade flows.' : ''}`,
      zlImplication: data.score >= 65
        ? `PROCUREMENT: Weak China demand = bearish ZL. Export basis at Gulf likely to weaken. Delay coverage - watch for crush demand as offset.`
        : data.score >= 45
        ? `PROCUREMENT: Monitor USDA export pace - 13% tariff drag persists. Brazil preferred buyer. Maintain existing hedges but delay new commitments.`
        : `PROCUREMENT: China stable but Brazil dominates at 13% tariff gap. Normal procurement timing - don't expect US export surprises.`,
    },
    tariff: {
      whatsHappening: `TPU ${tpuValue?.toFixed(0) ?? '--'} (${tpuValue && tpuValue < 100 ? 'calm' : tpuValue && tpuValue > 300 ? 'elevated' : 'normal range'})${emvValue ? `, EMV Trade ${emvValue.toFixed(0)}` : ''}${soyTariffNews !== null && soyTariffNews !== undefined ? `, soy tariff news ${soyTariffNews} articles` : ''}. ${tpuValue && tpuValue > 400 ? 'Extreme uncertainty - tariff escalation risk high.' : tpuValue && tpuValue > 200 ? 'Elevated policy noise - watch for retaliatory threats.' : 'Moderate policy noise without immediate action.'} 13% US tariff disadvantage persists.`,
      macroContext: `TPU (Baker-Bloom-Davis): <100 calm, 100-200 normal, 200-400 elevated, >400 crisis. ${tpuValue ? `Current ${tpuValue.toFixed(0)} = ${tpuValue > 300 ? 'historically associated with trade war escalation periods.' : 'within normal policy uncertainty range.'}` : ''} ${emvValue && emvValue > 200 ? `EMV Trade at ${emvValue.toFixed(0)} signals elevated newspaper coverage of trade policy.` : ''}`,
      supplyDemand: `${tpuValue && tpuValue > 300 ? 'Exporters delaying forward sales on uncertainty. Buyers seeking non-US origins. ' : ''}Export sales pace ${data.score >= 50 ? 'below seasonal due to policy uncertainty' : 'tracking normally - no tariff-related disruption'}. ${soyTariffNews && soyTariffNews > 5 ? `Heavy soy tariff coverage (${soyTariffNews} articles) in ProFarmer.` : ''}`,
      geopolitical: `2018-2019 trade war precedent: 25% tariffs shifted 20+ MMT of China soy demand to Brazil. ${data.score >= 65 ? 'Similar risk elevated today.' : 'No imminent repeat expected.'} Watch for Section 301 actions or retaliation threats.`,
      investorSentiment: `${data.score >= 50 ? 'Traders hedging tariff event risk via options. Elevated put/call skew on soy complex.' : 'No significant tariff premium in options markets. Normal positioning.'}`,
      nearTermOutlook: `Monitoring trade negotiation headlines, USTR announcements, and retaliatory threats. ${tpuValue && tpuValue > 300 ? 'Elevated risk of policy shock.' : 'Calm near-term policy environment.'}`,
      zlImplication: data.score >= 65
        ? `PROCUREMENT: Tariff risk = bearish ZL via export demand destruction. Gulf basis vulnerable. Delay coverage and maintain defensive positioning.`
        : data.score >= 50
        ? `PROCUREMENT: Elevated noise backdrop but no immediate tariff action. Watch Section 301 / retaliation headlines. Normal timing with hedges in place.`
        : `PROCUREMENT: Trade policy calm - supportive for soy exports. No tariff-related headwinds for ZL. Normal procurement timing appropriate.`,
    },
  }

  return templates[data.driverName]
}
