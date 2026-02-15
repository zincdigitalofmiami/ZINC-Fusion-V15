"""
ZINC-FUSION Quality News Source Configuration
==============================================
Defines high-quality sources for Claude sentiment scoring.

Based on CBI-V14/V15 Data Links document:
- Prioritizes institutional/government sources
- Filters out social media noise (Twitter Christmas posts, etc.)
- Ranks by ZL market impact potential

Usage:
    from config.quality_news_sources import is_quality_source, get_source_priority

    if is_quality_source(article.source):
        # Worth Claude API credits
        claude_score(article)
"""

# =============================================================================
# TIER 1: CRITICAL - Always score with Claude
# These sources move markets and provide actionable intelligence
# =============================================================================

TIER_1_CRITICAL = {
    # USDA - Official government data
    "usda_press",  # USDA Press Releases
    "usda_nass",  # NASS reports
    "usda_wasde",  # WASDE monthly
    "usda_fas",  # Foreign Agricultural Service
    "usda_oil_crops",  # Oil Crops Outlook
    # Brazil - Major soybean exporter
    "conab",  # CONAB official forecasts
    "conab_oficial",  # CONAB official Twitter (actual data posts)
    "abiove",  # ABIOVE (Brazil crush association)
    # China - Major demand driver
    "cofco",  # COFCO announcements
    "sinograin",  # Sinograin reserves
    "mofcom",  # Ministry of Commerce
    # US Policy - Trade and biofuel
    "federal_register_tariffs",  # Federal Register tariff rules
    "federal_register_eo",  # Executive orders
    "whitehouse_eo",  # White House policy
    "whitehouse_briefing",  # White House statements
    "ustr_press",  # USTR trade policy
    "epa_news",  # EPA biofuel mandates
    # Fed/Macro - Rate decisions
    "fed_news",  # Federal Reserve releases
    "fed_speeches",  # FOMC member speeches
    # Energy/Biofuel - Critical for ZL demand
    "eia_today",  # EIA Today in Energy
    "eia_petroleum",  # EIA petroleum reports
    "biodiesel_mag",  # Biodiesel Magazine
    # Premium Ag Intelligence
    "farm_policy_news",  # Farm Policy News (U of I)
    "farmdoc_daily",  # FarmDoc Daily (U of I)
    "soybean_corn_advisor",  # Dr. Cordonnier's analysis
    "dtn_progressive",  # DTN market analysis
}

# =============================================================================
# TIER 2: HIGH VALUE - Score with Claude when budget allows
# Quality analysis and market-relevant news
# =============================================================================

TIER_2_HIGH_VALUE = {
    # Ag Industry Publications
    "agweb_soybeans",  # AgWeb soybean coverage
    "agrimoney_grains",  # Agrimoney grains
    "agrimoney_china",  # Agrimoney China
    "reuters_commodities",  # Reuters commodities desk
    "reuters_china",  # Reuters Asia/China
    "farm_progress",  # Farm Progress
    "world_grain",  # World Grain
    "agriculture_com",  # Agriculture.com
    # Palm Oil (substitution dynamics)
    "mpob_news",  # MPOB Malaysia
    "gapki",  # GAPKI Indonesia
    "palm_oil_today",  # Palm Oil Today
    # Substitutes
    "canola_council",  # Canola Council Canada
    "oilseed_grain",  # Oilseed & Grain News
    # Macro/FX
    "ecb_press",  # ECB releases
    # Political/Policy
    "politico_trade",  # Politico trade coverage
    # Additional EIA/White House
    "eia_rss",  # EIA general RSS
    "whitehouse_rss",  # White House RSS
    "agfunder_news",  # AgFunder (ag tech/investment)
}

# =============================================================================
# TIER 3: MODERATE VALUE - Use FinBERT only, skip Claude
# Useful for sentiment aggregation but not worth Claude credits individually
# =============================================================================

TIER_3_FINBERT_ONLY = {
    # General Ag Media
    "biofuels_digest",
    "feedstuffs",
    # Softs/Substitutes
    "sunflower_nsa",
    "ice_canola",
    # Volatility
    "cboe_insights",
    # FRED calendar (data releases, not analysis)
    "fred_release_calendar",
    # Industry associations
    "rspo_news",
}

# =============================================================================
# TIER 1.5: PREMIUM TWITTER ANALYSTS - Real market intelligence
# These accounts post actual market data, not personal content
# =============================================================================

