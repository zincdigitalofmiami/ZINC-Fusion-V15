#!/usr/bin/env python3
"""
Core Training Pipeline Orchestrator
=====================================

Runs all 6 phases in sequence with ENFORCED dependency order.

DEPENDENCY RULES (ENFORCED, NOT ADVISORY):
- Phase 3 REQUIRES Phase 1 completed (options must exist)
- Phase 6 REQUIRES Phase 5 passed with MATCHING HASHES (hash-bound artifact)
- Skipping phases requires ZINC_DANGEROUS_MODE=1 env var AND --skip-dependency-check

Usage:
    python -m fusion.core_training.run_pipeline
    python -m fusion.core_training.run_pipeline --start-phase 3
    python -m fusion.core_training.run_pipeline --horizons 5 21

Phases:
    1. Options Features (BLOCKING GATE)
    2. Validate Elite (features)
    3. Build Core Matrix
    4. Create OOF Schema
    5. Pre-Flight Audit (MANDATORY GATE) - produces hash-bound artifact
    6. Sequential Training - validates artifact hashes match current state
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Tuple

import psycopg2

from . import phase1_options_features
from . import phase2_validate_gold_elite
from . import phase3_build_core_matrix
from . import phase4_create_oof_schema
from . import phase5_audit_preflight
from . import phase6_train_core_seq
from .config import DATABASE_URL, TARGET_SYMBOL, HORIZONS, OOF_TABLE_NAME

logger = logging.getLogger(__name__)

# Artifact directory for storing gate pass records
ARTIFACT_DIR = Path("models/core_v2/.pipeline_artifacts")

# Environment variable for dangerous mode
DANGEROUS_MODE_ENV = "ZINC_DANGEROUS_MODE"


def setup_logging(log_file: Optional[Path] = None):
    """Configure logging for pipeline run."""
    handlers = [logging.StreamHandler(sys.stdout)]

    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file))

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=handlers,
    )


def save_gate_artifact(gate_name: str, data: dict):
    """Save artifact recording that a gate passed."""
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    artifact_path = ARTIFACT_DIR / f"{gate_name}.json"

    data["saved_at"] = datetime.utcnow().isoformat()

    with open(artifact_path, "w") as f:
        json.dump(data, f, indent=2)

    logger.info(f"   Saved gate artifact: {artifact_path}")


def load_gate_artifact(gate_name: str) -> Optional[dict]:
    """Load artifact if it exists."""
    artifact_path = ARTIFACT_DIR / f"{gate_name}.json"

    if not artifact_path.exists():
        return None

    with open(artifact_path) as f:
        return json.load(f)


def check_dangerous_mode_enabled() -> bool:
    """Check if dangerous mode is enabled via environment variable."""
    return os.getenv(DANGEROUS_MODE_ENV, "").strip() == "1"


def check_options_exist(symbol: str) -> bool:
    """Check if options features exist for Phase 3 dependency."""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) FROM features.options_1d
                WHERE symbol = %s
            """,
                (symbol,),
            )
            count = cur.fetchone()[0]
        conn.close()
        return count > 0
    except:
        return False


def check_preflight_passed(
    current_hashes: Dict[str, Optional[str]],
) -> Tuple[bool, List[str]]:
    """
    Check if Phase 5 passed with MATCHING hashes for current state.

    Hash-bound validation:
    - core_matrix_hash: must match current matrix_1d
    - options_hash: must match current features.options_1d
    - elite_hash: must match current features.elite_1d
    - config_hash: must match current config (horizons, quantiles, guardrails)

    Returns:
        (passed: bool, mismatches: list of mismatch descriptions)
    """
    artifact = load_gate_artifact("phase5_audit")

    if artifact is None:
        return False, ["No preflight artifact found"]

    if not artifact.get("passed", False):
        return False, ["Artifact shows preflight failed"]

    # Validate all hashes match
    mismatches = []
    artifact_hashes = artifact.get("hashes", {})

    for hash_name, current_value in current_hashes.items():
        artifact_value = artifact_hashes.get(hash_name)

        # Both None is OK (table doesn't exist yet)
        if current_value is None and artifact_value is None:
            continue
        elif current_value is None:
            # Current is None but artifact had a value - table was deleted?
            mismatches.append(
                f"{hash_name}: artifact had value but current is None (table deleted?)"
            )
        elif artifact_value is None:
            # Artifact was None but current has value - table was added after audit
            mismatches.append(
                f"{hash_name}: artifact was None but current has value (run audit again)"
            )
        elif artifact_value != current_value:
            mismatches.append(
                f"{hash_name}: artifact={artifact_value} != current={current_value}"
            )

    if mismatches:
        logger.warning(
            "Preflight artifact exists but hashes don't match current state:"
        )
        for m in mismatches:
            logger.warning(f"   {m}")
        return False, mismatches

    return True, []


