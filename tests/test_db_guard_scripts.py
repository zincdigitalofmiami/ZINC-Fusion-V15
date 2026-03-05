"""Unit tests for DB guardrail scripts (logic-only, no live DB required)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load_script_module(rel_path: str, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, ROOT / rel_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


db_guard = _load_script_module("scripts/db_identity_guard.py", "db_identity_guard")
sync_db = _load_script_module(
    "scripts/sync_cloud_to_local_db.py", "sync_cloud_to_local_db"
)
backfill = _load_script_module(
    "scripts/backfill_model_runs_event.py", "backfill_model_runs_event"
)


def test_db_guard_normalize_url_appends_gssencmode():
    out = db_guard.normalize_url("postgresql://user:pass@db.prisma.io:5432/postgres")
    assert out.endswith("gssencmode=disable")


def test_db_guard_normalize_url_rejects_prisma_scheme():
    with pytest.raises(SystemExit):
        db_guard.normalize_url("prisma+postgres://example")


def test_db_guard_host_db_constraints_accepts_cloud():
    db_guard.check_host_db_constraints("cloud", "db.prisma.io", "postgres")


def test_db_guard_host_db_constraints_rejects_wrong_local_db():
    with pytest.raises(SystemExit):
        db_guard.check_host_db_constraints(
            "local-runtime", "localhost", "rabid_raccoon"
        )


def test_sync_validate_urls_accepts_expected_contract():
    sync_db.validate_urls(
        "postgresql://user:pass@db.prisma.io:5432/postgres",
        "postgresql://postgres:postgres@127.0.0.1:5432/zinc_fusion_v15_local",
    )


def test_sync_validate_urls_rejects_non_local_destination():
    with pytest.raises(SystemExit):
        sync_db.validate_urls(
            "postgresql://user:pass@db.prisma.io:5432/postgres",
            "postgresql://user:pass@db.prisma.io:5432/zinc_fusion_v15_local",
        )


def test_sync_parse_tables_rejects_unknown_table():
    with pytest.raises(SystemExit):
        sync_db.parse_tables(["training.unknown_table"])


def test_backfill_pinball_loss_returns_float():
    y_true = np.array([10.0, 11.0, 12.0], dtype=float)
    y_pred = np.array([9.0, 11.5, 11.0], dtype=float)
    loss = backfill.pinball_loss(y_true, y_pred, 0.5)
    assert isinstance(loss, float)
    assert loss >= 0.0
