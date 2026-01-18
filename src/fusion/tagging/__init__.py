"""
Specialist Tagging Module - Single Source of Truth

This module consolidates all Big-11 specialist tagging logic.
Use this module for all text classification to specialist buckets.

Usage:
    from fusion.tagging import classify_specialists, BIG_11_SPECIALISTS

    tags = classify_specialists("China trade deal announced")
    # Returns: ["china", "tariff", "trump_effect"]
"""

from .constants import BIG_11_SPECIALISTS, DUAL_TAG_KEYWORDS
from .keywords import SPECIALIST_KEYWORDS
from .specialist_classifier import classify_specialists

__all__ = [
    "BIG_11_SPECIALISTS",
    "DUAL_TAG_KEYWORDS",
    "SPECIALIST_KEYWORDS",
    "classify_specialists",
]
