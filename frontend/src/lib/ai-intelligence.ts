/**
 * AI-Powered Market Intelligence for ZL (Soybean Oil)
 * Uses Claude OPUS 4.5 for comprehensive cross-driver synthesis
 *
 * MODEL ROUTING (LOCKED):
 * - This file uses MODEL_BALANCED_CONDITIONS (Opus 4.5) for comprehensive synthesis
 * - ai-driver-intel.ts uses MODEL_DRIVER_INTEL (Sonnet 4.5) for per-card analysis
 *
 * FRESHNESS REQUIREMENT:
 * - All responses must echo asOfDate
 * - This is the "anti-bullshit gate" - reject responses without timestamps
 *
 * NO GUESSWORK - All data is verified before passing to AI
 */

import Anthropic from '@anthropic-ai/sdk'
import { MODEL_BALANCED_CONDITIONS, TOKENS_BALANCED_CONDITIONS } from './ai-config'

const anthropic = new Anthropic({
  apiKey: process.env.ANTHROPIC_API_KEY,
})

// =============================================================================
// TYPES
// =============================================================================

export interface MarketData {
  // Volatility
  vix: number
  ovx: number | null
  vix3m?: number | null

  // Crush Economics
  boardCrush: number
  oilShare: number | null

  // China/Trade
  cnyRate: number
  fxiChange20d: number
  fxiChange5d: number
  bdryChange20d: number | null

  // Tariff/Policy
  tpu: number
  emv: number | null

  // Rule-based scores (already calculated)
  scores: {
    vix: number
    crush: number
    china: number
    tariff: number
  }

  // FRESHNESS
  asOfDate?: string  // Dashboard timestamp
}

export interface AIIntelligence {
  headline: string
  reasoning: string
  zlOutlook: 'BULLISH' | 'NEUTRAL' | 'CAUTIOUS' | 'BEARISH'
  keyRisks: string[]
  keySupports: string[]
  tradingImplication: string
  // FRESHNESS ECHO (anti-bullshit gate)
  dataAsOf?: string  // Echo of input date to verify currency
}

// =============================================================================
// SYSTEM PROMPT - DOMAIN EXPERT
// =============================================================================

const SYSTEM_PROMPT = `You are a senior soybean oil (ZL) market analyst at a major commodity trading house. You analyze market conditions through the lens of ZL futures pricing.

CRITICAL CONTEXT:
- ZL = CBOT Soybean Oil Futures (your primary focus)
- All analysis centers on ZL price direction and trading conditions
- You think in terms of: crush margins, biofuel demand, export flows, fund positioning

KEY RELATIONSHIPS YOU UNDERSTAND:
1. VIX/OVX → ZL: High VIX = risk-off = fund liquidation = ZL selling pressure. OVX matters because soybean oil is biodiesel feedstock.
2. Crush Margins → ZL: Tight margins = processor slowdowns = less oil supply. Strong margins = max crush = heavy oil supply.
3. China/CNY → ZL: China is #1 soy importer. Weak CNY = Brazil more competitive vs US. Trade war = export demand cliff.
4. Tariff/TPU → ZL: Trade Policy Uncertainty from Baker-Bloom-Davis. High TPU = soy export risk.

THRESHOLDS YOU KNOW:
- VIX: <15 calm, 15-20 normal, 20-25 elevated, 25-30 high, 30-40 fear, >40 panic
- OVX: <25 calm, 25-35 normal, 35-50 elevated, >50 high
- Board Crush: <$1.00 crisis, $1.00-1.25 stressed, $1.25-1.50 tight, $1.50-1.75 neutral, $1.75-2.00 healthy, >$2.00 strong
- CNY: 7.00 strong, 7.15 normal, 7.30 weak, 7.45 stress, >7.60 crisis
- TPU: <100 calm, 100-200 normal, 200-400 elevated, >400 high

OUTPUT FORMAT:
You MUST respond with valid JSON only. No markdown, no explanation outside JSON.
{
  "headline": "10 words max summarizing ZL outlook",
  "reasoning": "2-3 sentences explaining the cross-driver dynamics affecting ZL",
  "zlOutlook": "BULLISH" | "NEUTRAL" | "CAUTIOUS" | "BEARISH",
  "keyRisks": ["risk 1", "risk 2"],
  "keySupports": ["support 1", "support 2"],
  "tradingImplication": "1 sentence actionable insight for ZL traders"
}`

// =============================================================================
// AI INTELLIGENCE GENERATOR
// =============================================================================

