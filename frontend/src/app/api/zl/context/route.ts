/**
 * ZL Market Context — AI-powered "What's Happening" summary
 *
 * Streams a 2-3 sentence market context using the brief data.
 * Uses Vercel AI SDK with Claude Sonnet 4.5 for fast, actionable intel.
 * Works even when some drivers are stale — tells the buyer what we know
 * and what we're missing.
 *
 * NEW: Also receives recent event headlines from the Event Pulse system.
 * When events contradict lagging driver scores, the AI leads with events.
 */

import { streamText } from "ai";
import { anthropic } from "@ai-sdk/anthropic";
import { MODEL_DRIVER_INTEL } from "@/lib/ai-config";

export const dynamic = "force-dynamic";

interface ContextRequest {
  price?: { current: number; changePct: number };
  drivers?: Array<{
    name: string;
    score: number;
    status: string;
    source: "live" | "stale" | "proxy" | "unavailable";
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

export async function POST(request: Request) {
  let payload: ContextRequest = {};
  try {
    payload = (await request.json()) as ContextRequest;
  } catch {
    return new Response("Invalid request", { status: 400 });
  }

  if (!process.env.ANTHROPIC_API_KEY) {
    return new Response("AI briefing unavailable — no API key configured.", { status: 200 });
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
    const proxy = payload.drivers.filter((d) => d.source === "proxy");
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
    for (const d of proxy) {
      lines.push(
        `${d.name}: score ${d.score}/100 (${d.status}), raw ${d.rawValue} ${d.unit} [PROXY]`,
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

  const systemPrompt = hasEvents
    ? `You are a senior procurement intelligence analyst for a US soybean oil buyer. Write 3-5 sentences of actionable market context.

${DOMAIN_CONTEXT}

INSTRUCTIONS:
${isElevated ? "CRITICAL: Event velocity is extremely elevated. LEAD with what is happening in the world RIGHT NOW. The driver scores lag — they reflect last week, not today." : "Weigh both the quantitative driver scores AND the recent event headlines."}
- When you see war, military action, sanctions, or strait closures: IMMEDIATELY explain the CAUSAL CHAIN to soybean oil prices (conflict → crude supply → energy prices → biofuel economics → ZL demand → price).
- Name the specific countries affected and how they will react (India cutting imports, EU scrambling for LNG, China redirecting soybean trade).
- If crude oil is surging, quantify the ZL impact: "Crude +X% typically pulls soybean oil 30-50% of that move via biofuel substitution."
- If there's a disconnect between calm driver scores and alarming headlines, say so explicitly: "Scores show calm but the world has changed — [explain why]."
- If tariffs/sanctions are in play, explain who gets hurt and who benefits in soybean trade flows.
- Be direct and specific. No generic statements. Name countries, name commodities, name percentages. Write like a Bloomberg terminal flash from someone who understands the full supply chain.`
    : `You are a senior procurement intelligence analyst for a US soybean oil buyer. Write 2-3 sentences of actionable market context.

${DOMAIN_CONTEXT}

Be direct — tell the buyer what matters RIGHT NOW. If data is stale, acknowledge it briefly but still give useful guidance from what's available. If drivers are missing, say what we're blind to. No preamble, no bullet points, no hedging. Write like a Bloomberg terminal flash.`;

  const result = streamText({
    model: anthropic(MODEL_DRIVER_INTEL),
    maxOutputTokens: 500,
    system: systemPrompt,
    prompt: lines.join("\n"),
  });

  return result.toTextStreamResponse();
}
