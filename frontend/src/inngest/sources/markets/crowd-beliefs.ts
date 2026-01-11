/**
 * ZINC-FUSION-V15: Polymarket Crowd Beliefs Ingestion
 *
 * Behavioral signal capturing crowd probability estimates for policy outcomes.
 * Forward-looking complement to backward-looking EPU indices.
 *
 * API: https://gamma-api.polymarket.com/events
 * Schedule: Daily at 6 PM ET (after market close)
 *
 * Cross-Specialist Routing:
 * - trump_effect: trump, executive, doge, deportation
 * - china: china, taiwan, trade_war
 * - tariff: tariff, import, trade
 * - biofuel: rfs, ethanol, epa, mandate
 * - energy: oil, sanctions, opec
 * - fed: fed, rates, inflation, recession
 * - volatility: vix, crash, crisis
 */

import { inngest } from "../../client";
import { prisma } from "@/lib/db";
import { Decimal } from "@prisma/client/runtime/library";

// =============================================================================
// TYPE DEFINITIONS
// =============================================================================

interface PolymarketMarket {
  id: string;
  question: string;
  outcomePrices: string[]; // [YES, NO] as string decimals
  liquidity: string;
  endDate: string;
}

interface PolymarketEvent {
  id: string;
  ticker: string;
  slug: string;
  title: string;
  volume: number;
  volume24hr: number;
  volume1wk: number;
  liquidity: number;
  active: boolean;
  closed: boolean;
  endDate: string;
  markets: PolymarketMarket[];
}

interface ProcessedBelief {
  eventSlug: string;
  outcomeQuestion: string;
  capturedAt: Date;
  impliedProbYes: number;
  impliedProbNo: number;
  attentionIndex24h: number;
  attentionIndex7d: number;
  probMomentum24h: number | null;
  probMomentum7d: number | null;
  consensusStrength: number;
  eventCategory: string;
  specialistTags: string[];
  eventResolutionDate: Date | null;
  daysToResolution: number | null;
  rawBettingVolumeUsd: number;
  rawLiquidityUsd: number;
}

// =============================================================================
// CATEGORY ROUTING
// =============================================================================

/**
 * Maps event categories to specialist tags for cross-specialist routing.
 * An event can route to multiple specialists.
 */
const CATEGORY_TO_SPECIALISTS: Record<string, string[]> = {
  tariff: ["tariff", "trump_effect", "china"],
  china: ["china", "trump_effect"],
  taiwan: ["china", "volatility"],
  trump: ["trump_effect"],
  doge: ["trump_effect", "fed"],
  executive: ["trump_effect"],
  deportation: ["trump_effect"],
  immigration: ["trump_effect"],
  fed: ["fed", "volatility"],
  rates: ["fed"],
  inflation: ["fed", "energy"],
  recession: ["fed", "volatility"],
  rfs: ["biofuel"],
  ethanol: ["biofuel", "energy"],
  biodiesel: ["biofuel"],
  epa: ["biofuel", "trump_effect"],
  mandate: ["biofuel"],
  oil: ["energy"],
  sanctions: ["energy", "china"],
  opec: ["energy"],
  drilling: ["energy", "trump_effect"],
  vix: ["volatility"],
  crash: ["volatility"],
  crisis: ["volatility"],
  trade: ["tariff", "china"],
  deficit: ["fed", "trump_effect"],
  spending: ["fed", "trump_effect"],
};

/**
 * Keywords to filter relevant events from Polymarket.
 * Only events containing these keywords are ingested.
 */
const RELEVANT_KEYWORDS = [
  "tariff",
  "china",
  "taiwan",
  "trump",
  "doge",
  "deport",
  "trade",
  "deficit",
  "spending",
  "fed",
  "rate",
  "inflation",
  "recession",
  "rfs",
  "ethanol",
  "biodiesel",
  "epa",
  "mandate",
  "oil",
  "sanction",
  "opec",
  "drill",
  "vix",
  "crash",
  "crisis",
  "immigration",
];

// =============================================================================
// HELPER FUNCTIONS
// =============================================================================

/**
 * Determines if an event is relevant for ZL forecasting.
 */
function isRelevantEvent(event: PolymarketEvent): boolean {
  const searchText = `${event.title} ${event.slug}`.toLowerCase();
  return RELEVANT_KEYWORDS.some((keyword) => searchText.includes(keyword));
}

/**
 * Extracts the primary category from event title/slug.
 */
