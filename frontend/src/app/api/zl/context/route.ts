/**
 * ZL Market Context — AI-powered "What's Happening" summary
 *
 * Streams a 2-3 sentence market context using the brief data.
 * Uses Vercel AI SDK with Claude Sonnet 4.5 for fast, actionable intel.
 * Works even when some drivers are stale — tells the buyer what we know
 * and what we're missing.
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
    source: "live" | "stale" | "unavailable";
    rawValue: number | null;
    unit: string;
  }>;
  forecastsAvailable?: boolean;
  dataIssues?: string[];
  stalenessWarnings?: string[];
}

export async function POST(request: Request) {
  let payload: ContextRequest = {};
  try {
    payload = (await request.json()) as ContextRequest;
  } catch {
    return new Response("Invalid request", { status: 400 });
  }

  if (!process.env.ANTHROPIC_API_KEY) {
    return new Response("AI unavailable", { status: 503 });
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

  const result = streamText({
    model: anthropic(MODEL_DRIVER_INTEL),
    maxOutputTokens: 250,
    system: `You are a procurement intelligence analyst for a US soybean oil buyer. Write 2-3 sentences of actionable market context. Be direct — tell the buyer what matters RIGHT NOW. If data is stale, acknowledge it briefly but still give useful guidance from what's available. If drivers are missing, say what we're blind to. No preamble, no bullet points, no hedging. Write like a Bloomberg terminal flash.`,
    prompt: lines.join("\n"),
  });

  return result.toTextStreamResponse();
}
