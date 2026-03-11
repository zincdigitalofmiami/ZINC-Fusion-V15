/**
 * Per-section AI brief — streams 1-2 sentence analysis for a policy section.
 *
 * Called once per section (agency, executive, news). Each gets its own
 * tailored prompt. Returns streamed text, not JSON.
 */

import { MODEL_DRIVER_INTEL } from "@/lib/ai-config";
import { hasOpenRouterApiKey, openRouterCompleteText } from "@/lib/openrouter";

export const dynamic = "force-dynamic";

interface SectionRequest {
  section: "agency" | "executive" | "news";
  regime: { score: number; label: string };
  data: Array<Record<string, unknown>>;
}

const SECTION_PROMPTS: Record<string, string> = {
  agency: `CARD LOCATION: Federal Register Agency Activity section on the Legislation page. The user sees a ranked list of agencies with filing counts and a 90-day activity chart.

ZL FOCUS: Identify which agency's filings most directly affect ZL (CBOT soybean oil futures) — EPA (biofuel mandates, RVO, 45Z, SRE waivers → RIN prices → soybean oil demand), USTR (tariffs → China soy diversion → Gulf basis), or USDA (export programs, crop reports). ONE sentence only: name the agency, what they filed, and the specific ZL price implication. No hedging.`,
  executive: `CARD LOCATION: Executive Actions section on the Legislation page. The user sees presidential executive orders and memoranda with dates and ZL impact scores.

ZL FOCUS: Executive orders hit ZL (CBOT soybean oil futures) through biofuel policy (RVO mandates, 45Z credits, SRE waivers → RIN prices → soybean oil demand), trade policy (Section 301, retaliatory tariffs → China pivots to Brazil → Gulf basis collapse), or energy policy (SPR releases, drilling orders → crude price → biofuel economics → ZL). ONE sentence only: name the most impactful action, trace its causal chain to ZL price, and give a directional call. No hedging.`,
  news: `CARD LOCATION: Policy News Intelligence section on the Legislation page. The user sees Google News headlines with source attribution and category tags.

ZL FOCUS: Filter for headlines that move ZL (CBOT soybean oil futures) — biofuel legislation affecting soybean oil demand, China trade actions affecting US soy exports, EPA regulation affecting RIN/RVO, tariff escalation affecting Gulf basis. ONE sentence only: state the dominant narrative theme and whether it is bullish or bearish for ZL with the specific causal mechanism. No hedging.`,
};

function buildSectionFallback(payload: SectionRequest): string {
  const first = payload.data[0] ?? {};
  if (payload.section === "agency") {
    const agency = typeof first.agency === "string" ? first.agency : "EPA/USTR/USDA";
    return `${agency} is the key filing source right now, and that policy flow matters for ZL through biofuel mandate signals (RVO/45Z/SRE) and export competitiveness expectations.`;
  }
  if (payload.section === "executive") {
    const headline = typeof first.headline === "string" ? first.headline : "Executive policy flow";
    return `${headline} is the main executive signal on screen, and the ZL impact channel is policy-driven demand and trade posture rather than intraday noise.`;
  }
  return `Policy news flow is elevated, and the dominant ZL transmission path remains regulation/trade headlines changing soybean oil demand expectations and Gulf basis risk.`;
}

export async function POST(request: Request) {
  let payload: SectionRequest;
  try {
    payload = (await request.json()) as SectionRequest;
  } catch {
    return new Response("Invalid request", { status: 400 });
  }

  if (!hasOpenRouterApiKey()) {
    return new Response(buildSectionFallback(payload), {
      status: 200,
      headers: { "Content-Type": "text/plain; charset=utf-8" },
    });
  }

  const lines: string[] = [];
  lines.push(`Policy Threat: ${payload.regime.score}/100 — "${payload.regime.label}"`);
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

    return new Response(text, {
      status: 200,
      headers: { "Content-Type": "text/plain; charset=utf-8" },
    });
  } catch (error) {
    console.error("[policy/section-brief] OpenRouter generation failed:", error);
    return new Response(buildSectionFallback(payload), {
      status: 200,
      headers: { "Content-Type": "text/plain; charset=utf-8" },
    });
  }
}