TIER_PREMIUM_TWITTER = {
    # Professional Market Analysts - Posts contain actual data
    "twitter_ProFarmer",  # DTN/ProFarmer market intelligence
    "twitter_ArlanFF101",  # Arlan Suderman (StoneX chief commodity economist)
    "twitter_JavierBlas",  # Javier Blas (Bloomberg commodities columnist)
    "twitter_SoybeanCorn",  # Dr. Michael Cordonnier
    "twitter_dtnpf",  # DTN Progressive Farmer
    "twitter_conab_oficial",  # CONAB official data posts
    # Wire Services - Breaking news
    "twitter_Reuters",
    "twitter_FT",  # Financial Times
    # Government officials (policy signals)
    "twitter_SecVilsack",  # USDA Secretary
}

# =============================================================================
# TIER 4: NOISE - Skip entirely (personal posts, holiday wishes, PR)
# =============================================================================

TIER_4_NOISE = {
    # Personal/PR Twitter - NOT market intelligence
    "twitter_EricTrump",  # Personal/political
    "twitter_SecYellen",  # Treasury - not ag relevant
    "twitter_GrowthEnergy",  # PR/advocacy posts
    "twitter_EthanolRFA",  # "Merry Christmas" type posts
    "twitter_Cargill",  # Corporate PR
    "twitter_EconomicPolicy",  # Think tank
    "twitter_ASA_Soybeans",  # "Congrats!" type posts
    "twitter_ChinaDaily",  # State media - propaganda
    "twitter_CommodityWX",  # Weather forecasts (use NOAA instead)
    "twitter_NationalCorn",  # Miller Lite jokes, PR
    "twitter_AEI",  # Think tank
    "twitter_kannbwx",  # Personal posts (running races, etc.)
    "twitter_CatoInstitute",  # Think tank
    "twitter_BrookingsInst",  # Think tank
    "twitter_FarmBureau",  # Advocacy/PR
    "twitter_AgriPulse",  # Can be good but mixed
    "twitter",  # Generic twitter
    # Generic political news (not ag-specific)
    "thehill_politics",
    "scmp_china",  # South China Morning Post - general news
    # Google search results (unreliable)
    "google_search",
    # TradingEconomics (price data, not news)
    "tradingec_palm",
    "tradingec_canola",
    "tradingec_sunflower",
    "tradingec_rapeseed",
    # ICE factsheets (static documents)
    "ice_factsheets",
}

# =============================================================================
# SPECIAL HANDLING: TRUTH SOCIAL (Trump Effect Specialist)
# Only score via ScrapeCreators API with proper filtering
# =============================================================================

TRUTH_SOCIAL_SOURCES = {
    "truth_social",  # realDonaldTrump via ScrapeCreators
}

# Keywords to filter Trump posts for ZL relevance
TRUMP_ZL_KEYWORDS = [
    "tariff",
    "china",
    "trade",
    "soybean",
    "farmer",
    "agriculture",
    "biodiesel",
    "ethanol",
    "energy",
    "fuel",
    "oil",
    "epa",
    "regulation",
    "import",
    "export",
    "brazil",
    "argentina",
]

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================


def get_source_tier(source_id: str) -> int:
    """
    Get the quality tier for a source.

    Returns:
        1: Critical - Always Claude score
        1.5: Premium Twitter analysts - Claude score
        2: High Value - Claude when budget allows
        3: FinBERT only
        4: Noise - Skip
        5: Special handling (Truth Social)
        0: Unknown source
    """
    source_lower = source_id.lower() if source_id else ""

    # Check each tier in order of priority
    if source_lower in TIER_1_CRITICAL or source_id in TIER_1_CRITICAL:
        return 1
    if source_lower in TIER_PREMIUM_TWITTER or source_id in TIER_PREMIUM_TWITTER:
        return 1  # Treat premium Twitter same as Tier 1
    if source_lower in TIER_2_HIGH_VALUE or source_id in TIER_2_HIGH_VALUE:
        return 2
    if source_lower in TIER_3_FINBERT_ONLY or source_id in TIER_3_FINBERT_ONLY:
        return 3
    if source_lower in TIER_4_NOISE or source_id in TIER_4_NOISE:
        return 4
    if source_lower in TRUTH_SOCIAL_SOURCES or source_id in TRUTH_SOCIAL_SOURCES:
        return 5

    # Check for partial matches (e.g., "twitter_" prefix)
    if source_lower.startswith("twitter_"):
        return 4  # Default unknown Twitter to noise

    return 0  # Unknown