def run_pipeline(
    symbol: str = TARGET_SYMBOL,
    horizons: list = None,
    start_phase: int = 1,
    stop_phase: int = 6,
    dry_run: bool = False,
    skip_dependency_check: bool = False,
) -> bool:
    """
    Execute Core Training Pipeline with ENFORCED dependency order.

    Args:
        symbol: Target symbol (default: ZL)
        horizons: Horizons to train (default: all)
        start_phase: Phase to start from (1-6)
        stop_phase: Phase to stop at (1-6)
        dry_run: If True, log but don't execute
        skip_dependency_check: DANGEROUS - skip dependency validation

    Returns:
        success: True if all phases completed
    """
    if horizons is None:
        horizons = HORIZONS

    run_id = f"pipeline_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

    logger.info("=" * 70)
    logger.info("CORE TRAINING PIPELINE v1.1 (ENFORCED DEPENDENCIES)")
    logger.info("=" * 70)
    logger.info(f"Run ID: {run_id}")
    logger.info(f"Symbol: {symbol}")
    logger.info(f"Horizons: {horizons}")
    logger.info(f"Phases: {start_phase} → {stop_phase}")
    logger.info(f"Dry run: {dry_run}")
    if skip_dependency_check:
        logger.warning("⚠️ DEPENDENCY CHECK DISABLED - YOU ARE ON YOUR OWN")
    logger.info("=" * 70)

    if dry_run:
        logger.info("DRY RUN - No changes will be made")
        return True

    # =========================================================================
    # DEPENDENCY ENFORCEMENT
    # =========================================================================

    if not skip_dependency_check:
        # If starting at Phase 3+, verify Phase 1 completed
        if start_phase >= 3:
            logger.info("Checking Phase 3 dependency: options features must exist...")
            if not check_options_exist(symbol):
                logger.error(
                    "❌ DEPENDENCY FAILED: features.options_1d has no data"
                )
                logger.error("   Run Phase 1 first: --start-phase 1 --stop-phase 1")
                return False
            logger.info("   ✅ Options features exist")

        # If starting at Phase 6, verify Phase 5 passed
        if start_phase == 6:
            logger.info("Checking Phase 6 dependency: pre-flight audit must pass...")
            logger.warning("   Phase 6 requires Phase 5 in same run OR valid artifact")
            logger.warning("   Running Phase 5 first to verify...")

            # Actually run Phase 5 to get current state
            success, audit = phase5_audit_preflight.run(symbol)
            if not success:
                logger.error("❌ DEPENDENCY FAILED: Pre-flight audit did not pass")
                logger.error("   Fix errors before training")
                return False

            # Save artifact with ALL hashes for potential resume
            save_gate_artifact(
                "phase5_audit",
                {
                    "passed": True,
                    "hashes": audit.get_all_hashes(),
                    "stats": audit.stats,
                },
            )

    # Track lineage versions
    versions = {
        "options_version": None,
        "elite_version": None,
        "matrix_version": None,
        "run_hash": None,
    }

    # Track Phase 5 audit result for Phase 6 validation
    phase5_audit_result: Optional[phase5_audit_preflight.AuditResult] = None

    # Phase 1: Options Features (BLOCKING GATE)
    if start_phase <= 1 <= stop_phase:
        logger.info("")
        logger.info("=" * 70)
        logger.info("PHASE 1: OPTIONS FEATURES")
        logger.info("=" * 70)

        success, options_version = phase1_options_features.run(symbol)

        if not success:
            logger.error(
                "❌ PIPELINE ABORTED - Options features failed (BLOCKING GATE)"
            )
            return False

        versions["options_version"] = options_version

    # Phase 2: Validate Gold Elite
    if start_phase <= 2 <= stop_phase:
        logger.info("")
        logger.info("=" * 70)
        logger.info("PHASE 2: VALIDATE ELITE (FEATURES)")
        logger.info("=" * 70)

        success, elite_version = phase2_validate_gold_elite.run(symbol)

        if not success:
            logger.error("❌ PIPELINE ABORTED - Elite indicators validation failed")
            return False

        versions["elite_version"] = elite_version

    # Phase 3: Build Core Matrix
    if start_phase <= 3 <= stop_phase:
        logger.info("")
        logger.info("=" * 70)
        logger.info("PHASE 3: BUILD CORE MATRIX")
        logger.info("=" * 70)

        success, matrix_version, feature_count = phase3_build_core_matrix.run(symbol)

        if not success:
            logger.error("❌ PIPELINE ABORTED - Core matrix build failed")
            return False

        versions["matrix_version"] = matrix_version
        logger.info(f"   Features: {feature_count}")

    # Phase 4: Create OOF Schema
    if start_phase <= 4 <= stop_phase:
        logger.info("")
        logger.info("=" * 70)
        logger.info("PHASE 4: CREATE OOF SCHEMA")
        logger.info("=" * 70)

        success, created = phase4_create_oof_schema.run()

        if not success:
            logger.error("❌ PIPELINE ABORTED - OOF schema creation failed")
            return False

    # Phase 5: Pre-Flight Audit (MANDATORY GATE)
    if start_phase <= 5 <= stop_phase:
        logger.info("")
        logger.info("=" * 70)
        logger.info("PHASE 5: PRE-FLIGHT AUDIT (MANDATORY GATE)")
        logger.info("=" * 70)

        success, audit = phase5_audit_preflight.run(symbol)

        if not success:
            logger.error("❌ PIPELINE ABORTED - Pre-flight audit failed")
            logger.error("   Fix the reported errors before training")
            return False

        # Store audit result for Phase 6 validation
        phase5_audit_result = audit

        # Save hash-bound artifact
        save_gate_artifact(
            "phase5_audit",
            {
                "passed": True,
                "hashes": audit.get_all_hashes(),
                "stats": audit.stats,
            },
        )

    # Phase 6: Sequential Training
    if start_phase <= 6 <= stop_phase:
        logger.info("")
        logger.info("=" * 70)
        logger.info("PHASE 6: SEQUENTIAL TRAINING")
        logger.info("=" * 70)

        # ENFORCE: Phase 5 must have passed with matching hashes
        if not skip_dependency_check:
            if phase5_audit_result is None:
                # Phase 5 didn't run in this invocation - check artifact
                logger.info(
                    "Phase 5 did not run in this invocation, checking artifact..."
                )

                # Need to compute current hashes to validate
                logger.info("Computing current hashes for validation...")
                success, current_audit = phase5_audit_preflight.run(symbol)

                if not success:
                    logger.error(
                        "❌ DEPENDENCY FAILED: Current state doesn't pass preflight"
                    )
                    return False

                # Check artifact hashes against current
                passed, mismatches = check_preflight_passed(
                    current_audit.get_all_hashes()
                )

                if not passed:
                    logger.error(
                        "❌ DEPENDENCY FAILED: Artifact hashes don't match current state"
                    )
                    for m in mismatches:
                        logger.error(f"   {m}")
                    logger.error(
                        "   Data has changed since preflight - run full pipeline"
                    )
                    return False

                logger.info("   ✅ Artifact hashes match current state - proceeding")
                phase5_audit_result = current_audit

        # Add run_hash to versions for lineage
        import hashlib

        versions["run_hash"] = hashlib.sha256(
            f"{versions.get('matrix_version', '')}_{run_id}".encode()
        ).hexdigest()[:16]

        success, results = phase6_train_core_seq.run(symbol, horizons, versions)

        if not success:
            logger.error("❌ PIPELINE COMPLETED WITH ERRORS - Some horizons failed")
            return False

    # Final summary
    logger.info("")
    logger.info("=" * 70)
    logger.info("✅ PIPELINE COMPLETE")
    logger.info("=" * 70)
    logger.info(f"Run ID: {run_id}")
    logger.info(f"Options version: {versions['options_version']}")
    logger.info(f"Elite version: {versions['elite_version']}")
    logger.info(f"Matrix version: {versions['matrix_version']}")
    logger.info(f"Run hash: {versions['run_hash']}")
    logger.info("=" * 70)

    return True


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Core Training Pipeline (ENFORCED DEPENDENCIES)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Phases:
  1. Options Features - Compute IV/Greeks from mkt options (BLOCKING GATE)
  2. Validate Elite (features) - Verify elite indicators completeness
  3. Build Core Matrix - Assemble curated feature matrix (~213 features)
  4. Create OOF Schema - Define OOF table structure
  5. Pre-Flight Audit - MANDATORY validation gate (HARD FAIL)
  6. Sequential Training - Train all horizons (5→21→63→126)

