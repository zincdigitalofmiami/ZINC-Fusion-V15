"""Tests for SignalOutput dataclass validation contract."""

from __future__ import annotations

from datetime import date

import pytest

from fusion.specialists.base import SPECIALIST_BUCKETS, SignalOutput


class TestSignalOutputValid:
    """Valid construction scenarios."""

    def test_valid_output(self, valid_signal_output):
        so = SignalOutput(**valid_signal_output())
        assert so.signal_1 == 0.75
        assert so.bucket == "crush"

    @pytest.mark.parametrize("bucket", sorted(SPECIALIST_BUCKETS))
    def test_all_11_buckets_accepted(self, valid_signal_output, bucket):
        so = SignalOutput(**valid_signal_output(bucket=bucket))
        assert so.bucket == bucket

    def test_to_dict_prefers_conf_over_confidence(self, valid_signal_output):
        so = SignalOutput(**valid_signal_output(conf=0.9, confidence=0.5))
        d = so.to_dict()
        assert d["conf"] == 0.9


class TestSignalOutputDateValidation:
    """Date boundary enforcement."""

    def test_rejects_pre_1990_date(self, valid_signal_output):
        with pytest.raises(ValueError, match="1990"):
            SignalOutput(**valid_signal_output(as_of_date=date(1989, 12, 31)))

    def test_rejects_epoch_date(self, valid_signal_output):
        with pytest.raises(ValueError, match="1990"):
            SignalOutput(**valid_signal_output(as_of_date=date(1970, 1, 1)))

    def test_accepts_modern_date(self, valid_signal_output):
        so = SignalOutput(**valid_signal_output(as_of_date=date(2024, 6, 1)))
        assert so.as_of_date == date(2024, 6, 1)


class TestSignalOutputBucketValidation:
    """Bucket membership enforcement."""

    def test_rejects_invalid_bucket(self, valid_signal_output):
        with pytest.raises(ValueError, match="bucket"):
            SignalOutput(**valid_signal_output(bucket="nonexistent"))


class TestSignalOutputNumericValidation:
    """Numeric field enforcement."""

    def test_rejects_nan_signal_1(self, valid_signal_output):
        with pytest.raises(ValueError, match="signal_1"):
            SignalOutput(**valid_signal_output(signal_1=float("nan")))

    def test_rejects_inf_signal_1(self, valid_signal_output):
        with pytest.raises(ValueError, match="signal_1"):
            SignalOutput(**valid_signal_output(signal_1=float("inf")))

    def test_rejects_nan_signal_2(self, valid_signal_output):
        with pytest.raises(ValueError, match="signal_2"):
            SignalOutput(**valid_signal_output(signal_2=float("nan")))

    def test_rejects_conf_above_1(self, valid_signal_output):
        with pytest.raises(ValueError, match="conf"):
            SignalOutput(**valid_signal_output(conf=1.5))

    def test_rejects_conf_below_0(self, valid_signal_output):
        with pytest.raises(ValueError, match="conf"):
            SignalOutput(**valid_signal_output(conf=-0.1))

    def test_rejects_confidence_above_1(self, valid_signal_output):
        with pytest.raises(ValueError, match="confidence"):
            SignalOutput(**valid_signal_output(confidence=1.5, conf=None))

    def test_rejects_negative_max_input_age_days(self, valid_signal_output):
        with pytest.raises(ValueError, match="max_input_age_days"):
            SignalOutput(**valid_signal_output(max_input_age_days=-1))


class TestSignalOutputBoolValidation:
    """Boolean field enforcement."""

    def test_rejects_non_bool_abstained(self, valid_signal_output):
        with pytest.raises((ValueError, TypeError)):
            SignalOutput(**valid_signal_output(abstained="yes"))

    def test_rejects_non_bool_warmup(self, valid_signal_output):
        with pytest.raises((ValueError, TypeError)):
            SignalOutput(**valid_signal_output(warmup="yes"))