function extractCategory(event: PolymarketEvent): string {
  const searchText = `${event.title} ${event.slug}`.toLowerCase();

  // Priority order matters - more specific first
  if (searchText.includes("tariff")) return "tariff";
  if (searchText.includes("taiwan")) return "taiwan";
  if (searchText.includes("china")) return "china";
  if (searchText.includes("doge")) return "doge";
  if (searchText.includes("deport") || searchText.includes("immigration"))
    return "deportation";
  if (searchText.includes("trump")) return "trump";
  if (searchText.includes("rfs") || searchText.includes("ethanol"))
    return "biofuel";
  if (searchText.includes("biodiesel") || searchText.includes("mandate"))
    return "biofuel";
  if (searchText.includes("oil") || searchText.includes("sanction"))
    return "energy";
  if (searchText.includes("fed") || searchText.includes("rate")) return "fed";
  if (
    searchText.includes("recession") ||
    searchText.includes("crash") ||
    searchText.includes("vix")
  )
    return "volatility";
  if (searchText.includes("deficit") || searchText.includes("spending"))
    return "deficit";
  if (searchText.includes("trade")) return "trade";

  return "other";
}

/**
 * Gets specialist tags for a category.
 */
function getSpecialistTags(category: string): string[] {
  return CATEGORY_TO_SPECIALISTS[category] || ["trump_effect"];
}

/**
 * Calculates consensus strength from YES/NO probabilities.
 * 1.0 = unanimous (one side at 100%)
 * 0.5 = maximally split (50/50)
 */
function calculateConsensusStrength(probYes: number): number {
  // Distance from 0.5 (maximum uncertainty)
  const distanceFrom50 = Math.abs(probYes - 0.5);
  // Scale to 0-1 where 1 = unanimous
  return distanceFrom50 * 2;
}

/**
 * Calculates attention index (normalized betting activity).
 * Returns 0-100 scale based on volume relative to baseline.
 */
function calculateAttentionIndex(
  volume: number,
  baselineVolume: number
): number {
  if (baselineVolume === 0) return 50; // Default baseline
  const ratio = volume / baselineVolume;
  // Cap at 100, scale logarithmically
  return Math.min(100, Math.log2(ratio + 1) * 50);
}

/**
 * Fetches prior beliefs for momentum calculation.
 */
async function fetchPriorBeliefs(
  eventSlug: string,
  outcomeQuestion: string,
  daysBack: number
): Promise<{ impliedProbYes: Decimal } | null> {
  const cutoffDate = new Date();
  cutoffDate.setDate(cutoffDate.getDate() - daysBack);

  const prior = await prisma.crowdBeliefsEvent.findFirst({
    where: {
      eventSlug,
      outcomeQuestion,
      capturedAt: { lte: cutoffDate },
    },
    orderBy: { capturedAt: "desc" },
    select: { impliedProbYes: true },
  });

  return prior;
}

// =============================================================================
// MAIN INGESTION FUNCTION
// =============================================================================

