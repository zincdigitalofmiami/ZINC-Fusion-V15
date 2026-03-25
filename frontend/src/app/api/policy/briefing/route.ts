/**
 * Policy Intelligence Briefing — AI analysis of the policy landscape.
 *
 * Uses OpenRouter GPT-OSS-120B with high reasoning to produce an actionable
 * 1-2 sentence briefing with threat level indicator and ZL price implication.
 *
 * Pattern follows /api/zl/context and /api/sentiment/narrative.
 */

import {
  AI_DAILY_REFRESH_UTC_HOUR,
  AI_OUTPUT_VERSION,
  MODEL_DRIVER_INTEL,
} from "@/lib/ai-config";
import { hasOpenRouterApiKey, openRouterCompleteText } from "@/lib/openrouter";
import { createHash } from "crypto";

export const dynamic = "force-dynamic";

const AI_REFRESH_UTC_HOUR = AI_DAILY_REFRESH_UTC_HOUR;
const policyBriefingCache = new Map<string, string>();

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
  return `${AI_OUTPUT_VERSION}:${getAiDayKey()}:${payloadHash}`;
}

interface PolicyBriefingRequest {
  regime: {
    score: number;
    label: string;
    headline?: string;
    uncertaintyIndex: number;
    vix: number;
    oilChange5d: number;
    inflationExpectation: number;
    iranWarNews: number;
    newsVelocity: number;
  };
  metrics: {
    velocity: number | null;
    deadlinesActive: number;
    shockwaveCount: number;
    agencyCount: number;
    activeEvents: number;
  };
  topAgencies: Array<{ agency: string; count: number }>;
  recentLegislation: Array<{ title: string; agency: string; date: string }>;
  recentExecutive: Array<{ headline: string; date: string; impact: number | null }>;
  recentNews: Array<{ headline: string; source: string; date: string; tags: string[] }>;
}

function buildDeterministicBriefing(payload: PolicyBriefingRequest): string {
  const score = payload.regime.score;
  const indicator =
    score >= 70
      ? "🔴 CRITICAL"
      : score >= 55
        ? "🟠 ELEVATED"
        : score >= 35
          ? "🟡 WATCH"
          : "🟢 CLEAR";

  const topAgency = payload.topAgencies[0]?.agency ?? "agency flow";
  const topCount = payload.topAgencies[0]?.count ?? 0;
  const velocityText =
    payload.metrics.velocity !== null
      ? `${payload.metrics.velocity.toFixed(1)} actions/week`
      : `${payload.metrics.activeEvents} active policy events`;
  const directional =
    score >= 55
      ? "Macro threat is skewed risk-up for ZL through oil shock, uncertainty, and geopolitical channels."
      : "Macro threat is contained, so ZL direction is currently more tied to crush and baseline demand flow.";

  return `${indicator} — ${payload.regime.label}: ${topAgency} leads with ${topCount} recent actions and ${velocityText}. ${directional}`;
}

