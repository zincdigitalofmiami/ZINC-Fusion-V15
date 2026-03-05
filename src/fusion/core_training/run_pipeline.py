#!/usr/bin/env python3
"""
Core Training Pipeline
======================

Four-phase pipeline:
  Phase 3: Build feature matrix (training.matrix_1d)
  Phase 6: Train models for all horizons
  Phase 7: Forward inference → forecasts.production_1d
  Phase 8: Monte Carlo probability layer (prob_enter_zone, prob_touch_*, mc_runs)

Usage:
    python -m fusion.core_training.run_pipeline
    python -m fusion.core_training.run_pipeline --horizons 5 21
    python -m fusion.core_training.run_pipeline --skip-matrix  # Train only
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import subprocess
import sys
from datetime import datetime

from . import build_matrix, train_models
from .config import HORIZONS, PROJECT_ROOT, TARGET_SYMBOL

logger = logging.getLogger(__name__)


def setup_logging():
    """Configure logging for pipeline run."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def run_pipeline(
    symbol: str = TARGET_SYMBOL,
    horizons: list = None,
    skip_matrix: bool = False,
    dry_run: bool = False,
) -> bool:
    """
    Execute Core Training Pipeline.

    Args:
        symbol: Target symbol (default: ZL)
        horizons: Horizons to train (default: [5, 21, 63, 126])
        skip_matrix: Skip Phase 3 (use existing matrix)
        dry_run: Preview only, don't execute

    Returns:
        success: True if pipeline completed
    """
    if horizons is None:
        horizons = HORIZONS

    run_id = f"pipeline_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    logger.info("=" * 70)
    logger.info("CORE TRAINING PIPELINE v2.0")
    logger.info("=" * 70)
    logger.info(f"Run ID: {run_id}")
    logger.info(f"Symbol: {symbol}")
    logger.info(f"Horizons: {horizons}")
    logger.info(f"Skip matrix rebuild: {skip_matrix}")
    logger.info("=" * 70)

    if dry_run:
        logger.info("DRY RUN - No changes will be made")
        return True

    matrix_version = None

    # =========================================================================
    # PHASE 3: BUILD CORE MATRIX
    # =========================================================================
    if not skip_matrix:
        logger.info("")
        logger.info("=" * 70)
        logger.info("PHASE 3: BUILD CORE MATRIX")
        logger.info("=" * 70)

        success, matrix_version, feature_count = build_matrix.run(symbol)

        if not success:
            logger.error("PIPELINE ABORTED - Core matrix build failed")
            return False

        logger.info(f"   Matrix version: {matrix_version}")
        logger.info(f"   Feature count: {feature_count}")
    else:
        logger.info("")
        logger.info("Skipping Phase 3 (--skip-matrix)")

    # =========================================================================
    # PHASE 6: TRAIN MODELS
    # =========================================================================
    logger.info("")
    logger.info("=" * 70)
    logger.info("PHASE 6: TRAIN MODELS")
    logger.info("=" * 70)

    # Create run hash for lineage
    run_hash = hashlib.sha256(
        f"{matrix_version or 'existing'}_{run_id}".encode()
    ).hexdigest()[:16]

    versions = {
        "matrix_version": matrix_version,
        "run_hash": run_hash,
    }

    success, results = train_models.run(symbol, horizons, versions)

    if not success:
        logger.error("PIPELINE COMPLETED WITH ERRORS - Some horizons failed")
        return False

    # =========================================================================
    # PHASE 7: FORWARD INFERENCE → PRODUCTION FORECASTS
    # =========================================================================
    logger.info("")
    logger.info("=" * 70)
    logger.info("PHASE 7: FORWARD INFERENCE → PRODUCTION FORECASTS")
    logger.info("=" * 70)

    forecast_script = PROJECT_ROOT / "scripts" / "generate_forward_forecasts.py"
    if forecast_script.exists():
        result = subprocess.run(
            [sys.executable, str(forecast_script)],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode == 0:
            logger.info("Production forecasts generated successfully")
            for line in result.stdout.strip().splitlines()[-5:]:
                logger.info(f"   {line}")
        else:
            logger.error("PIPELINE ABORTED - Production forecast generation FAILED")
            for line in result.stderr.strip().splitlines()[-10:]:
                logger.error(f"   {line}")
            return False
    else:
        logger.error(
            f"PIPELINE ABORTED - Forecast script not found at {forecast_script}"
        )
        return False

    # =========================================================================
    # PHASE 8: MONTE CARLO PROBABILITY LAYER
    # =========================================================================
    logger.info("")
    logger.info("=" * 70)
    logger.info("PHASE 8: MONTE CARLO PROBABILITY LAYER")
    logger.info("=" * 70)

    mc_script = PROJECT_ROOT / "scripts" / "run_monte_carlo.py"
    if mc_script.exists():
        result = subprocess.run(
            [sys.executable, str(mc_script), "--horizon", "all"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode == 0:
            logger.info("Monte Carlo probability layer completed successfully")
            for line in result.stdout.strip().splitlines()[-5:]:
                logger.info(f"   {line}")
        else:
            logger.error("PIPELINE ABORTED - Monte Carlo simulation FAILED")
            for line in result.stderr.strip().splitlines()[-10:]:
                logger.error(f"   {line}")
            return False
    else:
        logger.error(f"PIPELINE ABORTED - Monte Carlo script not found at {mc_script}")
        return False

    # Final summary
    logger.info("")
    logger.info("=" * 70)
    logger.info("PIPELINE COMPLETE")
    logger.info("=" * 70)
    logger.info(f"Run ID: {run_id}")
    logger.info(f"Matrix version: {matrix_version or 'existing'}")
    logger.info(f"Run hash: {run_hash}")
    logger.info("=" * 70)

    return True


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Core Training Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Phases:
  3. Build Core Matrix - Assemble feature matrix from all sources
  6. Train Models - Train AutoGluon models for each horizon
  7. Forward Inference - True model predict() -> forecasts.production_1d
  8. Monte Carlo - Probability layer (prob_enter_zone, prob_touch_*, mc_runs)

Examples:
  # Full pipeline (rebuild matrix + train)
  python -m fusion.core_training.run_pipeline

  # Train only (use existing matrix)
  python -m fusion.core_training.run_pipeline --skip-matrix

  # Train only tactical horizons
  python -m fusion.core_training.run_pipeline --horizons 5 21

  # Dry run (preview only)
  python -m fusion.core_training.run_pipeline --dry-run
        """,
    )

    parser.add_argument(
        "--symbol",
        default=TARGET_SYMBOL,
        help=f"Target symbol (default: {TARGET_SYMBOL})",
    )
    parser.add_argument(
        "--horizons",
        type=int,
        nargs="+",
        default=HORIZONS,
        help=f"Horizons to train (default: {HORIZONS})",
    )
    parser.add_argument(
        "--skip-matrix",
        action="store_true",
        help="Skip matrix rebuild, use existing training.matrix_1d",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview pipeline without executing",
    )

    args = parser.parse_args()

    setup_logging()

    success = run_pipeline(
        symbol=args.symbol,
        horizons=args.horizons,
        skip_matrix=args.skip_matrix,
        dry_run=args.dry_run,
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
