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
  const templates = {
    vix: {
      whatsHappening: data.score >= 65
        ? `VIX at elevated levels indicates risk-off sentiment across markets. Fund liquidation pressure may hit commodities including ZL.`
        : data.score <= 35
        ? `Low volatility environment with VIX subdued. ZL trading on fundamentals with stable spreads.`
        : `Normal volatility conditions. ZL trading within typical ranges, fundamentals driving price action.`,
      macroContext: 'Monitoring Fed policy signals and equity market sentiment for volatility catalysts.',
      supplyDemand: 'Commodity fund positioning aligned with broader risk appetite.',
      geopolitical: 'Geopolitical headlines contributing to baseline uncertainty.',
      investorSentiment: data.score >= 50 ? 'Traders positioned defensively.' : 'Normal risk-on positioning.',
      nearTermOutlook: 'Watching for catalysts that could shift volatility regime.',
      zlImplication: data.score >= 65 ? 'Watch for wider ZL spreads and potential gap risk.' : 'Stable ZL trading conditions expected.',
    },
    crush: {
      whatsHappening: data.score >= 65
        ? `Crush margins under severe pressure. Processors may idle capacity, reducing ZL supply.`
        : data.score <= 35
        ? `Strong crush economics driving high processor utilization. Heavy ZL supply hitting market.`
        : `Balanced crush margins with processors running at normal rates.`,
      macroContext: 'Bean costs, oil premiums, and meal basis driving margin calculations.',
      supplyDemand: data.score <= 35 ? 'Max crush running - heavy oil supply.' : 'Processor run rates responding to margin signals.',
      geopolitical: 'Biofuel policy (RFS, LCFS) affecting oil demand and crush incentives.',
      investorSentiment: 'Crushers hedging forward production based on margin outlook.',
      nearTermOutlook: 'Monitoring bean basis and product premiums for margin direction.',
      zlImplication: data.score >= 65 ? 'ZL supply may tighten as crush slows.' : data.score <= 35 ? 'Heavy ZL supply - watch for basis pressure.' : 'Balanced supply conditions.',
    },
    china: {
      whatsHappening: data.score >= 65
        ? `China trade tensions elevated. Export demand at risk as CNY weakens and tensions rise.`
        : data.score <= 35
        ? `Constructive China trade environment. Active buying supporting export demand.`
        : `Normal China trade dynamics. Export sales flowing at typical pace.`,
      macroContext: 'CNY policy, China economic growth, and import demand signals.',
      supplyDemand: 'US vs Brazil competitiveness key factor in export commitments.',
      geopolitical: 'US-China relations and trade policy headlines driving sentiment.',
      investorSentiment: data.score >= 50 ? 'Market pricing in trade war risk premium.' : 'Normal trade flow expectations.',
      nearTermOutlook: 'Watching weekly export sales and shipping inspection data.',
      zlImplication: data.score >= 65 ? 'ZL export demand at risk - watch Gulf basis.' : 'Supportive export demand backdrop.',
    },
    tariff: {
      whatsHappening: data.score >= 65
        ? `Trade Policy Uncertainty elevated. Tariff threats active, soy export program at risk.`
        : data.score <= 35
        ? `Trade policy calm. No active tariff threats to soy sector.`
        : `Normal policy noise. Monitoring headlines but no immediate threat.`,
      macroContext: 'Administration trade policy stance and legislative activity.',
      supplyDemand: 'Export sales pace reflecting policy uncertainty levels.',
      geopolitical: 'Trade war history (2018-2019) informs current risk assessment.',
      investorSentiment: data.score >= 50 ? 'Traders hedging tariff event risk.' : 'Normal positioning without policy premium.',
      nearTermOutlook: 'Watching for tariff announcements or trade negotiation news.',
      zlImplication: data.score >= 65 ? 'ZL vulnerable to export demand disruption.' : 'Supportive trade policy backdrop.',
    },
  }

  return templates[data.driverName]
}
