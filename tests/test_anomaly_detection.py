"""Tests for AnomalyDetector rules."""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from fusion.validators.anomaly_detection import AnomalyDetector


class TestMarketFuturesDetector:
    def test_empty_df_returns_zero(self):
        det = AnomalyDetector()
        result = det.detect_market_futures(pd.DataFrame())
        assert result["anomaly_count"] == 0

    def test_price_spike_detected(self):
        dates = pd.date_range("2024-01-01", periods=3, freq="B")
        df = pd.DataFrame(
            {
                "symbol": ["ZL"] * 3,
                "event_date": dates,
                "open": [50.0, 50.0, 50.0],
                "high": [51.0, 60.0, 51.0],
                "low": [49.0, 49.0, 49.0],
                "close": [50.0, 60.0, 50.0],  # 20% spike
                "volume": [1000, 1000, 1000],
            }
        )
        result = AnomalyDetector().detect_market_futures(df)
        assert result["anomaly_count"] > 0
        assert (
            "price_spike" in result["quality_issues"]
            or "price_extreme" in result["quality_issues"]
        )

    def test_invalid_ohlc_detected(self):
        dates = pd.date_range("2024-01-01", periods=2, freq="B")
        df = pd.DataFrame(
            {
                "symbol": ["ZL"] * 2,
                "event_date": dates,
                "open": [50.0, 50.0],
                "high": [48.0, 51.0],  # high < low on first row
                "low": [49.0, 49.0],
                "close": [50.0, 50.0],
                "volume": [1000, 1000],
            }
        )
        result = AnomalyDetector().detect_market_futures(df)
        assert "invalid_ohlc" in result["quality_issues"]

    def test_volume_zero_detected(self):
        dates = pd.date_range("2024-01-01", periods=2, freq="B")
        df = pd.DataFrame(
            {
                "symbol": ["ZL"] * 2,
                "event_date": dates,
                "open": [50.0, 50.0],
                "high": [51.0, 51.0],
                "low": [49.0, 49.0],
                "close": [50.0, 50.0],
                "volume": [1000, 0],
            }
        )
        result = AnomalyDetector().detect_market_futures(df)
        assert "volume_zero" in result["quality_issues"]

    def test_weekend_data_detected(self):
        # 2024-01-06 is a Saturday
        df = pd.DataFrame(
            {
                "symbol": ["ZL"],
                "event_date": [datetime(2024, 1, 6)],
                "open": [50.0],
                "high": [51.0],
                "low": [49.0],
                "close": [50.0],
                "volume": [1000],
            }
        )
        result = AnomalyDetector().detect_market_futures(df)
        assert "weekend_data" in result["quality_issues"]


class TestWeatherDetector:
    def test_empty_returns_zero(self):
        result = AnomalyDetector().detect_weather(pd.DataFrame())
        assert result["anomaly_count"] == 0

    def test_temp_extreme_high(self):
        df = pd.DataFrame(
            {
                "event_date": [datetime(2024, 7, 1)],
                "region": ["us_midwest"],
                "tavg_c": [55.0],  # > 50
                "tmin_c": [30.0],
                "tmax_c": [60.0],
                "prcp_mm": [0.0],
            }
        )
        result = AnomalyDetector().detect_weather(df)
        assert "temp_extreme_high" in result["quality_issues"]

    def test_negative_precip(self):
        df = pd.DataFrame(
            {
                "event_date": [datetime(2024, 7, 1)],
                "region": ["us_midwest"],
                "tavg_c": [25.0],
                "tmin_c": [20.0],
                "tmax_c": [30.0],
                "prcp_mm": [-5.0],
            }
        )
        result = AnomalyDetector().detect_weather(df)
        assert "precip_negative" in result["quality_issues"]
