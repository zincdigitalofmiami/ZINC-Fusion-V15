"""
Specialist Bucket Router
========================
AI-powered routing of data sources to specialist training buckets.

The 11 Economic Drivers (Big-11):
1. crush        - Soybean crush margins and processing economics
2. china        - China import demand, trade flow behavior
3. fx           - Foreign exchange impacts on global oil pricing
4. fed          - Rates, liquidity, and monetary policy transmission
5. tariff       - Tariffs, trade policy, and regulatory friction
6. energy       - Crude, diesel, and energy complex spillover
7. biofuel      - RFS, SAF, biodiesel incentives and demand
8. palm         - Palm oil supply, pricing, and substitution effects
9. volatility   - Market stress, convexity, regime shifts
10. substitutes - Cross-oil substitution (canola, UCO, etc.)
11. trump_effect - Trump/policy regime dynamics, trade war, EPA waivers
"""

from typing import Dict, List, Set, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
import re
from ..taxonomy import ECONOMIC_DRIVERS, DRIVER_DESCRIPTIONS


class SpecialistBucket(Enum):
    """The 11 specialist buckets for soybean oil forecasting."""

    CRUSH = "crush"
    CHINA = "china"
    FX = "fx"
    FED = "fed"
    TARIFF = "tariff"
    ENERGY = "energy"
    BIOFUEL = "biofuel"
    PALM = "palm"
    VOLATILITY = "volatility"
    SUBSTITUTES = "substitutes"
    TRUMP_EFFECT = "trump_effect"


@dataclass
class RoutingRule:
    """Rule for routing data to a specialist bucket."""

    bucket: SpecialistBucket
    patterns: List[str]  # Regex patterns
    keywords: Set[str]  # Exact keyword matches
    series_prefixes: List[str] = field(default_factory=list)  # FRED series prefixes
    weight: float = 1.0  # Priority weight for conflicts


# =============================================================================
# ROUTING RULES BY BUCKET
# =============================================================================

