"""
Forward Fill Configuration - ZINC-FUSION-V15

This module defines TTL (time-to-live) thresholds for forward-filled data
according to the Forward Fill Policy (Docs/FORWARD_FILL_POLICY.md).

TTL Guidelines by Cadence:
- Daily series: 3-5 days (ETL tolerance)
- Weekly: 10-14 days
- Monthly: 45-60 days
- Quarterly: 120-150 days

Weekend/holiday carve-out: Standard market closures don't count toward TTL
for market-aligned series (prices, volumes).
"""

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class SourceConfig:
    """Configuration for a data source's forward-fill behavior."""

    # Source identifier (table or series name)
    source: str

    # Native cadence: 'daily', 'weekly', 'monthly', 'quarterly'
    cadence: str

    # Maximum TTL in calendar days (None = no forward fill allowed)
    ttl_days: Optional[int]

    # Whether to use event encoding instead of level forward-fill
    use_event_encoding: bool = False

    # Whether weekend/holiday gaps are exempt from TTL
    market_aligned: bool = False

    # Critical for specialist signals (fail-hard if stale)
    is_critical: bool = False

    # Description for documentation
    description: str = ""


# =============================================================================
# TTL Configuration by Data Source
# =============================================================================

# FRED Economic Data (econ.* tables)
FRED_CONFIG: Dict[str, SourceConfig] = {
    # Daily rates - tight TTL
    "DGS2": SourceConfig("DGS2", "daily", 5, market_aligned=True, is_critical=True,
                         description="2-Year Treasury Constant Maturity Rate"),
    "DGS10": SourceConfig("DGS10", "daily", 5, market_aligned=True, is_critical=True,
                          description="10-Year Treasury Constant Maturity Rate"),
    "DFF": SourceConfig("DFF", "daily", 5, market_aligned=True, is_critical=True,
                        description="Federal Funds Effective Rate"),
    "SOFR": SourceConfig("SOFR", "daily", 5, market_aligned=True, is_critical=True,
                         description="Secured Overnight Financing Rate"),
    "T10Y2Y": SourceConfig("T10Y2Y", "daily", 5, market_aligned=True, is_critical=True,
                           description="10Y-2Y Treasury Spread"),

    # Daily volatility indices - tight TTL
    "VIXCLS": SourceConfig("VIXCLS", "daily", 5, market_aligned=True, is_critical=True,
                           description="CBOE VIX Close"),
    "OVXCLS": SourceConfig("OVXCLS", "daily", 5, market_aligned=True, is_critical=True,
                           description="CBOE Crude Oil VIX"),

    # Daily FX - tight TTL
    "DEXBZUS": SourceConfig("DEXBZUS", "daily", 5, market_aligned=True, is_critical=True,
                            description="Brazil/US FX Rate"),
    "DEXCHUS": SourceConfig("DEXCHUS", "daily", 5, market_aligned=True, is_critical=True,
                            description="China/US FX Rate"),
    "DEXMXUS": SourceConfig("DEXMXUS", "daily", 5, market_aligned=True, is_critical=True,
                            description="Mexico/US FX Rate"),
    "DTWEXBGS": SourceConfig("DTWEXBGS", "daily", 5, market_aligned=True, is_critical=True,
                             description="Trade Weighted US Dollar Index"),

    # Weekly series - moderate TTL
    "ICSA": SourceConfig("ICSA", "weekly", 14, use_event_encoding=True,
                         description="Initial Claims"),

    # Monthly series - use event encoding, not level ffill
    "CPIAUCSL": SourceConfig("CPIAUCSL", "monthly", None, use_event_encoding=True,
                             is_critical=True, description="CPI All Urban Consumers"),
    "PPIACO": SourceConfig("PPIACO", "monthly", None, use_event_encoding=True,
                           description="Producer Price Index All Commodities"),
    "UNRATE": SourceConfig("UNRATE", "monthly", None, use_event_encoding=True,
                           description="Unemployment Rate"),
    "PAYEMS": SourceConfig("PAYEMS", "monthly", None, use_event_encoding=True,
                           description="Nonfarm Payrolls"),
    "M2SL": SourceConfig("M2SL", "monthly", 60, use_event_encoding=True,
                         description="M2 Money Stock"),

    # Monthly EPU indices - event encoding
    "USEPUINDXD": SourceConfig("USEPUINDXD", "daily", 5, is_critical=True,
                               description="US Economic Policy Uncertainty Daily"),
    "USEPUINDXM": SourceConfig("USEPUINDXM", "monthly", None, use_event_encoding=True,
                               description="US Economic Policy Uncertainty Monthly"),
    "EPUTRADE": SourceConfig("EPUTRADE", "monthly", None, use_event_encoding=True,
                             description="Trade Policy Uncertainty"),
}


