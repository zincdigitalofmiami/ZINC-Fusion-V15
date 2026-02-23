"""Tests for frozen config constants in core_training.config."""

from __future__ import annotations

from fusion.core_training.config import (
    HORIZONS,
    MODEL_ZOO_FROZEN,
    TARGET_SYMBOL,
)
from fusion.specialists.base import SPECIALIST_BUCKETS


class TestFrozenConstants:
    def test_target_symbol_is_zl(self):
        assert TARGET_SYMBOL == "ZL"

    def test_horizons(self):
        assert HORIZONS == [5, 21, 63, 126]

    def test_model_zoo_is_frozenset(self):
        assert isinstance(MODEL_ZOO_FROZEN, frozenset)

    def test_model_zoo_has_expected_count(self):
        # 5 baselines + 10 statistical + 3 tabular + 1 foundation = 19
        assert len(MODEL_ZOO_FROZEN) == 19

    def test_model_zoo_contains_key_models(self):
        assert "Naive" in MODEL_ZOO_FROZEN
        assert "AutoETS" in MODEL_ZOO_FROZEN
        assert "DirectTabular" in MODEL_ZOO_FROZEN
        assert "Chronos2" in MODEL_ZOO_FROZEN

    def test_specialist_buckets_has_11_entries(self):
        assert len(SPECIALIST_BUCKETS) == 11

    def test_specialist_buckets_includes_trump_effect(self):
        assert "trump_effect" in SPECIALIST_BUCKETS