ROUTING_RULES: Dict[SpecialistBucket, RoutingRule] = {
    SpecialistBucket.CRUSH: RoutingRule(
        bucket=SpecialistBucket.CRUSH,
        patterns=[
            r"crush.*margin",
            r"soybean.*process",
            r"meal.*spread",
            r"board.*crush",
            r"gpr.*crush",
            r"zs.*zm.*spread",
        ],
        keywords={
            "crush",
            "crushing",
            "crusher",
            "soybean_meal",
            "meal_price",
            "oil_extraction",
            "processing_margin",
            "crush_spread",
            "ZS",
            "ZM",
            "SM",
            "BO",
            "soybean_oil_yield",
        },
        series_prefixes=["SOYBEAN", "MEAL", "CRUSH"],
        weight=1.0,
    ),
    SpecialistBucket.CHINA: RoutingRule(
        bucket=SpecialistBucket.CHINA,
        patterns=[
            r"china.*import",
            r"chinese.*demand",
            r"cofco",
            r"sinograin",
            r"dalian.*commodity",
            r"cn.*soybean",
            r"pboc",
        ],
        keywords={
            "china",
            "chinese",
            "cofco",
            "sinograin",
            "ndrc",
            "dalian",
            "cn_import",
            "china_demand",
            "chinese_crush",
            "pboc",
            "renminbi",
            "yuan",
            "cny",
            "usdcny",
        },
        series_prefixes=["CN", "CHINA", "PBOC"],
        weight=1.2,  # Higher weight - China is key driver
    ),
    SpecialistBucket.FX: RoutingRule(
        bucket=SpecialistBucket.FX,
        patterns=[
            r"usd.*brl",
            r"usd.*ars",
            r"usd.*cny",
            r"forex",
            r"exchange.*rate",
            r"currency",
            r"fx_",
        ],
        keywords={
            "fx",
            "forex",
            "currency",
            "exchange_rate",
            "usd",
            "brl",
            "ars",
            "cny",
            "eur",
            "dollar_index",
            "dxy",
            "usdbrl",
            "usdars",
            "usdcny",
            "real",
            "peso",
            "yuan",
            "euro",
        },
        series_prefixes=["DEXUS", "DTWEX", "FX", "EXCH"],
        weight=1.0,
    ),
    SpecialistBucket.FED: RoutingRule(
        bucket=SpecialistBucket.FED,
        patterns=[
            r"fed.*fund",
            r"fomc",
            r"federal.*reserve",
            r"monetary.*policy",
            r"interest.*rate",
            r"treasury.*yield",
            r"liquidity",
        ],
        keywords={
            "fed",
            "fomc",
            "federal_reserve",
            "fed_funds",
            "interest_rate",
            "treasury",
            "yield_curve",
            "t10y2y",
            "t10y3m",
            "sofr",
            "libor",
            "quantitative_easing",
            "qe",
            "qt",
            "balance_sheet",
            "liquidity",
        },
        series_prefixes=["DFF", "DGS", "T10Y", "TB", "SOFR", "FEDFUNDS"],
        weight=1.1,
    ),
    SpecialistBucket.TARIFF: RoutingRule(
        bucket=SpecialistBucket.TARIFF,
        patterns=[
            r"tariff",
            r"trade.*war",
            r"trade.*policy",
            r"sanction",
            r"import.*duty",
            r"export.*restriction",
            r"trade.*barrier",
        ],
        keywords={
            "tariff",
            "trade_war",
            "sanction",
            "duty",
            "quota",
            "embargo",
            "trade_policy",
            "section_301",
            "section_232",
            "wto",
            "ustr",
            "cbp",
            "import_ban",
            "export_ban",
            "retaliatory",
            "trade_dispute",
        },
        series_prefixes=["TARIFF", "TRADE"],
        weight=1.3,  # High weight - tariffs are market movers
    ),
    SpecialistBucket.ENERGY: RoutingRule(
        bucket=SpecialistBucket.ENERGY,
        patterns=[
            r"crude.*oil",
            r"brent",
            r"wti",
            r"heating.*oil",
            r"diesel",
            r"nat.*gas",
            r"energy.*price",
            r"opec",
        ],
        keywords={
            "crude",
            "crude_oil",
            "wti",
            "brent",
            "cl",
            "heating_oil",
            "ho",
            "diesel",
            "ulsd",
            "gasoline",
            "rb",
            "natural_gas",
            "ng",
            "opec",
            "energy",
            "petroleum",
            "refinery",
            "crack_spread",
        },
        series_prefixes=["WTISPL", "DCOIL", "GASREG", "DGASREG"],
        weight=1.0,
    ),
    SpecialistBucket.BIOFUEL: RoutingRule(
        bucket=SpecialistBucket.BIOFUEL,
        patterns=[
            r"biofuel",
            r"biodiesel",
            r"renewable.*diesel",
            r"rfs",
            r"rin.*price",
            r"saf",
            r"sustainable.*aviation",
        ],
        keywords={
            "biofuel",
            "biodiesel",
            "renewable_diesel",
            "rfs",
            "rin",
            "d4",
            "saf",
            "sustainable_aviation_fuel",
            "lcfs",
            "blender_credit",
            "epa_mandate",
            "volume_obligation",
            "rvo",
            "ethanol",
            "corn_ethanol",
        },
        series_prefixes=["RIN", "BIO", "EPA"],
        weight=1.2,
    ),
    SpecialistBucket.PALM: RoutingRule(
        bucket=SpecialistBucket.PALM,
        patterns=[
            r"palm.*oil",
            r"cpo",
            r"malaysia.*palm",
            r"indonesia.*palm",
            r"mpob",
            r"gapki",
            r"bursa.*malaysia",
        ],
        keywords={
            "palm",
            "palm_oil",
            "cpo",
            "crude_palm_oil",
            "pko",
            "palm_kernel",
            "malaysia",
            "indonesia",
            "mpob",
            "gapki",
            "export_levy",
            "export_ban",
            "deforestation",
            "rspo",
            "ispo",
            "biodiesel_mandate",
        },
        series_prefixes=["PALM", "CPO", "MY", "ID"],
        weight=1.0,
    ),
    SpecialistBucket.VOLATILITY: RoutingRule(
        bucket=SpecialistBucket.VOLATILITY,
        patterns=[
            r"volatility",
            r"vix",
            r"implied.*vol",
            r"realized.*vol",
            r"option.*vol",
            r"skew",
            r"risk.*premium",
        ],
        keywords={
            "volatility",
            "vol",
            "vix",
            "implied_vol",
            "realized_vol",
            "iv",
            "rv",
            "skew",
            "kurtosis",
            "risk_premium",
            "option",
            "straddle",
            "strangle",
            "gamma",
            "vega",
            "theta",
            "risk_reversal",
            "atm_vol",
        },
        series_prefixes=["VIX", "VXO", "OVX", "VXCLS"],
        weight=0.9,
    ),
    SpecialistBucket.SUBSTITUTES: RoutingRule(
        bucket=SpecialistBucket.SUBSTITUTES,
        patterns=[
            r"canola",
            r"rapeseed",
            r"sunflower",
            r"used.*cooking.*oil",
            r"uco",
            r"tallow",
            r"animal.*fat",
        ],
        keywords={
            "canola",
            "rapeseed",
            "sunflower",
            "uco",
            "used_cooking_oil",
            "tallow",
            "animal_fat",
            "lard",
            "choice_white_grease",
            "cwg",
            "yellow_grease",
            "brown_grease",
            "vegetable_oil",
            "edible_oil",
        },
        series_prefixes=["CANOLA", "RAPE", "SUN"],
        weight=0.8,
    ),
    SpecialistBucket.TRUMP_EFFECT: RoutingRule(
        bucket=SpecialistBucket.TRUMP_EFFECT,
        patterns=[
            r"trump",
            r"executive.*order",
            r"policy.*uncertainty",
            r"trade.*war",
            r"section.*301",
            r"epa.*waiver",
            r"rfs.*waiver",
            r"mfp.*payment",
            r"truth.*social",
        ],
        keywords={
            "trump",
            "trump_effect",
            "executive_order",
            "policy_uncertainty",
            "trade_war",
            "section_301",
            "epa_waiver",
            "rfs_waiver",
            "mfp",
            "market_facilitation",
            "tweet",
            "truth_social",
            "whitehouse",
            "ustr",
            "tariff_threat",
            "china_deal",
            "phase_one",
        },
        series_prefixes=["USEPUINDXD", "EPUTRADE", "EMVTRADE", "CHNMAINLAND", "TPU"],
        weight=1.4,  # High weight - regime-specific dynamics
    ),
}


