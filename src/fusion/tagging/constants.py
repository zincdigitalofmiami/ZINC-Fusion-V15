"""
Big-11 Specialist Constants - Single Source of Truth

These constants define the canonical specialist buckets for ZINC-FUSION-V15.
Any changes to this list require coordination across Python and TypeScript.

Reference: Docs/RAW_SOURCE_SPECIALIST_MAPPING.md (LOCKED)
"""

from typing import Tuple

# Canonical Big-11 Specialists
# Order matches src/fusion/taxonomy.py and src/fusion/ingestion/router.py
BIG_11_SPECIALISTS: Tuple[str, ...] = (
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
)

# Keywords that trigger BOTH tariff AND trump_effect
# Per RAW_SOURCE_SPECIALIST_MAPPING.md lines 27-40:
# - Trade deals/agreements affect both trade policy (tariff) and regime uncertainty (trump_effect)
# - Phase One deal, China-specific tariff actions are dual-tagged
DUAL_TAG_KEYWORDS: Tuple[str, ...] = (
    "trade deal",
    "trade agreement",
    "trade negotiation",
    "phase one",
    "phase 1",
    "china tariff",
    "tariff negotiation",
    "trade talks",
)

# Fallback tag when no specialists match
GENERAL_TAG = "general"
