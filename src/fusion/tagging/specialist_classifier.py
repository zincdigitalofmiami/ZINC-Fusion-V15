"""
Specialist Classifier - Single Source of Truth

This module provides the canonical text classification function for
mapping text content to Big-11 specialist buckets.

Usage:
    from fusion.tagging import classify_specialists

    tags = classify_specialists("China trade deal announced by Trump")
    # Returns: ["china", "tariff", "trump_effect"]

    tags = classify_specialists("USDA reports strong soybean crush margins")
    # Returns: ["crush"]

    tags = classify_specialists("Weather is nice today")
    # Returns: ["general"]

TypeScript Port: frontend/src/lib/specialist-classifier.ts
"""

from typing import List, Set

from .constants import DUAL_TAG_KEYWORDS, GENERAL_TAG
from .keywords import SPECIALIST_KEYWORDS


def classify_specialists(text: str) -> List[str]:
    """
    Classify text to Big-11 specialist buckets.

    Args:
        text: Input text to classify (title, headline, description, etc.)

    Returns:
        List of matched specialist bucket names.
        Returns ["general"] if no specialists match.

    Notes:
        - Keywords are matched case-insensitively via substring search
        - DUAL_TAG_KEYWORDS trigger both "tariff" and "trump_effect"
        - Each specialist is matched at most once (no duplicates)
        - Results are returned in arbitrary order (use sorted() if needed)
    """
    if not text:
        return [GENERAL_TAG]

    text_lower = text.lower()
    matched: Set[str] = set()

    # Check dual-tag keywords first (trade deals → both tariff + trump_effect)
    # Per RAW_SOURCE_SPECIALIST_MAPPING.md: trade agreements affect both buckets
    for kw in DUAL_TAG_KEYWORDS:
        if kw in text_lower:
            matched.add("tariff")
            matched.add("trump_effect")

    # Standard keyword matching - break on first match per specialist
    for specialist, keywords in SPECIALIST_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                matched.add(specialist)
                break  # Only match each specialist once

    return list(matched) if matched else [GENERAL_TAG]


def classify_specialists_with_scores(text: str) -> dict[str, int]:
    """
    Classify text and return match counts per specialist.

    Useful for debugging or weighted classification.

    Args:
        text: Input text to classify

    Returns:
        Dict mapping specialist name to number of keyword matches
    """
    if not text:
        return {}

    text_lower = text.lower()
    scores: dict[str, int] = {}

    for specialist, keywords in SPECIALIST_KEYWORDS.items():
        count = sum(1 for kw in keywords if kw in text_lower)
        if count > 0:
            scores[specialist] = count

    return scores


def validate_specialists(tags: List[str]) -> List[str]:
    """
    Validate and filter tags to only include valid Big-11 specialists.

    Args:
        tags: List of tag strings to validate

    Returns:
        Filtered list containing only valid specialist names + "general"
    """
    from .constants import BIG_11_SPECIALISTS

    valid = set(BIG_11_SPECIALISTS) | {GENERAL_TAG}
    return [t for t in tags if t in valid]