class SpecialistRouter:
    """
    AI-powered router for classifying data into specialist buckets.

    Uses pattern matching, keyword analysis, and context-aware scoring
    to determine the optimal specialist bucket for each data point.
    """

    def __init__(self, rules: Optional[Dict[SpecialistBucket, RoutingRule]] = None):
        self.rules = rules or ROUTING_RULES
        self._compiled_patterns = self._compile_patterns()

    def _compile_patterns(self) -> Dict[SpecialistBucket, List[re.Pattern]]:
        """Pre-compile regex patterns for efficiency."""
        compiled = {}
        for bucket, rule in self.rules.items():
            compiled[bucket] = [re.compile(p, re.IGNORECASE) for p in rule.patterns]
        return compiled

    def route(
        self,
        text: str,
        series_id: Optional[str] = None,
        source: Optional[str] = None,
    ) -> List[tuple[SpecialistBucket, float]]:
        """
        Route data to specialist bucket(s) with confidence scores.

        Args:
            text: Text content to classify (description, headline, etc.)
            series_id: Optional FRED/data series ID
            source: Optional source identifier

        Returns:
            List of (bucket, score) tuples sorted by score descending
        """
        scores: Dict[SpecialistBucket, float] = {b: 0.0 for b in SpecialistBucket}
        text_lower = text.lower()

        for bucket, rule in self.rules.items():
            score = 0.0

            # Pattern matching (highest weight)
            for pattern in self._compiled_patterns[bucket]:
                if pattern.search(text_lower):
                    score += 2.0 * rule.weight

            # Keyword matching
            for keyword in rule.keywords:
                if keyword.lower() in text_lower:
                    score += 1.0 * rule.weight

            # Series prefix matching (if series_id provided)
            if series_id:
                series_upper = series_id.upper()
                for prefix in rule.series_prefixes:
                    if series_upper.startswith(prefix):
                        score += 3.0 * rule.weight  # Strong signal

            scores[bucket] = score

        # Normalize and filter
        max_score = max(scores.values()) if max(scores.values()) > 0 else 1.0
        results = [
            (bucket, score / max_score) for bucket, score in scores.items() if score > 0
        ]

        return sorted(results, key=lambda x: x[1], reverse=True)

    def route_single(
        self,
        text: str,
        series_id: Optional[str] = None,
        threshold: float = 0.3,
    ) -> Optional[SpecialistBucket]:
        """
        Route to a single best bucket if confidence exceeds threshold.

        Returns None if no bucket meets threshold.
        """
        results = self.route(text, series_id)
        if results and results[0][1] >= threshold:
            return results[0][0]
        return None

    def route_multi(
        self,
        text: str,
        series_id: Optional[str] = None,
        threshold: float = 0.5,
        max_buckets: int = 3,
    ) -> List[SpecialistBucket]:
        """
        Route to multiple buckets for data that spans categories.

        Returns list of buckets meeting threshold, up to max_buckets.
        """
        results = self.route(text, series_id)
        return [bucket for bucket, score in results[:max_buckets] if score >= threshold]


