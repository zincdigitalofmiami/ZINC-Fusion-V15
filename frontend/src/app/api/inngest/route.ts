import { serve } from "inngest/next";
import { inngest } from "@/inngest/client";
import {
  zl15m,
  zl1h,
  zlDaily,
  zlLive1m,
  zlLive5m,
  zlLive15m,
  zlLive1h,
  zlLive1d,
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
  cftcWeekly,
  federalRegisterDaily,
  nyfedDaily,
  cbpTradeDaily,
  iceReleasesDaily,
  farmdocRinsDaily,
  aeiTradeDaily,
  conabNewsDaily,
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
  cleanupStaleRuns,
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

// Extend Vercel Lambda timeout to maximum (Fluid Compute / streaming mode).
// On Vercel Pro this allows steps up to ~800s instead of the default 300s.
export const maxDuration = 300;

export const { GET, POST, PUT } = serve({
  client: inngest,
  streaming: "allow",
  functions: [
    // Price data
    zl15m,
    zl1h,
    zlDaily,
    zlLive1m,
    zlLive5m,
    zlLive15m,
    zlLive1h,
    zlLive1d,
    // FRED macro series
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
    // Government/regulatory
    cftcWeekly,
    federalRegisterDaily,
    nyfedDaily,
    eiaDaily,
    epaRinPricesDaily,
    // Trade data
    cbpTradeDaily,
    iceReleasesDaily,
    aeiTradeDaily,
    usdaExportSalesWeekly,
    usdaWasdeMonthly,
    // News/press
    farmdocRinsDaily,
    conabNewsDaily,
    whitehouseDaily,
    usdaDaily,
    nassWeekly,
    // Weather
    noaaWeatherDaily,
    openmeteoWeatherDaily,
    weatherFeaturesDaily,
    // FX/commodities
    fxSpotDaily,
    cpoPalmOilDaily,
    cpoTradingEconomics,
    // Other
    glideVegasSync,
    // Premium subscriptions
    profarmerDaily,
    profarmerBackfill,
    // Databento market data
    ...databentoFuturesDailyShards,
    databentoFutures1h,
    ...databentoStatisticsDailyShards,
    databentoFxDaily,
    ...databentoOptionsDailyShards,
    databentoEtfDaily,
    databentoEtfBackfill,
    databentoEtfVwapDaily,
    databentoEtfVwapBackfill,
    futuresLegacySymbolsNightly,
    // FX Databento
    fxDatabentoSpotDaily,
    // Analytics calculations
    boardCrushDaily,
    boardCrushBackfill,
    // EIA biofuel data
    eiaBiodieselMonthly,
    eiaBiodieselBackfill,
    // Monitoring
    optionsStalenessCheck,
    // Critical supply data (monthly)
    mpobPalmMonthly,
    conabProductionMonthly,
    argentinaCrushMonthly,
    // FRED blog news
    fredBlogDaily,
    // ZL 1m backfill
    zl1mBackfill,
    zl1mScheduledBackfill,
    // Ops cleanup
    cleanupStaleRuns,
    // Supply data (weekly)
    lcfsCreditWeekly,
    // Specialist signal synchronization (all 11 buckets)
    specialistSignalsSync,
    specialistSignalsSyncManual,
    // Global failure monitor (catches all function failures)
    globalFailureMonitor,
    // Freshness SLAs for critical tables
    freshnessMonitor,
    // Yahoo Finance indices (VIX + DX)
    yahooIndicesDaily,
    yahooIndicesBackfill,
    // USDA ESMIS publications (WASDE, Oil Crops, Crush, Biofuels, Trade)
    esmisPublicationsDaily,
    esmisPublicationsBackfill,
    // FAS reports (oilseeds, biofuels, GAIN, attaché)
    fasReportsDaily,
    // USDA AMS fats & oils (UCO, yellow grease, tallow prices)
    usdaAmsFatsOilsDaily,
    // Federal Reserve speeches (hawkish/dovish sentiment)
    fedSpeechesDaily,
    // Congress.gov bills & legislation tracker
    congressBillsDaily,
    // EIA biodiesel weekly production (EPOORDB + EPOORDO)
    eiaBiodieselWeekly,
    eiaBiodieselWeeklyBackfill,
    // ProFarmer weekly auto-backfill (Sunday catch-up)
    profarmerWeeklyBackfill,
    // Yahoo Finance ETF fallback (when Databento ETF stale)
    yahooEtfFallbackDaily,
    yahooEtfBackfill,
    // BLS PPI/CPI/employment (monthly)
    blsMonthly,
    // China soybean complex imports (UN Comtrade, monthly)
    chinaSoyImportsMonthly,
    // Panama Canal operations + transit data (daily)
    panamaCanalDaily,
    // FAS GATS soybean complex trade (monthly)
    fasGatsTradeMonthly,
  ],
  // Explicit host to prevent empty URL sync issues
  ...(serveHost && { serveHost }),
});