# CFTC Positioning (pos.* tables)
CFTC_CONFIG: Dict[str, SourceConfig] = {
    "cftc_1w": SourceConfig("pos.cftc_1w", "weekly", 14, use_event_encoding=True,
                            is_critical=True, description="CFTC Commitment of Traders"),
}


# USDA Supply Data (supply.* tables)
USDA_CONFIG: Dict[str, SourceConfig] = {
    "wasde_1m": SourceConfig("supply.usda_wasde_1m", "monthly", None,
                             use_event_encoding=True, is_critical=True,
                             description="WASDE Monthly Report"),
    "usda_exports_1w": SourceConfig("supply.usda_exports_1w", "weekly", 21,
                                    use_event_encoding=True,
                                    description="USDA Export Sales Weekly"),
}


# EPA/Biofuel Data (supply.* tables)
BIOFUEL_CONFIG: Dict[str, SourceConfig] = {
    "epa_rin_1d": SourceConfig("supply.epa_rin_1d", "daily", 14, is_critical=True,
                               description="EPA RIN Prices"),
    "lcfs_1d": SourceConfig("supply.lcfs_1d", "weekly", 21, is_critical=True,
                            description="California LCFS Credits"),
}


# Market Data (mkt.* tables) - NO forward fill for prices
MARKET_CONFIG: Dict[str, SourceConfig] = {
    "futures_1d": SourceConfig("mkt.futures_1d", "daily", None, market_aligned=True,
                               is_critical=True, description="Daily Futures - NO FFILL"),
    "etf_1d": SourceConfig("mkt.etf_1d", "daily", None, market_aligned=True,
                           is_critical=True, description="Daily ETFs - NO FFILL"),
    "options_1d": SourceConfig("mkt.options_1d", "daily", None, market_aligned=True,
                               description="Daily Options - NO FFILL"),
    "fx_1d": SourceConfig("mkt.fx_1d", "daily", None, market_aligned=True,
                          is_critical=True, description="Daily FX - NO FFILL"),
}


# PMI / Activity Data
PMI_CONFIG: Dict[str, SourceConfig] = {
    "cn_caixin_pmi": SourceConfig("cn_caixin_pmi", "monthly", 60, use_event_encoding=True,
                                  is_critical=True, description="China Caixin Manufacturing PMI"),
    "us_ism_pmi": SourceConfig("us_ism_pmi", "monthly", 60, use_event_encoding=True,
                               description="US ISM Manufacturing PMI"),
}


# =============================================================================
# Specialist-Level Configuration
# =============================================================================

@dataclass(frozen=True)
class SpecialistConfig:
    """Configuration for a specialist's critical inputs and staleness thresholds."""

    bucket: str
    critical_sources: tuple  # Sources that must be fresh
    max_staleness_days: int  # Overall max staleness for the specialist
    strict_mode: bool = True  # Fail-hard if any critical source is stale


