"""
ZINC-FUSION Anomaly Detection Module

Detects anomalies in landing tables and logs results to ops.data_quality_log.
Does NOT modify landing tables - append-only architecture.

Usage:
    # Check all tables
    python -m src.fusion.validators.anomaly_detection --check-all

    # Check specific table
    python -m src.fusion.validators.anomaly_detection --table mkt.futures_1d

    # Dry run (no writes)
    python -m src.fusion.validators.anomaly_detection --check-all --dry-run
"""

import os
import sys
import argparse
import logging
from typing import Dict, Optional, Any
from datetime import datetime
from dataclasses import dataclass

import pandas as pd
import psycopg2
from psycopg2.extras import Json

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# =============================================================================
# TABLE CONFIGURATION - Correct schema mappings
# =============================================================================

# Tables to check with their source queries
TABLE_CONFIG = {
    # Market data
    "mkt.futures_1d": {
        "query": """
            SELECT event_date, symbol, open, high, low, close, volume
            FROM mkt.futures_1d
            ORDER BY symbol, event_date
        """,
        "detector": "market_futures",
        "group_by": "symbol",
        "date_col": "event_date",
    },
    "mkt.etf_1d": {
        "query": """
            SELECT event_date, symbol, open, high, low, close, volume
            FROM mkt.etf_1d
            ORDER BY symbol, event_date
        """,
        "detector": "market_futures",
        "group_by": "symbol",
        "date_col": "event_date",
    },
    "mkt.fx_1d": {
        "query": """
            SELECT id, pair, event_date, rate
            FROM mkt.fx_1d
            ORDER BY pair, event_date
        """,
        "detector": "fx",
        "group_by": "pair",
        "date_col": "event_date",
    },
    # Alternative data
    "alt.weather_1d": {
        "query": """
            SELECT id, event_date, region, tavg_c, tmin_c, tmax_c, prcp_mm
            FROM alt.weather_1d
        """,
        "detector": "weather",
        "group_by": None,
        "date_col": "event_date",
    },
    "alt.policy_news": {
        "query": """
            SELECT id, event_date, headline, zl_sentiment
            FROM alt.policy_news
        """,
        "detector": "news",
        "group_by": None,
        "date_col": "event_date",
    },
    # Positioning data
    "pos.cftc_1w": {
        "query": """
            SELECT id, event_date, symbol, open_interest, managed_money_net
            FROM pos.cftc_1w
            ORDER BY symbol, event_date
        """,
        "detector": "cot",
        "group_by": "symbol",
        "date_col": "event_date",
    },
    # Supply data
    "supply.epa_rin_1d": {
        "query": """
            SELECT id, event_date, rin_type, price
            FROM supply.epa_rin_1d
            ORDER BY rin_type, event_date
        """,
        "detector": "rin",
        "group_by": "rin_type",
        "date_col": "event_date",
    },
    # Economic data - 8 FRED tables
    "econ.rates_1d": {
        "query": """
            SELECT id, series_id, event_date, value
            FROM econ.rates_1d
            ORDER BY series_id, event_date
        """,
        "detector": "fred",
        "group_by": "series_id",
        "date_col": "event_date",
    },
    "econ.inflation_1d": {
        "query": """
            SELECT id, series_id, event_date, value
            FROM econ.inflation_1d
            ORDER BY series_id, event_date
        """,
        "detector": "fred",
        "group_by": "series_id",
        "date_col": "event_date",
    },
    "econ.labor_1d": {
        "query": """
            SELECT id, series_id, event_date, value
            FROM econ.labor_1d
            ORDER BY series_id, event_date
        """,
        "detector": "fred",
        "group_by": "series_id",
        "date_col": "event_date",
    },
    "econ.activity_1d": {
        "query": """
            SELECT id, series_id, event_date, value
            FROM econ.activity_1d
            ORDER BY series_id, event_date
        """,
        "detector": "fred",
        "group_by": "series_id",
        "date_col": "event_date",
    },
    "econ.vol_indices_1d": {
        "query": """
            SELECT id, series_id, event_date, value
            FROM econ.vol_indices_1d
            ORDER BY series_id, event_date
        """,
        "detector": "fred",
        "group_by": "series_id",
        "date_col": "event_date",
    },
    "econ.commodities_1d": {
        "query": """
            SELECT id, series_id, event_date, value
            FROM econ.commodities_1d
            ORDER BY series_id, event_date
        """,
        "detector": "fred",
        "group_by": "series_id",
        "date_col": "event_date",
    },
    "econ.money_1d": {
        "query": """
            SELECT id, series_id, event_date, value
            FROM econ.money_1d
            ORDER BY series_id, event_date
        """,
        "detector": "fred",
        "group_by": "series_id",
        "date_col": "event_date",
    },
}