def is_quality_source(source_id: str) -> bool:
    """Check if source is worth Claude API credits (Tier 1 or 2)."""
    return get_source_tier(source_id) in (1, 2, 5)


def is_noise_source(source_id: str) -> bool:
    """Check if source should be skipped entirely."""
    return get_source_tier(source_id) == 4


def should_use_claude(source_id: str, budget_mode: str = "normal") -> bool:
    """
    Determine if article from this source should use Claude scoring.

    Args:
        source_id: The source identifier
        budget_mode: 'strict' (Tier 1 only), 'normal' (Tier 1+2), 'full' (Tier 1+2+5)

    Returns:
        True if Claude scoring recommended
    """
    tier = get_source_tier(source_id)

    if budget_mode == "strict":
        return tier == 1
    elif budget_mode == "normal":
        return tier in (1, 2)
    else:  # full
        return tier in (1, 2, 5)


def filter_trump_post_for_zl(content: str) -> bool:
    """
    Check if a Trump post is relevant to ZL markets.
    Filters out personal posts, holiday wishes, etc.
    """
    if not content:
        return False

    content_lower = content.lower()
    return any(kw in content_lower for kw in TRUMP_ZL_KEYWORDS)


# =============================================================================
# SOURCE METADATA
# =============================================================================

SOURCE_METADATA = {
    "usda_press": {
        "name": "USDA Press Releases",
        "specialist": "crush",
        "update_freq": "daily",
    },
    "conab": {"name": "CONAB Brazil", "specialist": "crush", "update_freq": "monthly"},
    "farm_policy_news": {
        "name": "Farm Policy News",
        "specialist": "crush",
        "update_freq": "daily",
    },
    "farmdoc_daily": {
        "name": "FarmDoc Daily",
        "specialist": "crush",
        "update_freq": "daily",
    },
    "epa_news": {
        "name": "EPA Biofuel News",
        "specialist": "biofuel",
        "update_freq": "weekly",
    },
    "fed_news": {
        "name": "Federal Reserve",
        "specialist": "fed",
        "update_freq": "as_needed",
    },
    "truth_social": {
        "name": "Truth Social (Trump)",
        "specialist": "trump_effect",
        "update_freq": "realtime",
    },
    "mpob_news": {
        "name": "MPOB Malaysia",
        "specialist": "palm",
        "update_freq": "monthly",
    },
    "dtn_progressive": {
        "name": "DTN Progressive Farmer",
        "specialist": "crush",
        "update_freq": "daily",
    },
}


def get_all_quality_sources() -> set:
    """Get all sources worth processing (Tier 1-3)."""
    return (
        TIER_1_CRITICAL | TIER_2_HIGH_VALUE | TIER_3_FINBERT_ONLY | TRUTH_SOCIAL_SOURCES
    )


def get_claude_sources() -> set:
    """Get all sources worth Claude API credits."""
    return (
        TIER_1_CRITICAL
        | TIER_PREMIUM_TWITTER
        | TIER_2_HIGH_VALUE
        | TRUTH_SOCIAL_SOURCES
    )


def print_source_tiers():
    """Print summary of source tiers for debugging."""
    print("\n" + "=" * 60)
    print("ZINC-FUSION NEWS SOURCE TIERS")
    print("=" * 60)

    print(f"\nTIER 1 (Critical - Always Claude): {len(TIER_1_CRITICAL)} sources")
    for s in sorted(TIER_1_CRITICAL):
        print(f"  - {s}")

    print(
        f"\nTIER 1.5 (Premium Twitter - Always Claude): {len(TIER_PREMIUM_TWITTER)} sources"
    )
    for s in sorted(TIER_PREMIUM_TWITTER):
        print(f"  - {s}")

    print(
        f"\nTIER 2 (High Value - Claude when budget allows): {len(TIER_2_HIGH_VALUE)} sources"
    )
    for s in sorted(TIER_2_HIGH_VALUE):
        print(f"  - {s}")

    print(f"\nTIER 3 (FinBERT only): {len(TIER_3_FINBERT_ONLY)} sources")
    for s in sorted(TIER_3_FINBERT_ONLY):
        print(f"  - {s}")

    print(f"\nTIER 4 (Noise - Skip): {len(TIER_4_NOISE)} sources")
    for s in sorted(TIER_4_NOISE):
        print(f"  - {s}")

    print(f"\nSPECIAL (Truth Social): {len(TRUTH_SOCIAL_SOURCES)} sources")


if __name__ == "__main__":
    print_source_tiers()