export async function POST(request: Request) {
  let payload: PolicyBriefingRequest;
  try {
    payload = (await request.json()) as PolicyBriefingRequest;
  } catch {
    return new Response("Invalid request", { status: 400 });
  }

  if (!hasOpenRouterApiKey()) {
    return new Response(buildDeterministicBriefing(payload), {
      status: 200,
      headers: { "Content-Type": "text/plain; charset=utf-8" },
    });
  }

  const cacheKey = getCacheKey(payload);
  const cached = policyBriefingCache.get(cacheKey);
  if (cached) {
    return new Response(cached, {
      status: 200,
      headers: { "Content-Type": "text/plain; charset=utf-8" },
    });
  }

  // Build context from policy data
  const lines: string[] = [];

  // Regime status
  lines.push(`MACRO THREAT LEVEL: ${payload.regime.score}/100 — "${payload.regime.label}"`);
  lines.push(
    `Uncertainty Index: ${payload.regime.uncertaintyIndex.toFixed(0)} | VIX: ${payload.regime.vix.toFixed(1)} | CL 5d: ${(payload.regime.oilChange5d * 100).toFixed(1)}%`,
  );
  lines.push(
    `Inflation (T5YIE): ${payload.regime.inflationExpectation.toFixed(2)}% | Iran/War Headlines: ${payload.regime.iranWarNews} | Macro News (7d): ${payload.regime.newsVelocity}`,
  );
  if (payload.regime.headline) {
    lines.push(`Status: ${payload.regime.headline}`);
  }

  // Activity metrics
  lines.push("");
  lines.push("ACTIVITY METRICS:");
  if (payload.metrics.velocity !== null) {
    lines.push(`- Bureaucracy Velocity: ${payload.metrics.velocity.toFixed(1)} actions/week`);
  }
  lines.push(`- Active Deadlines (90d): ${payload.metrics.deadlinesActive}`);
  lines.push(`- High-Impact Events: ${payload.metrics.shockwaveCount}`);
  lines.push(`- Active Agencies (90d): ${payload.metrics.agencyCount}`);
  lines.push(`- Total Active Events: ${payload.metrics.activeEvents}`);

  // Top agencies
  if (payload.topAgencies.length > 0) {
    lines.push("");
    lines.push("MOST ACTIVE AGENCIES:");
    for (const a of payload.topAgencies.slice(0, 5)) {
      lines.push(`- ${a.agency}: ${a.count} actions`);
    }
  }

  // Recent legislation
  if (payload.recentLegislation.length > 0) {
    lines.push("");
    lines.push("RECENT FEDERAL REGISTER (last 7 days):");
    for (const l of payload.recentLegislation.slice(0, 5)) {
      lines.push(`- [${l.date}] ${l.agency}: ${l.title}`);
    }
  }

  // Executive actions
  if (payload.recentExecutive.length > 0) {
    lines.push("");
    lines.push("RECENT EXECUTIVE ACTIONS:");
    for (const e of payload.recentExecutive.slice(0, 5)) {
      const impact = e.impact ? ` (ZL impact: ${(e.impact * 100).toFixed(1)}%)` : "";
      lines.push(`- [${e.date}] ${e.headline}${impact}`);
    }
  }

  // News intelligence
  if (payload.recentNews.length > 0) {
    lines.push("");
    lines.push("NEWS INTELLIGENCE (Google News, last 48h):");
    for (const n of payload.recentNews.slice(0, 8)) {
      lines.push(`- [${n.source}] ${n.headline} [tags: ${n.tags.join(", ")}]`);
    }
  }

  const system = `CARD LOCATION: This renders as the AI Policy Intelligence card at the top of the Legislation page. The user sees a regime threat gauge (score/100 + label), bureaucracy velocity chart, Federal Register agency filing counts, executive action timeline, and Google News policy headlines surrounding this card.

ZL FOCUS: You decode macro + policy signals into ZL (CBOT soybean oil futures) price impact. Causal chains you must trace:
- Iran-war / Hormuz risk -> crude oil spike -> renewable diesel economics -> soybean oil pull -> ZL up
- Inflation + uncertainty + VIX rise -> higher risk premium and wider ZL ranges
- EPA RVO / 45Z credit / SRE waivers -> RIN prices -> renewable diesel demand -> soybean oil pull
- Agency velocity still matters, but tariffs are secondary versus oil + macro regime in the current context.

OUTPUT FORMAT — ONE PARAGRAPH ONLY:
Start with exactly one indicator: 🟢 CLEAR | 🟡 WATCH | 🟠 ELEVATED | 🔴 CRITICAL — then a short headline.
Follow with 1-2 sentences MAX: name the single most important policy action, trace its causal chain to ZL price, and give a directional call. No hedging. No "could" or "may." State what IS happening.`;
  const prompt = lines.join("\n");

  try {
    const text = await openRouterCompleteText({
      model: MODEL_DRIVER_INTEL,
      messages: [
        { role: "system", content: system },
        { role: "user", content: prompt },
      ],
      maxTokens: 250,
      temperature: 0.0,
      reasoning: { effort: "high" },
    });

    policyBriefingCache.set(cacheKey, text);

    return new Response(text, {
      status: 200,
      headers: { "Content-Type": "text/plain; charset=utf-8" },
    });
  } catch (error) {
    console.error("[policy/briefing] OpenRouter generation failed:", error);
    return new Response(buildDeterministicBriefing(payload), {
      status: 200,
      headers: { "Content-Type": "text/plain; charset=utf-8" },
    });
  }
}
