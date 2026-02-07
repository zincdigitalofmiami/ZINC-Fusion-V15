#!/usr/bin/env python3
"""
backup_model_training.py

Safe backup utility for AutoGluon model directories.
- Copy first
- Verify
- Prune to last N
- Append to manifest

Usage:
    python scripts/backup_model_training.py \
      --source "models/core_v2/horizon_63d" \
      --archive-root "/Volumes/Satechi Hub/Training Evaluations - Last 5" \
      --family core_v2 \
      --horizon horizon_63d \
      --training-run-id "core_v2_20260124_120000" \
      --hash
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# AutoGluon 1.5 structure: trainer.pkl is inside models/
REQUIRED_FILES = [
    "predictor.pkl",
    "learner.pkl",
    "version.txt",
]
# Nested files for full verification (trainer + actual Chronos2 weights)
REQUIRED_NESTED = [
    "models/trainer.pkl",
    "models/Chronos2/model.pkl",  # The actual model weights - critical
]
REQUIRED_DIRS = [
    "models",
]

DEFAULT_KEEP_LAST = 5


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def file_meta(path: Path, do_hash: bool) -> Dict[str, Optional[str]]:
    if not path.exists():
        return {"path": str(path), "exists": False, "size_bytes": None, "sha256": None}
    meta = {"path": str(path), "exists": True, "size_bytes": path.stat().st_size, "sha256": None}
    if do_hash:
        meta["sha256"] = sha256_file(path)
    return meta


def verify_backup(dst: Path) -> Tuple[bool, List[str]]:
    missing: List[str] = []
    for rf in REQUIRED_FILES:
        if not (dst / rf).exists():
            missing.append(rf)
    for rn in REQUIRED_NESTED:
        if not (dst / rn).exists():
            missing.append(rn)
    for rd in REQUIRED_DIRS:
        if not (dst / rd).is_dir():
            missing.append(f"{rd}/")
    return (len(missing) == 0), missing


def list_backups(horizon_dir: Path) -> List[Path]:
    if not horizon_dir.exists():
        return []
    dirs = [p for p in horizon_dir.iterdir() if p.is_dir() and not p.name.startswith(".")]
    dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return dirs


def prune_old(horizon_dir: Path, keep_last: int) -> List[Path]:
    backups = list_backups(horizon_dir)
    to_delete = backups[keep_last:]
    deleted: List[Path] = []
    for p in to_delete:
        shutil.rmtree(p, ignore_errors=False)
        deleted.append(p)
    return deleted


def append_manifest(manifest_path: Path, record: dict) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    if manifest_path.exists():
        data = json.loads(manifest_path.read_text())
        if not isinstance(data, list):
            data = [data]
    else:
        data = []
    data.append(record)
    manifest_path.write_text(json.dumps(data, indent=2, sort_keys=False))


def main() -> None:
    ap = argparse.ArgumentParser(description="Safe backup for AutoGluon model directories")
    ap.add_argument("--source", required=True, help="Source model directory")
    ap.add_argument("--archive-root", required=True, help="Archive root directory")
    ap.add_argument("--family", required=True, help="Model family (core_v2, specialists)")
    ap.add_argument("--horizon", required=True, help="Horizon label (horizon_63d)")
    ap.add_argument("--training-run-id", required=True, help="Canonical training_run_id")
    ap.add_argument("--keep-last", type=int, default=DEFAULT_KEEP_LAST, help="Backups to keep")
    ap.add_argument("--hash", action="store_true", help="Compute sha256 for key files")
    args = ap.parse_args()

    src = Path(args.source).resolve()
    if not src.exists() or not src.is_dir():
        raise SystemExit(f"Source directory does not exist: {src}")

    archive_root = Path(args.archive_root).resolve()
    horizon_dir = archive_root / args.family / args.horizon
    horizon_dir.mkdir(parents=True, exist_ok=True)

    backup_name = f"{args.training_run_id}__{utc_stamp()}"
    dst = horizon_dir / backup_name

    tmp = horizon_dir / f".tmp__{backup_name}"
    if tmp.exists():
        shutil.rmtree(tmp)

    print(f"Copying {src} -> {tmp}")
    shutil.copytree(src, tmp, dirs_exist_ok=False)

    ok, missing = verify_backup(tmp)
    if not ok:
        shutil.rmtree(tmp, ignore_errors=True)
        raise SystemExit(f"Backup verification failed. Missing: {missing}")

    tmp.rename(dst)
    print(f"Verified and renamed to {dst}")

    record = {
        "training_run_id": args.training_run_id,
        "family": args.family,
        "horizon": args.horizon,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_path": str(src),
        "archive_path": str(dst),
        "source_mtime": datetime.fromtimestamp(src.stat().st_mtime, tz=timezone.utc).isoformat(),
        "files": {
            "predictor.pkl": file_meta(dst / "predictor.pkl", args.hash),
            "learner.pkl": file_meta(dst / "learner.pkl", args.hash),
            "models/trainer.pkl": file_meta(dst / "models" / "trainer.pkl", args.hash),
            "models/Chronos2/model.pkl": file_meta(dst / "models" / "Chronos2" / "model.pkl", args.hash),
            "version.txt": file_meta(dst / "version.txt", args.hash),
        },
    }

    manifest_path = archive_root / "metadata" / "training_manifest.json"
    append_manifest(manifest_path, record)
    print(f"Manifest updated: {manifest_path}")

    deleted = prune_old(horizon_dir, args.keep_last)
    print(f"\nBACKUP OK: {dst}")
    if deleted:
        print("PRUNED:")
        for d in deleted:
            print(f"  - {d}")


if __name__ == "__main__":
    main()