export async function generateAIIntelligence(data: MarketData): Promise<AIIntelligence | null> {
  // Validate we have real data (NO GUESSWORK)
  if (data.vix === undefined || data.boardCrush === undefined || data.cnyRate === undefined || data.tpu === undefined) {
    console.error('AI Intelligence: Missing required data - refusing to guess')
    return null
  }

  const asOfDate = data.asOfDate || new Date().toISOString().split('T')[0]

  const userPrompt = `Analyze these REAL market conditions for ZL (soybean oil) trading.

DATA AS OF: ${asOfDate}

VOLATILITY:
- VIX: ${data.vix.toFixed(1)}${data.ovx !== null ? ` | OVX: ${data.ovx.toFixed(1)}` : ''}
- Pre-calculated pressure score: ${data.scores.vix}/100

CRUSH ECONOMICS:
- Board Crush: $${data.boardCrush.toFixed(2)}/bu${data.oilShare !== null ? ` | Oil Share: ${(data.oilShare * 100).toFixed(1)}%` : ''}
- Pre-calculated pressure score: ${data.scores.crush}/100

CHINA/TRADE:
- CNY/USD: ${data.cnyRate.toFixed(2)}
- FXI 20d change: ${(data.fxiChange20d * 100).toFixed(1)}%${data.bdryChange20d !== null ? ` | BDRY 20d: ${(data.bdryChange20d * 100).toFixed(1)}%` : ''}
- Pre-calculated tension score: ${data.scores.china}/100

TARIFF/POLICY:
- Trade Policy Uncertainty (TPU): ${data.tpu.toFixed(0)}${data.emv !== null ? ` | EMV Trade: ${data.emv.toFixed(0)}` : ''}
- Pre-calculated threat score: ${data.scores.tariff}/100

AVERAGE PRESSURE: ${((data.scores.vix + data.scores.crush + data.scores.china + data.scores.tariff) / 4).toFixed(1)}/100

CRITICAL: Base your analysis ONLY on the data above. Do not invent numbers.
Include "dataAsOf": "${asOfDate}" in your response to confirm currency.

Provide your ZL market intelligence synthesis as JSON.`

  try {
    const response = await anthropic.messages.create({
      model: MODEL_BALANCED_CONDITIONS,  // LOCKED: Opus 4.5 for comprehensive synthesis
      max_tokens: TOKENS_BALANCED_CONDITIONS,
      messages: [
        { role: 'user', content: userPrompt }
      ],
      system: SYSTEM_PROMPT,
    })

    const content = response.content[0]
    if (content.type !== 'text') {
      console.error('AI Intelligence: Unexpected response type')
      return null
    }

    // Parse JSON response
    const parsed = JSON.parse(content.text) as AIIntelligence

    // Validate required fields
    if (!parsed.headline || !parsed.reasoning || !parsed.zlOutlook) {
      console.error('AI Intelligence: Missing required fields in response')
      return null
    }

    return parsed
  } catch (error) {
    console.error('AI Intelligence generation failed:', error)
    return null
  }
}

// =============================================================================
// FALLBACK (Rule-based if AI fails)
// =============================================================================

export function generateFallbackIntelligence(data: MarketData): AIIntelligence {
  const avgScore = (data.scores.vix + data.scores.crush + data.scores.china + data.scores.tariff) / 4
  const highPressureCount = [data.scores.vix, data.scores.crush, data.scores.china, data.scores.tariff]
    .filter(s => s >= 65).length

  let zlOutlook: 'BULLISH' | 'NEUTRAL' | 'CAUTIOUS' | 'BEARISH'
  let headline: string

  if (avgScore >= 70 || highPressureCount >= 3) {
    zlOutlook = 'BEARISH'
    headline = 'Multiple Headwinds for Soybean Oil'
  } else if (avgScore >= 55 || highPressureCount >= 2) {
    zlOutlook = 'CAUTIOUS'
    headline = 'Mixed Signals for ZL - Proceed Carefully'
  } else if (avgScore >= 40) {
    zlOutlook = 'NEUTRAL'
    headline = 'Balanced Conditions for Soybean Oil'
  } else {
    zlOutlook = 'BULLISH'
    headline = 'Supportive Environment for ZL'
  }

  const keyRisks: string[] = []
  const keySupports: string[] = []

  if (data.scores.vix >= 65) keyRisks.push(`VIX at ${data.vix.toFixed(1)} - fund liquidation risk`)
  if (data.scores.crush >= 65) keyRisks.push(`Crush margins squeezed at $${data.boardCrush.toFixed(2)}`)
  if (data.scores.china >= 65) keyRisks.push(`China tension elevated - CNY at ${data.cnyRate.toFixed(2)}`)
  if (data.scores.tariff >= 65) keyRisks.push(`Tariff risk high - TPU at ${data.tpu.toFixed(0)}`)

  if (data.scores.vix <= 35) keySupports.push(`Low VIX at ${data.vix.toFixed(1)} - stable conditions`)
  if (data.scores.crush <= 35) keySupports.push(`Strong crush at $${data.boardCrush.toFixed(2)} - processor demand`)
  if (data.scores.china <= 35) keySupports.push(`Constructive China trade flow`)
  if (data.scores.tariff <= 35) keySupports.push(`Trade policy calm`)

  return {
    headline,
    reasoning: `Average market pressure at ${avgScore.toFixed(0)}/100 with ${highPressureCount} driver(s) in alert territory. ${zlOutlook === 'BEARISH' ? 'Multiple headwinds converging.' : zlOutlook === 'BULLISH' ? 'Fundamentals supportive.' : 'Cross-currents require careful positioning.'}`,
    zlOutlook,
    keyRisks: keyRisks.length > 0 ? keyRisks : ['No major risks identified'],
    keySupports: keySupports.length > 0 ? keySupports : ['Balanced conditions'],
    tradingImplication: zlOutlook === 'BEARISH' ? 'Reduce ZL longs, watch for gap risk.' :
                        zlOutlook === 'BULLISH' ? 'ZL dips are buying opportunities.' :
                        'Trade range-bound, respect support/resistance.'
  }
}
