/**
 * Specialist Classifier - TypeScript Port
 *
 * Single Source of Truth for Big-11 Specialist Tagging (TypeScript)
 * Mirrors: src/fusion/tagging/specialist_classifier.py
 *
 * Usage:
 *   import { classifySpecialists, BIG_11_SPECIALISTS } from '@/lib/specialist-classifier';
 *
 *   const tags = classifySpecialists("China trade deal announced");
 *   // Returns: ["china", "tariff", "trump_effect"]
 */

// Canonical Big-11 Specialists (matches Python exactly)
export const BIG_11_SPECIALISTS = [
  "crush",
  "china",
  "fx",
  "fed",
  "tariff",
  "energy",
  "biofuel",
  "palm",
  "volatility",
  "substitutes",
  "trump_effect",
] as const;

export type Specialist = (typeof BIG_11_SPECIALISTS)[number];
export type SpecialistOrGeneral = Specialist | "general";

// Keywords that trigger BOTH tariff AND trump_effect
// Per RAW_SOURCE_SPECIALIST_MAPPING.md: trade deals affect both buckets
const DUAL_TAG_KEYWORDS = [
  "trade deal",
  "trade agreement",
  "trade negotiation",
  "phase one",
  "phase 1",
  "china tariff",
  "tariff negotiation",
  "trade talks",
];

// Specialist Keywords Dictionary
// Mirrors: src/fusion/tagging/keywords.py
const SPECIALIST_KEYWORDS: Record<Specialist, string[]> = {
  // CRUSH - Soybean processing, crush margins, meal/oil spread
  crush: [
    "crush",
    "crushing",
    "crusher",
    "soybean meal",
    "soymeal",
    "soy meal",
    "soybean oil",
    "soy oil",
    "bean oil",
    "processing",
    "processor",
    "crush margin",
    "gpr",
    "gross processing revenue",
    "dcf",
    "nopa",
    "meal-oil spread",
    "soybean crush",
  ],

  // CHINA - Chinese demand, trade flows, ASF, import patterns
  china: [
    "china",
    "chinese",
    "beijing",
    "shanghai",
    "sinograin",
    "cofco",
    "asian demand",
    "pig herd",
    "asf",
    "african swine fever",
    "china imports",
    "china buying",
    "china purchases",
    "prc",
    "gacc",
    "cny",
  ],

  // FX - Currency movements, USD strength, BRL/MXN/CNY
  fx: [
    "dollar",
    "currency",
    "real",
    "brazilian real",
    "peso",
    "yuan",
    "exchange rate",
    "forex",
    "fx",
    "usd",
    "dxy",
    "dollar index",
    "brl",
    "mxn",
    "cnh",
    "renminbi",
    "currency hedge",
    "dollar strength",
    "dollar weakness",
  ],

  // FED - Federal Reserve, monetary policy, interest rates
  fed: [
    "federal reserve",
    "fed",
    "interest rate",
    "fomc",
    "powell",
    "monetary policy",
    "rate hike",
    "rate cut",
    "treasury",
    "yield",
    "quantitative",
    "qe",
    "qt",
    "basis points",
    "fed funds",
    "dot plot",
    "hawkish",
    "dovish",
  ],

  // TARIFF - Trade mechanisms, Section 301/232, duties, WTO
  // NOTE: Trade DEALS go in DUAL_TAG_KEYWORDS (both tariff + trump_effect)
  tariff: [
    "tariff",
    "trade war",
    "trade policy",
    "duties",
    "section 301",
    "section 232",
    "retaliation",
    "trade dispute",
    "wto",
    "anti-dumping",
    "countervailing",
    "ustr",
    "exclusion",
    "import duty",
    "export restriction",
    "trade barrier",
    "safeguard",
  ],

  // ENERGY - Crude oil, diesel, petroleum, OPEC
  energy: [
    "crude oil",
    "oil prices",
    "petroleum",
    "gasoline",
    "diesel",
    "natural gas",
    "energy costs",
    "brent",
    "wti",
    "opec",
    "heating oil",
    "ulsd",
    "energy markets",
    "refinery",
    "distillate",
    "jet fuel",
  ],

  // BIOFUEL - Biodiesel, RFS, RINs, renewable diesel, SAF
  biofuel: [
    "biodiesel",
    "renewable diesel",
    "rfs",
    "rvo",
    "rin",
    "epa",
    "biofuel",
    "renewable fuel",
    "saf",
    "sustainable aviation",
    "blending mandate",
    "lcfs",
    "clean fuel",
    "45z",
    "clean fuel production credit",
    "inflation reduction act",
    "ira",
    "d4 rin",
    "d6 rin",
    "biomass-based diesel",
  ],

  // PALM - Palm oil, Malaysia, Indonesia, MPOB
  palm: [
    "palm oil",
    "palm",
    "malaysia",
    "indonesia",
    "mpob",
    "cpo",
    "crude palm oil",
    "southeast asia",
    "tropical oils",
    "deforestation",
    "rspo",
    "sustainable palm",
    "palm kernel",
    "lauric",
  ],

  // VOLATILITY - VIX, risk, uncertainty, hedging
  volatility: [
    "volatility",
    "vix",
    "risk",
    "uncertainty",
    "hedge",
    "options",
    "implied vol",
    "vol spike",
    "market fear",
    "ovx",
    "risk-off",
    "risk-on",
    "flight to safety",
    "safe haven",
  ],

  // SUBSTITUTES - Canola, sunflower, cottonseed, tallow
  substitutes: [
    "canola",
    "rapeseed",
    "sunflower",
    "cottonseed",
    "vegetable oil",
    "cooking oil",
    "edible oil",
    "substitute",
    "competition",
    "tallow",
    "uco",
    "used cooking oil",
    "yellow grease",
    "animal fat",
    "waste oil",
    "corn oil",
    "olive oil",
  ],

  // TRUMP_EFFECT - Policy uncertainty, executive orders, EPU
  // NOTE: Trade DEALS go in DUAL_TAG_KEYWORDS (both tariff + trump_effect)
  // NOTE: Avoid short ambiguous keywords (e.g., "ice" matches "nice", "price")
  trump_effect: [
    "trump",
    "white house",
    "executive order",
    "truth social",
    "policy uncertainty",
    "epu",
    "political risk",
    "election",
    "doge",
    "elon musk",
    "deportation",
    "immigration",
    "ice enforcement",
    "border patrol",
    "border security",
    "mass deportation",
    "presidential action",
    "administration policy",
  ],
};

