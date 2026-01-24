#!/usr/bin/env python3
"""
repair_63d_trainer.py

Surgical repair of the 63d trainer.pkl that has an empty model_graph.
The model files exist on disk but were never registered in the trainer.

This script:
1. Works on the BACKUP first (safe)
2. Scans for physical model directories
3. Adds them as nodes to the trainer's model_graph
4. Sets model_best to a valid model
5. Saves the repaired trainer

After verification, the fixed trainer can be copied to production.
"""

import pickle
import shutil
from pathlib import Path
from datetime import datetime

# Paths (update to current Core family)
BACKUP_DIR = Path("/Volumes/Satechi Hub/Training Evaluations - Last 5/core_v2/horizon_63d/core_v2_20260124_120000__20260124T120000Z")
PRODUCTION_DIR = Path("/Volumes/Satechi Hub/ZINC-FUSION-V15/models/core_v2/horizon_63d")


def repair_trainer(model_base_dir: Path, dry_run: bool = False):
    """Repair the trainer.pkl by registering discovered models."""

    trainer_path = model_base_dir / "models" / "trainer.pkl"

    print(f"Repairing trainer at: {trainer_path}")
    print(f"  Dry run: {dry_run}")
    print()

    if not trainer_path.exists():
        print("ERROR: trainer.pkl not found!")
        return False

    # Load the trainer
    with open(trainer_path, 'rb') as f:
        trainer = pickle.load(f)

    print(f"Current state:")
    print(f"  model_graph nodes: {list(trainer.model_graph.nodes())}")
    print(f"  model_best: {trainer.model_best}")
    print()

    # Scan for model directories (each should have model.pkl)
    models_dir = model_base_dir / "models"
    found_models = []

    for item in models_dir.iterdir():
        if item.is_dir() and (item / "model.pkl").exists():
            model_name = item.name
            found_models.append(model_name)
            print(f"  Found model: {model_name}")

    if not found_models:
        print("ERROR: No model directories with model.pkl found!")
        return False

    print()
    print(f"Found {len(found_models)} models on disk")

    # Add models to graph
    for model_name in found_models:
        if model_name not in trainer.model_graph.nodes():
            trainer.model_graph.add_node(model_name)
            print(f"  Added to graph: {model_name}")

    # Set model_best to first available model (prefer Chronos2 if present)
    if "Chronos2" in found_models:
        trainer.model_best = "Chronos2"
    else:
        trainer.model_best = found_models[0]

    print()
    print(f"Repaired state:")
    print(f"  model_graph nodes: {list(trainer.model_graph.nodes())}")
    print(f"  model_best: {trainer.model_best}")

    if dry_run:
        print()
        print("DRY RUN - not saving changes")
        return True

    # Backup original trainer
    backup_path = trainer_path.with_suffix(f".pkl.bak.{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    shutil.copy2(trainer_path, backup_path)
    print()
    print(f"Original backed up to: {backup_path}")

    # Save repaired trainer
    with open(trainer_path, 'wb') as f:
        pickle.dump(trainer, f)

    print(f"Saved repaired trainer to: {trainer_path}")
    return True


def verify_repair(model_base_dir: Path):
    """Verify the repaired trainer loads correctly."""
    from autogluon.timeseries import TimeSeriesPredictor

    print()
    print("=" * 60)
    print("VERIFICATION")
    print("=" * 60)

    try:
        predictor = TimeSeriesPredictor.load(str(model_base_dir))
        print(f"  prediction_length: {predictor.prediction_length}")
        print(f"  model_names: {predictor.model_names()}")
        print(f"  model_best: {predictor.model_best}")
        print()
        print("VERIFICATION PASSED")
        return True
    except Exception as e:
        print(f"VERIFICATION FAILED: {e}")
        return False


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Repair 63d trainer.pkl")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without saving")
    parser.add_argument("--production", action="store_true", help="Repair production instead of backup")
    parser.add_argument("--verify-only", action="store_true", help="Only verify, don't repair")
    args = parser.parse_args()

    target_dir = PRODUCTION_DIR if args.production else BACKUP_DIR

    print("=" * 60)
    print("63d TRAINER REPAIR")
    print("=" * 60)
    print(f"Target: {target_dir}")
    print()

    if args.verify_only:
        verify_repair(target_dir)
        return

    success = repair_trainer(target_dir, dry_run=args.dry_run)

    if success and not args.dry_run:
        verify_repair(target_dir)


if __name__ == "__main__":
    main()
