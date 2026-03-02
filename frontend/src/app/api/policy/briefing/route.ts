/**
 * Policy Intelligence Briefing — AI-streamed analysis of the policy landscape.
 *
 * Uses Vercel AI SDK + Claude Sonnet 4.5 to produce an actionable
 * 4-6 sentence briefing: threat level, key drivers, what changed,
 * and the ZL implications.
 *
 * Pattern follows /api/zl/context and /api/sentiment/narrative.
 */

import { streamText } from "ai";
import { anthropic } from "@ai-sdk/anthropic";
import { MODEL_DRIVER_INTEL } from "@/lib/ai-config";

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

  if (!process.env.ANTHROPIC_API_KEY) {
    return new Response("AI unavailable", { status: 503 });
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

  const result = streamText({
    model: anthropic(MODEL_DRIVER_INTEL),
    maxOutputTokens: 400,
    system: `You are an elite policy intelligence analyst for ZL (CBOT soybean oil futures). You decode policy into price impact.

DOMAIN KNOWLEDGE:
- Biofuel demand chain: EPA RVO → RIN prices → renewable diesel demand → soybean oil pull (6B+ lbs/year). 45Z credit ($1/gal). SRE waivers destroy RIN demand overnight.
- Trade war: US soy faces 13% China tariff vs Brazil 3%. Section 301 → Chinese buyers pivot to Brazil within 48h → Gulf basis collapse.
- Agency velocity: EPA + USTR + USDA accelerating simultaneously = regime shift. Normal: 5-10 filings/month. Crisis: 30+.
- TPU is LAGGING (newspaper coverage). Bureaucracy velocity is LEADING (actual government action). Divergence = edge.
- Cross-driver: Fed cuts → weak USD → bullish ZL. VIX spike + trade escalation → fund liquidation overshoot reverses in 5-10 days.

OUTPUT FORMAT — ONE PARAGRAPH ONLY:
Start with exactly one indicator: 🟢 CLEAR | 🟡 WATCH | 🟠 ELEVATED | 🔴 CRITICAL — then a short headline.
Follow with 2-3 sentences MAX: name the specific policy action that matters most, trace the causal chain to ZL price impact, and give a directional call. No hedging. No "could" or "may." State what IS happening.`,
    prompt: lines.join("\n"),
  });

  return result.toTextStreamResponse();
}
