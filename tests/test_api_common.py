"""Tests for API SQL safety and serialization helpers."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest
from fastapi import HTTPException

from fusion.api.routers.common import _serialize_value, _validate_readonly_sql


class TestReadonlyValidation:
    def test_allows_select(self):
        result = _validate_readonly_sql("SELECT * FROM mkt.futures_1d")
        assert result.startswith("SELECT")

    def test_allows_with(self):
        result = _validate_readonly_sql("WITH cte AS (SELECT 1) SELECT * FROM cte")
        assert result.startswith("WITH")

    def test_rejects_insert(self):
        with pytest.raises(HTTPException) as exc_info:
            _validate_readonly_sql("INSERT INTO mkt.futures_1d VALUES (1)")
        assert exc_info.value.status_code == 400

    def test_rejects_drop(self):
        with pytest.raises(HTTPException):
            _validate_readonly_sql("DROP TABLE mkt.futures_1d")

    def test_rejects_update(self):
        with pytest.raises(HTTPException):
            _validate_readonly_sql("UPDATE mkt.futures_1d SET close = 0")

    def test_rejects_delete(self):
        with pytest.raises(HTTPException):
            _validate_readonly_sql("DELETE FROM mkt.futures_1d")

    def test_rejects_semicolons(self):
        with pytest.raises(HTTPException) as exc_info:
            _validate_readonly_sql("SELECT 1; DROP TABLE mkt.futures_1d")
        assert "Semicolons" in exc_info.value.detail

    def test_rejects_empty_query(self):
        with pytest.raises(HTTPException) as exc_info:
            _validate_readonly_sql("")
        assert exc_info.value.status_code == 400

    def test_rejects_non_select_start(self):
        with pytest.raises(HTTPException):
            _validate_readonly_sql("EXPLAIN SELECT 1")


class TestSerializeValue:
    def test_datetime_to_iso(self):
        dt = datetime(2024, 6, 15, 12, 30, 0)
        assert _serialize_value(dt) == "2024-06-15T12:30:00"

    def test_date_to_iso(self):
        d = date(2024, 6, 15)
        assert _serialize_value(d) == "2024-06-15"

    def test_decimal_to_float(self):
        result = _serialize_value(Decimal("3.14"))
        assert result == pytest.approx(3.14)
        assert isinstance(result, float)

    def test_passthrough(self):
        assert _serialize_value(42) == 42
        assert _serialize_value("hello") == "hello"
        assert _serialize_value(None) is None
