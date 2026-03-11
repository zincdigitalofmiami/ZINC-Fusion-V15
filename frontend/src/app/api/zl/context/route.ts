/**
 * ZL Market Context — AI-powered "What's Happening" summary
 *
 * 1-2 sentence market context using driver scores and event headlines.
 * Uses OpenRouter GPT-OSS-120B with high reasoning for deep ZL analysis.
 * Works even when some drivers are stale — tells the buyer what we know
 * and what we're missing.
 *
 * Also receives recent event headlines from the Event Pulse system.
 * When events contradict lagging driver scores, the AI leads with events.
 */

import { MODEL_DRIVER_INTEL } from "@/lib/ai-config";
import { hasOpenRouterApiKey, openRouterCompleteText } from "@/lib/openrouter";
import { createHash } from "crypto";

export const dynamic = "force-dynamic";

const AI_REFRESH_UTC_HOUR = 10;
const zlContextCache = new Map<string, string>();

function getAiDayKey(now = new Date()): string {
  const d = new Date(now);
  if (d.getUTCHours() < AI_REFRESH_UTC_HOUR) {
    d.setUTCDate(d.getUTCDate() - 1);
  }
  return d.toISOString().slice(0, 10);
}

function getCacheKey(payload: unknown): string {
  const payloadHash = createHash("sha256")
    .update(JSON.stringify(payload))
    .digest("hex");
  return `${getAiDayKey()}:${payloadHash}`;
}

interface ContextRequest {
  price?: { current: number; changePct: number };
  drivers?: Array<{
    name: string;
    score: number;
    status: string;
    source: "live" | "stale" | "unavailable";
    rawValue: number | null;
    unit: string;
  }>;
  forecastsAvailable?: boolean;
  dataIssues?: string[];
  stalenessWarnings?: string[];
  recentEvents?: Array<{
    headline: string;
    source: string;
    hoursAgo: number;
    sentiment: string;
    confidence: number;
  }>;
  eventVelocity?: number;
  overrideReason?: string;
}

function buildContextDeterministic(payload: ContextRequest): string {
  const priceLine = payload.price
    ? `ZL is ${payload.price.changePct >= 0 ? "up" : "down"} ${Math.abs(payload.price.changePct).toFixed(1)}% at $${payload.price.current.toFixed(2)}.`
    : "No current signal.";

  const availableDrivers = (payload.drivers ?? []).filter((d) => d.source !== "unavailable");
  const topDriver =
    availableDrivers.length > 0
      ? availableDrivers.reduce((a, b) => (a.score >= b.score ? a : b))
      : null;

  const driverLine = topDriver
    ? `${topDriver.name} is the dominant pressure at ${topDriver.score}/100 (${topDriver.status}).`
    : "No current signal.";

  const missing = (payload.drivers ?? []).filter((d) => d.source === "unavailable");
  const coverageLine =
    missing.length > 0
      ? `Pending fresh data for: ${missing.map((d) => d.name).join(", ")}.`
      : "";

  if (payload.recentEvents && payload.recentEvents.length > 0) {
    const event = payload.recentEvents[0];
    const eventLine = `Top event flow: ${event.headline} (${event.source}, ${event.hoursAgo}h ago).`;
    return [priceLine, driverLine, eventLine, coverageLine].filter(Boolean).join(" ");
  }

  return [priceLine, driverLine, coverageLine].filter(Boolean).join(" ");
}