DEPENDENCY ENFORCEMENT:
  - Phase 3 requires Phase 1 completed (options must exist)
  - Phase 6 requires Phase 5 passed with MATCHING hashes (hash-bound)
  - --skip-dependency-check requires ZINC_DANGEROUS_MODE=1 env var

Examples:
  # Run full pipeline
  python -m fusion.core_training.run_pipeline

  # Start from Phase 3 (requires Phase 1 done previously)
  python -m fusion.core_training.run_pipeline --start-phase 3

  # Train only tactical horizons
  python -m fusion.core_training.run_pipeline --horizons 5 21

  # Dry run (preview only)
  python -m fusion.core_training.run_pipeline --dry-run

  # DANGEROUS: Skip dependency check (requires env var)
  ZINC_DANGEROUS_MODE=1 python -m fusion.core_training.run_pipeline --skip-dependency-check
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
        "--start-phase",
        type=int,
        default=1,
        choices=range(1, 7),
        help="Phase to start from (default: 1)",
    )
    parser.add_argument(
        "--stop-phase",
        type=int,
        default=6,
        choices=range(1, 7),
        help="Phase to stop at (default: 6)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview pipeline without executing"
    )
    parser.add_argument(
        "--skip-dependency-check",
        action="store_true",
        help="DANGEROUS: Skip dependency validation (requires ZINC_DANGEROUS_MODE=1)",
    )
    parser.add_argument(
        "--log-file", type=Path, default=None, help="Log file path (optional)"
    )

    args = parser.parse_args()

    # Setup logging
    setup_logging(args.log_file)

    # Validate phase range
    if args.start_phase > args.stop_phase:
        logger.error("start-phase must be <= stop-phase")
        sys.exit(1)

    # GUARD: --skip-dependency-check requires ZINC_DANGEROUS_MODE=1
    if args.skip_dependency_check:
        if not check_dangerous_mode_enabled():
            logger.error("=" * 70)
            logger.error("❌ --skip-dependency-check requires ZINC_DANGEROUS_MODE=1")
            logger.error("   This is a safety measure to prevent accidental bypass.")
            logger.error("")
            logger.error("   If you REALLY want to skip dependency checks, run:")
            logger.error(
                "   ZINC_DANGEROUS_MODE=1 python -m fusion.core_training.run_pipeline --skip-dependency-check"
            )
            logger.error("=" * 70)
            sys.exit(1)

        # Log to audit trail that dangerous mode was used
        logger.warning("=" * 70)
        logger.warning("⚠️  DANGEROUS MODE ENABLED (ZINC_DANGEROUS_MODE=1)")
        logger.warning("⚠️  --skip-dependency-check IS ACTIVE")
        logger.warning("⚠️  You are bypassing safety gates. If training fails")
        logger.warning("⚠️  or produces garbage, that's on you.")
        logger.warning("=" * 70)

        # Write to audit log file
        audit_log = ARTIFACT_DIR / "dangerous_mode_usage.log"
        ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        with open(audit_log, "a") as f:
            f.write(
                f"{datetime.utcnow().isoformat()}Z | skip_dependency_check | user={os.getenv('USER', 'unknown')}\n"
            )

    # Run pipeline
    success = run_pipeline(
        symbol=args.symbol,
        horizons=args.horizons,
        start_phase=args.start_phase,
        stop_phase=args.stop_phase,
        dry_run=args.dry_run,
        skip_dependency_check=args.skip_dependency_check,
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
