"""
Training environment initialization for ZINC-FUSION-V15.

Import this FIRST in training scripts to:
1. Set macOS-specific environment variables
2. Filter known harmless warnings (AutoGluon, joblib)
3. Register multiprocessing cleanup handlers

Usage:
    #!/usr/bin/env python3
    import scripts._init_env  # noqa: F401 - MUST BE FIRST

    # ... rest of imports
"""

import atexit
import gc
import os
import warnings

# =============================================================================
# ENVIRONMENT SETUP (before any imports that might use these)
# =============================================================================

# Disable Ray on macOS (causes GCS failures)
os.environ.setdefault("AUTOGLUON_DISABLE_RAY", "1")

# TensorFlow/Keras settings for M-series Macs
os.environ.setdefault("TF_USE_LEGACY_KERAS", "1")
os.environ.setdefault("KERAS_BACKEND", "tensorflow")
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")


# =============================================================================
# WARNING FILTERS
# =============================================================================

# AutoGluon uses deprecated pandas frequency alias 'H' internally
# This is in AutoGluon's code, not ours - filter until they update
warnings.filterwarnings(
    "ignore",
    message=r".*'H' is deprecated.*",
    category=FutureWarning,
)

# Joblib/loky semlock warnings on macOS - we handle cleanup below
warnings.filterwarnings(
    "ignore",
    message=r".*leaked semlock.*",
    category=UserWarning,
)
warnings.filterwarnings(
    "ignore",
    message=r".*resource_tracker.*",
    category=UserWarning,
)


# =============================================================================
# MULTIPROCESSING CLEANUP (macOS semlock fix)
# =============================================================================


def _cleanup_joblib():
    """
    Properly shutdown joblib executor to prevent semlock leaks.

    On macOS, joblib's loky backend can leak semaphore objects
    if not explicitly shutdown before process exit.
    """
    try:
        from joblib.externals.loky import get_reusable_executor

        executor = get_reusable_executor()
        executor.shutdown(wait=True, kill_workers=True)
    except Exception:
        pass

    gc.collect()


atexit.register(_cleanup_joblib)