SPECIALIST_CONFIGS: Dict[str, SpecialistConfig] = {
    "crush": SpecialistConfig(
        bucket="crush",
        critical_sources=("mkt.futures_1d", "pos.cftc_1w"),
        max_staleness_days=14,
        strict_mode=True,
    ),
    "china": SpecialistConfig(
        bucket="china",
        critical_sources=("mkt.futures_1d", "mkt.fx_1d", "cn_caixin_pmi"),
        max_staleness_days=60,
        strict_mode=True,
    ),
    "fx": SpecialistConfig(
        bucket="fx",
        critical_sources=("mkt.fx_1d", "DTWEXBGS", "DGS2", "DGS10"),
        max_staleness_days=5,
        strict_mode=True,
    ),
    "fed": SpecialistConfig(
        bucket="fed",
        critical_sources=("DFF", "DGS2", "DGS10", "T10Y2Y", "SOFR"),
        max_staleness_days=5,
        strict_mode=True,
    ),
    "volatility": SpecialistConfig(
        bucket="volatility",
        critical_sources=("VIXCLS", "OVXCLS"),
        max_staleness_days=5,
        strict_mode=True,
    ),
    "energy": SpecialistConfig(
        bucket="energy",
        critical_sources=("mkt.futures_1d",),  # CL, HO, RB
        max_staleness_days=5,
        strict_mode=True,
    ),
    "palm": SpecialistConfig(
        bucket="palm",
        critical_sources=("mkt.futures_1d",),  # FCPO
        max_staleness_days=7,
        strict_mode=True,
    ),
    "tariff": SpecialistConfig(
        bucket="tariff",
        critical_sources=("USEPUINDXD", "EPUTRADE"),
        max_staleness_days=60,
        strict_mode=False,  # Event-driven, can tolerate some staleness
    ),
    "biofuel": SpecialistConfig(
        bucket="biofuel",
        critical_sources=("supply.epa_rin_1d", "supply.lcfs_1d"),
        max_staleness_days=14,
        strict_mode=True,
    ),
    "substitutes": SpecialistConfig(
        bucket="substitutes",
        critical_sources=("mkt.futures_1d",),  # Canola, palm, sunflower futures
        max_staleness_days=7,
        strict_mode=True,
    ),
    "trump_effect": SpecialistConfig(
        bucket="trump_effect",
        critical_sources=("USEPUINDXD", "VIXCLS"),
        max_staleness_days=14,
        strict_mode=False,  # Event-driven
    ),
}


# =============================================================================
# Helper Functions
# =============================================================================

def get_ttl_days(source: str) -> Optional[int]:
    """Get TTL in days for a source. Returns None if forward fill not allowed."""
    # Check each config dict
    for config_dict in [FRED_CONFIG, CFTC_CONFIG, USDA_CONFIG, BIOFUEL_CONFIG,
                        MARKET_CONFIG, PMI_CONFIG]:
        if source in config_dict:
            return config_dict[source].ttl_days
    return None


def get_source_config(source: str) -> Optional[SourceConfig]:
    """Get full configuration for a source."""
    for config_dict in [FRED_CONFIG, CFTC_CONFIG, USDA_CONFIG, BIOFUEL_CONFIG,
                        MARKET_CONFIG, PMI_CONFIG]:
        if source in config_dict:
            return config_dict[source]
    return None


def should_use_event_encoding(source: str) -> bool:
    """Check if source should use event encoding instead of level ffill."""
    config = get_source_config(source)
    return config.use_event_encoding if config else False


def get_specialist_config(bucket: str) -> Optional[SpecialistConfig]:
    """Get specialist configuration by bucket name."""
    return SPECIALIST_CONFIGS.get(bucket)


def validate_staleness(source: str, age_days: int) -> bool:
    """
    Validate if data is fresh enough according to TTL policy.

    Returns True if data is acceptable, False if stale.
    """
    config = get_source_config(source)
    if config is None:
        # Unknown source - be conservative, require freshness
        return age_days <= 5

    if config.ttl_days is None:
        # No forward fill allowed - must have real data
        return age_days == 0

    return age_days <= config.ttl_days


# =============================================================================
# TTL Summary Table (for documentation)
# =============================================================================

TTL_SUMMARY = """
Forward Fill TTL Summary
========================

| Cadence   | Default TTL | Use Event Encoding |
|-----------|-------------|-------------------|
| Daily     | 3-5 days    | No                |
| Weekly    | 10-14 days  | Yes (recommended) |
| Monthly   | None (event)| Yes (required)    |
| Quarterly | None (event)| Yes (required)    |

Market Data: NO forward fill allowed (prices, spreads, vol)
FRED Daily: 5 day TTL with market-aligned carve-out
CFTC Weekly: 14 day TTL with event encoding
WASDE Monthly: Event encoding only, no level ffill
"""
