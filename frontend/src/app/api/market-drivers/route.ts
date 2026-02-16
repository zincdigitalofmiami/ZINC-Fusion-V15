import { NextResponse } from "next/server";
import {
  generateAIIntelligence,
  type MarketData,
  type AIIntelligence,
} from "@/lib/ai-intelligence";
import {
  generateDriverIntel,
  generateFallbackDriverIntel,
  type DriverIntel,
} from "@/lib/ai-driver-intel";
import { calculateVixStress } from "@/lib/services/vix-service";
import { calculateCrushPressure } from "@/lib/services/crush-service";
import { calculateChinaTension } from "@/lib/services/china-service";
import { calculateTariffThreat } from "@/lib/services/policy-service";
import { generateMarketIntelligence } from "@/lib/services/narrative-service";
import {
  fetchMarketDriversData,
  findMissingPrimaryData,
  computeDataFreshness,
  buildMarketData,
} from "@/lib/services/market-drivers-queries";

export const dynamic = "force-dynamic";
// Vercel Pro allows up to 300s. The 3 AM cron is the ONLY call that generates
// AI — let it take as long as it needs. Every other request serves from cache.
export const maxDuration = 300;

const CACHE_STALE_WHILE_REVALIDATE_SECONDS = 60 * 60;

// Must match frontend/vercel.json daily cron (3 AM UTC).
const DAILY_REFRESH_UTC_HOUR = 3;
const DAILY_REFRESH_UTC_MINUTE = 0;

// =============================================================================
// DAILY AI CACHE — Anthropic runs ONCE at 3 AM UTC, cached until next 3 AM
// =============================================================================
const AI_REFRESH_UTC_HOUR = 3; // Reset AI cache at 3 AM UTC each day

interface AiCacheEntry {
  dayKey: string;
  aiIntelligence: AIIntelligence | null;
  vixIntel: DriverIntel | null;
  crushIntel: DriverIntel | null;
  chinaIntel: DriverIntel | null;
  tariffIntel: DriverIntel | null;
}

// Module-level singleton — persists across requests within the same serverless
// instance. On Vercel, cold starts get a fresh cache = one AI call, then all
// subsequent requests in that instance reuse it until 5 AM UTC rolls over.
// NOTE: This is per-Lambda-instance, NOT shared across instances. Multiple
// concurrent users may each trigger one AI call on their first request if they
// hit different instances. This is an acceptable trade-off for Vercel serverless.
let aiCache: AiCacheEntry | null = null;

/** Returns YYYY-MM-DD for the current "AI day" (resets at 5 AM UTC). */
function getAiDayKey(now = new Date()): string {
  // Before 5 AM UTC → still "yesterday's" AI day
  const d = new Date(now);
  if (d.getUTCHours() < AI_REFRESH_UTC_HOUR) {
    d.setUTCDate(d.getUTCDate() - 1);
  }
  return d.toISOString().slice(0, 10);
}

function getAiCache(): AiCacheEntry | null {
  if (!aiCache) return null;
  if (aiCache.dayKey !== getAiDayKey()) return null; // stale — new day
  return aiCache;
}

function setAiCache(entry: AiCacheEntry): void {
  aiCache = entry;
}

function getDailyRefreshMeta(now = new Date()) {
  const nextRefresh = new Date(
    Date.UTC(
      now.getUTCFullYear(),
      now.getUTCMonth(),
      now.getUTCDate(),
      DAILY_REFRESH_UTC_HOUR,
      DAILY_REFRESH_UTC_MINUTE,
      0,
      0,
    ),
  );
  if (now >= nextRefresh) nextRefresh.setUTCDate(nextRefresh.getUTCDate() + 1);

  const sMaxAge = Math.max(
    60,
    Math.floor((nextRefresh.getTime() - now.getTime()) / 1000),
  );
  const headers = {
    "Cache-Control": `public, s-maxage=${sMaxAge}, stale-while-revalidate=${CACHE_STALE_WHILE_REVALIDATE_SECONDS}`,
    "X-Narrative-Next-Refresh-Utc": nextRefresh.toISOString(),
  };

  return {
    nextRefreshUtc: nextRefresh.toISOString(),
    headers,
  };
}

