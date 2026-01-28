import { serve } from "inngest/next";
import { inngest } from "@/inngest/client";
import {
  zl15m,
  zl1h,
  zlDaily,
  zlLive15m,
  zlLive1h,
  zlLive1d,
  yahooEod,
  yahooEtfDaily,
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
  fxSpotDaily,
  epaRinPricesDaily,
  usdaWasdeMonthly,
  usdaExportSalesWeekly,
  glideVegasSync,
  cpoPalmOilDaily,
  cpoTradingEconomics,
  profarmerDaily,
  profarmerBackfill,
  databentoFuturesDaily,
  databentoStatisticsDaily,
  boardCrushDaily,
  eiaBiodieselMonthly,
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

export const { GET, POST, PUT } = serve({
  client: inngest,
  functions: [
    // Price data
    zl15m,
    zl1h,
    zlDaily,
    zlLive15m,
    zlLive1h,
    zlLive1d,
    yahooEod,
    yahooEtfDaily,
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
    databentoFuturesDaily,
    databentoStatisticsDaily,
    // Analytics calculations
    boardCrushDaily,
    // EIA biofuel data
    eiaBiodieselMonthly,
  ],
  // Explicit host to prevent empty URL sync issues
  ...(serveHost && { serveHost }),
});
