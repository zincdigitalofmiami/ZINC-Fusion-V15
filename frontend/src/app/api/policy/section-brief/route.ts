/**
 * Per-section AI brief — streams 1-2 sentence analysis for a policy section.
 *
 * Called once per section (agency, executive, news). Each gets its own
 * tailored prompt. Returns streamed text, not JSON.
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
const policySectionBriefCache = new Map<string, string>();

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

interface SectionRequest {
  section: "agency" | "executive" | "news";
  regime: { score: number; label: string };
  data: Array<Record<string, unknown>>;
}

const SECTION_PROMPTS: Record<string, string> = {
  agency: `CARD LOCATION: Federal Register Agency Activity section on the Legislation page. The user sees a ranked list of agencies with filing counts and a 90-day activity chart.

ZL FOCUS: Identify which agency's filings most directly affect ZL (CBOT soybean oil futures) in the current macro regime — EPA (biofuel mandates, RVO, 45Z, SRE waivers), DOE/State/Defense (energy security, sanctions, conflict posture), Fed/Treasury-linked regulation (inflation/uncertainty channels), or USDA (export/crop programs). ONE sentence only: name the agency, what they filed, and the specific ZL price implication. No hedging.`,
  executive: `CARD LOCATION: Executive Actions section on the Legislation page. The user sees presidential executive orders and memoranda with dates and ZL impact scores.

ZL FOCUS: Executive actions hit ZL (CBOT soybean oil futures) through biofuel policy (RVO mandates, 45Z credits, SRE waivers), energy security/geopolitics (Iran-war posture, sanctions, SPR, shipping lanes), and macro policy signaling (inflation/uncertainty risk premium). ONE sentence only: name the most impactful action, trace its causal chain to ZL price, and give a directional call. No hedging.`,
  news: `CARD LOCATION: Policy News Intelligence section on the Legislation page. The user sees Google News headlines with source attribution and category tags.

ZL FOCUS: Filter for headlines that move ZL (CBOT soybean oil futures) — Iran war / Hormuz / sanctions (oil shock), inflation and uncertainty spikes, VIX regime change, biofuel legislation, and major energy policy actions. ONE sentence only: state the dominant narrative theme and whether it is bullish or bearish for ZL with the specific causal mechanism. No hedging.`,
};

function buildSectionDeterministic(payload: SectionRequest): string {
  const first = payload.data[0] ?? {};

  if (payload.section === "agency") {
    const agency = typeof first.agency === "string" ? first.agency : "EPA/USTR/USDA";
    const count = typeof first.count === "number" ? first.count : null;
    return `${agency}${count !== null ? ` (${count} actions)` : ""} is the dominant filing lane right now and remains the clearest policy transmission path into ZL pricing.`;
  }

  if (payload.section === "executive") {
    const headline =
      typeof first.headline === "string" ? first.headline : "Executive policy flow remains the active signal";
    return `${headline} is the highest-impact executive signal currently on screen and maps directly into ZL through energy/biofuel and macro-risk expectations.`;
  }

  const headline = typeof first.headline === "string" ? first.headline : null;
  const source = typeof first.source === "string" ? first.source : null;
  if (headline) {
    return `${headline}${source ? ` (${source})` : ""} is the dominant policy-news narrative and is setting near-term ZL direction through macro and energy expectations.`;
  }

  return "No current signal.";
}

export async function POST(request: Request) {
  let payload: SectionRequest;
  try {
    payload = (await request.json()) as SectionRequest;
  } catch {
    return new Response("Invalid request", { status: 400 });
  }

  if (!hasOpenRouterApiKey()) {
    return new Response(buildSectionDeterministic(payload), {
      status: 200,
      headers: { "Content-Type": "text/plain; charset=utf-8" },
    });
  }

  const cacheKey = getCacheKey(payload);
  const cached = policySectionBriefCache.get(cacheKey);
  if (cached) {
    return new Response(cached, {
      status: 200,
      headers: { "Content-Type": "text/plain; charset=utf-8" },
    });
  }

  const lines: string[] = [];
  lines.push(`Macro Threat: ${payload.regime.score}/100 — "${payload.regime.label}"`);
  lines.push("");

  for (const item of payload.data.slice(0, 8)) {
    const parts = Object.entries(item)
      .map(([k, v]) => `${k}: ${v}`)
      .join(" | ");
    lines.push(`- ${parts}`);
  }

  try {
    const text = await openRouterCompleteText({
      model: MODEL_DRIVER_INTEL,
      messages: [
        {
          role: "system",
          content: SECTION_PROMPTS[payload.section] ?? SECTION_PROMPTS.agency,
        },
        { role: "user", content: lines.join("\n") },
      ],
      maxTokens: 120,
      temperature: 0.0,
      reasoning: { effort: "high" },
    });

    policySectionBriefCache.set(cacheKey, text);

    return new Response(text, {
      status: 200,
      headers: { "Content-Type": "text/plain; charset=utf-8" },
    });
  } catch (error) {
    console.error("[policy/section-brief] OpenRouter generation failed:", error);
    return new Response(buildSectionDeterministic(payload), {
      status: 200,
      headers: { "Content-Type": "text/plain; charset=utf-8" },
    });
  }
}
