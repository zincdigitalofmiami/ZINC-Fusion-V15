/**
 * AI Model Configuration - SINGLE SOURCE OF TRUTH
 *
 * HARD-LOCKED MODEL ROUTING:
 * - OpenRouter provider for all market-context AI surfaces
 * - Model: openai/gpt-oss-120b:free (120B-param, high reasoning capability)
 * - Temperature: 0.0 (deterministic), Reasoning effort: high
 *
 * DO NOT CHANGE THESE WITHOUT EXPLICIT APPROVAL
 */

// =============================================================================
// MODEL IDENTIFIERS (LOCKED)
// =============================================================================

/**
 * GPT-OSS-120B via OpenRouter free tier — per-card driver intel and streamed page briefs.
 * 120B-param model with extended reasoning support for deep ZL analysis.
 */
export const MODEL_DRIVER_INTEL = 'openai/gpt-oss-120b:free'

/**
 * GPT-OSS-120B via OpenRouter free tier — comprehensive market synthesis.
 * Same model as driver intel; strongest free reasoning model available.
 */
export const MODEL_BALANCED_CONDITIONS = 'openai/gpt-oss-120b:free'

// =============================================================================
// REFRESH + CACHE VERSIONING
// =============================================================================

/**
 * Daily AI refresh boundary in UTC for server/client cache invalidation.
 */
export const AI_DAILY_REFRESH_UTC_HOUR = 10

/**
 * Bump to force regeneration of all AI outputs across dashboard + site.
 */
export const AI_OUTPUT_VERSION = '2026-03-25-v4'

// =============================================================================
// TOKEN LIMITS
// =============================================================================

export const TOKENS_DRIVER_INTEL = 800      // Per-card analysis
export const TOKENS_BALANCED_CONDITIONS = 6000  // Full synthesis - institutional-grade comprehensive report

// =============================================================================
// FRESHNESS CONFIG
// =============================================================================

export const DATA_STALENESS_THRESHOLD_HOURS = 48  // Flag data older than this
export const NEWS_WINDOW_HOURS = 36               // News recency window

// =============================================================================
// VALIDATION
// =============================================================================

/**
 * Verify response echoes the correct as_of_date
 * This is the anti-bullshit gate
 */
export function validateResponseFreshness(
  responseAsOfDate: string | undefined,
  expectedAsOfDate: string
): boolean {
  if (!responseAsOfDate) return false
  return responseAsOfDate === expectedAsOfDate
}

/**
 * Check if a timestamp is stale (beyond threshold)
 */
export function isDataStale(timestamp: Date | string, thresholdHours = DATA_STALENESS_THRESHOLD_HOURS): boolean {
  const ts = typeof timestamp === 'string' ? new Date(timestamp) : timestamp
  const now = new Date()
  const diffHours = (now.getTime() - ts.getTime()) / (1000 * 60 * 60)
  return diffHours > thresholdHours
}
