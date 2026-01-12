"""
ZINC-FUSION-V15 HUNTERS
========================

Hunters find the 22.

They don't just report data (2+2=4).
They discover patterns, anomalies, and signals that others miss (2+2=22).

Each Hunter:
1. Ingests domain-specific data
2. Compares against historical baselines
3. Detects anomalies and deviations
4. Finds lead-lag correlations
5. Discovers emerging signals
6. Outputs DISCOVERIES - not observations

The AI then synthesizes these discoveries into actionable intelligence.
"""

from .base import Hunter, Discovery, HuntResult
from .crush import CrushHunter

__all__ = [
    'Hunter',
    'Discovery', 
    'HuntResult',
    'CrushHunter',
]
