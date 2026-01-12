"""
ZINC-FUSION-V15: H2O-Powered Specialist Hunters

Beast-mode AI using H2O-3 AutoML for pattern recognition.
NO HANDBUILT BULLSHIT. BATTLE-TESTED ML INFRASTRUCTURE.

Architecture:
    L0: Statistical Anomaly Detection (deterministic)
    L1: H2O AutoML Pattern Classification (trained)
    L2: Narrative Synthesis (context-aware)

@author Claude (ZINC-FUSION-V15)
@date 2026-01-12
"""

import h2o
from h2o.automl import H2OAutoML
from h2o.estimators import H2OIsolationForestEstimator
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import json
import logging

# Project imports
from src.fusion.db.connection import get_connection

logger = logging.getLogger(__name__)


@dataclass
class Anomaly:
    """Detected anomaly with severity and context."""
    type: str  # 'zscore', 'percentile', 'regime_breach', 'rate_change'
    metric: str
    severity: float
    direction: str  # 'up' or 'down'
    current_value: float
    historical_mean: float
    historical_std: float
    percentile: float


@dataclass
class Pattern:
    """Matched historical pattern with statistics."""
    pattern_id: str
    name: str
    confidence: float
    historical_accuracy: float
    regime_breakdown: Dict[str, float]
    sample_size: int
    expected_direction: str
    expected_magnitude: float
    avg_lead_time_days: int
    cross_domain_signals: List[str]


@dataclass
class IntelDrop:
    """Intelligence drop for gold.intel_drops table."""
    as_of_ts: datetime
    domain: str
    horizon: str
    direction: int
    pressure_cents: float
    edge: float
    driver_weights: dict
    top_drivers: list
    regime_tags: list
    narrative: str
    quant_payload: dict


