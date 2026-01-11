"""
ZINC-FUSION-V15: Crowd Beliefs Feature Engineering

Extracts behavioral signals from Polymarket prediction markets for specialist training.
Forward-looking complement to backward-looking EPU indices.

Academic Foundation:
- Prediction markets aggregate dispersed information efficiently (NBER/Brookings)
- Favourite/longshot bias: high-likelihood events underpriced
- Probability momentum more predictive than levels (Wiley commodity sentiment study)
- 10-month lookback window optimal for sentiment signals

Cross-Specialist Routing:
- trump_effect: trump, executive, doge, deportation
- china: china, taiwan, trade_war
- tariff: tariff, import, trade
- biofuel: rfs, ethanol, epa, mandate
- energy: oil, sanctions, opec
- fed: fed, rates, inflation, recession
- volatility: vix, crash, crisis

Usage:
    from src.fusion.features.crowd_beliefs import CrowdBeliefsFeatureEngine

    engine = CrowdBeliefsFeatureEngine(conn)
    features = engine.compute_features(
        specialist='trump_effect',
        start_date='2025-01-01',
        end_date='2026-01-10'
    )
"""

import logging
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

import numpy as np
import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

# Event categories mapped to specialists
CATEGORY_SPECIALIST_MAP = {
    'tariff': ['tariff', 'trump_effect', 'china'],
    'china': ['china', 'trump_effect'],
    'taiwan': ['china', 'volatility'],
    'trump': ['trump_effect'],
    'doge': ['trump_effect', 'fed'],
    'executive': ['trump_effect'],
    'deportation': ['trump_effect'],
    'immigration': ['trump_effect'],
    'fed': ['fed', 'volatility'],
    'rates': ['fed'],
    'inflation': ['fed', 'energy'],
    'recession': ['fed', 'volatility'],
    'biofuel': ['biofuel'],
    'energy': ['energy'],
    'volatility': ['volatility'],
    'trade': ['tariff', 'china'],
    'deficit': ['fed', 'trump_effect'],
}

# Key event slugs to track (high signal-to-noise)
KEY_EVENT_SLUGS = {
    'trump_effect': [
        'tariff-revenue',
        'trump-deport',
        'doge-cut',
        'trump-executive',
    ],
    'china': [
        'china-taiwan',
        'china-tariff',
        'china-trade',
    ],
    'tariff': [
        'tariff-revenue',
        'tariff-rate',
    ],
    'biofuel': [
        'rfs-mandate',
        'ethanol-policy',
        'epa-waiver',
    ],
    'fed': [
        'fed-rate',
        'recession',
        'inflation-target',
    ],
    'volatility': [
        'market-crash',
        'vix-spike',
        'recession',
    ],
}


@dataclass
class CrowdBeliefSnapshot:
    """Single point-in-time crowd belief state."""
    as_of_date: date
    event_slug: str
    outcome_question: str
    implied_prob_yes: float
    attention_index_24h: float
    attention_index_7d: float
    prob_momentum_24h: Optional[float]
    prob_momentum_7d: Optional[float]
    consensus_strength: float
    days_to_resolution: Optional[int]
    specialist_tags: List[str]


# =============================================================================
# FEATURE ENGINE
# =============================================================================

