"""
Configuration module for ZINC-FUSION-V15.

Contains centralized configuration for:
- Forward fill policy (TTL thresholds, event encoding rules)
- Specialist configurations (critical sources, staleness limits)
"""

from .forward_fill_config import (
    SourceConfig,
    SpecialistConfig,
    FRED_CONFIG,
    CFTC_CONFIG,
    USDA_CONFIG,
    BIOFUEL_CONFIG,
    MARKET_CONFIG,
    PMI_CONFIG,
    SPECIALIST_CONFIGS,
    get_ttl_days,
    get_source_config,
    should_use_event_encoding,
    get_specialist_config,
    validate_staleness,
)

__all__ = [
    "SourceConfig",
    "SpecialistConfig",
    "FRED_CONFIG",
    "CFTC_CONFIG",
    "USDA_CONFIG",
    "BIOFUEL_CONFIG",
    "MARKET_CONFIG",
    "PMI_CONFIG",
    "SPECIALIST_CONFIGS",
    "get_ttl_days",
    "get_source_config",
    "should_use_event_encoding",
    "get_specialist_config",
    "validate_staleness",
]