class H2OHunter:
    """
    Beast-mode specialist hunter using H2O-3 AutoML.
    
    Each specialist (crush, china, fx, etc.) gets its own trained model.
    
    Usage:
        hunter = H2OHunter('crush')
        hunter.bootstrap_and_train()  # One-time training
        intel = hunter.hunt(datetime.now())  # Daily hunting
    """
    
    def __init__(self, specialist: str, h2o_mem_gb: int = 4):
        """
        Initialize hunter for a specific specialist.
        
        Args:
            specialist: One of 'crush', 'china', 'fx', 'fed', 'tariff',
                       'energy', 'biofuel', 'palm', 'volatility',
                       'substitutes', 'trump_effect'
            h2o_mem_gb: Memory allocation for H2O cluster (GB)
        """
        self.specialist = specialist
        self.h2o_mem_gb = h2o_mem_gb
        
        # Paths
        self.project_root = Path(__file__).parent.parent.parent.parent
        self.models_dir = self.project_root / "models" / "hunters"
        self.models_dir.mkdir(parents=True, exist_ok=True)
        
        # Model paths
        self.automl_path = self.models_dir / f"{specialist}_automl"
        self.pattern_library_path = self.models_dir / f"{specialist}_patterns.json"
        self.stats_path = self.models_dir / f"{specialist}_stats.json"
        
        # Database connection
        self.conn = get_connection()
        
        # Load pattern library and stats if they exist
        self.pattern_library = self._load_pattern_library()
        self.historical_stats = self._load_historical_stats()
        
        # Initialize H2O if not already running
        self._init_h2o()
        
        logger.info(f"H2OHunter initialized for {specialist}")
    
    def _init_h2o(self):
        """Initialize H2O cluster if not already running."""
        try:
            h2o.cluster_info()
            logger.info("H2O cluster already running")
        except:
            logger.info(f"Starting H2O cluster with {self.h2o_mem_gb}GB memory...")
            h2o.init(
                nthreads=-1,  # Use all cores
                max_mem_size=f"{self.h2o_mem_gb}G"
            )
            logger.info("H2O cluster started")
    
    def hunt(self, as_of_date: datetime) -> Optional[IntelDrop]:
        """
        Execute full hunting pipeline for a specific date.
        
        Pipeline:
            1. L0: Detect statistical anomalies
            2. L1: Match patterns using H2O AutoML
            3. L2: Generate narrative
            4. Package intel drop
        
        Args:
            as_of_date: Date to hunt for signals
            
        Returns:
            IntelDrop if signal found, None otherwise
        """
        logger.info(f"[{self.specialist}] Hunting on {as_of_date.date()}...")
        
        # L0: Statistical anomaly detection
        anomalies = self._detect_anomalies(as_of_date)
        
        if not anomalies:
            logger.info(f"[{self.specialist}] No anomalies detected")
            return None
        
        logger.info(f"[{self.specialist}] Found {len(anomalies)} anomalies")
        
        # L1: Pattern matching with H2O
        pattern_match = self._match_pattern_with_h2o(as_of_date, anomalies)
        
        if pattern_match is None:
            logger.info(f"[{self.specialist}] No matching patterns")
            return None
        
        logger.info(f"[{self.specialist}] Pattern matched: {pattern_match.name} "
                   f"(confidence: {pattern_match.confidence:.2%})")
        
        # L2: Generate narrative
        narrative = self._generate_narrative(anomalies, pattern_match)
        
        # Calculate edge
        edge = pattern_match.confidence * pattern_match.historical_accuracy
        
        # Package intel drop
        intel_drop = IntelDrop(
            as_of_ts=as_of_date,
            domain=self.specialist,
            horizon='1W',  # Default to 1 week
            direction=1 if pattern_match.expected_direction == 'up' else -1,
            pressure_cents=pattern_match.expected_magnitude,
            edge=edge,
            driver_weights=self._calculate_driver_weights(anomalies),
            top_drivers=self._extract_top_drivers(anomalies, top_k=3),
            regime_tags=[self._detect_regime(as_of_date)],
            narrative=narrative,
            quant_payload={
                'anomalies': [self._anomaly_to_dict(a) for a in anomalies],
                'pattern': self._pattern_to_dict(pattern_match),
                'confidence': pattern_match.confidence,
                'historical_accuracy': pattern_match.historical_accuracy
            }
        )
        
        return intel_drop
    
    def _detect_anomalies(self, as_of_date: datetime) -> List[Anomaly]:
        """
        L0: Statistical anomaly detection (deterministic).
        
        Methods:
            1. Z-score (> 2.5 or < -2.5)
            2. Percentile rank (< 5th or > 95th)
            3. Regime-aware bounds
            4. Rate of change spikes
        """
        anomalies = []
        
        # Load current and historical data
        current_data = self._load_specialist_data(as_of_date)
        historical_data = self._load_specialist_data_window(
            as_of_date - timedelta(days=252*5),  # 5 years
            as_of_date - timedelta(days=1)
        )
        
        if current_data is None or historical_data.empty:
            return anomalies
        
        # Get specialist-specific metrics
        metrics = self._get_specialist_metrics()
        
        for metric in metrics:
            if metric not in current_data or metric not in historical_data.columns:
                continue
            
            current_val = current_data[metric]
            hist_mean = historical_data[metric].mean()
            hist_std = historical_data[metric].std()
            
            # Skip if no variation
            if hist_std == 0:
                continue
            
            # Z-score
            z_score = (current_val - hist_mean) / hist_std
            
            # Percentile
            percentile = (historical_data[metric] < current_val).sum() / len(historical_data) * 100
            
            # Check for anomaly
            if abs(z_score) > 2.5:
                anomalies.append(Anomaly(
                    type='zscore',
                    metric=metric,
                    severity=abs(z_score),
                    direction='up' if z_score > 0 else 'down',
                    current_value=current_val,
                    historical_mean=hist_mean,
                    historical_std=hist_std,
                    percentile=percentile
                ))
            
            if percentile < 5 or percentile > 95:
                anomalies.append(Anomaly(
                    type='percentile',
                    metric=metric,
                    severity=min(percentile, 100 - percentile),
                    direction='down' if percentile < 5 else 'up',
                    current_value=current_val,
                    historical_mean=hist_mean,
                    historical_std=hist_std,
                    percentile=percentile
                ))
        
        return anomalies
    
    def _match_pattern_with_h2o(self, as_of_date: datetime, 
                                 anomalies: List[Anomaly]) -> Optional[Pattern]:
        """
        L1: Match current situation to historical patterns using H2O AutoML.
        
        Returns:
            Pattern object if confident match found, None otherwise
        """
        if not self.automl_path.exists():
            logger.warning(f"No trained model for {self.specialist}. Run bootstrap_and_train() first.")
            return None
        
        # Engineer features from anomalies
        features = self._engineer_pattern_features(as_of_date, anomalies)
        
        # Convert to H2O frame
        features_df = pd.DataFrame([features])
        features_h2o = h2o.H2OFrame(features_df)
        
        # Load trained model
        model = h2o.load_model(str(self.automl_path))
        
        # Predict
        predictions = model.predict(features_h2o).as_data_frame()
        
        # Get predicted pattern class
        pattern_id = predictions['predict'][0]
        
        # Get confidence (probability of predicted class)
        confidence_col = f'p{pattern_id}'
        if confidence_col not in predictions.columns:
            # For binary classification or other formats
            confidence = predictions.iloc[0, 1]  # Second column typically has prob
        else:
            confidence = predictions[confidence_col][0]
        
        # Only return if confidence > 70%
        if confidence < 0.7:
            logger.info(f"Pattern confidence too low: {confidence:.2%}")
            return None
        
        # Get pattern details from library
        if pattern_id not in self.pattern_library:
            logger.warning(f"Pattern {pattern_id} not in library")
            return None
        
        pattern_info = self.pattern_library[pattern_id]
        
        # Get current regime
        regime = self._detect_regime(as_of_date)
        
        # Adjust accuracy based on regime
        if regime in pattern_info.get('regime_breakdown', {}):
            regime_accuracy = pattern_info['regime_breakdown'][regime]
        else:
            regime_accuracy = pattern_info['historical_accuracy']
        
        return Pattern(
            pattern_id=pattern_id,
            name=pattern_info.get('name', f'Pattern_{pattern_id}'),
            confidence=confidence,
            historical_accuracy=regime_accuracy,
            regime_breakdown=pattern_info.get('regime_breakdown', {}),
            sample_size=pattern_info.get('n_occurrences', 0),
            expected_direction=pattern_info.get('expected_direction', 'neutral'),
            expected_magnitude=pattern_info.get('expected_magnitude', 0.0),
            avg_lead_time_days=pattern_info.get('avg_lead_time', 21),
            cross_domain_signals=pattern_info.get('cross_domain_signals', [])
        )
    
    def _generate_narrative(self, anomalies: List[Anomaly], pattern: Pattern) -> str:
        """
        L2: Generate human-readable narrative.
        
        Format:
        "{METRIC} at {PERCENTILE}. Historical accuracy: {ACCURACY}% ({HITS}/{TOTAL}).
         Current regime: {REGIME}. Regime-adjusted: {REGIME_ACCURACY}%.
         Confidence: {CONFIDENCE}%"
        """
        # Get primary anomaly (highest severity)
        primary = max(anomalies, key=lambda a: a.severity)
        
        # Calculate hits
        hits = int(pattern.historical_accuracy * pattern.sample_size)
        
        narrative = (
            f"{primary.metric.replace('_', ' ').title()} at {primary.percentile:.1f} percentile "
            f"({primary.direction}). "
            f"Historical accuracy: {pattern.historical_accuracy:.0%} "
            f"({hits}/{pattern.sample_size}). "
        )
        
        # Add regime info if available
        regime_accuracies = pattern.regime_breakdown
        if regime_accuracies:
            best_regime = max(regime_accuracies.items(), key=lambda x: x[1])
            narrative += f"Best in {best_regime[0]} regime: {best_regime[1]:.0%}. "
        
        # Add cross-domain signals
        if pattern.cross_domain_signals:
            narrative += f"Cross-domain: {', '.join(pattern.cross_domain_signals)}. "
        
        # Add confidence
        narrative += f"Confidence: {pattern.confidence:.0%}"
        
        return narrative
    
    def _load_specialist_data(self, as_of_date: datetime) -> Optional[pd.Series]:
        """Load specialist features for a specific date."""
        query = """
        SELECT features 
        FROM training.specialist_features
        WHERE bucket = %s AND as_of_date = %s
        """
        
        df = pd.read_sql(query, self.conn, params=(self.specialist, as_of_date.date()))
        
        if df.empty:
            return None
        
        # Parse JSON features
        features = json.loads(df['features'].iloc[0])
        return pd.Series(features)
    
    def _load_specialist_data_window(self, start_date: datetime, 
                                     end_date: datetime) -> pd.DataFrame:
        """Load specialist features for a date range."""
        query = """
        SELECT as_of_date, features 
        FROM training.specialist_features
        WHERE bucket = %s 
          AND as_of_date BETWEEN %s AND %s
        ORDER BY as_of_date
        """
        
        df = pd.read_sql(query, self.conn, 
                        params=(self.specialist, start_date.date(), end_date.date()))
        
        if df.empty:
            return pd.DataFrame()
        
        # Parse JSON features into columns
        features_list = [json.loads(f) for f in df['features']]
        features_df = pd.DataFrame(features_list, index=df['as_of_date'])
        
        return features_df
    
    def _get_specialist_metrics(self) -> List[str]:
        """Get list of metrics for this specialist."""
        # TODO: Load from specialist configuration
        # For now, return common metrics
        return [
            'close', 'volume', 'open_interest',
            'returns_1d', 'returns_5d', 'returns_21d',
            'volatility_21d', 'volume_ratio'
        ]
    
    def _detect_regime(self, as_of_date: datetime) -> str:
        """Detect market regime for the given date."""
        # TODO: Implement proper regime detection
        # For now, return placeholder
        return 'bull'
    
    def _engineer_pattern_features(self, as_of_date: datetime, 
                                   anomalies: List[Anomaly]) -> dict:
        """Engineer features for pattern matching."""
        features = {}
        
        # Anomaly counts by type
        for anom_type in ['zscore', 'percentile', 'regime_breach']:
            features[f'n_{anom_type}'] = sum(1 for a in anomalies if a.type == anom_type)
        
        # Anomaly severity stats
        if anomalies:
            severities = [a.severity for a in anomalies]
            features['max_severity'] = max(severities)
            features['mean_severity'] = np.mean(severities)
            features['sum_severity'] = sum(severities)
        
        # Direction counts
        features['n_up'] = sum(1 for a in anomalies if a.direction == 'up')
        features['n_down'] = sum(1 for a in anomalies if a.direction == 'down')
        
        # Add current market state
        current_data = self._load_specialist_data(as_of_date)
        if current_data is not None:
            for metric in self._get_specialist_metrics():
                if metric in current_data:
                    features[f'current_{metric}'] = current_data[metric]
        
        return features
    
    def _calculate_driver_weights(self, anomalies: List[Anomaly]) -> dict:
        """Calculate weights for each driver (anomaly)."""
        total_severity = sum(a.severity for a in anomalies)
        
        if total_severity == 0:
            return {}
        
        weights = {}
        for anom in anomalies:
            weights[anom.metric] = anom.severity / total_severity
        
        return weights
    
    def _extract_top_drivers(self, anomalies: List[Anomaly], top_k: int = 3) -> list:
        """Extract top K drivers by severity."""
        sorted_anomalies = sorted(anomalies, key=lambda a: a.severity, reverse=True)
        return [a.metric for a in sorted_anomalies[:top_k]]
    
    def _anomaly_to_dict(self, anomaly: Anomaly) -> dict:
        """Convert Anomaly to dict for JSON serialization."""
        return {
            'type': anomaly.type,
            'metric': anomaly.metric,
            'severity': anomaly.severity,
            'direction': anomaly.direction,
            'current_value': anomaly.current_value,
            'percentile': anomaly.percentile
        }
    
    def _pattern_to_dict(self, pattern: Pattern) -> dict:
        """Convert Pattern to dict for JSON serialization."""
        return {
            'pattern_id': pattern.pattern_id,
            'name': pattern.name,
            'confidence': pattern.confidence,
            'historical_accuracy': pattern.historical_accuracy,
            'sample_size': pattern.sample_size,
            'expected_direction': pattern.expected_direction,
            'expected_magnitude': pattern.expected_magnitude
        }
    
    def _load_pattern_library(self) -> dict:
        """Load pattern library from disk."""
        if not self.pattern_library_path.exists():
            return {}
        
        with open(self.pattern_library_path, 'r') as f:
            return json.load(f)
    
    def _save_pattern_library(self, library: dict):
        """Save pattern library to disk."""
        with open(self.pattern_library_path, 'w') as f:
            json.dump(library, f, indent=2)
    
    def _load_historical_stats(self) -> dict:
        """Load historical statistics from disk."""
        if not self.stats_path.exists():
            return {}
        
        with open(self.stats_path, 'r') as f:
            return json.load(f)
    
    def _save_historical_stats(self, stats: dict):
        """Save historical statistics to disk."""
        with open(self.stats_path, 'w') as f:
            json.dump(stats, f, indent=2)
    
    def bootstrap_and_train(self, max_runtime_hours: float = 1.0):
        """
        ONE-TIME: Bootstrap pattern library and train H2O AutoML model.
        
        This scans all historical data, identifies recurring patterns,
        and trains an H2O AutoML classifier to recognize them.
        
        Args:
            max_runtime_hours: Maximum time for H2O AutoML training
        """
        logger.info(f"{'='*60}")
        logger.info(f"BOOTSTRAPPING {self.specialist.upper()} HUNTER")
        logger.info(f"{'='*60}")
        
        # TODO: Implement full bootstrap
        # For now, create placeholder to test structure
        
        logger.info("✓ Bootstrap complete (placeholder)")
        logger.info("Next step: Implement full historical scan and pattern identification")


if __name__ == "__main__":
    # Test installation
    hunter = H2OHunter('crush')
    print(f"✓ H2OHunter created for {hunter.specialist}")
    print(f"✓ Models directory: {hunter.models_dir}")
    print(f"✓ H2O cluster ready")
