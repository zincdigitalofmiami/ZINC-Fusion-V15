"""
Specialist Keywords Dictionary - Single Source of Truth

This dictionary maps each Big-11 specialist to its trigger keywords.
Keywords are matched case-insensitively via substring search.

Source: Consolidated from scripts/ingest_barchart_rss.py with additions
        per Specialist Tagging Audit Report (2026-01-18)

Maintenance:
- Add new keywords here, they will propagate to all tagging code
- Mirror changes to frontend/src/lib/specialist-classifier.ts
- Avoid overlap between tariff and trump_effect (use DUAL_TAG_KEYWORDS for shared cases)
"""

from typing import Dict, List

SPECIALIST_KEYWORDS: Dict[str, List[str]] = {
    # ============================================================
    # CRUSH - Soybean processing, crush margins, meal/oil spread
    # ============================================================
    "crush": [
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
        "nopa",  # National Oilseed Processors Association
        "meal-oil spread",
        "soybean crush",
    ],

    # ============================================================
    # CHINA - Chinese demand, trade flows, ASF, import patterns
    # ============================================================
    "china": [
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
        "gacc",  # General Administration of Customs of China
        "cny",
    ],

    # ============================================================
    # FX - Currency movements, USD strength, BRL/MXN/CNY
    # ============================================================
    "fx": [
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

    # ============================================================
    # FED - Federal Reserve, monetary policy, interest rates
    # ============================================================
    "fed": [
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

    # ============================================================
    # TARIFF - Trade mechanisms, Section 301/232, duties, WTO
    # NOTE: Trade DEALS go in DUAL_TAG_KEYWORDS (both tariff + trump_effect)
    # ============================================================
    "tariff": [
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

    # ============================================================
    # ENERGY - Crude oil, diesel, petroleum, OPEC
    # ============================================================
    "energy": [
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

    # ============================================================
    # BIOFUEL - Biodiesel, RFS, RINs, renewable diesel, SAF
    # ============================================================
    "biofuel": [
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
        "45z",  # Clean Fuel Production Credit
        "clean fuel production credit",
        "inflation reduction act",
        "ira",
        "d4 rin",
        "d6 rin",
        "biomass-based diesel",
    ],

    # ============================================================
    # PALM - Palm oil, Malaysia, Indonesia, MPOB
    # ============================================================
    "palm": [
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

    # ============================================================
    # VOLATILITY - VIX, risk, uncertainty, hedging
    # ============================================================
    "volatility": [
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

    # ============================================================
    # SUBSTITUTES - Canola, sunflower, cottonseed, tallow
    # ============================================================
    "substitutes": [
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

    # ============================================================
    # TRUMP_EFFECT - Policy uncertainty, executive orders, EPU
    # NOTE: Trade DEALS go in DUAL_TAG_KEYWORDS (both tariff + trump_effect)
    # NOTE: Avoid short ambiguous keywords (e.g., "ice" matches "nice", "price")
    # ============================================================
    "trump_effect": [
        "trump",
        "white house",
        "executive order",
        "truth social",
        "policy uncertainty",
        "epu",
        "political risk",
        "election",
        "doge",  # Department of Government Efficiency
        "elon musk",  # More specific to avoid partial matches
        "deportation",
        "immigration",
        "ice enforcement",  # "ice" alone matches "nice", "price", etc.
        "border patrol",
        "border security",
        "mass deportation",
        "presidential action",
        "administration policy",
    ],
}
