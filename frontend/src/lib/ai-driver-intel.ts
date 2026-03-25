/**
 * AI-Powered Per-Driver Intelligence for ZL
 * Each driver gets its own deep analysis using free OpenRouter GPT-OSS-120B
 *
 * MODEL ROUTING (LOCKED):
 * - This file uses MODEL_DRIVER_INTEL (openai/gpt-oss-120b:free) for per-card analysis
 * - ai-intelligence.ts uses MODEL_BALANCED_CONDITIONS (openai/gpt-oss-120b:free) for synthesis
 *
 * FRESHNESS REQUIREMENT:
 * - All responses must echo asOfDate and inputTimestamps
 * - This is the "anti-bullshit gate" - reject responses without timestamps
 *
 * Uses CURRENT data (yesterday's values) - no guesswork
 */

import { MODEL_DRIVER_INTEL, TOKENS_DRIVER_INTEL } from "./ai-config";
import { hasOpenRouterApiKey, openRouterCompleteText } from "./openrouter";
import { parseAIJson } from "./parse-ai-json";

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

const VIX_EXPERT_PROMPT = `CARD LOCATION: VIX Stress driver card on the Dashboard. The user sees a score gauge (0-100), raw VIX value, OVX value, VIX3M ratio, and a sparkline trend.

ZL FOCUS: Explain how equity and oil volatility transmit to ZL (CBOT soybean oil futures). Every JSON field must connect back to ZL price impact.

KEY RELATIONSHIPS:
- VIX spike → Risk-off → Fund liquidation → ZL selling pressure
- OVX (oil volatility) → Biodiesel margin uncertainty → ZL basis volatility
- VIX term structure (VIX/VIX3M) → Near-term panic indicator
- VIX levels: <15 calm, 15-20 normal, 20-25 elevated, 25-30 high, 30-40 fear, >40 panic

OUTPUT: Valid JSON only, no markdown. 1-2 sentences per field.
{
  "whatsHappening": "1-2 sentences on current vol conditions and what they mean for ZL",
  "macroContext": "Economic factors driving vol and their ZL transmission",
  "supplyDemand": "How vol is affecting commodity fund positioning in ZL",
  "geopolitical": "Geopolitical drivers of current vol regime and ZL impact",
  "investorSentiment": "How traders are positioned and what it means for ZL flows",
  "nearTermOutlook": "Next 5-10 day vol expectations and ZL implications",
  "zlImplication": "Direct impact on ZL trading - selling pressure, spreads, liquidity"
}`;

const CRUSH_EXPERT_PROMPT = `CARD LOCATION: Crush Pressure driver card on the Dashboard. The user sees a score gauge (0-100), board crush value ($/bu), oil share %, and a sparkline.

ZL FOCUS: Explain how processor crush economics affect ZL (CBOT soybean oil futures) supply. When margins are strong, processors run hard and flood the market with soybean oil. When margins collapse, run rates drop and ZL supply tightens. Oil share rising = oil demand pulling crush decisions = bullish ZL. Every JSON field must trace to ZL supply/price.

KEY RELATIONSHIPS:
- Board crush = (11 × ZM) + (ZL/100) - ZS (simplified)
- <USD 1.00/bu = crisis, USD 1.00-1.25 = stressed, USD 1.25-1.50 = tight, USD 1.50-1.75 = neutral, USD 1.75-2.00 = healthy, >USD 2.00 = strong
- Oil share = ZL value / total product value (typically 42-48%)
- Falling oil share = meal driving crush decisions, rising = oil demand strong

OUTPUT: Valid JSON only, no markdown. 1-2 sentences per field.
{
  "whatsHappening": "1-2 sentences on crush economics and ZL supply impact",
  "macroContext": "Economic factors affecting crush margins and ZL supply",
  "supplyDemand": "Processor run rates and ZL supply pressure",
  "geopolitical": "Policy factors (RIN prices, RVO mandates, biofuel credits) and ZL demand",
  "investorSentiment": "Crusher hedging activity and ZL positioning",
  "nearTermOutlook": "Next 5-10 day crush margin expectations and ZL direction",
  "zlImplication": "Direct impact on ZL - supply pressure, basis, spreads"
}`;

