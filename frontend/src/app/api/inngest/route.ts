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
} from "@/inngest/functions";

/**
 * Compute the serve host explicitly to prevent empty URL issues.
 *
 * Priority:
 * 1. APP_ORIGIN (explicit, most reliable)
 * 2. VERCEL_PROJECT_PRODUCTION_URL (Vercel's production domain)
 * 3. VERCEL_URL (Vercel's deployment URL - includes preview deploys)
 *
 * The empty https:///api/inngest bug happens when none of these resolve.
 */
function getServeHost(): string | undefined {
  // Explicit override (most reliable)
  if (process.env.APP_ORIGIN) {
    return process.env.APP_ORIGIN;
  }

  // Vercel production URL (e.g., zinc-fusion-v15.vercel.app)
  if (process.env.VERCEL_PROJECT_PRODUCTION_URL) {
    return `https://${process.env.VERCEL_PROJECT_PRODUCTION_URL}`;
  }

  // Vercel deployment URL (works for preview and production)
  if (process.env.VERCEL_URL) {
    return `https://${process.env.VERCEL_URL}`;
  }

  // Let the SDK auto-detect (fallback)
  return undefined;
}

const serveHost = getServeHost();

// Log for debugging (only in development/build)
if (process.env.NODE_ENV !== 'production') {
  console.log('[Inngest] Computed serveHost:', serveHost);
}

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
  ],
  // Explicit host to prevent empty URL sync issues
  ...(serveHost && { serveHost }),
});