# =============================================================================
# DATA ROUTER (Higher-level abstraction)
# =============================================================================


@dataclass
class RoutedData:
    """Container for routed data with metadata."""

    data: Any
    primary_bucket: SpecialistBucket
    secondary_buckets: List[SpecialistBucket]
    confidence: float
    source: str
    routing_metadata: Dict[str, Any] = field(default_factory=dict)


class DataRouter:
    """
    High-level data router for batch processing.

    Routes entire datasets to their appropriate specialist tables.
    """

    def __init__(self):
        self.router = SpecialistRouter()

    def route_fred_series(self, series_id: str, description: str) -> RoutedData:
        """Route a FRED series to specialist bucket(s)."""
        results = self.router.route(description, series_id=series_id)

        if not results:
            # Default to FED for unclassified macro data
            return RoutedData(
                data={"series_id": series_id},
                primary_bucket=SpecialistBucket.FED,
                secondary_buckets=[],
                confidence=0.5,
                source="fred",
                routing_metadata={"reason": "default_macro"},
            )

        primary = results[0]
        secondary = [b for b, s in results[1:3] if s >= 0.5]

        return RoutedData(
            data={"series_id": series_id},
            primary_bucket=primary[0],
            secondary_buckets=secondary,
            confidence=primary[1],
            source="fred",
            routing_metadata={"all_scores": dict(results)},
        )

    def route_news_article(self, headline: str, body: str = "") -> RoutedData:
        """Route a news article to specialist bucket(s)."""
        full_text = f"{headline} {body}"
        results = self.router.route(full_text)

        if not results:
            return RoutedData(
                data={"headline": headline},
                primary_bucket=SpecialistBucket.VOLATILITY,  # News often = vol
                secondary_buckets=[],
                confidence=0.3,
                source="news",
                routing_metadata={"reason": "default_news"},
            )

        primary = results[0]
        secondary = [b for b, s in results[1:3] if s >= 0.4]

        return RoutedData(
            data={"headline": headline},
            primary_bucket=primary[0],
            secondary_buckets=secondary,
            confidence=primary[1],
            source="news",
            routing_metadata={"all_scores": dict(results)},
        )

    def get_target_table(self, bucket: SpecialistBucket, grain: str = "1d") -> str:
        """Get the target training table for a bucket."""
        # Map to canonical specialist naming
        bucket_map = {
            SpecialistBucket.CRUSH: "crush",
            SpecialistBucket.CHINA: "china",
            SpecialistBucket.FX: "fx",
            SpecialistBucket.FED: "fed",
            SpecialistBucket.TARIFF: "tariff",
            SpecialistBucket.ENERGY: "energy",
            SpecialistBucket.BIOFUEL: "biofuel",
            SpecialistBucket.PALM: "palm",
            SpecialistBucket.VOLATILITY: "volatility",
            SpecialistBucket.SUBSTITUTES: "substitutes",
            SpecialistBucket.TRUMP_EFFECT: "trump_effect",
        }
        bucket_name = bucket_map.get(bucket, "volatility")
        return f"training.specialist_{bucket_name}_{grain}"


