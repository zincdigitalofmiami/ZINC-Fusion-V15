import { serve } from "inngest/next";
import { inngest } from "@/inngest/client";
import {
  zlDaily,
  zlLive1m,
  zlLive1d,
  zl1h,
  fredDailyFed,
  fredDailyFx,
  fredDailyEnergy,
  fredDailyBiofuel,
  fredDailyCrush,
  fredDailyPalm,
  fredDailyVolatility,
  fredDailyTrumpEffect,
  fredDailyChina,
  fredDailyGeneral,
  fredDailyFxManual,
  fredDailyVolatilityManual,
  fredDailyTrumpEffectManual,
  cftcWeekly,
  federalRegisterDaily,
  nyfedDaily,
  cbpTradeDaily,
  iceReleasesDaily,
  farmdocRinsDaily,
  aeiTradeDaily,
  conabNewsDaily,
  googleNewsDaily,
  whitehouseDaily,
  usdaDaily,
  eiaDaily,
  nassWeekly,
  noaaWeatherDaily,
  openmeteoWeatherDaily,
  weatherFeaturesDaily,
  fxSpotDaily,
  epaRinPricesDaily,
  usdaWasdeMonthly,
  usdaExportSalesWeekly,
  glideVegasSync,
  cpoPalmOilDaily,
  cpoTradingEconomics,
  profarmerDaily,
  profarmerScheduledReports,
  profarmerBackfill,
  databentoFuturesDailyShards,
  databentoFutures1h,
  databentoStatisticsDailyShards,
  databentoFxDaily,
  databentoOptionsDailyShards,
  databentoEtfDaily,
  databentoEtfBackfill,
  databentoEtfVwapDaily,
  databentoEtfVwapBackfill,
  futuresLegacySymbolsNightly,
  boardCrushDaily,
  boardCrushDailyManual,
  boardCrushBackfill,
  eiaBiodieselMonthly,
  eiaBiodieselBackfill,
  fxDatabentoSpotDaily,
  optionsStalenessCheck,
  mpobPalmMonthly,
  conabProductionMonthly,
  argentinaCrushMonthly,
  fredBlogDaily,
  zl1mBackfill,
  zl1mScheduledBackfill,
  zl1mIntradayRefresh,
  cleanupStaleRuns,
  price1mRetentionCleanup,
  lcfsCreditWeekly,
  specialistSignalsSync,
  specialistSignalsSyncManual,
  globalFailureMonitor,
  freshnessMonitor,
  yahooIndicesDaily,
  yahooIndicesBackfill,
  esmisPublicationsDaily,
  esmisPublicationsBackfill,
  fasReportsDaily,
  usdaAmsFatsOilsDaily,
  fedSpeechesDaily,
  congressBillsDaily,
  eiaBiodieselWeekly,
  eiaBiodieselWeeklyBackfill,
  profarmerWeeklyBackfill,
  yahooEtfFallbackDaily,
  yahooEtfBackfill,
  blsMonthly,
  chinaSoyImportsMonthly,
  panamaCanalDaily,
  fasGatsTradeMonthly,
} from "@/inngest/functions";

function isUnsafeServeHost(hostname: string): boolean {
  const host = hostname.toLowerCase();
  return (
    host === "localhost" ||
    host === "0.0.0.0" ||
    host === "::1" ||
    host === "host.docker.internal" ||
    host.startsWith("127.") ||
    host.endsWith(".local")
  );
}

/**
 * Only set serveHost for true Vercel production.
 * Local/dev must not advertise host URLs, even if env leakage occurs.
 */
function getServeHost(): string | undefined {
  const isVercelProd = process.env.VERCEL === "1" && process.env.VERCEL_ENV === "production";
  if (!isVercelProd) return undefined;

  const candidates = [
    process.env.APP_ORIGIN,
    process.env.VERCEL_PROJECT_PRODUCTION_URL
      ? `https://${process.env.VERCEL_PROJECT_PRODUCTION_URL}`
      : undefined,
    process.env.VERCEL_URL ? `https://${process.env.VERCEL_URL}` : undefined,
  ];

  for (const candidate of candidates) {
    const raw = candidate?.trim();
    if (!raw) continue;
    try {
      const parsed = new URL(raw);
      if (parsed.protocol !== "https:") continue;
      if (isUnsafeServeHost(parsed.hostname)) continue;
      return parsed.origin;
    } catch {
      // Ignore invalid candidates and continue.
    }
  }

  return undefined;
}

const serveHost = getServeHost();

// Match frontend/vercel.json so route-level and deploy-level limits stay aligned.
export const maxDuration = 800;

export const { GET, POST, PUT } = serve({
  client: inngest,
  streaming: "allow",
  functions: [],
  // Explicit host to prevent empty URL sync issues
  ...(serveHost && { serveHost }),
});
