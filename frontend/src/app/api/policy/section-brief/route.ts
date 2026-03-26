/**
 * Per-section AI brief — streams a detailed paragraph analysis for a policy section.
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

ZL FOCUS: Identify which agency's filings most directly affect ZL (CBOT soybean oil futures) in the current macro regime — EPA (biofuel mandates, RVO, 45Z, SRE waivers), DOE/State/Defense (energy security, sanctions, conflict posture), Fed/Treasury-linked regulation (inflation/uncertainty channels), or USDA (export/crop programs). Write one detailed paragraph of at least 4 sentences: name the dominant agency, explain what was filed, connect it to transmission into ZL, and explain why this section should matter for execution today. No hedging.`,
  executive: `CARD LOCATION: Executive Actions section on the Legislation page. The user sees presidential executive orders and memoranda with dates and ZL impact scores.

ZL FOCUS: Executive actions hit ZL (CBOT soybean oil futures) through biofuel policy (RVO mandates, 45Z credits, SRE waivers), energy security/geopolitics (Iran-war posture, sanctions, SPR, shipping lanes), and macro policy signaling (inflation/uncertainty risk premium). Write one detailed paragraph of at least 4 sentences: identify the most impactful action, trace its causal chain to ZL price, explain corroboration from surrounding signals, and give a directional call for near-term procurement pressure. No hedging.`,
  news: `CARD LOCATION: Policy News Intelligence section on the Legislation page. The user sees Google News headlines with source attribution and category tags.

ZL FOCUS: Filter for headlines that move ZL (CBOT soybean oil futures) — Iran war / Hormuz / sanctions (oil shock), inflation and uncertainty spikes, VIX regime change, biofuel legislation, and major energy policy actions. Write one detailed paragraph of at least 4 sentences: state the dominant narrative theme, show the causal mechanism into ZL, identify what is signal versus noise in this news lane, and finish with directional pressure for buyers. No hedging.`,
};

function buildSectionDeterministic(payload: SectionRequest): string {
  const first = payload.data[0] ?? {};

  if (payload.section === "agency") {
    const agency = typeof first.agency === "string" ? first.agency : "EPA/USTR/USDA";
    const count = typeof first.count === "number" ? first.count : null;
    return `${agency}${count !== null ? ` (${count} actions)` : ""} is the dominant filing lane right now and remains the clearest policy transmission path into ZL pricing. This section is actionable because filing intensity and agency mix are early signals of policy follow-through before price fully reprices. When this lane accelerates, ZL procurement risk should be treated as active rather than theoretical. Use the agency mix here as a direct signal for whether policy pressure is building or fading this week.`;
  }

  if (payload.section === "executive") {
    const headline =
      typeof first.headline === "string" ? first.headline : "Executive policy flow remains the active signal";
    return `${headline} is the highest-impact executive signal currently on screen and maps directly into ZL through energy, biofuel, and macro-risk expectations. This section matters because executive actions can change price expectations faster than slow-moving rulemaking lanes. In practice, this means procurement timing should incorporate the policy shock path rather than waiting for lagged confirmation. Treat executive flow here as immediate context for directional risk and volatility expansion.`;
  }

  const headline = typeof first.headline === "string" ? first.headline : null;
  const source = typeof first.source === "string" ? first.source : null;
  if (headline) {
    return `${headline}${source ? ` (${source})` : ""} is the dominant policy-news narrative and is setting near-term ZL direction through macro and energy expectations. This news lane is useful because it captures narrative acceleration before many quantitative inputs refresh. The key is whether these headlines reinforce oil-shock, inflation, uncertainty, and trade-friction pressure channels at the same time. Use this section to separate high-velocity macro signal from background headline noise.`;
  }

  return "No current signal. The section currently lacks enough structured observations to identify a dominant policy transmission path into ZL. Treat this as missing context rather than a clean risk-off or risk-on indication. Keep execution anchored to the live regime metrics until this lane repopulates.";
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
      maxTokens: 650,
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