export async function POST(request: Request) {
  let payload: ContextRequest = {};
  try {
    payload = (await request.json()) as ContextRequest;
  } catch {
    return new Response("Invalid request", { status: 400 });
  }

  if (!hasOpenRouterApiKey()) {
    return new Response(buildContextDeterministic(payload), {
      status: 200,
      headers: { "Content-Type": "text/plain; charset=utf-8" },
    });
  }

  const cacheKey = getCacheKey(payload);
  const cached = zlContextCache.get(cacheKey);
  if (cached) {
    return new Response(cached, {
      status: 200,
      headers: { "Content-Type": "text/plain; charset=utf-8" },
    });
  }

  // Build context string from available data
  const lines: string[] = [];

  if (payload.price) {
    const dir = payload.price.changePct >= 0 ? "up" : "down";
    lines.push(
      `ZL soybean oil at $${payload.price.current.toFixed(2)}/lb, ${dir} ${Math.abs(payload.price.changePct).toFixed(1)}% today.`,
    );
  }

  if (payload.drivers) {
    const live = payload.drivers.filter((d) => d.source === "live");
    const stale = payload.drivers.filter((d) => d.source === "stale");
    const missing = payload.drivers.filter((d) => d.source === "unavailable");

    for (const d of live) {
      lines.push(
        `${d.name}: score ${d.score}/100 (${d.status}), raw ${d.rawValue} ${d.unit} [LIVE]`,
      );
    }
    for (const d of stale) {
      lines.push(
        `${d.name}: score ${d.score}/100 (${d.status}), raw ${d.rawValue} ${d.unit} [STALE]`,
      );
    }
    if (missing.length > 0) {
      lines.push(
        `Missing data: ${missing.map((d) => d.name).join(", ")} [NO DATA]`,
      );
    }
  }

  if (payload.forecastsAvailable === false) {
    lines.push("Model forecasts: NOT AVAILABLE");
  }

  // Event headlines — the real-time signal layer
  if (payload.recentEvents && payload.recentEvents.length > 0) {
    lines.push("");
    lines.push("RECENT EVENTS (last 72h):");
    for (const e of payload.recentEvents.slice(0, 8)) {
      const timeLabel = e.hoursAgo <= 24 ? `${e.hoursAgo}h ago` : `${Math.round(e.hoursAgo / 24)}d ago`;
      lines.push(
        `- [${timeLabel}] [${e.source}] ${e.headline} (${e.sentiment}, conf: ${e.confidence.toFixed(1)})`,
      );
    }

    if (payload.eventVelocity !== undefined && payload.eventVelocity > 1.5) {
      lines.push(
        `EVENT VELOCITY: ${payload.eventVelocity}x baseline (${payload.eventVelocity > 3 ? "CRITICAL" : payload.eventVelocity > 2 ? "ELEVATED" : "ABOVE NORMAL"})`,
      );
    }
  }

  if (payload.overrideReason) {
    lines.push("");
    lines.push(`POSTURE OVERRIDE ACTIVE: ${payload.overrideReason}`);
  }

  // Adapt system prompt based on whether events are present
  const hasEvents = payload.recentEvents && payload.recentEvents.length > 0;
  const isElevated = (payload.eventVelocity ?? 0) > 2;

  const DOMAIN_CONTEXT = `
DOMAIN KNOWLEDGE (use this to connect the dots):
- Soybean oil (ZL) is 40%+ consumed by US biofuel production (biodiesel, renewable diesel).
- Crude oil price drives biodiesel economics: when crude surges, soybean oil demand as feedstock rises, pulling ZL prices up.
- Middle East conflict / Strait of Hormuz closure → crude oil supply shock → energy prices spike → soybean oil gets pulled up as biofuel feedstock.
- Iran produces ~3.2M bbl/day. Hormuz handles 20% of world oil. Any disruption is massively bullish for energy and ag-energy complex.
- China buys 60% of global soybeans. US-China tariffs / trade war = demand destruction for US exports, but shifts Brazil premium.
- Sanctions on Iran/Russia = supply disruption bullish signal for energy and downstream commodity complex.
- India is #1 edible oil importer. India's reaction to oil shocks directly impacts palm/soy oil trade flows.
- EU, Japan, Korea energy dependence means their response to Hormuz disruption amplifies the shock.
`.trim();

  const CARD_PREAMBLE = `CARD LOCATION: This renders as the AI Market Context card on the Strategy page. The user sees the ZL price chart with horizontal Target Zones, 4 driver score gauges (VIX Stress, Crush Pressure, China Tension, Tariff Threat), forecast horizon confidence bars, and an Event Pulse timeline.

ZL FOCUS: Tell a soybean oil procurement buyer what matters RIGHT NOW for ZL price direction. Connect driver scores and event headlines to ZL through specific mechanisms: VIX spike → fund liquidation → ZL selling. Crush margin squeeze → processor slowdowns → less oil supply → ZL up. China tariff → export diversion → Gulf basis collapse → ZL down. Crude surge → biofuel economics → ZL pulled up.`;

  const systemPrompt = hasEvents
    ? `${CARD_PREAMBLE}

${DOMAIN_CONTEXT}

INSTRUCTIONS:
${isElevated ? "CRITICAL: Event velocity is extremely elevated. LEAD with what is happening in the world RIGHT NOW. The driver scores lag — they reflect last week, not today." : "Weigh both the quantitative driver scores AND the recent event headlines."}
- When you see war, military action, sanctions, or strait closures: trace the CAUSAL CHAIN to ZL (conflict → crude supply → energy prices → biofuel economics → ZL demand → price).
- Name the specific countries, commodities, and percentages. No generic statements.
- If there's a disconnect between calm driver scores and alarming headlines, say so explicitly.

OUTPUT: 1-2 sentences MAX. No bullet points, no preamble. Write like a Bloomberg terminal flash.`
    : `${CARD_PREAMBLE}

${DOMAIN_CONTEXT}

OUTPUT: 1-2 sentences MAX. Be direct — tell the buyer what matters RIGHT NOW for ZL. If data is stale, acknowledge it briefly. If drivers are missing, say what we're blind to. No preamble, no bullet points, no hedging.`;

  try {
    const text = await openRouterCompleteText({
      model: MODEL_DRIVER_INTEL,
      messages: [
        { role: "system", content: systemPrompt },
        { role: "user", content: lines.join("\n") },
      ],
      maxTokens: 250,
      temperature: 0.0,
      reasoning: { effort: "high" },
    });

    zlContextCache.set(cacheKey, text);

    return new Response(text, {
      status: 200,
      headers: { "Content-Type": "text/plain; charset=utf-8" },
    });
  } catch (error) {
    console.error("[zl/context] OpenRouter generation failed:", error);
    return new Response(buildContextDeterministic(payload), {
      status: 200,
      headers: { "Content-Type": "text/plain; charset=utf-8" },
    });
  }
}
