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

import Anthropic from "@anthropic-ai/sdk";
import { MODEL_DRIVER_INTEL, TOKENS_DRIVER_INTEL } from "./ai-config";
import { parseAIJson } from "./parse-ai-json";

const anthropic = new Anthropic({
  apiKey: process.env.ANTHROPIC_API_KEY,
});

// =============================================================================
// TYPES
// =============================================================================

export interface DriverIntelData {
  driverName: "vix" | "crush" | "china" | "tariff" | "energy";
  score: number;
  level: string;
  regime: string;
  components: Record<string, number | null>;
  asOfDate: string;
  inputTimestamps?: Record<string, string>; // Series name → last observation date
}

export interface DriverIntel {
  whatsHappening: string; // 2-3 sentence summary
  macroContext: string; // Economic variables affecting this driver
  supplyDemand: string; // S/D dynamics specific to this driver
  geopolitical: string; // Geopolitical factors
  investorSentiment: string; // How traders are positioned
  nearTermOutlook: string; // Next 5-10 days
  zlImplication: string; // What it means for ZL specifically
  // FRESHNESS ECHO (anti-bullshit gate)
  dataAsOf?: string; // Echo of asOfDate from input
  dataQuality?: string; // Any staleness flags
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
}`;

const CRUSH_EXPERT_PROMPT = `You are a soybean crush margin specialist analyzing processor economics and their impact on ZL (soybean oil).

KEY RELATIONSHIPS:
- Board crush = (11 × ZM) + (ZL/100) - ZS  (simplified)
- <USD 1.00/bu = crisis, USD 1.00-1.25 = stressed, USD 1.25-1.50 = tight, USD 1.50-1.75 = neutral, USD 1.75-2.00 = healthy, >USD 2.00 = strong
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
}`;

const CHINA_EXPERT_PROMPT = `You are a China soy trade specialist analyzing export demand dynamics and their impact on ZL (soybean oil).

KEY RELATIONSHIPS:
- China buys ~60% of globally traded soybeans
- CNY/USD: 7.0 psychological, 7.2 PBOC defense, 7.3+ competitive disadvantage for US soy
- Weak CNY = Brazil more competitive vs US Gulf
- Focus on FX rates and specialist signals (ETF data disabled due to quality issues)

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
}`;

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
}`;

const ENERGY_EXPERT_PROMPT = `You are an energy market specialist analyzing crude oil shocks and their impact on ZL (soybean oil) via the biofuel channel.

KEY RELATIONSHIPS:
- Crude oil (CL) spikes can raise renewable diesel economics and pull more soy oil into fuel demand
- OVX is a stress thermometer for oil market uncertainty
- 5-day and 20-day CL momentum help separate noise from true supply shocks
- Geopolitical disruptions (Hormuz, OPEC cuts, sanctions) can quickly transmit into biofuel feedstock pressure

You analyze how ENERGY STRESS changes near-term soybean oil risk.
Focus on: crude momentum, volatility regime, shock persistence, and biofuel demand pass-through.

OUTPUT: Valid JSON only, no markdown.
{
  "whatsHappening": "2-3 sentences on current energy stress conditions",
  "macroContext": "Macro/energy factors (oil supply risk, rates, global demand)",
  "supplyDemand": "How energy conditions influence biofuel pull on soy oil",
  "geopolitical": "Energy geopolitics impacting supply risk",
  "investorSentiment": "How markets are positioned for energy volatility",
  "nearTermOutlook": "Next 5-10 day energy risk expectations",
  "zlImplication": "Direct impact on ZL procurement risk and timing"
}`;

// =============================================================================
// GENERATE DRIVER-SPECIFIC INTEL
// =============================================================================

// JSON parsing delegated to shared parseAIJson<T> in parse-ai-json.ts