const CHINA_EXPERT_PROMPT = `CARD LOCATION: China Tension driver card on the Dashboard. The user sees a score gauge (0-100), CNY/USD exchange rate, FXI ETF 5d/20d changes, and a sparkline.

ZL FOCUS: Explain how China demand dynamics affect ZL (CBOT soybean oil futures) demand and price. China buys ~60% of globally traded soybeans. Weak CNY and slowing growth reduce import appetite and can shift flow away from US origins. Every JSON field must trace to ZL demand/price.

KEY RELATIONSHIPS:
- CNY/USD: 7.0 psychological, 7.2 PBOC defense, 7.3+ competitive disadvantage for US soy
- Weak CNY = Brazil more competitive vs US Gulf
- Focus on FX rates and specialist signals (ETF data disabled due to quality issues)

OUTPUT: Valid JSON only, no markdown. 1-2 sentences per field.
{
  "whatsHappening": "1-2 sentences on China trade conditions and ZL demand impact",
  "macroContext": "Economic factors in China affecting ZL demand (PMI, currency, policy)",
  "supplyDemand": "Export sales pace vs Brazil competition and ZL implications",
  "geopolitical": "US-China relations and geopolitical risks affecting ZL export demand",
  "investorSentiment": "How market is pricing China demand risk for ZL",
  "nearTermOutlook": "Next 5-10 day China buying expectations and ZL direction",
  "zlImplication": "Direct impact on ZL - export demand, Gulf basis, price direction"
}`;

const TARIFF_EXPERT_PROMPT = `CARD LOCATION: Macro Threat driver card on the Dashboard. The user sees a score gauge (0-100) plus uncertainty, oil, inflation, geopolitical-news, and volatility components.

ZL FOCUS: Explain how macro shock inputs affect ZL (CBOT soybean oil futures) procurement risk. Prioritize this chain: Iran war / Hormuz risk -> crude oil spike -> biofuel economics tighten -> soybean oil demand pull -> ZL up. Include inflation pressure, policy uncertainty, VIX, and news velocity. Every JSON field must trace to ZL price risk.

KEY RELATIONSHIPS:
- Iran war / Hormuz disruption = immediate oil supply risk -> higher ZL via biofuel channel
- VIX spike = risk-off liquidation + wider spreads for ZL
- Oil 5d surge = higher renewable diesel pull for soybean oil
- Inflation expectations rising = commodity risk premium and higher replacement costs
- Uncertainty index + macro news velocity = regime intensity, not just one headline

OUTPUT: Valid JSON only, no markdown. 1-2 sentences per field.
{
  "whatsHappening": "1-2 sentences on current macro threat regime and ZL impact",
  "macroContext": "How uncertainty, inflation, and volatility are shaping ZL risk",
  "supplyDemand": "How oil/biofuel and geopolitical stress alter soybean oil balance",
  "geopolitical": "Iran-war and related conflict channels relevant to ZL",
  "investorSentiment": "How funds and hedgers are positioned under this macro regime",
  "nearTermOutlook": "Next 5-10 day macro path and ZL implications",
  "zlImplication": "Direct impact on ZL procurement risk and timing"
}`;

// =============================================================================
// GENERATE DRIVER-SPECIFIC INTEL
// =============================================================================

// JSON parsing delegated to shared parseAIJson<T> in parse-ai-json.ts

const ENERGY_EXPERT_PROMPT = `CARD LOCATION: Energy Stress driver card on the Dashboard. The user sees a score gauge (0-100), crude oil price data, and a sparkline.

ZL FOCUS: Explain the crude oil → biofuel → ZL (CBOT soybean oil futures) transmission chain. 50%+ of US soybean oil goes to biodiesel/renewable diesel — the energy-ZL link is STRUCTURAL. Crude up = more soy oil diverted to fuel = ZL up = bad for the buyer. Hormuz/OPEC/Iran disruptions → crude supply shock → ZL pulled higher. Every JSON field must trace the energy→biofuel→ZL chain.

KEY RELATIONSHIPS:
- Crude oil UP → biofuel economics shift → more soy oil to renewable diesel → ZL UP
- Crude oil DOWN → less biofuel demand for soy oil → ZL DOWN
- OVX (oil volatility) → energy market uncertainty
- Hormuz/OPEC/Iran → supply disruption → crude spike → ZL pressure
- CL 5d change thresholds: 2% normal, 4% notable, 7% supply shock, 12%+ crisis

OUTPUT: Valid JSON only, no markdown. 1-2 sentences per field.
{
  "whatsHappening": "1-2 sentences on energy conditions and ZL impact via biofuel channel",
  "macroContext": "Global energy drivers and their transmission to ZL",
  "supplyDemand": "How energy prices are affecting biofuel demand for soy oil",
  "geopolitical": "Geopolitical risk to energy supply and ZL implications",
  "investorSentiment": "Energy trader positioning and ZL flow impact",
  "nearTermOutlook": "Next 5-10 day energy expectations and ZL direction",
  "zlImplication": "Direct impact on ZL via biofuel economics and renewable diesel"
}`;

