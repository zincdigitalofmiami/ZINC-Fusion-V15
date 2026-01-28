#!/usr/bin/env python3
"""
ZINC-FUSION-V15: Tariff Deadline Feature Engineering

Provides feature engineering for tariff policy deadline tracking,
supporting the tariff specialist with time-sensitive policy risk signals.

Key Deadlines (as of Jan 2026):
- Nov 10, 2026: Section 301 reciprocal tariff suspension expires
- Dec 31, 2026: China agricultural tariff suspension expires

Features Generated:
1. days_to_section301_expiry - Days until Nov 10, 2026
2. days_to_china_ag_expiry - Days until Dec 31, 2026
3. deadline_risk_score - Sigmoid-based urgency signal (accelerates as deadline approaches)
4. deadline_vol_multiplier - Volatility adjustment factor based on deadline proximity

Usage:
    from src.fusion.features.tariff_deadlines import (
        TariffDeadlineFeatureEngine,
        calculate_deadline_risk_score,
        get_active_deadlines,
    )

    engine = TariffDeadlineFeatureEngine()
    features = engine.compute_features_for_date(datetime.date.today())
"""

import logging
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS
# =============================================================================

# Known policy deadlines (update as new deadlines are identified)
POLICY_DEADLINES = {
    "section_301_tariff_suspension": {
        "date": date(2026, 11, 10),
        "policy_type": "TRADE",
        "description": "US reciprocal tariffs on China suspended until this date",
        "impact_weight": 1.0,  # High impact
    },
    "china_ag_tariff_suspension": {
        "date": date(2026, 12, 31),
        "policy_type": "AGRICULTURE",
        "description": "China retaliatory tariffs on US agricultural products suspended",
        "impact_weight": 0.8,  # High impact but slightly less direct for ZL
    },
}

# Sigmoid parameters for deadline risk calculation
DEADLINE_RISK_MIDPOINT_DAYS = 90  # Risk score = 0.5 at 90 days out
DEADLINE_RISK_STEEPNESS = 30  # Controls sigmoid steepness


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class DeadlineInfo:
    """Information about a single policy deadline."""
    name: str
    deadline_date: date
    days_to_expiry: int
    policy_type: str
    description: str
    impact_weight: float
    risk_score: float  # 0-1 scale, accelerates as deadline approaches
    is_imminent: bool  # True if < 60 days


@dataclass
class TariffDeadlineFeatures:
    """Complete tariff deadline feature set for a given date."""
    as_of_date: date
    days_to_section301_expiry: int
    days_to_china_ag_expiry: int
    min_days_to_any_deadline: int
    deadline_risk_score: float  # Composite risk score (0-1)
    deadline_vol_multiplier: float  # Suggested vol adjustment (1.0-1.5)
    imminent_deadline_count: int  # Count of deadlines < 60 days out
    active_deadline_names: List[str]


# =============================================================================
# CORE CALCULATIONS
# =============================================================================

def calculate_deadline_risk_score(days_to_expiry: int) -> float:
    """
    Calculate deadline risk score using sigmoid function.

    Risk accelerates as deadline approaches:
    - At 180+ days: ~0.05 (low risk)
    - At 90 days: 0.5 (medium risk - inflection point)
    - At 30 days: ~0.88 (high risk)
    - At 0 days: ~0.95 (very high risk)

    Args:
        days_to_expiry: Days until policy deadline

    Returns:
        Risk score between 0 and 1
    """
    if days_to_expiry < 0:
        return 1.0  # Deadline passed

    # Sigmoid: 1 / (1 + exp((days - midpoint) / steepness))
    exponent = (days_to_expiry - DEADLINE_RISK_MIDPOINT_DAYS) / DEADLINE_RISK_STEEPNESS
    return 1.0 / (1.0 + math.exp(exponent))


def calculate_vol_multiplier(deadline_risk_score: float) -> float:
    """
    Calculate volatility multiplier based on deadline risk.

    Higher risk → higher expected volatility.

    Args:
        deadline_risk_score: Risk score from calculate_deadline_risk_score (0-1)

    Returns:
        Volatility multiplier (1.0 to 1.5)
    """
    # Linear mapping: risk 0 → mult 1.0, risk 1 → mult 1.5
    return 1.0 + (0.5 * deadline_risk_score)