# =============================================================================
# FRED SERIES CLASSIFICATION (Pre-defined mappings)
# =============================================================================

# Canonical FRED series → bucket mappings
FRED_SERIES_BUCKETS: Dict[str, SpecialistBucket] = {
    # FED bucket
    "DFF": SpecialistBucket.FED,  # Fed Funds Rate
    "FEDFUNDS": SpecialistBucket.FED,  # Federal Funds Effective Rate
    "DFEDTARL": SpecialistBucket.FED,  # Fed Funds Target Range (Lower)
    "DFEDTARU": SpecialistBucket.FED,  # Fed Funds Target Range (Upper)
    "DGS10": SpecialistBucket.FED,  # 10-Year Treasury
    "DGS2": SpecialistBucket.FED,  # 2-Year Treasury
    "T10Y2Y": SpecialistBucket.FED,  # Yield Curve
    "T10Y3M": SpecialistBucket.FED,  # Yield Curve
    "SOFR": SpecialistBucket.FED,  # SOFR Rate
    "BOGMBASE": SpecialistBucket.FED,  # Monetary Base
    "M2SL": SpecialistBucket.FED,  # M2 Money Supply
    "TOTRESNS": SpecialistBucket.FED,  # Total Reserves
    "BUSLOANS": SpecialistBucket.FED,  # Commercial & Industrial Loans
    "DRCCLACBS": SpecialistBucket.FED,  # Credit Card Delinquency Rate
    "WALCL": SpecialistBucket.FED,  # Fed Balance Sheet
    "PCE": SpecialistBucket.FED,  # Personal Consumption Expenditures
    "PPIACO": SpecialistBucket.FED,  # PPI All Commodities
    "PPIFGS": SpecialistBucket.FED,  # PPI Finished Goods
    "GDP": SpecialistBucket.FED,  # Gross Domestic Product
    "GDPC1": SpecialistBucket.FED,  # Real GDP
    "HOUST": SpecialistBucket.FED,  # Housing Starts
    "PERMIT": SpecialistBucket.FED,  # Housing Permits
    "MANEMP": SpecialistBucket.FED,  # Manufacturing Employment
    "RSXFS": SpecialistBucket.FED,  # Retail Sales
    # FX bucket
    "DEXUSEU": SpecialistBucket.FX,  # USD/EUR
    "DEXBZUS": SpecialistBucket.FX,  # USD/BRL
    "DEXCHUS": SpecialistBucket.FX,  # USD/CNY
    "DEXMXUS": SpecialistBucket.FX,  # USD/MXN
    "DTWEXBGS": SpecialistBucket.FX,  # Trade Weighted USD
    "DTWEXM": SpecialistBucket.FX,  # Trade Weighted USD (Major)
    # ENERGY bucket
    "DCOILWTICO": SpecialistBucket.ENERGY,  # WTI Crude
    "DCOILBRENTEU": SpecialistBucket.ENERGY,  # Brent Crude
    "DHHNGSP": SpecialistBucket.ENERGY,  # Henry Hub Natural Gas
    "GASREGW": SpecialistBucket.ENERGY,  # Gasoline Prices
    "DHOILNYH": SpecialistBucket.ENERGY,  # Heating Oil NY Harbor
    "PNGASEUUSDM": SpecialistBucket.ENERGY,  # EU Natural Gas Price
    "WPU057303": SpecialistBucket.ENERGY,  # PPI Diesel Fuel
    "PCU32411032411012": SpecialistBucket.ENERGY,  # PPI Motor Gasoline
    "APU000074714": SpecialistBucket.BIOFUEL,  # Gasoline CPI (Unleaded Regular)
    "WPU06140341": SpecialistBucket.BIOFUEL,  # PPI Ethanol
    # CRUSH bucket (soybean-related)
    "PSOYBOILUSDM": SpecialistBucket.CRUSH,  # Soybean Oil
    "PSOYBEANMEALUSDM": SpecialistBucket.CRUSH,  # Soybean Meal
    "PCU311224311224": SpecialistBucket.CRUSH,  # PPI Soybean Oil Processing
    # Macro / Inflation (often fed-related)
    "CPIAUCSL": SpecialistBucket.FED,  # CPI (headline)
    "PCEPI": SpecialistBucket.FED,  # PCE Price Index
    # VOLATILITY bucket
    "SP500": SpecialistBucket.VOLATILITY,  # S&P 500
    "NASDAQCOM": SpecialistBucket.VOLATILITY,  # NASDAQ Composite
    "VIXCLS": SpecialistBucket.VOLATILITY,  # VIX
    "STLFSI": SpecialistBucket.VOLATILITY,  # Financial Stress Index (legacy)
    "TEDRATE": SpecialistBucket.VOLATILITY,  # TED Spread
    "STLFSI4": SpecialistBucket.VOLATILITY,  # Financial Stress Index
    "BAMLH0A0HYM2": SpecialistBucket.VOLATILITY,  # HY OAS proxy for risk
    "OVXCLS": SpecialistBucket.VOLATILITY,  # Oil VIX
    # SUBSTITUTES bucket
    "PCOPPUSDM": SpecialistBucket.SUBSTITUTES,  # Copper Price
    "PRICENPQUSDM": SpecialistBucket.SUBSTITUTES,  # Rice Price
    "PSUNOUSDM": SpecialistBucket.SUBSTITUTES,  # Sunflower Oil Price
    "WPU01830161": SpecialistBucket.SUBSTITUTES,  # PPI Farm Products: Sunflower
    "WPU01830171": SpecialistBucket.SUBSTITUTES,  # PPI Farm Products: Canola
    # TARIFF bucket
    "BOPGSTB": SpecialistBucket.TARIFF,  # Trade Balance
    "EXPGS": SpecialistBucket.TARIFF,  # Exports of Goods & Services
    "IMPGS": SpecialistBucket.TARIFF,  # Imports of Goods & Services
    # CHINA bucket
    "CHNCPIALLMINMEI": SpecialistBucket.CHINA,  # China CPI
    "IR3TIB01CNM156N": SpecialistBucket.CHINA,  # China 3M Interbank Rate
    "MYAGM2CNM189N": SpecialistBucket.CHINA,  # China M2
    # TRUMP_EFFECT bucket (policy uncertainty + trade flow)
    "USEPUINDXD": SpecialistBucket.TRUMP_EFFECT,  # US Economic Policy Uncertainty (Daily)
    "USEPUINDXM": SpecialistBucket.TRUMP_EFFECT,  # US Economic Policy Uncertainty (Monthly)
    "EPUTRADE": SpecialistBucket.TARIFF,  # Trade Policy Uncertainty (per RAW_SOURCE_SPECIALIST_MAPPING.md)
    "EMVTRADEPOLEMV": SpecialistBucket.TRUMP_EFFECT,  # Equity Market Volatility: Trade Policy
    "CHNMAINLANDTPU": SpecialistBucket.TRUMP_EFFECT,  # China Trade Policy Uncertainty
    "B235RC1Q027SBEA": SpecialistBucket.TRUMP_EFFECT,  # Customs Duties (tariff receipts)
    "IMPCH": SpecialistBucket.TRUMP_EFFECT,  # US Imports from China
}


def get_fred_bucket(series_id: str) -> SpecialistBucket:
    """Get the specialist bucket for a FRED series."""
    # First check explicit mapping
    if series_id in FRED_SERIES_BUCKETS:
        return FRED_SERIES_BUCKETS[series_id]

    # Fall back to router
    router = SpecialistRouter()
    result = router.route_single(series_id, series_id=series_id)
    return result or SpecialistBucket.FED  # Default to FED for macro
