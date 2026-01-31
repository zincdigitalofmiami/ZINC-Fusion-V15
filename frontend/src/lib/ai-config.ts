/**
 * AI Model Configuration - SINGLE SOURCE OF TRUTH
 *
 * HARD-LOCKED MODEL ROUTING:
 * - Driver cards (4x): Sonnet 4.5 for fast, domain-focused analysis
 * - Combined narrative: Opus 4.5 for comprehensive cross-driver synthesis
 *
 * DO NOT CHANGE THESE WITHOUT EXPLICIT APPROVAL
 */

// =============================================================================
// MODEL IDENTIFIERS (LOCKED)
// =============================================================================

/**
 * Sonnet 4.5 for individual driver "What's Happening?" intel
 * Fast, cost-effective, domain-focused
 */
export const MODEL_DRIVER_INTEL = 'claude-sonnet-4-5-20250929'

/**
 * Opus 4.5 for combined "Balanced Conditions" market narrative
 * Comprehensive synthesis across all 4 drivers
 */
export const MODEL_BALANCED_CONDITIONS = 'claude-opus-4-5-20251101'

// =============================================================================
// TOKEN LIMITS
// =============================================================================

export const TOKENS_DRIVER_INTEL = 800      // Per-card analysis
export const TOKENS_BALANCED_CONDITIONS = 4000  // Full synthesis - comprehensive report

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
