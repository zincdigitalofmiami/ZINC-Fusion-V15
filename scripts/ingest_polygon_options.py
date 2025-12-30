#!/usr/bin/env python3
"""
Polygon.io Options Ingestion Pipeline
=====================================
Pulls ZL, ZS, ZM, CL options with full Greeks for ZINC-FUSION-V15.

Features:
- Contract metadata from /v3/reference/options/contracts
- Historical OHLCV from /v2/aggs/ticker/...
- Current Greeks snapshot from /v1/snapshot/options/...
- Stores to both DuckDB (archive) and Prisma (authoritative)

Author: ZINC-FUSION-V15
Date: 2025-12-29
"""

import os
import sys
import time
import requests
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, List, Dict, Any
import json

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import duckdb
import psycopg2
from dotenv import load_dotenv

# Load environment
load_dotenv()

POLYGON_API_KEY = os.getenv("POLYGON_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
DUCKDB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "fusion.db")

# Configuration
UNDERLYINGS = ["ZL", "ZS", "ZM", "CL"]  # Soy oil, Soybeans, Soy meal, Crude
EXPIRY_BUCKETS = [30, 90, 180]  # 1M, 3M, 6M in days
STRIKE_RANGE_PCT = 0.15  # ±15% from spot
BATCH_SIZE = 100
RATE_LIMIT_DELAY = 0.25  # 4 requests/second for free tier