def get_active_deadlines(as_of_date: date) -> List[DeadlineInfo]:
    """
    Get all active (future) policy deadlines.

    Args:
        as_of_date: Reference date for calculation

    Returns:
        List of DeadlineInfo for all future deadlines
    """
    active = []
    for name, info in POLICY_DEADLINES.items():
        deadline_date = info["date"]
        days_to_expiry = (deadline_date - as_of_date).days

        if days_to_expiry >= 0:  # Only future deadlines
            risk_score = calculate_deadline_risk_score(days_to_expiry)
            active.append(DeadlineInfo(
                name=name,
                deadline_date=deadline_date,
                days_to_expiry=days_to_expiry,
                policy_type=info["policy_type"],
                description=info["description"],
                impact_weight=info["impact_weight"],
                risk_score=risk_score,
                is_imminent=(days_to_expiry < 60),
            ))

    return sorted(active, key=lambda x: x.days_to_expiry)


# =============================================================================
# FEATURE ENGINE
# =============================================================================

class TariffDeadlineFeatureEngine:
    """
    Engine for computing tariff deadline features.

    Features are designed to integrate with the tariff specialist signal generator.
    """

    def __init__(self, db_connection=None):
        """
        Initialize the feature engine.

        Args:
            db_connection: Optional database connection for loading dynamic deadlines.
                          If not provided, uses hardcoded POLICY_DEADLINES.
        """
        self.db_connection = db_connection
        self._deadline_cache: Optional[List[DeadlineInfo]] = None

    def _load_deadlines_from_db(self, as_of_date: date) -> List[DeadlineInfo]:
        """Load deadlines from alt.tariff_deadlines table if available."""
        if self.db_connection is None:
            return []

        try:
            import psycopg2
            cursor = self.db_connection.cursor()
            cursor.execute("""
                SELECT deadline_name, deadline_date, days_to_expiry,
                       policy_type, description, renewal_probability
                FROM alt.tariff_deadlines
                WHERE is_active = true AND deadline_date >= %s
                ORDER BY deadline_date
            """, (as_of_date,))

            rows = cursor.fetchall()
            deadlines = []
            for row in rows:
                deadline_date = row[1] if isinstance(row[1], date) else row[1].date()
                days_to_expiry = (deadline_date - as_of_date).days
                risk_score = calculate_deadline_risk_score(days_to_expiry)

                deadlines.append(DeadlineInfo(
                    name=row[0],
                    deadline_date=deadline_date,
                    days_to_expiry=days_to_expiry,
                    policy_type=row[3] or "TRADE",
                    description=row[4] or "",
                    impact_weight=1.0,  # Could be enhanced with renewal_probability
                    risk_score=risk_score,
                    is_imminent=(days_to_expiry < 60),
                ))

            cursor.close()
            return deadlines
        except Exception as e:
            logger.warning(f"Failed to load deadlines from DB: {e}")
            return []

    def get_deadlines(self, as_of_date: date) -> List[DeadlineInfo]:
        """
        Get all active deadlines, preferring DB if available.

        Args:
            as_of_date: Reference date for calculation

        Returns:
            List of DeadlineInfo
        """
        # Try DB first
        db_deadlines = self._load_deadlines_from_db(as_of_date)
        if db_deadlines:
            return db_deadlines

        # Fall back to hardcoded deadlines
        return get_active_deadlines(as_of_date)

    def compute_features_for_date(self, as_of_date: date) -> TariffDeadlineFeatures:
        """
        Compute all tariff deadline features for a given date.

        Args:
            as_of_date: Date to compute features for

        Returns:
            TariffDeadlineFeatures dataclass with all features
        """
        deadlines = self.get_deadlines(as_of_date)

        if not deadlines:
            # No active deadlines - return neutral features
            return TariffDeadlineFeatures(
                as_of_date=as_of_date,
                days_to_section301_expiry=365,
                days_to_china_ag_expiry=365,
                min_days_to_any_deadline=365,
                deadline_risk_score=0.0,
                deadline_vol_multiplier=1.0,
                imminent_deadline_count=0,
                active_deadline_names=[],
            )

        # Find specific deadlines
        section301_deadline = next(
            (d for d in deadlines if "section_301" in d.name.lower() or "301" in d.name),
            None
        )
        china_ag_deadline = next(
            (d for d in deadlines if "china" in d.name.lower() and "ag" in d.name.lower()),
            None
        )

        days_to_section301 = section301_deadline.days_to_expiry if section301_deadline else 365
        days_to_china_ag = china_ag_deadline.days_to_expiry if china_ag_deadline else 365

        # Composite risk score (weighted average)
        total_weight = sum(d.impact_weight for d in deadlines)
        if total_weight > 0:
            composite_risk = sum(
                d.risk_score * d.impact_weight for d in deadlines
            ) / total_weight
        else:
            composite_risk = 0.0

        return TariffDeadlineFeatures(
            as_of_date=as_of_date,
            days_to_section301_expiry=days_to_section301,
            days_to_china_ag_expiry=days_to_china_ag,
            min_days_to_any_deadline=min(d.days_to_expiry for d in deadlines),
            deadline_risk_score=round(composite_risk, 4),
            deadline_vol_multiplier=round(calculate_vol_multiplier(composite_risk), 4),
            imminent_deadline_count=sum(1 for d in deadlines if d.is_imminent),
            active_deadline_names=[d.name for d in deadlines],
        )

    def compute_features_for_range(
        self,
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        """
        Compute features for a date range.

        Args:
            start_date: Start of range (inclusive)
            end_date: End of range (inclusive)

        Returns:
            DataFrame with one row per date
        """
        records = []
        current = start_date
        while current <= end_date:
            features = self.compute_features_for_date(current)
            records.append({
                "trade_date": features.as_of_date,
                "days_to_section301_expiry": features.days_to_section301_expiry,
                "days_to_china_ag_expiry": features.days_to_china_ag_expiry,
                "min_days_to_any_deadline": features.min_days_to_any_deadline,
                "deadline_risk_score": features.deadline_risk_score,
                "deadline_vol_multiplier": features.deadline_vol_multiplier,
                "imminent_deadline_count": features.imminent_deadline_count,
            })
            current += timedelta(days=1)

        return pd.DataFrame(records)


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def get_current_deadline_features() -> TariffDeadlineFeatures:
    """Get deadline features for today."""
    engine = TariffDeadlineFeatureEngine()
    return engine.compute_features_for_date(date.today())


def get_deadline_risk_for_date(as_of_date: date) -> float:
    """Get composite deadline risk score for a specific date."""
    engine = TariffDeadlineFeatureEngine()
    features = engine.compute_features_for_date(as_of_date)
    return features.deadline_risk_score


if __name__ == "__main__":
    # Quick test
    logging.basicConfig(level=logging.INFO)

    engine = TariffDeadlineFeatureEngine()
    today_features = engine.compute_features_for_date(date.today())

    print(f"\n=== Tariff Deadline Features ({date.today()}) ===")
    print(f"Days to Section 301 expiry: {today_features.days_to_section301_expiry}")
    print(f"Days to China Ag expiry: {today_features.days_to_china_ag_expiry}")
    print(f"Min days to any deadline: {today_features.min_days_to_any_deadline}")
    print(f"Deadline risk score: {today_features.deadline_risk_score:.4f}")
    print(f"Vol multiplier: {today_features.deadline_vol_multiplier:.4f}")
    print(f"Imminent deadline count: {today_features.imminent_deadline_count}")
    print(f"Active deadlines: {today_features.active_deadline_names}")

    # Show risk curve
    print("\n=== Risk Score Curve ===")
    for days in [365, 180, 120, 90, 60, 30, 14, 7, 0]:
        risk = calculate_deadline_risk_score(days)
        print(f"  {days:3d} days → risk {risk:.3f}")
