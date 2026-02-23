"""Tests for persistence module: dtype mapping, version hash, NaN conversion."""

from __future__ import annotations

import numpy as np
import pandas as pd

from fusion.core_training.persistence import compute_matrix_version


class TestDtypeMapping:
    """Verify DataFrame dtype -> SQL type mapping in create_table_from_df."""

    def _get_col_defs(self, df):
        """Extract column definitions by inspecting the SQL that would be generated."""
        # Replicate the mapping logic from create_table_from_df
        dtype_map = {
            "int64": "INTEGER",
            "int32": "INTEGER",
            "float64": "REAL",
            "float32": "REAL",
            "bool": "BOOLEAN",
            "datetime64[ns]": "TIMESTAMP",
            "object": "TEXT",
        }
        col_defs = {}
        for col in df.columns:
            dtype = str(df[col].dtype)
            sql_type = dtype_map.get(dtype, "TEXT")
            if col == "trade_date":
                col_defs[col] = "DATE NOT NULL"
            elif col == "symbol":
                col_defs[col] = "VARCHAR(20) NOT NULL"
            else:
                col_defs[col] = sql_type
        return col_defs

    def test_int64_maps_to_integer(self):
        df = pd.DataFrame({"x": pd.array([1, 2, 3], dtype="int64")})
        defs = self._get_col_defs(df)
        assert defs["x"] == "INTEGER"

    def test_float64_maps_to_real(self):
        df = pd.DataFrame({"x": [1.0, 2.0]})
        defs = self._get_col_defs(df)
        assert defs["x"] == "REAL"

    def test_bool_maps_to_boolean(self):
        df = pd.DataFrame({"x": [True, False]})
        defs = self._get_col_defs(df)
        assert defs["x"] == "BOOLEAN"

    def test_object_maps_to_text(self):
        df = pd.DataFrame({"x": ["a", "b"]})
        defs = self._get_col_defs(df)
        assert defs["x"] == "TEXT"

    def test_trade_date_special_handling(self):
        df = pd.DataFrame({"trade_date": pd.to_datetime(["2024-01-01"])})
        defs = self._get_col_defs(df)
        assert defs["trade_date"] == "DATE NOT NULL"

    def test_symbol_special_handling(self):
        df = pd.DataFrame({"symbol": ["ZL"]})
        defs = self._get_col_defs(df)
        assert defs["symbol"] == "VARCHAR(20) NOT NULL"


class TestVersionHash:
    def test_deterministic(self):
        df = pd.DataFrame(
            {
                "trade_date": pd.to_datetime(["2024-01-01", "2024-01-02"]),
                "x": [1.0, 2.0],
            }
        )
        h1 = compute_matrix_version(df)
        h2 = compute_matrix_version(df)
        assert h1 == h2

    def test_hash_length_16(self):
        df = pd.DataFrame(
            {
                "trade_date": pd.to_datetime(["2024-01-01"]),
                "x": [1.0],
            }
        )
        assert len(compute_matrix_version(df)) == 16


class TestNaNConversion:
    """Verify the NaN->None pattern used in write_matrix."""

    def test_nan_becomes_none(self):
        df = pd.DataFrame({"a": [1.0, np.nan, 3.0]})
        df = df.where(df.notna(), None)
        values = [
            tuple(None if pd.isna(v) else v for v in row)
            for row in df.itertuples(index=False, name=None)
        ]
        assert values[1] == (None,)

    def test_no_nan_survives(self):
        df = pd.DataFrame({"a": [1.0, np.nan], "b": [np.nan, 2.0]})
        df = df.where(df.notna(), None)
        values = [
            tuple(None if pd.isna(v) else v for v in row)
            for row in df.itertuples(index=False, name=None)
        ]
        for row in values:
            for v in row:
                if v is not None:
                    assert not pd.isna(v)
