"""
AI-Powered Data Ingestion System
================================
Intelligent ingestion with automatic specialist bucket routing.

This module provides:
1. AI-powered classification of data sources to specialist buckets
2. Automatic routing to the correct training tables
3. News/sentiment analysis with NLP classification
4. Data quality validation and enrichment
"""

from .router import SpecialistRouter, DataRouter

# Optional modules: keep package importable even if experimental components
# are not present in the workspace.
try:
    from .sources import (  # type: ignore
        FREDIngestionSource,
        CFTCIngestionSource,
        WeatherIngestionSource,
        EIAIngestionSource,
        USDAIngestionSource,
        NewsIngestionSource,
    )
except ModuleNotFoundError:  # pragma: no cover
    FREDIngestionSource = None  # type: ignore
    CFTCIngestionSource = None  # type: ignore
    WeatherIngestionSource = None  # type: ignore
    EIAIngestionSource = None  # type: ignore
    USDAIngestionSource = None  # type: ignore
    NewsIngestionSource = None  # type: ignore

# Optional modules: keep package importable even if experimental components
# are not present in the workspace.
try:
    from .classifier import BucketClassifier, NewsClassifier  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    BucketClassifier = None  # type: ignore
    NewsClassifier = None  # type: ignore

__all__ = [
    "SpecialistRouter",
    "DataRouter",
]

if BucketClassifier is not None:
    __all__.append("BucketClassifier")
if NewsClassifier is not None:
    __all__.append("NewsClassifier")

if FREDIngestionSource is not None:
    __all__.append("FREDIngestionSource")
if CFTCIngestionSource is not None:
    __all__.append("CFTCIngestionSource")
if WeatherIngestionSource is not None:
    __all__.append("WeatherIngestionSource")
if EIAIngestionSource is not None:
    __all__.append("EIAIngestionSource")
if USDAIngestionSource is not None:
    __all__.append("USDAIngestionSource")
if NewsIngestionSource is not None:
    __all__.append("NewsIngestionSource")