/**
 * Classify text to Big-11 specialist buckets.
 *
 * @param text - Input text to classify (title, headline, description, etc.)
 * @returns Array of matched specialist bucket names. Returns ["general"] if no match.
 */
export function classifySpecialists(text: string): string[] {
  if (!text) {
    return ["general"];
  }

  const textLower = text.toLowerCase();
  const matched = new Set<string>();

  // Check dual-tag keywords first (trade deals -> both tariff + trump_effect)
  for (const kw of DUAL_TAG_KEYWORDS) {
    if (textLower.includes(kw)) {
      matched.add("tariff");
      matched.add("trump_effect");
    }
  }

  // Standard keyword matching - break on first match per specialist
  for (const [specialist, keywords] of Object.entries(SPECIALIST_KEYWORDS)) {
    for (const kw of keywords) {
      if (textLower.includes(kw)) {
        matched.add(specialist);
        break; // Only match each specialist once
      }
    }
  }

  return matched.size > 0 ? Array.from(matched) : ["general"];
}

/**
 * Validate and filter tags to only include valid Big-11 specialists.
 *
 * @param tags - Array of tag strings to validate
 * @returns Filtered array containing only valid specialist names + "general"
 */
export function validateSpecialists(tags: string[]): string[] {
  const valid = new Set([...BIG_11_SPECIALISTS, "general"]);
  return tags.filter((t) => valid.has(t));
}

/**
 * Check if a tag is a valid Big-11 specialist.
 *
 * @param tag - Tag string to check
 * @returns True if valid specialist or "general"
 */
export function isValidSpecialist(tag: string): tag is SpecialistOrGeneral {
  return BIG_11_SPECIALISTS.includes(tag as Specialist) || tag === "general";
}