class CrowdBeliefsFeatureEngine:
    """
    Extracts behavioral features from Polymarket crowd beliefs.

    Features extracted per specialist:
    - Probability levels (current belief state)
    - Momentum signals (rate of change in beliefs)
    - Attention signals (betting activity spikes)
    - Consensus signals (crowd agreement level)
    - Time decay (urgency as resolution approaches)

    Academic notes:
    - Momentum more predictive than levels (Wiley study)
    - Attention spikes indicate news/events
    - Calibration degrades far from resolution date
    """

    def __init__(self, conn: psycopg2.extensions.connection):
        """
        Initialize with PostgreSQL connection.

        Args:
            conn: psycopg2 connection to fusion database
        """
        self.conn = conn

    def _load_beliefs(
        self,
        specialist: str,
        start_date: date,
        end_date: date
    ) -> pd.DataFrame:
        """
        Load crowd beliefs tagged to a specific specialist.

        Args:
            specialist: Specialist bucket name (e.g., 'trump_effect')
            start_date: Start of date range
            end_date: End of date range

        Returns:
            DataFrame with raw belief data
        """
        query = """
        SELECT
            DATE(captured_at) AS as_of_date,
            event_slug,
            outcome_question,
            implied_prob_yes,
            implied_prob_no,
            attention_index_24h,
            attention_index_7d,
            prob_momentum_24h,
            prob_momentum_7d,
            consensus_strength,
            event_category,
            specialist_tags,
            days_to_resolution,
            event_resolution_date,
            raw_betting_volume_usd,
            raw_liquidity_usd
        FROM raw.crowd_beliefs_event
        WHERE %s = ANY(specialist_tags)
          AND DATE(captured_at) BETWEEN %s AND %s
        ORDER BY captured_at
        """

        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, (specialist, start_date, end_date))
            rows = cur.fetchall()

        if not rows:
            logger.warning(f"No crowd beliefs found for {specialist} in date range")
            return pd.DataFrame()

        return pd.DataFrame(rows)

    def _compute_probability_features(
        self,
        df: pd.DataFrame,
        specialist: str
    ) -> pd.DataFrame:
        """
        Compute probability-based features.

        Features:
        - prob_max_yes: Highest belief for negative outcome
        - prob_avg_yes: Average belief across tracked events
        - prob_weighted_avg: Volume-weighted average belief
        """
        if df.empty:
            return pd.DataFrame()

        features = df.groupby('as_of_date').agg({
            'implied_prob_yes': ['max', 'mean', 'std'],
            'implied_prob_no': ['max', 'mean'],
        }).reset_index()

        # Flatten column names
        features.columns = [
            'as_of_date',
            f'{specialist}_prob_max_yes',
            f'{specialist}_prob_avg_yes',
            f'{specialist}_prob_std_yes',
            f'{specialist}_prob_max_no',
            f'{specialist}_prob_avg_no',
        ]

        return features

    def _compute_momentum_features(
        self,
        df: pd.DataFrame,
        specialist: str
    ) -> pd.DataFrame:
        """
        Compute momentum-based features (rate of change in beliefs).

        Research: Momentum more predictive than levels (Wiley study)

        Features:
        - momentum_24h_max: Largest 24h shift
        - momentum_7d_avg: Average 7d shift
        - momentum_direction: Net directional shift
        """
        if df.empty:
            return pd.DataFrame()

        # Filter out nulls for momentum
        mom_df = df.dropna(subset=['prob_momentum_24h', 'prob_momentum_7d'])

        if mom_df.empty:
            return pd.DataFrame()

        features = mom_df.groupby('as_of_date').agg({
            'prob_momentum_24h': ['max', 'min', 'mean'],
            'prob_momentum_7d': ['max', 'min', 'mean'],
        }).reset_index()

        features.columns = [
            'as_of_date',
            f'{specialist}_momentum_24h_max',
            f'{specialist}_momentum_24h_min',
            f'{specialist}_momentum_24h_avg',
            f'{specialist}_momentum_7d_max',
            f'{specialist}_momentum_7d_min',
            f'{specialist}_momentum_7d_avg',
        ]

        # Add directional signal
        features[f'{specialist}_momentum_direction'] = np.sign(
            features[f'{specialist}_momentum_7d_avg']
        )

        return features

    def _compute_attention_features(
        self,
        df: pd.DataFrame,
        specialist: str
    ) -> pd.DataFrame:
        """
        Compute attention-based features (event detection).

        Research: Attention spikes indicate news/events

        Features:
        - attention_spike: Max attention across events
        - attention_avg: Average attention level
        - attention_divergence: Attention change without prob change
        """
        if df.empty:
            return pd.DataFrame()

        features = df.groupby('as_of_date').agg({
            'attention_index_24h': ['max', 'mean'],
            'attention_index_7d': ['max', 'mean'],
        }).reset_index()

        features.columns = [
            'as_of_date',
            f'{specialist}_attention_spike_24h',
            f'{specialist}_attention_avg_24h',
            f'{specialist}_attention_spike_7d',
            f'{specialist}_attention_avg_7d',
        ]

        # Attention divergence: high attention but low momentum = noise
        # (This would need momentum data, so compute it separately)

        return features

    def _compute_consensus_features(
        self,
        df: pd.DataFrame,
        specialist: str
    ) -> pd.DataFrame:
        """
        Compute consensus-based features (crowd uncertainty).

        Features:
        - consensus_avg: Average consensus strength
        - consensus_min: Minimum (most uncertain) consensus
        - crowd_uncertainty: 1 - consensus (higher = more uncertain)
        """
        if df.empty:
            return pd.DataFrame()

        features = df.groupby('as_of_date').agg({
            'consensus_strength': ['mean', 'min', 'max'],
        }).reset_index()

        features.columns = [
            'as_of_date',
            f'{specialist}_consensus_avg',
            f'{specialist}_consensus_min',
            f'{specialist}_consensus_max',
        ]

        # Crowd uncertainty is inverse of consensus
        features[f'{specialist}_crowd_uncertainty'] = (
            1 - features[f'{specialist}_consensus_avg']
        )

        return features

    def _compute_urgency_features(
        self,
        df: pd.DataFrame,
        specialist: str
    ) -> pd.DataFrame:
        """
        Compute time-decay / urgency features.

        Research: Calibration degrades far from resolution date

        Features:
        - resolution_urgency: 1/sqrt(days) - more weight as event approaches
        - near_term_events: Count of events resolving within 30 days
        """
        if df.empty:
            return pd.DataFrame()

        # Filter for events with resolution dates
        res_df = df.dropna(subset=['days_to_resolution'])

        if res_df.empty:
            return pd.DataFrame()

        # Add urgency score
        res_df = res_df.copy()
        res_df['urgency'] = 1 / np.sqrt(res_df['days_to_resolution'].clip(lower=1))

        features = res_df.groupby('as_of_date').agg({
            'urgency': ['max', 'mean'],
            'days_to_resolution': [
                'min',  # Nearest resolution
                lambda x: (x <= 30).sum(),  # Count near-term
            ],
        }).reset_index()

        features.columns = [
            'as_of_date',
            f'{specialist}_urgency_max',
            f'{specialist}_urgency_avg',
            f'{specialist}_nearest_resolution_days',
            f'{specialist}_near_term_event_count',
        ]

        return features

    def compute_features(
        self,
        specialist: str,
        start_date: date,
        end_date: date
    ) -> pd.DataFrame:
        """
        Compute all crowd belief features for a specialist.

        Args:
            specialist: Specialist bucket name (e.g., 'trump_effect')
            start_date: Start of date range
            end_date: End of date range

        Returns:
            DataFrame with all features indexed by as_of_date
        """
        logger.info(f"Computing crowd belief features for {specialist}")

        # Load raw beliefs
        df = self._load_beliefs(specialist, start_date, end_date)

        if df.empty:
            logger.warning(f"No crowd beliefs data for {specialist}")
            return pd.DataFrame()

        # Compute feature groups
        prob_features = self._compute_probability_features(df, specialist)
        momentum_features = self._compute_momentum_features(df, specialist)
        attention_features = self._compute_attention_features(df, specialist)
        consensus_features = self._compute_consensus_features(df, specialist)
        urgency_features = self._compute_urgency_features(df, specialist)

        # Merge all features
        result = prob_features

        for feature_df in [momentum_features, attention_features,
                          consensus_features, urgency_features]:
            if not feature_df.empty:
                result = result.merge(feature_df, on='as_of_date', how='left')

        logger.info(
            f"Generated {len(result.columns)-1} crowd belief features "
            f"for {specialist} across {len(result)} dates"
        )

        return result

    def compute_composite_signal(
        self,
        specialist: str,
        as_of_date: date
    ) -> Dict[str, float]:
        """
        Compute composite behavioral signal for a single date.

        Used for real-time inference and dashboard display.

        Returns:
            Dict with composite signals:
            - crowd_uncertainty: 0-1 (high = uncertain)
            - momentum_signal: -1 to +1 (directional)
            - attention_alert: bool (spike detected)
            - urgency_weight: 0-1 (high = near-term events)
        """
        # Fetch latest beliefs for this specialist
        df = self._load_beliefs(
            specialist,
            as_of_date - timedelta(days=1),
            as_of_date
        )

        if df.empty:
            return {
                'crowd_uncertainty': 0.5,
                'momentum_signal': 0.0,
                'attention_alert': False,
                'urgency_weight': 0.0,
            }

        latest = df[df['as_of_date'] == as_of_date]
        if latest.empty:
            latest = df.iloc[-1:]

        return {
            'crowd_uncertainty': 1 - latest['consensus_strength'].mean(),
            'momentum_signal': np.clip(
                latest['prob_momentum_7d'].mean() if 'prob_momentum_7d' in latest else 0,
                -1, 1
            ),
            'attention_alert': latest['attention_index_24h'].max() > 70,
            'urgency_weight': (1 / np.sqrt(
                latest['days_to_resolution'].min() or 365
            )) if 'days_to_resolution' in latest else 0.0,
        }


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def get_crowd_features_for_training(
    conn: psycopg2.extensions.connection,
    specialist: str,
    start_date: date,
    end_date: date
) -> pd.DataFrame:
    """
    Get crowd belief features ready for specialist training.

    Convenience function that creates engine and computes features.

    Args:
        conn: Database connection
        specialist: Specialist bucket name
        start_date: Training start date
        end_date: Training end date

    Returns:
        DataFrame with features indexed by as_of_date
    """
    engine = CrowdBeliefsFeatureEngine(conn)
    return engine.compute_features(specialist, start_date, end_date)