export const crowdBeliefs = inngest.createFunction(
  {
    id: "crowd-beliefs-daily",
    name: "Polymarket Crowd Beliefs",
    retries: 3,
  },
  { cron: "0 11 * * *" }, // 5AM CT = 11AM UTC, Daily
  async ({ event, step }) => {
    // Step 1: Fetch events from Polymarket Gamma API
    const events = await step.run("fetch-polymarket-events", async () => {
      const response = await fetch(
        "https://gamma-api.polymarket.com/events?active=true&closed=false",
        {
          headers: { Accept: "application/json" },
        }
      );

      if (!response.ok) {
        throw new Error(`Polymarket API error: ${response.status}`);
      }

      const data: PolymarketEvent[] = await response.json();
      return data;
    });

    // Step 2: Filter for relevant events
    const relevantEvents = await step.run("filter-relevant-events", async () => {
      return events.filter(isRelevantEvent);
    });

    console.log(
      `Found ${relevantEvents.length} relevant events out of ${events.length} total`
    );

    // Step 3: Process each event into beliefs
    const processedBeliefs = await step.run("process-beliefs", async () => {
      const beliefs: ProcessedBelief[] = [];
      const capturedAt = new Date();

      // Calculate baseline volume for attention index
      const totalVolume24h = events.reduce(
        (sum, e) => sum + (e.volume24hr || 0),
        0
      );
      const avgVolume24h = totalVolume24h / Math.max(events.length, 1);

      for (const event of relevantEvents) {
        const category = extractCategory(event);
        const specialistTags = getSpecialistTags(category);

        // Process each market (outcome) within the event
        for (const market of event.markets) {
          const probYes = parseFloat(market.outcomePrices[0] || "0");
          const probNo = parseFloat(market.outcomePrices[1] || "0");

          // Calculate attention index
          const attentionIndex24h = calculateAttentionIndex(
            event.volume24hr || 0,
            avgVolume24h
          );
          const attentionIndex7d = calculateAttentionIndex(
            event.volume1wk || 0,
            avgVolume24h * 7
          );

          // Calculate days to resolution
          let daysToResolution: number | null = null;
          let eventResolutionDate: Date | null = null;
          if (market.endDate) {
            eventResolutionDate = new Date(market.endDate);
            const diffMs = eventResolutionDate.getTime() - capturedAt.getTime();
            daysToResolution = Math.ceil(diffMs / (1000 * 60 * 60 * 24));
          }

          beliefs.push({
            eventSlug: event.slug,
            outcomeQuestion: market.question,
            capturedAt,
            impliedProbYes: probYes,
            impliedProbNo: probNo,
            attentionIndex24h,
            attentionIndex7d,
            probMomentum24h: null, // Will be calculated in next step
            probMomentum7d: null,
            consensusStrength: calculateConsensusStrength(probYes),
            eventCategory: category,
            specialistTags,
            eventResolutionDate,
            daysToResolution,
            rawBettingVolumeUsd: event.volume || 0,
            rawLiquidityUsd: event.liquidity || 0,
          });
        }
      }

      return beliefs;
    });

    // Step 4: Calculate momentum (requires DB lookup)
    const beliefsWithMomentum = await step.run(
      "calculate-momentum",
      async () => {
        const updatedBeliefs: ProcessedBelief[] = [];

        for (const belief of processedBeliefs) {
          // Lookup 24h prior
          const prior24h = await fetchPriorBeliefs(
            belief.eventSlug,
            belief.outcomeQuestion,
            1
          );

          // Lookup 7d prior
          const prior7d = await fetchPriorBeliefs(
            belief.eventSlug,
            belief.outcomeQuestion,
            7
          );

          updatedBeliefs.push({
            ...belief,
            probMomentum24h: prior24h
              ? belief.impliedProbYes - prior24h.impliedProbYes.toNumber()
              : null,
            probMomentum7d: prior7d
              ? belief.impliedProbYes - prior7d.impliedProbYes.toNumber()
              : null,
          });
        }

        return updatedBeliefs;
      }
    );

    // Step 5: Upsert to database
    const upsertResult = await step.run("upsert-beliefs", async () => {
      let inserted = 0;
      let updated = 0;

      for (const belief of beliefsWithMomentum) {
        try {
          await prisma.crowdBeliefsEvent.upsert({
            where: {
              eventSlug_outcomeQuestion_capturedAt: {
                eventSlug: belief.eventSlug,
                outcomeQuestion: belief.outcomeQuestion,
                capturedAt: belief.capturedAt,
              },
            },
            update: {
              impliedProbYes: belief.impliedProbYes,
              impliedProbNo: belief.impliedProbNo,
              attentionIndex24h: belief.attentionIndex24h,
              attentionIndex7d: belief.attentionIndex7d,
              probMomentum24h: belief.probMomentum24h,
              probMomentum7d: belief.probMomentum7d,
              consensusStrength: belief.consensusStrength,
              eventCategory: belief.eventCategory,
              specialistTags: belief.specialistTags,
              eventResolutionDate: belief.eventResolutionDate,
              daysToResolution: belief.daysToResolution,
              rawBettingVolumeUsd: belief.rawBettingVolumeUsd,
              rawLiquidityUsd: belief.rawLiquidityUsd,
            },
            create: {
              eventSlug: belief.eventSlug,
              outcomeQuestion: belief.outcomeQuestion,
              capturedAt: belief.capturedAt,
              impliedProbYes: belief.impliedProbYes,
              impliedProbNo: belief.impliedProbNo,
              attentionIndex24h: belief.attentionIndex24h,
              attentionIndex7d: belief.attentionIndex7d,
              probMomentum24h: belief.probMomentum24h,
              probMomentum7d: belief.probMomentum7d,
              consensusStrength: belief.consensusStrength,
              eventCategory: belief.eventCategory,
              specialistTags: belief.specialistTags,
              eventResolutionDate: belief.eventResolutionDate,
              daysToResolution: belief.daysToResolution,
              rawBettingVolumeUsd: belief.rawBettingVolumeUsd,
              rawLiquidityUsd: belief.rawLiquidityUsd,
              source: "polymarket",
            },
          });
          inserted++;
        } catch (error) {
          console.error(`Error upserting belief: ${belief.eventSlug}`, error);
        }
      }

      return { inserted, updated, total: beliefsWithMomentum.length };
    });

    return {
      success: true,
      eventsScanned: events.length,
      relevantEvents: relevantEvents.length,
      beliefsProcessed: upsertResult.total,
      timestamp: new Date().toISOString(),
    };
  }
);
