"""
ZINC-FUSION-V15 Validators

Pre-training validation tools to ensure data and schema integrity.
Run these BEFORE every training run.

Usage:
    # Full validation suite
    python -m src.fusion.validators.run_all

    # Individual validators
    python -m src.fusion.validators.schema_contract
    python -m src.fusion.validators.freshness_monitor
    python -m src.fusion.validators.quarantine_verifier

Validators:
- SchemaContractValidator: Ensures ingestion contract compliance (naming + columns)
- FreshnessMonitor: Checks for stale data based on cadence
- QuarantineVerifier: Tests quarantine pipeline functionality
"""

from .schema_contract import SchemaContractValidator
from .freshness_monitor import FreshnessMonitor
from .quarantine_verifier import QuarantineVerifier

__all__ = [
    "SchemaContractValidator",
    "FreshnessMonitor",
    "QuarantineVerifier",
]