# =============================================================================
# ANOMALY THRESHOLDS
# =============================================================================


@dataclass
class AnomalyThresholds:
    """Thresholds for anomaly detection."""

    zscore_extreme: float = 4.0  # >4 std = extreme outlier
    zscore_warning: float = 3.0  # >3 std = warning
    pct_change_spike: float = 0.15  # 15% single-day move
    pct_change_extreme: float = 0.25  # 25% single-day move
    gap_threshold: float = 0.05  # 5% gap up/down
    volume_spike_mult: float = 5.0  # 5x average volume


# =============================================================================
# ANOMALY DETECTION CLASS
# =============================================================================


class AnomalyDetector:
    """Detects anomalies in data tables."""

    def __init__(self, thresholds: Optional[AnomalyThresholds] = None):
        self.thresholds = thresholds or AnomalyThresholds()

    def detect_market_futures(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Detect anomalies in market/ETF OHLCV data."""
        anomalies = []

        if df.empty:
            return {"anomaly_count": 0, "anomalies": [], "quality_issues": []}

        for symbol, group in df.groupby("symbol"):
            group = group.sort_values("event_date").copy()

            for i, (idx, row) in enumerate(group.iterrows()):
                flags = []
                prior_row = group.iloc[i - 1] if i > 0 else None

                # Price spike detection
                if (
                    prior_row is not None
                    and prior_row["close"]
                    and prior_row["close"] > 0
                ):
                    pct_change = (
                        abs(row["close"] - prior_row["close"]) / prior_row["close"]
                    )
                    if pct_change > self.thresholds.pct_change_extreme:
                        flags.append("price_extreme")
                    elif pct_change > self.thresholds.pct_change_spike:
                        flags.append("price_spike")

                # Gap detection
                if (
                    prior_row is not None
                    and prior_row["close"]
                    and prior_row["close"] > 0
                    and row["open"]
                ):
                    gap = (row["open"] - prior_row["close"]) / prior_row["close"]
                    if gap > self.thresholds.gap_threshold:
                        flags.append("gap_up")
                    elif gap < -self.thresholds.gap_threshold:
                        flags.append("gap_down")

                # Volume spike
                if i >= 20 and row.get("volume"):
                    avg_vol = group.iloc[i - 20 : i]["volume"].mean()
                    if (
                        avg_vol
                        and avg_vol > 0
                        and row["volume"] > avg_vol * self.thresholds.volume_spike_mult
                    ):
                        flags.append("volume_spike")

                # Zero volume
                if row.get("volume") == 0:
                    flags.append("volume_zero")

                # Invalid OHLC
                if row.get("high") and row.get("low") and row["high"] < row["low"]:
                    flags.append("invalid_ohlc")

                # Weekend data
                if (
                    hasattr(row["event_date"], "weekday")
                    and row["event_date"].weekday() >= 5
                ):
                    flags.append("weekend_data")

                if flags:
                    anomalies.append(
                        {
                            "date": str(row["event_date"]),
                            "symbol": symbol,
                            "flags": flags,
                        }
                    )

        return {
            "anomaly_count": len(anomalies),
            "anomalies": anomalies[:100],  # Cap at 100 for JSON size
            "quality_issues": list(set(f for a in anomalies for f in a["flags"])),
        }

    def detect_weather(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Detect anomalies in weather data."""
        anomalies = []

        for idx, row in df.iterrows():
            flags = []

            # Temperature checks
            if pd.notna(row.get("tavg_c")):
                if row["tavg_c"] > 50:
                    flags.append("temp_extreme_high")
                elif row["tavg_c"] < -50:
                    flags.append("temp_extreme_low")

            if pd.notna(row.get("tmax_c")) and pd.notna(row.get("tmin_c")):
                if row["tmax_c"] - row["tmin_c"] > 40:
                    flags.append("temp_spike")

            # Precipitation checks
            if pd.notna(row.get("prcp_mm")):
                if row["prcp_mm"] < 0:
                    flags.append("precip_negative")
                elif row["prcp_mm"] > 200:
                    flags.append("precip_extreme")

            if flags:
                anomalies.append(
                    {
                        "date": str(row.get("event_date")),
                        "region": row.get("region"),
                        "flags": flags,
                    }
                )

        return {
            "anomaly_count": len(anomalies),
            "anomalies": anomalies[:100],
            "quality_issues": list(set(f for a in anomalies for f in a["flags"])),
        }

    def detect_fred(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Detect anomalies in FRED economic data."""
        anomalies = []

        if df.empty:
            return {"anomaly_count": 0, "anomalies": [], "quality_issues": []}

        for series_id, group in df.groupby("series_id"):
            group = group.sort_values("event_date").copy()

            # Calculate rolling stats
            if len(group) >= 20:
                group["rolling_mean"] = group["value"].rolling(20).mean()
                group["rolling_std"] = group["value"].rolling(20).std()

            for i, (idx, row) in enumerate(group.iterrows()):
                flags = []
                prior_row = group.iloc[i - 1] if i > 0 else None

                # Z-score spike
                if pd.notna(row.get("rolling_mean")) and pd.notna(
                    row.get("rolling_std")
                ):
                    if row["rolling_std"] > 0:
                        zscore = (
                            abs(row["value"] - row["rolling_mean"]) / row["rolling_std"]
                        )
                        if zscore > self.thresholds.zscore_extreme:
                            flags.append("value_spike")

                # Large revision
                if (
                    prior_row is not None
                    and prior_row["value"]
                    and prior_row["value"] != 0
                ):
                    pct_change = abs(row["value"] - prior_row["value"]) / abs(
                        prior_row["value"]
                    )
                    if pct_change > 0.10:
                        flags.append("revision_large")

                # Future dated
                if hasattr(row["event_date"], "date"):
                    if row["event_date"].date() > datetime.now().date():
                        flags.append("future_dated")

                if flags:
                    anomalies.append(
                        {
                            "date": str(row["event_date"]),
                            "series_id": series_id,
                            "flags": flags,
                        }
                    )

        return {
            "anomaly_count": len(anomalies),
            "anomalies": anomalies[:100],
            "quality_issues": list(set(f for a in anomalies for f in a["flags"])),
        }

    def detect_news(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Detect anomalies in news data."""
        anomalies = []

        for idx, row in df.iterrows():
            flags = []

            # Extreme sentiment
            if pd.notna(row.get("sentiment_score")):
                if abs(row["sentiment_score"]) > 0.95:
                    flags.append("sentiment_extreme")

            # Empty content
            if (
                pd.isna(row.get("headline"))
                or str(row.get("headline", "")).strip() == ""
            ):
                flags.append("empty_content")

            if flags:
                anomalies.append(
                    {
                        "date": str(row.get("event_date")),
                        "flags": flags,
                    }
                )

        return {
            "anomaly_count": len(anomalies),
            "anomalies": anomalies[:100],
            "quality_issues": list(set(f for a in anomalies for f in a["flags"])),
        }

    def detect_cot(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Detect anomalies in CFTC COT data."""
        anomalies = []

        if df.empty:
            return {"anomaly_count": 0, "anomalies": [], "quality_issues": []}

        for symbol, group in df.groupby("symbol"):
            group = group.sort_values("event_date").copy()

            for i, (idx, row) in enumerate(group.iterrows()):
                flags = []
                prior_row = group.iloc[i - 1] if i > 0 else None

                # Position spike
                if (
                    prior_row is not None
                    and prior_row.get("managed_money_net")
                    and prior_row["managed_money_net"] != 0
                ):
                    pct_change = abs(
                        row["managed_money_net"] - prior_row["managed_money_net"]
                    ) / abs(prior_row["managed_money_net"])
                    if pct_change > 0.50:
                        flags.append("position_spike")

                # OI spike
                if (
                    prior_row is not None
                    and prior_row.get("open_interest")
                    and prior_row["open_interest"] > 0
                ):
                    oi_change = (
                        abs(row["open_interest"] - prior_row["open_interest"])
                        / prior_row["open_interest"]
                    )
                    if oi_change > 0.30:
                        flags.append("oi_spike")

                # Zero OI
                if row.get("open_interest") == 0:
                    flags.append("zero_oi")

                # Impossible position
                if row.get("managed_money_net") and row.get("open_interest"):
                    if abs(row["managed_money_net"]) > row["open_interest"]:
                        flags.append("impossible_position")

                if flags:
                    anomalies.append(
                        {
                            "date": str(row["event_date"]),
                            "symbol": symbol,
                            "flags": flags,
                        }
                    )

        return {
            "anomaly_count": len(anomalies),
            "anomalies": anomalies[:100],
            "quality_issues": list(set(f for a in anomalies for f in a["flags"])),
        }

    def detect_fx(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Detect anomalies in FX data."""
        anomalies = []

        if df.empty:
            return {"anomaly_count": 0, "anomalies": [], "quality_issues": []}

        for pair, group in df.groupby("pair"):
            group = group.sort_values("event_date").copy()

            for i, (idx, row) in enumerate(group.iterrows()):
                flags = []
                prior_row = group.iloc[i - 1] if i > 0 else None

                # Rate spike
                if (
                    prior_row is not None
                    and prior_row.get("rate")
                    and prior_row["rate"] > 0
                ):
                    pct_change = (
                        abs(row["rate"] - prior_row["rate"]) / prior_row["rate"]
                    )
                    if pct_change > 0.10:
                        flags.append("rate_extreme")
                    elif pct_change > 0.05:
                        flags.append("rate_spike")

                # Rate errors
                if row.get("rate") is not None and row["rate"] <= 0:
                    flags.append("rate_zero" if row["rate"] == 0 else "rate_negative")

                # Weekend rate
                if (
                    hasattr(row["event_date"], "weekday")
                    and row["event_date"].weekday() >= 5
                ):
                    flags.append("weekend_rate")

                if flags:
                    anomalies.append(
                        {
                            "date": str(row["event_date"]),
                            "pair": pair,
                            "flags": flags,
                        }
                    )

        return {
            "anomaly_count": len(anomalies),
            "anomalies": anomalies[:100],
            "quality_issues": list(set(f for a in anomalies for f in a["flags"])),
        }

    def detect_rin(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Detect anomalies in EPA RIN data."""
        anomalies = []

        if df.empty:
            return {"anomaly_count": 0, "anomalies": [], "quality_issues": []}

        for rin_type, group in df.groupby("rin_type"):
            group = group.sort_values("event_date").copy()

            for i, (idx, row) in enumerate(group.iterrows()):
                flags = []
                prior_row = group.iloc[i - 1] if i > 0 else None

                # Price spike
                if (
                    prior_row is not None
                    and prior_row.get("price")
                    and prior_row["price"] > 0
                ):
                    pct_change = (
                        abs(row["price"] - prior_row["price"]) / prior_row["price"]
                    )
                    if pct_change > 0.20:
                        flags.append("price_spike")

                # Price errors
                if row.get("price") is not None:
                    if row["price"] < 0:
                        flags.append("price_negative")
                    elif row["price"] == 0:
                        flags.append("price_zero")
                    elif row["price"] > 3.00:
                        flags.append("price_extreme_high")

                if flags:
                    anomalies.append(
                        {
                            "date": str(row["event_date"]),
                            "rin_type": rin_type,
                            "flags": flags,
                        }
                    )

        return {
            "anomaly_count": len(anomalies),
            "anomalies": anomalies[:100],
            "quality_issues": list(set(f for a in anomalies for f in a["flags"])),
        }


# =============================================================================
# LOGGING TO ops.data_quality_log
# =============================================================================


def log_quality_check(
    conn,
    table_name: str,
    df: pd.DataFrame,
    anomaly_results: Dict[str, Any],
    date_col: str,
    dry_run: bool = False,
) -> None:
    """Log quality check results to ops.data_quality_log."""

    if df.empty:
        row_count = 0
        null_count = 0
        latest_date = None
        oldest_date = None
    else:
        row_count = len(df)
        null_count = int(df.isnull().sum().sum())
        latest_date = df[date_col].max() if date_col in df.columns else None
        oldest_date = df[date_col].min() if date_col in df.columns else None

    issues = {
        "anomaly_count": anomaly_results.get("anomaly_count", 0),
        "quality_issues": anomaly_results.get("quality_issues", []),
        "sample_anomalies": anomaly_results.get("anomalies", [])[:10],
    }

    if dry_run:
        logger.info(
            f"  [DRY RUN] Would log: {table_name} - {row_count} rows, {anomaly_results['anomaly_count']} anomalies"
        )
        return

    insert_query = """
        INSERT INTO ops.data_quality_log (
            table_name, check_date, row_count, null_count,
            latest_date, oldest_date, issues, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """

    with conn.cursor() as cur:
        cur.execute(
            insert_query,
            (
                table_name,
                datetime.now(),
                row_count,
                null_count,
                latest_date,
                oldest_date,
                Json(issues),
                datetime.now(),
            ),
        )
    conn.commit()

    logger.info(
        f"  Logged: {table_name} - {row_count} rows, {anomaly_results['anomaly_count']} anomalies"
    )


# =============================================================================
# MAIN CHECK FUNCTIONS
# =============================================================================


def check_table(conn, table_name: str, dry_run: bool = False) -> Dict[str, Any]:
    """Run anomaly detection on a single table."""
    if table_name not in TABLE_CONFIG:
        logger.error(f"Unknown table: {table_name}")
        logger.info(f"Available tables: {list(TABLE_CONFIG.keys())}")
        return {"error": f"Unknown table: {table_name}"}

    config = TABLE_CONFIG[table_name]
    logger.info(f"Checking {table_name}...")

    try:
        df = pd.read_sql(config["query"], conn)
    except Exception as e:
        logger.warning(f"  Could not query {table_name}: {e}")
        return {"error": str(e), "row_count": 0}

    if df.empty:
        logger.info(f"  No data in {table_name}")
        return {"row_count": 0, "anomaly_count": 0}

    logger.info(f"  Loaded {len(df):,} rows")

    # Run detector
    detector = AnomalyDetector()
    detector_method = getattr(detector, f"detect_{config['detector']}")
    results = detector_method(df)

    # Log to ops.data_quality_log
    log_quality_check(conn, table_name, df, results, config["date_col"], dry_run)

    return {
        "row_count": len(df),
        "anomaly_count": results["anomaly_count"],
        "quality_issues": results["quality_issues"],
    }


def check_all_tables(conn, dry_run: bool = False) -> Dict[str, Any]:
    """Run anomaly detection on all configured tables."""
    logger.info("=" * 60)
    logger.info("ANOMALY DETECTION - ALL TABLES")
    logger.info("=" * 60)

    results = {}
    total_rows = 0
    total_anomalies = 0

    for table_name in TABLE_CONFIG:
        result = check_table(conn, table_name, dry_run)
        results[table_name] = result
        total_rows += result.get("row_count", 0)
        total_anomalies += result.get("anomaly_count", 0)

    logger.info("=" * 60)
    logger.info("CHECK COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Total rows scanned: {total_rows:,}")
    logger.info(f"Total anomalies found: {total_anomalies:,}")

    return results


# =============================================================================
# MAIN
# =============================================================================


def main():
    parser = argparse.ArgumentParser(description="Anomaly detection for landing tables")
    parser.add_argument("--check-all", action="store_true", help="Check all tables")
    parser.add_argument(
        "--table", type=str, help="Check specific table (e.g., mkt.futures_1d)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Don't write to ops.data_quality_log"
    )
    parser.add_argument(
        "--list-tables", action="store_true", help="List available tables"
    )
    args = parser.parse_args()

    if args.list_tables:
        print("Available tables:")
        for table in sorted(TABLE_CONFIG.keys()):
            print(f"  {table}")
        return 0

    conn_string = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
    if not conn_string:
        print("ERROR: DATABASE_URL or POSTGRES_URL required")
        sys.exit(1)

    conn = psycopg2.connect(conn_string)

    try:
        if args.check_all:
            check_all_tables(conn, args.dry_run)
        elif args.table:
            check_table(conn, args.table, args.dry_run)
        else:
            parser.print_help()
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
