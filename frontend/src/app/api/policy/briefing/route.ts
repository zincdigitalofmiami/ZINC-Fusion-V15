/**
 * Policy Intelligence Briefing — AI analysis of the policy landscape.
 *
 * Uses OpenRouter GPT-OSS-120B with high reasoning to produce an actionable
 * 1-2 sentence briefing with threat level indicator and ZL price implication.
 *
 * Pattern follows /api/zl/context and /api/sentiment/narrative.
 */

import { MODEL_DRIVER_INTEL } from "@/lib/ai-config";
import { hasOpenRouterApiKey, openRouterCompleteText } from "@/lib/openrouter";

export const dynamic = "force-dynamic";

interface PolicyBriefingRequest {
  regime: {
    score: number;
    label: string;
    headline?: string;
    tpu: number;
    emv: number;
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

export async function POST(request: Request) {
  let payload: PolicyBriefingRequest;
  try {
    payload = (await request.json()) as PolicyBriefingRequest;
  } catch {
    return new Response("Invalid request", { status: 400 });
  }

  if (!hasOpenRouterApiKey()) {
    return new Response("AI briefing unavailable — no API key configured.", { status: 200 });
  }

  // Build context from policy data
  const lines: string[] = [];

  // Regime status
  lines.push(`POLICY THREAT LEVEL: ${payload.regime.score}/100 — "${payload.regime.label}"`);
  lines.push(`TPU (Trade Policy Uncertainty): ${payload.regime.tpu.toFixed(0)} | EMV Trade: ${payload.regime.emv.toFixed(0)}`);
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

ZL FOCUS: You decode US government policy actions into ZL (CBOT soybean oil futures) price impact. Causal chains you must trace:
- EPA RVO / 45Z credit / SRE waivers → RIN prices → renewable diesel demand → soybean oil pull (6B+ lbs/year)
- USTR Section 301 tariffs → China pivots to Brazil within 48h → US Gulf basis collapse → ZL bearish
- Agency velocity: EPA + USTR + USDA accelerating simultaneously = regime shift. Normal: 5-10 filings/month. Crisis: 30+.
- TPU is LAGGING (newspaper coverage). Bureaucracy velocity is LEADING (actual government action). Divergence = edge.
- Fed cuts → weak USD → bullish ZL. VIX spike + trade escalation → fund liquidation overshoot reverses in 5-10 days.

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

    return new Response(text, {
      status: 200,
      headers: { "Content-Type": "text/plain; charset=utf-8" },
    });
  } catch (error) {
    console.error("[policy/briefing] OpenRouter generation failed:", error);
    return new Response("AI briefing unavailable.", { status: 200 });
  }
}