export async function generateDriverIntel(
  data: DriverIntelData,
): Promise<DriverIntel | null> {
  if (!hasOpenRouterApiKey()) return null;

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
    const text = await openRouterCompleteText({
      model: MODEL_DRIVER_INTEL,
      maxTokens: TOKENS_DRIVER_INTEL,
      temperature: 0.0,
      reasoning: { effort: "high" },
      messages: [
        { role: "system", content: systemPrompt },
        { role: "user", content: userPrompt },
      ],
    });

    const parsed = parseAIJson<DriverIntel>(text);
    if (!parsed) {
      console.error(
        `AI Intel invalid JSON for ${data.driverName}`,
        text.slice(0, 160),
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
  const hgChange20d =
    data.components.hg_change_20d ?? data.components.fxi_change_20d;
  const bdiyChange =
    data.components.bdiy_change_20d ?? data.components.bdry_change_20d;
  const uncertaintyValue =
    data.components.uncertainty_value ??
    data.components.tpu_value ??
    data.components.tpu;
  const oilChange5d =
    data.components.oil_change_5d ?? data.components.cl_change_5d;
  const iranWarNewsCount =
    data.components.iran_war_news_count ?? data.components.energy_news_count;

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
          ? `China demand conditions are weak. A softer yuan and slower industrial momentum are limiting import appetite and keeping pressure on soy complex demand.`
          : data.score >= 45
            ? `China buying is mixed, not a strong demand impulse. Flows are steady but not strong enough to tighten global soybean oil balance.`
            : `China demand is stable and mostly in line with expectations, so it is not the main shock driver right now.`,
      macroContext:
        cnyRate && cnyRate > 7.2
          ? `Yuan is weak at ${cnyRate.toFixed(2)}, which tends to slow import demand and favor lower-cost origins.`
          : `Currency conditions are not extreme, so demand sensitivity is mostly about growth and crush economics.`,
      supplyDemand: `China import pace still sets the marginal tone for global soy/oilseed flows; weaker buying leaves more supply available and caps ZL upside.`,
      geopolitical:
        data.score >= 50
          ? `Geopolitical friction and policy uncertainty can still reroute flow quickly, so the demand picture can change fast.`
          : `No immediate geopolitical shock in China trade flow, but surprises remain possible.`,
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
          ? `Macro risk is elevated. Iran-war headlines, volatile oil, and high uncertainty are all stacking up at once. Stay defensive on coverage timing.`
          : data.score >= 50
            ? `Macro noise is elevated but not full crisis. Oil, VIX, and uncertainty are above normal, so risk can reprice quickly on news.`
            : `Macro backdrop is relatively contained. No immediate systemic shock signal from oil, volatility, or geopolitical flow.`,
      macroContext:
        uncertaintyValue && uncertaintyValue > 200
          ? `Uncertainty is high enough to keep risk premia elevated across commodities, including soybean oil.`
          : `Uncertainty is in a manageable range, so fundamentals matter more than panic headlines.`,
      supplyDemand:
        oilChange5d !== null && oilChange5d > 0.05
          ? `Crude oil is up ${(oilChange5d * 100).toFixed(1)}% in 5 days, which strengthens renewable diesel pull for soybean oil and tightens availability.`
          : `Oil-driven demand pull is not extreme right now, so supply pressure from the energy channel is moderate.`,
      geopolitical:
        (iranWarNewsCount ?? 0) >= 4
          ? `Iran-war/Hormuz coverage is heavy this week (${iranWarNewsCount} headlines), so geopolitical risk to energy supply is a live input for ZL.`
          : `Geopolitical risk is present but not dominating the tape right now.`,
      investorSentiment:
        data.score >= 50
          ? `Funds are paying up for macro protection, which can keep soybean oil risk premium sticky.`
          : `Positioning looks closer to normal with less macro-hedging premium.`,
      nearTermOutlook:
        data.score >= 65
          ? `Watch Iran-war flow, VIX spikes, and crude moves daily. This regime can jump from alert to shock quickly.`
          : `Macro conditions are calmer; monitor headlines, but no immediate shock catalyst is dominant.`,
      zlImplication:
        data.score >= 65
          ? `DEFENSIVE POSTURE. Macro shock risk can lift ZL quickly through oil/biofuel channels. Keep coverage layered and avoid waiting for perfect entry.`
          : data.score >= 50
            ? `STAY ALERT but avoid panic. Keep normal buying cadence with tight monitoring of oil, VIX, and geopolitical headlines.`
            : `CONDITIONS ARE CONTAINED. Good window to execute scheduled coverage without crisis premium.`,
    },
    energy: {
      whatsHappening:
        data.score >= 80
          ? `ENERGY CRISIS. Crude oil is surging on supply disruption. When oil spikes, biofuel economics shift massively - more soybean oil gets diverted to renewable diesel. That means less oil for food use, prices UP.`
          : data.score >= 65
            ? `Oil supply shock underway. Crude is rising fast, which pushes biofuel margins and pulls soybean oil into the renewable diesel channel. Expect tighter physical supply and rising basis.`
            : data.score >= 50
              ? `Energy markets are running hot. Crude oil trending up, which keeps biofuel demand for soy oil strong. Not crisis mode, but costs are elevated.`
              : data.score >= 35
                ? `Energy markets are normal. Crude oil is stable, no supply disruptions. Biofuel demand for soy oil is steady at normal levels.`
                : `Energy is a tailwind right now. Falling crude eases biofuel cost pressure, meaning less soy oil gets pulled into renewable diesel. More supply for food use.`,
      macroContext:
        data.score >= 65
          ? `Geopolitical supply disruptions (Middle East, OPEC cuts, sanctions) are driving crude higher. The biofuel channel transmits this directly to soy oil.`
          : `Energy markets are balanced. No major supply disruptions or OPEC surprises moving crude prices.`,
      supplyDemand:
        data.score >= 65
          ? `Over 50% of US soybean oil now goes to biodiesel/renewable diesel. When crude spikes, that channel pulls even harder. Physical soy oil supply for food gets tight.`
          : `Biofuel demand for soy oil is steady at ~50% of domestic use. No unusual pull from the energy side.`,
      geopolitical:
        data.score >= 65
          ? `Strait of Hormuz risk, Iran/Israel tensions, or OPEC supply cuts can spike crude overnight. Each $10/barrel move in crude shifts biofuel economics significantly.`
          : `Geopolitical energy risk is background level. Hormuz open, OPEC stable, no active supply disruptions.`,
      investorSentiment:
        data.score >= 50
          ? `Energy traders are positioning for further upside in crude. That spills into soy oil via the biofuel linkage.`
          : `Energy positioning is neutral. No speculative pressure spilling into soy oil markets.`,
      nearTermOutlook:
        data.score >= 65
          ? `Watch crude oil closely. If CL breaks higher, soy oil will follow via biofuel demand. Basis could widen fast.`
          : `Energy outlook is stable. No imminent catalysts for crude spikes. Normal biofuel demand patterns expected.`,
      zlImplication:
        data.score >= 80
          ? `LOCK IN COVERAGE NOW. Energy crisis is pulling soy oil into biofuel hard. Prices will keep rising until crude stabilizes. Don't wait.`
          : data.score >= 65
            ? `ACT QUICKLY on coverage. Oil supply shock means higher biofuel demand for soy oil. Every day you wait, costs go up.`
            : data.score >= 50
              ? `STAY ALERT. Energy costs are elevated. Keep coverage current but don't panic-buy. Watch crude for direction.`
              : data.score >= 35
                ? `NORMAL CONDITIONS. Energy isn't pressuring soy oil. Buy on your schedule.`
                : `GOOD WINDOW. Falling crude means less biofuel pull on soy oil. Favorable conditions for buyers.`,
    },
  };

  return templates[data.driverName];
}
