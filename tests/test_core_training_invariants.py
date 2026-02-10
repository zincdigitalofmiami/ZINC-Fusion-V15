#!/usr/bin/env python3
"""
Test Core Training Package Invariants

These tests verify the structural guarantees of the training package:
1. Hash binding prevents stale data from being used
2. Dangerous mode requires explicit env var
3. zscore_normalize is disabled
4. Phase 5 checks block on violations
"""

__test__ = False  # Pytest should not collect integration scripts.


import os
import sys

# Ensure we can import from src
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def test_hash_mismatch_detection():
    """Test that hash mismatches are detected and rejected."""
    import json
    import tempfile
    from pathlib import Path
    from fusion.core_training import run_pipeline
    from fusion.core_training.run_pipeline import check_preflight_passed

    # Create temp gate artifact directory
    original_artifact_dir = run_pipeline.ARTIFACT_DIR
    temp_dir = Path(tempfile.mkdtemp())
    run_pipeline.ARTIFACT_DIR = temp_dir

    try:
        # Create a fake artifact with specific hashes
        artifact = {
            "passed": True,
            "hashes": {
                "core_matrix": "artifact_core_hash",
                "options": None,
                "elite": "artifact_elite_hash",
                "config": "artifact_config_hash",
            },
        }
        artifact_path = temp_dir / "phase5_audit.json"
        with open(artifact_path, "w") as f:
            json.dump(artifact, f)

        # Test 1: Hash mismatch should fail
        result, mismatches = check_preflight_passed(
            {
                "core_matrix": "wrong_hash",
                "options": None,
                "elite": "wrong_elite",
                "config": "wrong_config",
            }
        )
        assert result == False, "Hash mismatch should return False"
        assert len(mismatches) > 0, "Should have mismatch messages"
        print("✅ Test 1: Hash mismatch correctly detected")

        # Test 2: All hashes match should pass
        result, mismatches = check_preflight_passed(
            {
                "core_matrix": "artifact_core_hash",
                "options": None,
                "elite": "artifact_elite_hash",
                "config": "artifact_config_hash",
            }
        )
        assert result == True, f"Matching hashes should pass: {mismatches}"
        print("✅ Test 2: Matching hashes correctly accepted")

        # Test 3: Artifact shows failed should fail
        artifact["passed"] = False
        with open(artifact_path, "w") as f:
            json.dump(artifact, f)
        result, mismatches = check_preflight_passed(
            {
                "core_matrix": "artifact_core_hash",
                "options": None,
                "elite": "artifact_elite_hash",
                "config": "artifact_config_hash",
            }
        )
        assert result == False, "Failed artifact should block"
        print("✅ Test 3: Failed audit artifact correctly blocks training")

        # Test 4: No artifact should fail
        artifact_path.unlink()
        result, mismatches = check_preflight_passed(
            {"core_matrix": "any", "options": None, "elite": "any", "config": "any"}
        )
        assert result == False, "Missing artifact should fail"
        print("✅ Test 4: Missing artifact correctly blocks training")

    finally:
        # Restore original
        run_pipeline.ARTIFACT_DIR = original_artifact_dir
        # Cleanup temp dir
        import shutil

        shutil.rmtree(temp_dir, ignore_errors=True)


def test_dangerous_mode_guard():
    """Test that dangerous mode requires explicit env var."""
    from fusion.core_training.run_pipeline import check_dangerous_mode_enabled

    # Save original
    original = os.environ.get("ZINC_DANGEROUS_MODE")

    try:
        # Clear env var
        if "ZINC_DANGEROUS_MODE" in os.environ:
            del os.environ["ZINC_DANGEROUS_MODE"]

        enabled = check_dangerous_mode_enabled()
        assert enabled == False, "Should be disabled without env var"
        print("✅ Test 5: Dangerous mode disabled without env var")

        # Set wrong value
        os.environ["ZINC_DANGEROUS_MODE"] = "0"
        enabled = check_dangerous_mode_enabled()
        assert enabled == False, "Should be disabled with value '0'"
        print("✅ Test 6: Dangerous mode disabled with value '0'")

        # Set correct value
        os.environ["ZINC_DANGEROUS_MODE"] = "1"
        enabled = check_dangerous_mode_enabled()
        assert enabled == True, "Should be enabled with value '1'"
        print("✅ Test 7: Dangerous mode enabled with value '1'")

    finally:
        # Restore original
        if original is not None:
            os.environ["ZINC_DANGEROUS_MODE"] = original
        elif "ZINC_DANGEROUS_MODE" in os.environ:
            del os.environ["ZINC_DANGEROUS_MODE"]


def test_zscore_normalize_disabled():
    """Test that zscore_normalize raises RuntimeError."""
    from fusion.core_training.phase3_build_core_matrix import zscore_normalize
    import pandas as pd

    df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})

    try:
        zscore_normalize(df, exclude_cols=["a"])
        assert False, "zscore_normalize should raise RuntimeError"
    except RuntimeError as e:
        error_msg = str(e).lower()
        assert "deprecated" in error_msg or "leakage" in error_msg, f"Wrong error: {e}"
        print("✅ Test 8: zscore_normalize correctly disabled (raises RuntimeError)")


def test_config_hash_computation():
    """Test that config hash is computed correctly."""
    from fusion.core_training.phase5_audit_preflight import compute_config_hash

    hash1 = compute_config_hash()
    hash2 = compute_config_hash()

    assert hash1 == hash2, "Same config should produce same hash"
    assert len(hash1) == 16, f"Hash should be 16 chars (truncated SHA256): {hash1}"
    print(f"✅ Test 9: Config hash computed correctly: {hash1}")


def main():
    print("=" * 60)
    print("CORE TRAINING INVARIANT TESTS")
    print("=" * 60)
    print()

    test_hash_mismatch_detection()
    print()

    test_dangerous_mode_guard()
    print()

    test_zscore_normalize_disabled()
    print()

    test_config_hash_computation()
    print()

    print("=" * 60)
    print("ALL INVARIANT TESTS PASSED ✅")
    print("=" * 60)


if __name__ == "__main__":
    main()
