#!/usr/bin/env python3
"""
DEPRECATED: Legacy Full Pipeline Orchestrator (L0→L5)

This script is SUPERSEDED by:
    python -m fusion.core_training.run_pipeline

The active training pipeline (Phase 3 → Phase 6 → Phase 7) lives in:
    src/fusion/core_training/run_pipeline.py

This legacy orchestrator references scripts that no longer exist
(train_core_chronos.py, train_specialist.py, train_meta_ensemble.py).
It is kept for reference only. Do NOT use for production training.

For production training:
    python -m fusion.core_training.run_pipeline
    python -m fusion.core_training.run_pipeline --skip-matrix  # Train only
    python -m fusion.core_training.run_pipeline --horizons 5 21

For standalone forecast promotion:
    python scripts/generate_production_forecasts.py
"""

import os
import sys
import subprocess
import logging
import argparse
import warnings
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

warnings.warn(
    "scripts/run_pipeline.py is DEPRECATED. "
    "Use 'python -m fusion.core_training.run_pipeline' instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Load environment
load_dotenv()
load_dotenv(".env.vercel")

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"

# Horizons
HORIZONS = [5, 21, 63, 126]

# Specialist buckets (11 specialists)
SPECIALIST_BUCKETS = [
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
    "trump_effect",  # 11th specialist: Trump/policy regime dynamics
]


def run_script(script_name: str, args: List[str], dry_run: bool = False) -> bool:
    """Run a pipeline script with arguments.

    Returns True if successful, False otherwise.
    """
    script_path = SCRIPTS_DIR / script_name

    if not script_path.exists():
        logger.error(f"Script not found: {script_path}")
        return False

    # Build command
    python_path = PROJECT_ROOT / ".venv" / "bin" / "python"
    if not python_path.exists():
        python_path = "python"

    cmd = [str(python_path), str(script_path)] + args

    if dry_run:
        cmd.append("--dry-run")

    logger.info(f"Running: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            capture_output=False,  # Stream output to console
            text=True,
        )

        if result.returncode != 0:
            logger.error(f"Script failed with exit code {result.returncode}")
            return False

        return True

    except Exception as e:
        logger.error(f"Failed to run script: {e}")
        return False


def check_llm_availability() -> Optional[str]:
    """Check if LLM API keys are available.

    Returns the provider name if available, None otherwise.
    """
    if os.getenv("ANTHROPIC_API_KEY"):
        return "Anthropic (Claude)"
    elif os.getenv("OPENAI_API_KEY"):
        return "OpenAI (GPT-4)"
    return None


def run_l2_core(horizon: int, mode: str, dry_run: bool) -> bool:
    """Run L2: Core Baseline (Chronos-2 + AutoGluon)."""
    logger.info("=" * 60)
    logger.info("L2: CORE BASELINE (CHRONOS-2 + AUTOGLUON)")
    logger.info("=" * 60)

    return run_script(
        "train_core_chronos.py",
        [
            "--horizon",
            str(horizon),
            "--mode",
            mode,
        ],
        dry_run,
    )


def run_l3_specialists(horizon: int, mode: str, dry_run: bool) -> bool:
    """Run L3: Specialist Models (10 buckets)."""
    logger.info("=" * 60)
    logger.info("L3: SPECIALIST MODELS (10 BUCKETS)")
    logger.info("=" * 60)

    # Train all specialists for this horizon
    return run_script(
        "train_specialist.py",
        [
            "--bucket",
            "all",
            "--horizon",
            str(horizon),
            "--mode",
            mode,
        ],
        dry_run,
    )


def run_l4_meta_ensemble(horizon: int, dry_run: bool) -> bool:
    """Run L4: Meta-Ensemble + Attribution."""
    logger.info("=" * 60)
    logger.info("L4: META-ENSEMBLE + ATTRIBUTION")
    logger.info("=" * 60)

    return run_script(
        "train_meta_ensemble.py",
        [
            "--horizon",
            str(horizon),
        ],
        dry_run,
    )


def run_l5a_monte_carlo(horizon: int, dry_run: bool) -> bool:
    """Run L5-A: Monte Carlo Simulation."""
    logger.info("=" * 60)
    logger.info("L5-A: MONTE CARLO SIMULATION")
    logger.info("=" * 60)

    return run_script(
        "run_monte_carlo.py",
        [
            "--horizon",
            str(horizon),
        ],
        dry_run,
    )


def run_l5d_analogs(horizon: int, dry_run: bool) -> bool:
    """Run L5-D: Historical Analogs."""
    logger.info("=" * 60)
    logger.info("L5-D: HISTORICAL ANALOGS")
    logger.info("=" * 60)

    return run_script(
        "find_analogs.py",
        [
            "--horizon",
            str(horizon),
        ],
        dry_run,
    )


def run_l5c_synthesis(horizon: int, dry_run: bool) -> bool:
    """Run L5-C: LLM Synthesis."""
    logger.info("=" * 60)
    logger.info("L5-C: LLM SYNTHESIS")
    logger.info("=" * 60)

    return run_script(
        "generate_synthesis.py",
        [
            "--horizon",
            str(horizon),
        ],
        dry_run,
    )


def run_full_pipeline(
    horizon: int,
    mode: str = "quick",
    dry_run: bool = False,
    skip_llm: bool = False,
) -> bool:
    """Run the complete L2→L5 pipeline for a single horizon.

    Args:
        horizon: Forecast horizon in days (5, 21, 63, 126)
        mode: Training mode ("ultrafast", "quick", or "full")
        dry_run: If True, validate without training
        skip_llm: If True, skip L5-C LLM synthesis

    Returns:
        True if all steps succeeded, False otherwise
    """
    start_time = datetime.now()

    logger.info("\n" + "=" * 60)
    logger.info(f"ZINC-FUSION-V15 PIPELINE: {horizon}d HORIZON")
    logger.info(f"Mode: {mode.upper()}")
    logger.info(f"Dry Run: {dry_run}")
    logger.info(f"Started: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    # Check LLM availability if not skipping
    if not skip_llm:
        llm_provider = check_llm_availability()
        if llm_provider:
            logger.info(f"LLM Provider: {llm_provider}")
        else:
            logger.warning("No LLM API key found. L5-C synthesis will be skipped.")
            logger.warning("Set ANTHROPIC_API_KEY or OPENAI_API_KEY for LLM synthesis.")
            skip_llm = True

    steps = [
        ("L2: Core Baseline", lambda: run_l2_core(horizon, mode, dry_run)),
        ("L3: Specialists", lambda: run_l3_specialists(horizon, mode, dry_run)),
        ("L4: Meta-Ensemble", lambda: run_l4_meta_ensemble(horizon, dry_run)),
        ("L5-A: Monte Carlo", lambda: run_l5a_monte_carlo(horizon, dry_run)),
        ("L5-D: Analogs", lambda: run_l5d_analogs(horizon, dry_run)),
    ]

    if not skip_llm:
        steps.append(
            ("L5-C: LLM Synthesis", lambda: run_l5c_synthesis(horizon, dry_run))
        )

    results = {}

    for step_name, step_fn in steps:
        logger.info(f"\n>>> Starting {step_name}")

        try:
            success = step_fn()
            results[step_name] = "✅ Success" if success else "❌ Failed"

            if not success:
                logger.error(f"Step {step_name} failed. Stopping pipeline.")
                break

        except Exception as e:
            results[step_name] = f"❌ Error: {e}"
            logger.error(f"Step {step_name} raised exception: {e}")
            break

    # Summary
    end_time = datetime.now()
    duration = end_time - start_time

    logger.info("\n" + "=" * 60)
    logger.info("PIPELINE SUMMARY")
    logger.info("=" * 60)

    for step_name, result in results.items():
        logger.info(f"  {step_name}: {result}")

    logger.info(f"\nDuration: {duration}")
    logger.info("=" * 60)

    # Check if all steps succeeded
    all_success = all("✅" in r for r in results.values())
    return all_success


def main():
    parser = argparse.ArgumentParser(
        description="Run ZINC-FUSION-V15 full training pipeline (L2→L5)"
    )
    parser.add_argument(
        "--horizon",
        type=str,
        required=True,
        help="Horizon in days (5, 21, 63, 126) or 'all'",
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["ultrafast", "quick", "full"],
        default="quick",
        help="Training mode: 'ultrafast' (~15min), 'quick' (~1hr), or 'full' (~4hrs)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Validate pipeline without training"
    )
    parser.add_argument(
        "--skip-llm", action="store_true", help="Skip L5-C LLM synthesis"
    )

    args = parser.parse_args()

    # Determine horizons
    if args.horizon.lower() == "all":
        horizons = HORIZONS
    else:
        horizon = int(args.horizon)
        if horizon not in HORIZONS:
            logger.error(f"Invalid horizon: {horizon}. Must be one of {HORIZONS}")
            sys.exit(1)
        horizons = [horizon]

    # Run pipeline for each horizon
    all_results = {}

    for horizon in horizons:
        success = run_full_pipeline(
            horizon=horizon,
            mode=args.mode,
            dry_run=args.dry_run,
            skip_llm=args.skip_llm,
        )
        all_results[horizon] = success

    # Final summary
    if len(horizons) > 1:
        logger.info("\n" + "=" * 60)
        logger.info("MULTI-HORIZON SUMMARY")
        logger.info("=" * 60)

        for horizon, success in all_results.items():
            status = "✅" if success else "❌"
            logger.info(f"  {horizon}d: {status}")

        logger.info("=" * 60)

    # Exit with appropriate code
    if all(all_results.values()):
        logger.info("\n✅ Pipeline completed successfully!")
        sys.exit(0)
    else:
        logger.error("\n❌ Pipeline completed with errors.")
        sys.exit(1)


if __name__ == "__main__":
    main()