export async function generateDriverIntel(
  data: DriverIntelData,
): Promise<DriverIntel | null> {
  const systemPrompt = {
    vix: VIX_EXPERT_PROMPT,
    crush: CRUSH_EXPERT_PROMPT,
    china: CHINA_EXPERT_PROMPT,
    tariff: TARIFF_EXPERT_PROMPT,
    energy: ENERGY_EXPERT_PROMPT,
  }[data.driverName];

  const componentsList = Object.entries(data.components)
    .filter(([, v]) => v !== null)
    .map(([k, v]) => `${k}: ${typeof v === "number" ? v.toFixed(2) : v}`)
    .join("\n");

  // Include input timestamps if provided
  const timestampsList = data.inputTimestamps
    ? Object.entries(data.inputTimestamps)
        .map(([k, v]) => `${k}: ${v}`)
        .join("\n")
    : "Not provided";

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
Keep each JSON field concise (1-2 sentences max) and keep the full response under 500 tokens.

Provide your expert analysis as JSON.`;

  try {
    const response = await anthropic.messages.create({
      model: MODEL_DRIVER_INTEL, // LOCKED: Sonnet 4.5 for per-card intel
      max_tokens: TOKENS_DRIVER_INTEL,
      messages: [{ role: "user", content: userPrompt }],
      system: systemPrompt,
    });

    const content = response.content[0];
    if (content.type !== "text") return null;

    const parsed = parseAIJson<DriverIntel>(content.text);
    if (!parsed) {
      console.error(
        `AI Intel invalid JSON for ${data.driverName}`,
        content.text.slice(0, 160),
      );
      return null;
    }

    if (!parsed.whatsHappening) return null;

    return parsed;
  } catch (error) {
    console.error(`AI Intel generation failed for ${data.driverName}:`, error);
    return null;
  }
}

// =============================================================================
// FALLBACK INTEL (Rule-based if AI fails)
// =============================================================================

export function generateFallbackDriverIntel(
  data: DriverIntelData,
): DriverIntel {
  // Extract values - FULL data now passed from route.ts
  void (data.components.vix_value ?? data.components.vix_level_score); // vixValue extracted for potential future use
  const crushValue =
    data.components.board_crush_value ?? data.components.board_crush;
  const oilShare = data.components.oil_share_value;
  const cnyRate = data.components.cny_rate;
  const hgChange20d = data.components.hg_change_20d;
  const bdiyChange = data.components.bdiy_change_20d;
  const tpuValue = data.components.tpu_value ?? data.components.tpu;
  const clChange5d = data.components.cl_change_5d;
  const clChange20d = data.components.cl_change_20d;
  const ovxValue = data.components.ovx_value;
  const energyNewsCount = data.components.energy_news_count;

  // PLAIN ENGLISH FOR VEGAS BUYERS - NO QUANT JARGON
  const templates = {
    vix: {
      whatsHappening:
        data.score >= 65
          ? `Wall Street is panicking. When the stock market sells off hard, big funds dump commodities too - including soybean oil. Expect wild price swings and wider spreads until this calms down.`
          : data.score >= 50
            ? `Markets are nervous. Stock volatility is elevated, which sometimes spills into commodities. Prices may be jumpier than usual - not crisis mode, but stay alert.`
            : data.score >= 35
              ? `Markets are calm. No panic selling, no fund liquidations. Soybean oil is trading on its own fundamentals - supply, demand, crush economics. Normal conditions.`
              : `Dead calm in the markets. Low volatility usually means steady prices. Good window to lock in coverage without worrying about sudden moves.`,
      macroContext:
        data.score >= 50
          ? `When Wall Street panics, hedge funds sell everything including commodities. We're seeing that spillover effect now.`
          : `Stock market volatility is low. Soybean oil prices are being driven by actual supply/demand, not financial market chaos.`,
      supplyDemand:
        data.score >= 50
          ? `Biodiesel buyers may hesitate to commit when energy prices are swinging wildly. Could temporarily soften soybean oil demand.`
          : `Stable conditions support normal buying patterns from biodiesel producers and food manufacturers.`,
      geopolitical: `Middle East tensions, Fed policy, and trade headlines can spike volatility without warning. Keep some dry powder.`,
      investorSentiment:
        data.score >= 50
          ? `Big money is risk-off right now. Hedge funds trimming commodity positions.`
          : `Risk appetite is healthy. No forced selling pressure from the financial side.`,
      nearTermOutlook:
        data.score >= 65
          ? `Wait for this to blow over. Could be days, could be weeks. Don't catch a falling knife.`
          : `No major volatility catalysts on the immediate horizon. Fed meetings and earnings season are the watch items.`,
      zlImplication:
        data.score >= 65
          ? `HOLD OFF on new purchases. Prices could gap down on any headline. Wait for VIX to drop below 25 before adding coverage.`
          : data.score >= 50
            ? `BE CAUTIOUS with timing. Keep existing hedges, but don't rush to add. Let the dust settle.`
            : `GOOD BUYING WINDOW. Stable conditions, tight spreads, no panic premium. Lock in what you need.`,
    },
    crush: {
      whatsHappening:
        data.score >= 65
          ? `Crushers are getting squeezed hard. At $${crushValue?.toFixed(2) ?? "<1.25"}/bu margins, some plants will slow down or shut. Less crushing = less soybean oil supply = prices should firm up.`
          : data.score <= 35
            ? `Crushers are printing money at $${crushValue?.toFixed(2) ?? ">1.75"}/bu margins. Every plant is running full tilt. That means a flood of soybean oil hitting the market. Prices face headwinds.`
            : `Crush margins around $${crushValue?.toFixed(2) ?? "1.50"}/bu are workable. Plants running normal schedules. Supply is steady, nothing dramatic either way.`,
      macroContext:
        crushValue && crushValue < 1.25
          ? `Bean prices are too high relative to what crushers can sell oil and meal for. Something has to give - either beans drop or product prices rise.`
          : crushValue && crushValue > 1.75
            ? `Crushers are making bank. They'll keep running hard until margins compress. Expect heavy supply.`
            : `Margins are in the normal range. No pressure to slow down, no windfall profits either.`,
      supplyDemand:
        oilShare && oilShare > 48
          ? `Oil is carrying more of the crush value than usual (${oilShare.toFixed(0)}% oil share). Biofuel demand is pulling hard.`
          : oilShare && oilShare < 44
            ? `Meal is driving crush decisions right now (only ${oilShare.toFixed(0)}% oil share). Oil is almost a byproduct.`
            : `Oil and meal values are balanced. Crush decisions based on overall economics.`,
      geopolitical: `Renewable diesel mandates (45Z tax credit, RVO requirements) put a floor under soybean oil demand. Biofuel is now ~40% of domestic use.`,
      investorSentiment:
        crushValue && crushValue > 1.5
          ? `Crushers are locking in forward sales to protect these margins. They expect things to tighten.`
          : `Crushers are cautious on commitments with margins this thin.`,
      nearTermOutlook:
        crushValue && crushValue < 1.25
          ? `Watch for crush slowdowns in NOPA data. That would tighten oil supply and support prices.`
          : crushValue && crushValue > 1.75
            ? `Heavy supply through Q1 at these margins. Basis should stay soft.`
            : `Normal seasonal patterns expected through spring.`,
      zlImplication:
        data.score >= 65
          ? `SUPPLY IS TIGHTENING. Plants slowing down. Consider locking coverage earlier than usual - prices could firm.`
          : data.score <= 35
            ? `SUPPLY IS HEAVY. Crushers flooding the market. No rush to buy - prices face downward pressure. Wait for dips.`
            : `BALANCED MARKET. Normal supply flow. Buy on your usual schedule.`,
    },
    china: {
      whatsHappening:
        data.score >= 65
          ? `China trade is in trouble. Whether it's tariff threats, weak yuan, or economic slowdown - US soybeans aren't moving. Brazil is eating our lunch.`
          : data.score >= 45
            ? `China buying is okay but nothing special. The US faces a permanent 13% tariff vs Brazil's 3%. We're always at a disadvantage - that's just reality.`
            : `China relations are stable, but don't get excited. Brazil still dominates because of the tariff gap. US exports are steady, not growing.`,
      macroContext:
        cnyRate && cnyRate > 7.2
          ? `Yuan is weak at ${cnyRate.toFixed(2)}. That makes Brazilian soy even cheaper for Chinese buyers. US gulf is uncompetitive.`
          : `Currency isn't helping or hurting much. The real issue is the 13% US tariff vs 3% for Brazil.`,
      supplyDemand: `Here's the math: US soy to China faces 13% tariff. Brazil/Argentina pay 3%. That's a USD 20-30/MT disadvantage before freight. We only win when Brazil runs short.`,
      geopolitical:
        data.score >= 50
          ? `Trade war risk is real. Remember 2018-2019? China switched to Brazil overnight. Could happen again.`
          : `No immediate trade war threat, but the structural disadvantage is permanent. Don't count on China demand surprises.`,
      investorSentiment:
        hgChange20d !== null && hgChange20d !== undefined && hgChange20d < -5
          ? `Copper is down ${Math.abs(hgChange20d).toFixed(0)}% this month. China demand concerns are real.`
          : `Copper is stable. No panic, but no boom either.`,
      nearTermOutlook:
        bdiyChange !== null && bdiyChange !== undefined && bdiyChange < -10
          ? `Shipping rates are collapsing (${bdiyChange.toFixed(0)}% down). That's a red flag for physical trade.`
          : `Shipping steady. Physical trade flowing normally.`,
      zlImplication:
        data.score >= 65
          ? `CHINA IS NOT BUYING. That hurts soybean basis at the Gulf, which indirectly pressures oil. Don't expect export-driven rallies.`
          : data.score >= 45
            ? `BRAZIL IS PREFERRED ORIGIN. US exports are steady but not growing. Price your coverage without counting on China surprises.`
            : `NORMAL EXPORT PROGRAM. Nothing exciting from China, but that's priced in. Trade on crush and biofuel demand instead.`,
    },
    tariff: {
      whatsHappening:
        data.score >= 65
          ? `Trade policy is a mess. Headlines are flying, threats are escalating. This is the kind of environment where China stops buying overnight. Stay defensive.`
          : data.score >= 50
            ? `Trade noise is elevated but no new tariffs yet. Lots of political posturing. Keep an eye on it but don't panic.`
            : `Trade policy is quiet. No new threats, negotiations stable. The existing 13% US tariff disadvantage isn't going away, but it's not getting worse.`,
      macroContext:
        tpuValue && tpuValue > 300
          ? `Policy uncertainty at these levels historically means trade war escalation. We saw this in 2018-2019.`
          : `Trade policy uncertainty is in normal range. Political noise, but no action.`,
      supplyDemand:
        data.score >= 50
          ? `Exporters are nervous about forward sales. Buyers are looking at non-US origins just in case.`
          : `Export sales are tracking normally. No tariff-related disruption.`,
      geopolitical: `Remember 2018-2019: when 25% tariffs hit, China shifted 20+ million tons of soy demand to Brazil. It can happen again if things escalate.`,
      investorSentiment:
        data.score >= 50
          ? `Options market is pricing tariff risk. That's adding premium to soy complex.`
          : `No tariff premium in the market. Normal positioning.`,
      nearTermOutlook:
        data.score >= 65
          ? `Watch USTR announcements and China retaliation threats. Could move fast.`
          : `Calm on the trade front. No imminent policy shocks expected.`,
      zlImplication:
        data.score >= 65
          ? `DEFENSIVE POSTURE. Tariff escalation would crush US export demand and pressure Gulf basis. Keep coverage light until clarity.`
          : data.score >= 50
            ? `STAY ALERT but don't overreact. Political noise, not policy action yet. Normal buying with one eye on headlines.`
            : `TRADE POLICY IS SUPPORTIVE. No new tariffs, calm environment. Good window to cover your needs.`,
    },
    energy: {
      whatsHappening:
        data.score >= 65
          ? `Energy stress is elevated. Crude is moving fast and volatility is high, which can tighten soy oil through the biofuel channel.`
          : data.score >= 50
            ? `Energy conditions are elevated but not crisis-level. Watch for spillover into renewable diesel feedstock demand.`
            : `Energy markets are mostly stable. No major crude shock is currently forcing soybean oil repricing.`,
      macroContext:
        ovxValue && ovxValue >= 50
          ? `Oil volatility is elevated (OVX ${ovxValue.toFixed(1)}), signaling fragile energy conditions with headline risk.`
          : `Oil volatility is contained, reducing the chance of abrupt biofuel-driven ZL repricing.`,
      supplyDemand:
        clChange5d && clChange5d > 0.05
          ? `Recent crude upside can improve renewable diesel pull and tighten soy oil balances at the margin.`
          : `No significant crude-driven demand shock is evident in current soy oil balance dynamics.`,
      geopolitical:
        data.score >= 65
          ? `Geopolitical energy risk is elevated; supply headlines can reprice crude and biofuel inputs quickly.`
          : `No acute geopolitical energy disruption is currently dominating price action.`,
      investorSentiment:
        energyNewsCount && energyNewsCount >= 5
          ? `Energy headline volume is elevated, and markets are pricing more near-term uncertainty.`
          : `Energy sentiment is relatively steady with limited panic positioning.`,
      nearTermOutlook:
        clChange20d && clChange20d > 0.1
          ? `Trend risk remains skewed higher in crude over the next week; maintain higher alert on feedstock-linked moves.`
          : `Expect mixed-to-stable energy conditions unless a new supply shock appears.`,
      zlImplication:
        data.score >= 65
          ? `HIGH ENERGY PASS-THROUGH RISK. Avoid waiting on full coverage if procurement windows are open.`
          : data.score >= 50
            ? `MODERATE ENERGY RISK. Stage purchases and monitor crude/OVX daily for escalation.`
            : `LOW ENERGY RISK. Normal procurement cadence is reasonable from an energy-spillover perspective.`,
    },
  };

  return templates[data.driverName];
}