class PolygonOptionsIngester:
    """Ingest options data from Polygon.io with Greeks."""

    def __init__(self):
        self.api_key = POLYGON_API_KEY
        self.base_url = "https://api.polygon.io"
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {self.api_key}"})

        # Initialize DB connections
        self.duck = duckdb.connect(DUCKDB_PATH)
        self.pg = psycopg2.connect(DATABASE_URL) if DATABASE_URL else None

        self._ensure_schema()

    def _ensure_schema(self):
        """Create options tables if they don't exist."""
        # DuckDB schema
        self.duck.execute("""
            CREATE SCHEMA IF NOT EXISTS options;
        """)

        # Options contracts metadata
        self.duck.execute("""
            CREATE TABLE IF NOT EXISTS options.contracts (
                ticker VARCHAR PRIMARY KEY,
                underlying_ticker VARCHAR,
                contract_type VARCHAR,  -- call/put
                expiration_date DATE,
                strike_price DECIMAL(12,4),
                shares_per_contract INTEGER,
                primary_exchange VARCHAR,
                cfi VARCHAR,
                exercise_style VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Options daily OHLCV with Greeks
        self.duck.execute("""
            CREATE TABLE IF NOT EXISTS options.daily_greeks (
                ticker VARCHAR,
                underlying VARCHAR,
                as_of_date DATE,
                expiration_date DATE,
                strike_price DECIMAL(12,4),
                option_type VARCHAR,  -- C/P
                open DECIMAL(10,4),
                high DECIMAL(10,4),
                low DECIMAL(10,4),
                close DECIMAL(10,4),
                volume BIGINT,
                open_interest BIGINT,
                implied_volatility DECIMAL(8,6),
                delta DECIMAL(8,6),
                gamma DECIMAL(8,6),
                theta DECIMAL(8,6),
                vega DECIMAL(8,6),
                days_to_expiry INTEGER,
                moneyness VARCHAR,  -- ITM, ATM, OTM
                expiry_bucket VARCHAR,  -- 1M, 3M, 6M
                underlying_price DECIMAL(10,4),
                source VARCHAR DEFAULT 'polygon',
                ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (ticker, as_of_date)
            );
        """)

        # Aggregated options features (daily)
        self.duck.execute("""
            CREATE TABLE IF NOT EXISTS options.features_daily (
                underlying VARCHAR,
                as_of_date DATE,
                expiry_bucket VARCHAR,  -- 1M, 3M, 6M
                -- IV metrics
                iv_atm_call DECIMAL(8,6),
                iv_atm_put DECIMAL(8,6),
                iv_skew DECIMAL(8,6),  -- OTM put IV - OTM call IV
                iv_term_structure DECIMAL(8,6),  -- 3M IV / 1M IV
                iv_percentile_30d DECIMAL(5,2),
                -- Greek aggregates
                delta_weighted_oi_call DECIMAL(18,4),
                delta_weighted_oi_put DECIMAL(18,4),
                gamma_exposure DECIMAL(18,4),
                net_gamma DECIMAL(18,4),
                vega_exposure DECIMAL(18,4),
                -- Volume/OI metrics
                put_call_ratio_volume DECIMAL(8,4),
                put_call_ratio_oi DECIMAL(8,4),
                total_volume BIGINT,
                total_open_interest BIGINT,
                -- Derived signals
                skew_zscore DECIMAL(6,4),
                gamma_flip_level DECIMAL(10,4),
                max_pain_strike DECIMAL(10,4),
                PRIMARY KEY (underlying, as_of_date, expiry_bucket)
            );
        """)

        self.duck.commit()
        print("DuckDB options schema ready")

    def _rate_limit(self):
        """Respect API rate limits."""
        time.sleep(RATE_LIMIT_DELAY)

    def _get(self, endpoint: str, params: Dict = None) -> Optional[Dict]:
        """Make GET request to Polygon API."""
        url = f"{self.base_url}{endpoint}"
        if params is None:
            params = {}
        params["apiKey"] = self.api_key

        try:
            self._rate_limit()
            resp = self.session.get(url, params=params, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            print(f"API error: {e}")
            return None

    def get_underlying_price(self, symbol: str) -> Optional[float]:
        """Get current/latest price for underlying futures."""
        # Map to Polygon futures ticker format
        # ZL -> ZL (soybean oil), ZS -> ZS (soybeans), etc.
        endpoint = f"/v2/aggs/ticker/{symbol}/prev"
        data = self._get(endpoint)

        if data and data.get("results"):
            return data["results"][0].get("c")  # close price
        return None

    def get_options_contracts(self, underlying: str,
                              expiry_min: datetime = None,
                              expiry_max: datetime = None) -> List[Dict]:
        """
        Get options contracts for an underlying.

        Polygon options tickers format: O:{UNDERLYING}{YYMMDD}{C/P}{STRIKE}
        Example: O:ZL250117C00045000 = ZL Jan 17 2025 $45.00 Call
        """
        if expiry_min is None:
            expiry_min = datetime.now()
        if expiry_max is None:
            expiry_max = datetime.now() + timedelta(days=max(EXPIRY_BUCKETS) + 30)

        contracts = []
        cursor = None

        while True:
            params = {
                "underlying_ticker": underlying,
                "expiration_date.gte": expiry_min.strftime("%Y-%m-%d"),
                "expiration_date.lte": expiry_max.strftime("%Y-%m-%d"),
                "limit": 1000,
                "order": "asc",
                "sort": "expiration_date"
            }
            if cursor:
                params["cursor"] = cursor

            endpoint = "/v3/reference/options/contracts"
            data = self._get(endpoint, params)

            if not data or "results" not in data:
                break

            contracts.extend(data["results"])
            print(f"  Fetched {len(contracts)} {underlying} contracts...")

            # Check for next page
            if data.get("next_url"):
                cursor = data["next_url"].split("cursor=")[-1].split("&")[0]
            else:
                break

        return contracts

    def filter_contracts_by_strike(self, contracts: List[Dict],
                                   spot_price: float) -> List[Dict]:
        """Filter contracts to ±15% strike range around spot."""
        if not spot_price:
            return contracts

        min_strike = spot_price * (1 - STRIKE_RANGE_PCT)
        max_strike = spot_price * (1 + STRIKE_RANGE_PCT)

        filtered = [
            c for c in contracts
            if min_strike <= c.get("strike_price", 0) <= max_strike
        ]

        print(f"  Filtered to {len(filtered)} contracts in strike range "
              f"${min_strike:.2f} - ${max_strike:.2f}")
        return filtered

    def get_options_snapshot(self, underlying: str) -> List[Dict]:
        """
        Get current options snapshot with Greeks.

        Uses /v3/snapshot/options/{underlyingAsset}
        Returns: Greeks, IV, prices, OI for all active contracts
        """
        endpoint = f"/v3/snapshot/options/{underlying}"
        params = {"limit": 250}

        all_results = []

        while True:
            data = self._get(endpoint, params)

            if not data or "results" not in data:
                break

            all_results.extend(data["results"])
            print(f"  Snapshot: {len(all_results)} {underlying} options...")

            if data.get("next_url"):
                # Extract cursor from next_url
                next_url = data["next_url"]
                if "cursor=" in next_url:
                    params["cursor"] = next_url.split("cursor=")[-1].split("&")[0]
                else:
                    break
            else:
                break

        return all_results

    def get_options_aggs(self, ticker: str,
                         from_date: datetime,
                         to_date: datetime) -> List[Dict]:
        """
        Get historical OHLCV for an options contract.

        Note: Historical Greeks not available via aggs - need snapshot.
        """
        endpoint = f"/v2/aggs/ticker/{ticker}/range/1/day/{from_date.strftime('%Y-%m-%d')}/{to_date.strftime('%Y-%m-%d')}"
        params = {"adjusted": "true", "limit": 50000}

        data = self._get(endpoint, params)

        if data and "results" in data:
            return data["results"]
        return []

    def classify_moneyness(self, strike: float, spot: float,
                           option_type: str) -> str:
        """Classify option as ITM, ATM, or OTM."""
        if not spot or not strike:
            return "UNKNOWN"

        pct_diff = (strike - spot) / spot

        if abs(pct_diff) < 0.02:  # Within 2% = ATM
            return "ATM"

        if option_type.upper() in ["C", "CALL"]:
            return "ITM" if strike < spot else "OTM"
        else:  # Put
            return "ITM" if strike > spot else "OTM"

    def classify_expiry_bucket(self, days_to_expiry: int) -> str:
        """Classify expiry into 1M, 3M, 6M bucket."""
        if days_to_expiry <= 45:
            return "1M"
        elif days_to_expiry <= 100:
            return "3M"
        else:
            return "6M"

    def store_snapshot_data(self, underlying: str,
                           snapshot_data: List[Dict],
                           spot_price: float):
        """Store options snapshot with Greeks to DuckDB."""
        if not snapshot_data:
            print(f"  No snapshot data for {underlying}")
            return 0

        today = datetime.now().date()
        rows_inserted = 0

        for opt in snapshot_data:
            try:
                details = opt.get("details", {})
                greeks = opt.get("greeks", {})
                day = opt.get("day", {})

                ticker = details.get("ticker", "")
                expiry = details.get("expiration_date")
                strike = details.get("strike_price")
                opt_type = details.get("contract_type", "").upper()[:1]  # C or P

                if not all([ticker, expiry, strike]):
                    continue

                # Parse expiry date
                if isinstance(expiry, str):
                    expiry_date = datetime.strptime(expiry, "%Y-%m-%d").date()
                else:
                    expiry_date = expiry

                days_to_expiry = (expiry_date - today).days
                if days_to_expiry < 0:
                    continue  # Skip expired

                moneyness = self.classify_moneyness(strike, spot_price, opt_type)
                expiry_bucket = self.classify_expiry_bucket(days_to_expiry)

                # Insert/update
                self.duck.execute("""
                    INSERT OR REPLACE INTO options.daily_greeks (
                        ticker, underlying, as_of_date, expiration_date,
                        strike_price, option_type, open, high, low, close,
                        volume, open_interest, implied_volatility,
                        delta, gamma, theta, vega, days_to_expiry,
                        moneyness, expiry_bucket, underlying_price
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, [
                    ticker,
                    underlying,
                    today,
                    expiry_date,
                    strike,
                    opt_type,
                    day.get("o"),
                    day.get("h"),
                    day.get("l"),
                    day.get("c"),
                    day.get("v"),
                    opt.get("open_interest"),
                    greeks.get("implied_volatility"),
                    greeks.get("delta"),
                    greeks.get("gamma"),
                    greeks.get("theta"),
                    greeks.get("vega"),
                    days_to_expiry,
                    moneyness,
                    expiry_bucket,
                    spot_price
                ])
                rows_inserted += 1

            except Exception as e:
                print(f"    Error storing {opt.get('details', {}).get('ticker')}: {e}")
                continue

        self.duck.commit()
        return rows_inserted

    def compute_daily_features(self, underlying: str, as_of_date: datetime.date):
        """
        Compute aggregated options features for a given date.

        Features by expiry bucket:
        - IV skew, term structure
        - Delta-weighted OI
        - Gamma exposure
        - Put/call ratios
        """
        for bucket in ["1M", "3M", "6M"]:
            # Get options for this bucket
            data = self.duck.execute("""
                SELECT
                    option_type,
                    moneyness,
                    strike_price,
                    close,
                    volume,
                    open_interest,
                    implied_volatility,
                    delta,
                    gamma,
                    theta,
                    vega,
                    underlying_price
                FROM options.daily_greeks
                WHERE underlying = ?
                  AND as_of_date = ?
                  AND expiry_bucket = ?
                  AND implied_volatility IS NOT NULL
            """, [underlying, as_of_date, bucket]).fetchall()

            if not data:
                continue

            # Aggregate metrics
            calls = [r for r in data if r[0] == 'C']
            puts = [r for r in data if r[0] == 'P']

            # IV ATM
            atm_calls = [r for r in calls if r[1] == 'ATM']
            atm_puts = [r for r in puts if r[1] == 'ATM']

            iv_atm_call = sum(r[6] or 0 for r in atm_calls) / len(atm_calls) if atm_calls else None
            iv_atm_put = sum(r[6] or 0 for r in atm_puts) / len(atm_puts) if atm_puts else None

            # IV Skew (OTM put - OTM call)
            otm_calls = [r for r in calls if r[1] == 'OTM']
            otm_puts = [r for r in puts if r[1] == 'OTM']

            iv_otm_call = sum(r[6] or 0 for r in otm_calls) / len(otm_calls) if otm_calls else 0
            iv_otm_put = sum(r[6] or 0 for r in otm_puts) / len(otm_puts) if otm_puts else 0
            iv_skew = iv_otm_put - iv_otm_call if (otm_puts and otm_calls) else None

            # Delta-weighted OI
            delta_oi_call = sum((r[7] or 0) * (r[5] or 0) for r in calls)
            delta_oi_put = sum((r[7] or 0) * (r[5] or 0) for r in puts)

            # Gamma exposure
            spot = data[0][11] if data else None
            if spot:
                gamma_exp = sum((r[8] or 0) * (r[5] or 0) * spot * spot * 0.01 for r in data)
            else:
                gamma_exp = None

            # Volume/OI ratios
            call_vol = sum(r[4] or 0 for r in calls)
            put_vol = sum(r[4] or 0 for r in puts)
            call_oi = sum(r[5] or 0 for r in calls)
            put_oi = sum(r[5] or 0 for r in puts)

            pc_ratio_vol = put_vol / call_vol if call_vol > 0 else None
            pc_ratio_oi = put_oi / call_oi if call_oi > 0 else None

            # Store features
            self.duck.execute("""
                INSERT OR REPLACE INTO options.features_daily (
                    underlying, as_of_date, expiry_bucket,
                    iv_atm_call, iv_atm_put, iv_skew,
                    delta_weighted_oi_call, delta_weighted_oi_put,
                    gamma_exposure, put_call_ratio_volume, put_call_ratio_oi,
                    total_volume, total_open_interest
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                underlying, as_of_date, bucket,
                iv_atm_call, iv_atm_put, iv_skew,
                delta_oi_call, delta_oi_put, gamma_exp,
                pc_ratio_vol, pc_ratio_oi,
                call_vol + put_vol, call_oi + put_oi
            ])

        self.duck.commit()

    def ingest_underlying(self, underlying: str):
        """Full ingestion for one underlying."""
        print(f"\n{'='*60}")
        print(f"Ingesting {underlying} options...")
        print(f"{'='*60}")

        # Get spot price
        spot = self.get_underlying_price(underlying)
        if spot:
            print(f"  Spot price: ${spot:.4f}")
        else:
            print(f"  Warning: Could not get spot price for {underlying}")

        # Get contracts metadata
        print(f"\n  Fetching contracts...")
        contracts = self.get_options_contracts(underlying)
        print(f"  Found {len(contracts)} total contracts")

        if spot and contracts:
            contracts = self.filter_contracts_by_strike(contracts, spot)

        # Store contract metadata
        for c in contracts:
            try:
                self.duck.execute("""
                    INSERT OR REPLACE INTO options.contracts (
                        ticker, underlying_ticker, contract_type,
                        expiration_date, strike_price, shares_per_contract,
                        primary_exchange, cfi, exercise_style
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, [
                    c.get("ticker"),
                    c.get("underlying_ticker"),
                    c.get("contract_type"),
                    c.get("expiration_date"),
                    c.get("strike_price"),
                    c.get("shares_per_contract"),
                    c.get("primary_exchange"),
                    c.get("cfi"),
                    c.get("exercise_style")
                ])
            except Exception as e:
                pass
        self.duck.commit()

        # Get current snapshot with Greeks
        print(f"\n  Fetching options snapshot with Greeks...")
        snapshot = self.get_options_snapshot(underlying)

        if snapshot:
            rows = self.store_snapshot_data(underlying, snapshot, spot)
            print(f"  Stored {rows} options with Greeks")

            # Compute daily features
            print(f"  Computing aggregated features...")
            self.compute_daily_features(underlying, datetime.now().date())
        else:
            print(f"  No snapshot data available")

        return len(contracts), len(snapshot) if snapshot else 0

    def sync_to_prisma(self):
        """Sync options data to Prisma Postgres."""
        if not self.pg:
            print("No Prisma connection, skipping sync")
            return

        print("\n" + "="*60)
        print("Syncing to Prisma...")
        print("="*60)

        cur = self.pg.cursor()

        # Check if options_greeks table exists, create if not
        cur.execute("""
            CREATE TABLE IF NOT EXISTS options_greeks (
                id SERIAL PRIMARY KEY,
                ticker VARCHAR(50),
                underlying VARCHAR(10),
                as_of_date DATE,
                expiration_date DATE,
                strike_price DECIMAL(12,4),
                option_type VARCHAR(1),
                open DECIMAL(10,4),
                high DECIMAL(10,4),
                low DECIMAL(10,4),
                close DECIMAL(10,4),
                volume BIGINT,
                open_interest BIGINT,
                implied_volatility DECIMAL(8,6),
                delta DECIMAL(8,6),
                gamma DECIMAL(8,6),
                theta DECIMAL(8,6),
                vega DECIMAL(8,6),
                days_to_expiry INTEGER,
                moneyness VARCHAR(10),
                expiry_bucket VARCHAR(5),
                underlying_price DECIMAL(10,4),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ticker, as_of_date)
            );
            CREATE INDEX IF NOT EXISTS idx_options_greeks_underlying ON options_greeks(underlying);
            CREATE INDEX IF NOT EXISTS idx_options_greeks_date ON options_greeks(as_of_date);
        """)
        self.pg.commit()

        # Fetch from DuckDB
        rows = self.duck.execute("""
            SELECT ticker, underlying, as_of_date, expiration_date,
                   strike_price, option_type, open, high, low, close,
                   volume, open_interest, implied_volatility,
                   delta, gamma, theta, vega, days_to_expiry,
                   moneyness, expiry_bucket, underlying_price
            FROM options.daily_greeks
            ORDER BY as_of_date, underlying, ticker
        """).fetchall()

        print(f"  Syncing {len(rows)} options records...")

        # Batch insert
        inserted = 0
        for i in range(0, len(rows), BATCH_SIZE):
            batch = rows[i:i+BATCH_SIZE]

            for row in batch:
                try:
                    cur.execute("""
                        INSERT INTO options_greeks (
                            ticker, underlying, as_of_date, expiration_date,
                            strike_price, option_type, open, high, low, close,
                            volume, open_interest, implied_volatility,
                            delta, gamma, theta, vega, days_to_expiry,
                            moneyness, expiry_bucket, underlying_price
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                  %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (ticker, as_of_date) DO UPDATE SET
                            implied_volatility = EXCLUDED.implied_volatility,
                            delta = EXCLUDED.delta,
                            gamma = EXCLUDED.gamma,
                            theta = EXCLUDED.theta,
                            vega = EXCLUDED.vega,
                            open_interest = EXCLUDED.open_interest
                    """, row)
                    inserted += 1
                except Exception as e:
                    print(f"    Error: {e}")

            self.pg.commit()

            if inserted % 500 == 0:
                print(f"    Progress: {inserted}/{len(rows)}")

        print(f"  Synced {inserted} records to Prisma")
        cur.close()

    def run(self):
        """Run full ingestion for all underlyings."""
        print("="*60)
        print("POLYGON OPTIONS INGESTION")
        print(f"Time: {datetime.now().isoformat()}")
        print(f"Underlyings: {UNDERLYINGS}")
        print("="*60)

        if not self.api_key:
            print("ERROR: POLYGON_API_KEY not set!")
            return

        total_contracts = 0
        total_options = 0

        for underlying in UNDERLYINGS:
            contracts, options = self.ingest_underlying(underlying)
            total_contracts += contracts
            total_options += options

        # Sync to Prisma
        self.sync_to_prisma()

        # Summary
        print("\n" + "="*60)
        print("INGESTION COMPLETE")
        print("="*60)
        print(f"Total contracts: {total_contracts}")
        print(f"Total options with Greeks: {total_options}")

        # Verify
        count = self.duck.execute("SELECT COUNT(*) FROM options.daily_greeks").fetchone()[0]
        print(f"DuckDB options.daily_greeks: {count} rows")

        features_count = self.duck.execute("SELECT COUNT(*) FROM options.features_daily").fetchone()[0]
        print(f"DuckDB options.features_daily: {features_count} rows")

        self.duck.close()
        if self.pg:
            self.pg.close()


def main():
    ingester = PolygonOptionsIngester()
    ingester.run()


if __name__ == "__main__":
    main()