def get_composite_crowd_signal(
    conn: psycopg2.extensions.connection,
    specialist: str,
    as_of_date: date
) -> Dict[str, float]:
    """
    Get composite crowd signal for real-time inference.

    Args:
        conn: Database connection
        specialist: Specialist bucket name
        as_of_date: Date for signal computation

    Returns:
        Dict with composite behavioral signals
    """
    engine = CrowdBeliefsFeatureEngine(conn)
    return engine.compute_composite_signal(specialist, as_of_date)


# =============================================================================
# INTEGRATION WITH TRUMP EFFECT SPECIALIST
# =============================================================================

def enhance_trump_effect_features(
    base_features: pd.DataFrame,
    conn: psycopg2.extensions.connection
) -> pd.DataFrame:
    """
    Enhance Trump Effect specialist features with crowd beliefs.

    This function integrates Polymarket signals into the existing
    TrumpEffectFeatureEngine output.

    Args:
        base_features: DataFrame from TrumpEffectFeatureEngine
        conn: Database connection

    Returns:
        Enhanced DataFrame with crowd belief features
    """
    if base_features.empty:
        return base_features

    start_date = base_features['as_of_date'].min()
    end_date = base_features['as_of_date'].max()

    # Get crowd features
    engine = CrowdBeliefsFeatureEngine(conn)
    crowd_features = engine.compute_features('trump_effect', start_date, end_date)

    if crowd_features.empty:
        logger.warning("No crowd belief data available for enhancement")
        return base_features

    # Merge on as_of_date
    enhanced = base_features.merge(
        crowd_features,
        on='as_of_date',
        how='left'
    )

    # Fill missing with neutral values
    crowd_cols = [c for c in enhanced.columns if c.startswith('trump_effect_')]
    for col in crowd_cols:
        if 'uncertainty' in col or 'consensus' in col:
            enhanced[col] = enhanced[col].fillna(0.5)
        elif 'momentum' in col or 'direction' in col:
            enhanced[col] = enhanced[col].fillna(0.0)
        else:
            enhanced[col] = enhanced[col].fillna(0.0)

    logger.info(
        f"Enhanced Trump Effect features with {len(crowd_cols)} crowd belief signals"
    )

    return enhanced


if __name__ == "__main__":
    # Test the feature engine
    import os
    from dotenv import load_dotenv

    load_dotenv()
    load_dotenv('.env.vercel')

    database_url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
    if not database_url:
        print("DATABASE_URL not found")
        exit(1)

    conn = psycopg2.connect(database_url)

    engine = CrowdBeliefsFeatureEngine(conn)
    features = engine.compute_features(
        specialist='trump_effect',
        start_date=date(2025, 1, 1),
        end_date=date.today()
    )

    print(f"\nComputed {len(features)} rows with columns:")
    print(features.columns.tolist())

    if not features.empty:
        print("\nSample data:")
        print(features.head())

    conn.close()