// =============================================================================
// MAIN API HANDLER — Pure Orchestration
// =============================================================================

// The nightly cron (3 AM UTC) is the ONLY request that calls Anthropic.
// No timeout — let it cook. Every daytime request serves from cache.
const AI_TIMEOUT_MS = 120_000; // 2 min safety net, but cron has 300s total

function withTimeout<T>(
  promise: Promise<T>,
  ms: number,
  fallback: T,
): Promise<T> {
  let timer: ReturnType<typeof setTimeout>;
  return Promise.race([
    promise.then((v) => {
      clearTimeout(timer);
      return v;
    }),
    new Promise<T>((resolve) => {
      timer = setTimeout(() => resolve(fallback), ms);
    }),
  ]);
}

export async function GET() {
  try {
    // 1. Fetch all data in parallel
    const rawData = await fetchMarketDriversData();

    // 2. Validate primary data — 503 if missing
    const missing = findMissingPrimaryData(rawData);
    if (missing.length > 0) {
      return NextResponse.json(
        {
          error:
            "Missing required market data — all 4 drivers must have live data",
          missing,
          data_quality: {
            vix: { date: rawData.vixDate, available: rawData.vix !== null },
            crush: {
              date: rawData.crushDate,
              available: rawData.crush !== null,
            },
            cny: { date: rawData.cnyDate, available: rawData.cnyRate !== null },
            tpu: { date: rawData.tpuDate, available: rawData.tpu !== null },
          },
        },
        { status: 503, headers: { "Cache-Control": "no-store" } },
      );
    }

    // Past the 503 guard: all 4 primary values are guaranteed non-null
    const vix = rawData.vix as number;
    const crush = rawData.crush as number;
    const cny = rawData.cnyRate as number;
    const tpu = rawData.tpu as number;
    const asOfDate = new Date().toISOString().split("T")[0];

    // 3. Score all 4 drivers
    const vixResult = calculateVixStress(
      vix,
      rawData.vix3m,
      rawData.ovx,
      rawData.realizedVol,
      rawData.vixZlCorr,
      rawData.hedgeCount,
      rawData.volSignal,
    );
    const crushResult = calculateCrushPressure(
      crush,
      rawData.oilShare,
      rawData.oilShare5dAgo,
      rawData.crushSignal,
    );
    const chinaResult = calculateChinaTension(
      rawData.fxiChange20d,
      rawData.fxiChange5d,
      cny,
      rawData.cnyChange20d,
      rawData.bdryChange20d,
      rawData.soyChinaNews,
      rawData.totalNews,
      rawData.chinaSignal,
    );
    const tariffResult = calculateTariffThreat(
      tpu,
      rawData.emv,
      rawData.legislationCount,
      rawData.soyTariffNews,
      rawData.tariffSignal,
    );

    // 4. Generate rule-based narrative
    const ruleBasedIntelligence = generateMarketIntelligence(
      vixResult,
      vix,
      crushResult,
      crush,
      rawData.oilShare,
      chinaResult,
      cny,
      rawData.fxiChange20d,
      tariffResult,
      tpu,
    );

    // 5. Build AI MarketData
    const marketData: MarketData = buildMarketData(
      rawData,
      {
        vix: vixResult.score,
        crush: crushResult.score,
        china: chinaResult.score,
        tariff: tariffResult.score,
      },
      asOfDate,
    );

    // 6. Daily AI cache — only call Anthropic ONCE per day
    const cached = getAiCache();
    let aiIntelligence: AIIntelligence | null;
    let vixIntel: DriverIntel | null;
    let crushIntel: DriverIntel | null;
    let chinaIntel: DriverIntel | null;
    let tariffIntel: DriverIntel | null;

    if (cached) {
      // Cache hit — skip ALL Anthropic calls
      aiIntelligence = cached.aiIntelligence;
      vixIntel = cached.vixIntel;
      crushIntel = cached.crushIntel;
      chinaIntel = cached.chinaIntel;
      tariffIntel = cached.tariffIntel;
    } else {
      // Cache miss — call AI with timeout, then cache for the rest of the day
      [aiIntelligence, vixIntel, crushIntel, chinaIntel, tariffIntel] =
        await Promise.all([
          withTimeout(
            generateAIIntelligence(marketData).catch(() => null),
            AI_TIMEOUT_MS,
            null,
          ),
          withTimeout(
            generateDriverIntel({
              driverName: "vix",
              score: vixResult.score,
              level: vixResult.level,
              regime: vixResult.regime,
              components: vixResult.components as unknown as Record<
                string,
                number | null
              >,
              asOfDate,
            }).catch(() => null),
            AI_TIMEOUT_MS,
            null,
          ),
          withTimeout(
            generateDriverIntel({
              driverName: "crush",
              score: crushResult.score,
              level: crushResult.level,
              regime: crushResult.regime,
              components: crushResult.components as unknown as Record<
                string,
                number | null
              >,
              asOfDate,
            }).catch(() => null),
            AI_TIMEOUT_MS,
            null,
          ),
          withTimeout(
            generateDriverIntel({
              driverName: "china",
              score: chinaResult.score,
              level: chinaResult.level,
              regime: chinaResult.regime,
              components: chinaResult.components as unknown as Record<
                string,
                number | null
              >,
              asOfDate,
            }).catch(() => null),
            AI_TIMEOUT_MS,
            null,
          ),
          withTimeout(
            generateDriverIntel({
              driverName: "tariff",
              score: tariffResult.score,
              level: tariffResult.level,
              regime: tariffResult.regime,
              components: tariffResult.components as unknown as Record<
                string,
                number | null
              >,
              asOfDate,
            }).catch(() => null),
            AI_TIMEOUT_MS,
            null,
          ),
        ]);

      // Persist to cache — all subsequent requests today skip AI entirely
      setAiCache({
        dayKey: getAiDayKey(),
        aiIntelligence,
        vixIntel,
        crushIntel,
        chinaIntel,
        tariffIntel,
      });
    }

    // 7. Shape intelligence response
    const intelligence = aiIntelligence
      ? {
          headline: aiIntelligence.headline,
          summary: aiIntelligence.reasoning,
          drivers: [
            ...aiIntelligence.keyRisks.map((r) => ({
              label: "Risk",
              outlook: "PRESSURE" as const,
              detail: r,
            })),
            ...aiIntelligence.keySupports.map((s) => ({
              label: "Support",
              outlook: "SUPPORTIVE" as const,
              detail: s,
            })),
          ],
          zlOutlook: aiIntelligence.zlOutlook,
          zlColor:
            aiIntelligence.zlOutlook === "BEARISH"
              ? "#EF4444"
              : aiIntelligence.zlOutlook === "CAUTIOUS"
                ? "#F97316"
                : aiIntelligence.zlOutlook === "NEUTRAL"
                  ? "#EAB308"
                  : "#22C55E",
          tradingImplication: aiIntelligence.tradingImplication,
          comprehensiveReport: aiIntelligence.comprehensiveReport,
          aiPowered: true,
        }
      : { ...ruleBasedIntelligence, aiPowered: false };

    // 8. Driver intel fallbacks
    const vixWhatsHappening =
      vixIntel ??
      generateFallbackDriverIntel({
        driverName: "vix",
        score: vixResult.score,
        level: vixResult.level,
        regime: vixResult.regime,
        components: vixResult.components as unknown as Record<
          string,
          number | null
        >,
        asOfDate,
      });
    const crushWhatsHappening =
      crushIntel ??
      generateFallbackDriverIntel({
        driverName: "crush",
        score: crushResult.score,
        level: crushResult.level,
        regime: crushResult.regime,
        components: crushResult.components as unknown as Record<
          string,
          number | null
        >,
        asOfDate,
      });
    const chinaWhatsHappening =
      chinaIntel ??
      generateFallbackDriverIntel({
        driverName: "china",
        score: chinaResult.score,
        level: chinaResult.level,
        regime: chinaResult.regime,
        components: chinaResult.components as unknown as Record<
          string,
          number | null
        >,
        asOfDate,
      });
    const tariffWhatsHappening =
      tariffIntel ??
      generateFallbackDriverIntel({
        driverName: "tariff",
        score: tariffResult.score,
        level: tariffResult.level,
        regime: tariffResult.regime,
        components: tariffResult.components as unknown as Record<
          string,
          number | null
        >,
        asOfDate,
      });

    // 9. Assemble response
    const dataFreshness = computeDataFreshness(rawData);
    const refreshMeta = getDailyRefreshMeta();

    return NextResponse.json(
      {
        as_of_date: asOfDate,
        narrative_refresh: {
          cadence: "daily",
          next_refresh_utc: refreshMeta.nextRefreshUtc,
          ai_cached: !!cached,
          ai_cache_day: getAiDayKey(),
        },
        drivers: {
          vix_stress: {
            name: "VIX Stress",
            score: vixResult.score,
            level: vixResult.level,
            regime: vixResult.regime,
            headline: vixResult.headline,
            components: vixResult.components,
            whatsHappening: vixWhatsHappening,
            aiPowered: vixIntel !== null,
            dataDate: rawData.vixDate,
          },
          crush_pressure: {
            name: "Crush Pressure",
            score: crushResult.score,
            level: crushResult.level,
            regime: crushResult.regime,
            headline: crushResult.headline,
            components: crushResult.components,
            whatsHappening: crushWhatsHappening,
            aiPowered: crushIntel !== null,
            dataDate: rawData.crushDate,
          },
          china_tension: {
            name: "China Tension",
            score: chinaResult.score,
            level: chinaResult.level,
            regime: chinaResult.regime,
            headline: chinaResult.headline,
            components: chinaResult.components,
            whatsHappening: chinaWhatsHappening,
            aiPowered: chinaIntel !== null,
            dataDate: rawData.cnyDate,
          },
          tariff_threat: {
            name: "Tariff Threat",
            score: tariffResult.score,
            level: tariffResult.level,
            regime: tariffResult.regime,
            headline: tariffResult.headline,
            components: tariffResult.components,
            whatsHappening: tariffWhatsHappening,
            aiPowered: tariffIntel !== null,
            dataDate: rawData.tpuDate,
          },
        },
        summary: {
          average_pressure:
            Math.round(
              ((vixResult.score +
                crushResult.score +
                chinaResult.score +
                tariffResult.score) /
                4) *
                10,
            ) / 10,
          highest_pressure: [
            { name: "VIX Stress", score: vixResult.score },
            { name: "Crush Pressure", score: crushResult.score },
            { name: "China Tension", score: chinaResult.score },
            { name: "Tariff Threat", score: tariffResult.score },
          ].sort((a, b) => b.score - a.score)[0],
          alert_count: [
            vixResult.score,
            crushResult.score,
            chinaResult.score,
            tariffResult.score,
          ].filter((s) => s >= 65).length,
        },
        intelligence,
        data_quality: dataFreshness,
      },
      { headers: refreshMeta.headers },
    );
  } catch (error) {
    console.error("Market drivers query failed:", error);
    return NextResponse.json(
      { error: "Market drivers query failed", details: String(error) },
      { status: 500, headers: { "Cache-Control": "no-store" } },
    );
  }
}
