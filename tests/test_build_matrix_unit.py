from __future__ import annotations

import numpy as np
import pandas as pd

from fusion.core_training.build_matrix import ffill_with_age, ffill_with_ttl


def test_ffill_with_ttl_expires_on_calendar_days() -> None:
    index = pd.to_datetime(["2026-01-02", "2026-01-05", "2026-01-06"])  # Fri, Mon, Tue
    series = pd.Series([10.0, np.nan, np.nan], index=index)

    filled = ffill_with_ttl(series, ttl_days=2, weekend_exempt=False)

    assert filled.iloc[0] == 10.0
    assert np.isnan(filled.iloc[1])  # 3-day calendar gap from Friday to Monday
    assert np.isnan(filled.iloc[2])  # 4-day calendar gap from Friday to Tuesday


def test_ffill_with_ttl_weekend_exempt_preserves_weekend_gap() -> None:
    index = pd.to_datetime(["2026-01-02", "2026-01-05", "2026-01-06"])  # Fri, Mon, Tue
    series = pd.Series([10.0, np.nan, np.nan], index=index)

    filled = ffill_with_ttl(series, ttl_days=2, weekend_exempt=True)

    assert filled.iloc[0] == 10.0
    assert filled.iloc[1] == 10.0
    assert filled.iloc[2] == 10.0


def test_ffill_with_age_returns_calendar_age_even_with_weekend_exempt() -> None:
    index = pd.to_datetime(["2026-01-02", "2026-01-05", "2026-01-06"])  # Fri, Mon, Tue
    series = pd.Series([10.0, np.nan, np.nan], index=index)

    filled, age_days = ffill_with_age(series, ttl_days=2, weekend_exempt=True)

    assert filled.tolist() == [10.0, 10.0, 10.0]
    assert age_days.tolist() == [0.0, 3.0, 4.0]
