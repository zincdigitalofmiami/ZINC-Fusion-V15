#!/usr/bin/env python3
"""
Polygon.io Options Ingestion Pipeline
=====================================
Pulls ZL, ZS, ZM, CL options with full Greeks for ZINC-FUSION-V15.

Features:
- Contract metadata from /v3/reference/options/contracts
- Current Greeks snapshot from /v3/snapshot/options/...
- Stores directly to Prisma Postgres (options_greeks, options_features)

Author: ZINC-FUSION-V15
Date: 2025-12-29
Updated: 2025-12-31 - Removed DuckDB, Prisma-only
"""

import os
import sys
import time
import logging
import argparse
import requests
from datetime import datetime, timedelta
from typing import Optional, List, Dict

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
from psycopg2.extras import execute_batch
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment
load_dotenv()

# Environment validation
POLYGON_API_KEY = os.getenv("POLYGON_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

if not POLYGON_API_KEY:
    logger.error("POLYGON_API_KEY not set in environment")
    sys.exit(1)

if not DATABASE_URL:
    logger.error("DATABASE_URL not set in environment")
    sys.exit(1)

# Configuration
UNDERLYINGS = ["ZL", "ZS", "ZM", "CL"]  # Soy oil, Soybeans, Soy meal, Crude
EXPIRY_BUCKETS = [30, 90, 180]  # 1M, 3M, 6M in days
STRIKE_RANGE_PCT = 0.15  # ±15% from spot
BATCH_SIZE = 100
RATE_LIMIT_DELAY = 1.0  # Be conservative with rate limits


class PolygonOptionsIngester:
    """Ingest options data from Polygon.io with Greeks - Prisma only."""

    def __init__(self, dry_run: bool = False):
        self.api_key = POLYGON_API_KEY
        self.base_url = "https://api.polygon.io"
        self.session = requests.Session()
        self.dry_run = dry_run

        # Initialize Postgres connection
        self.pg = psycopg2.connect(DATABASE_URL)
        logger.info("Connected to Prisma Postgres")

    def _rate_limit(self):
        """Respect API rate limits."""
        time.sleep(RATE_LIMIT_DELAY)

    def _get(self, endpoint: str, params: Dict = None, retries: int = 3) -> Optional[Dict]:
        """Make GET request to Polygon API with retry logic."""
        url = f"{self.base_url}{endpoint}"
        if params is None:
            params = {}
        params["apiKey"] = self.api_key

        for attempt in range(retries):
            try:
                self._rate_limit()
                resp = self.session.get(url, params=params, timeout=30)

                if resp.status_code == 429:
                    # Rate limited - exponential backoff
                    wait_time = (2 ** attempt) * 5
                    logger.warning(f"Rate limited, waiting {wait_time}s...")
                    time.sleep(wait_time)
                    continue

                resp.raise_for_status()
                return resp.json()

            except requests.exceptions.RequestException as e:
                logger.error(f"API error (attempt {attempt + 1}/{retries}): {e}")
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)

        return None

    def get_underlying_price(self, symbol: str) -> Optional[float]:
        """Get current/latest price for underlying futures."""
        endpoint = f"/v2/aggs/ticker/{symbol}/prev"
        data = self._get(endpoint)

        if data and data.get("results"):
            return data["results"][0].get("c")  # close price
        return None

    def get_options_contracts(self, underlying: str,
                              expiry_min: datetime = None,
                              expiry_max: datetime = None) -> List[Dict]:
        """Get options contracts for an underlying."""
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
            logger.info(f"  Fetched {len(contracts)} {underlying} contracts...")

            if data.get("next_url"):
                cursor = data["next_url"].split("cursor=")[-1].split("&")[0]
            else:
                break

        return contracts

    def filter_contracts_by_strike(self, contracts: List[Dict],
                                   spot_price: float) -> List[Dict]:
        """Filter contracts to ±15% strike range around spot."""
        if not spot_price:
            logger.warning("No spot price available, returning empty list")
            return []

        min_strike = spot_price * (1 - STRIKE_RANGE_PCT)
        max_strike = spot_price * (1 + STRIKE_RANGE_PCT)

        filtered = [
            c for c in contracts
            if min_strike <= c.get("strike_price", 0) <= max_strike
        ]

        logger.info(f"  Filtered to {len(filtered)} contracts in strike range "
              f"${min_strike:.2f} - ${max_strike:.2f}")
        return filtered

    def get_options_snapshot(self, underlying: str) -> List[Dict]:
        """Get current options snapshot with Greeks."""
        endpoint = f"/v3/snapshot/options/{underlying}"
        params = {"limit": 250}

        all_results = []

        while True:
            data = self._get(endpoint, params)

            if not data or "results" not in data:
                break

            all_results.extend(data["results"])
            logger.info(f"  Snapshot: {len(all_results)} {underlying} options...")

            if data.get("next_url"):
                next_url = data["next_url"]
                if "cursor=" in next_url:
                    params["cursor"] = next_url.split("cursor=")[-1].split("&")[0]
                else:
                    break
            else:
                break

        return all_results

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

    def store_options_greeks(self, underlying: str,
                             snapshot_data: List[Dict],
                             spot_price: float) -> int:
        """Store options snapshot with Greeks directly to Prisma."""
        if not snapshot_data:
            logger.info(f"  No snapshot data for {underlying}")
            return 0

        if self.dry_run:
            logger.info(f"  [DRY RUN] Would insert {len(snapshot_data)} options")
            return 0

        today = datetime.now().date()
        rows_to_insert = []

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

                rows_to_insert.append((
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
                ))

            except Exception as e:
                logger.error(f"    Error processing {opt.get('details', {}).get('ticker')}: {e}")
                continue

        # Batch insert to Prisma
        if rows_to_insert:
            cur = self.pg.cursor()
            try:
                execute_batch(cur, """
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
                        open_interest = EXCLUDED.open_interest,
                        volume = EXCLUDED.volume,
                        open = EXCLUDED.open,
                        high = EXCLUDED.high,
                        low = EXCLUDED.low,
                        close = EXCLUDED.close,
                        underlying_price = EXCLUDED.underlying_price
                """, rows_to_insert, page_size=BATCH_SIZE)
                self.pg.commit()
                cur.close()
            except Exception as e:
                logger.error(f"Error inserting options_greeks: {e}")
                self.pg.rollback()
                cur.close()
                return 0

        return len(rows_to_insert)

    def compute_and_store_features(self, underlying: str, as_of_date) -> int:
        """Compute aggregated options features and store to Prisma."""
        if self.dry_run:
            logger.info(f"  [DRY RUN] Would compute features for {underlying}")
            return 0

        cur = self.pg.cursor()
        features_stored = 0

        for bucket in ["1M", "3M", "6M"]:
            # Get options for this bucket from Prisma
            cur.execute("""
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
                FROM options_greeks
                WHERE underlying = %s
                  AND as_of_date = %s
                  AND expiry_bucket = %s
                  AND implied_volatility IS NOT NULL
            """, [underlying, as_of_date, bucket])

            data = cur.fetchall()

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

            # Store features to Prisma
            try:
                cur.execute("""
                    INSERT INTO options_features (
                        underlying, as_of_date, expiry_bucket,
                        iv_atm_call, iv_atm_put, iv_skew,
                        delta_weighted_oi_call, delta_weighted_oi_put,
                        gamma_exposure, put_call_ratio_volume, put_call_ratio_oi,
                        total_volume, total_open_interest
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (underlying, as_of_date, expiry_bucket) DO UPDATE SET
                        iv_atm_call = EXCLUDED.iv_atm_call,
                        iv_atm_put = EXCLUDED.iv_atm_put,
                        iv_skew = EXCLUDED.iv_skew,
                        delta_weighted_oi_call = EXCLUDED.delta_weighted_oi_call,
                        delta_weighted_oi_put = EXCLUDED.delta_weighted_oi_put,
                        gamma_exposure = EXCLUDED.gamma_exposure,
                        put_call_ratio_volume = EXCLUDED.put_call_ratio_volume,
                        put_call_ratio_oi = EXCLUDED.put_call_ratio_oi,
                        total_volume = EXCLUDED.total_volume,
                        total_open_interest = EXCLUDED.total_open_interest
                """, [
                    underlying, as_of_date, bucket,
                    iv_atm_call, iv_atm_put, iv_skew,
                    delta_oi_call, delta_oi_put, gamma_exp,
                    pc_ratio_vol, pc_ratio_oi,
                    call_vol + put_vol, call_oi + put_oi
                ])
                features_stored += 1
            except Exception as e:
                logger.error(f"Error storing features for {underlying}/{bucket}: {e}")

        self.pg.commit()
        cur.close()
        return features_stored

    def ingest_underlying(self, underlying: str) -> tuple:
        """Full ingestion for one underlying."""
        logger.info(f"\n{'='*60}")
        logger.info(f"Ingesting {underlying} options...")
        logger.info(f"{'='*60}")

        # Get spot price
        spot = self.get_underlying_price(underlying)
        if spot:
            logger.info(f"  Spot price: ${spot:.4f}")
        else:
            logger.warning(f"  Could not get spot price for {underlying}, skipping")
            return 0, 0

        # Get contracts metadata (for logging only)
        logger.info(f"\n  Fetching contracts...")
        contracts = self.get_options_contracts(underlying)
        logger.info(f"  Found {len(contracts)} total contracts")

        if contracts:
            contracts = self.filter_contracts_by_strike(contracts, spot)

        # Get current snapshot with Greeks
        logger.info(f"\n  Fetching options snapshot with Greeks...")
        snapshot = self.get_options_snapshot(underlying)

        if snapshot:
            rows = self.store_options_greeks(underlying, snapshot, spot)
            logger.info(f"  Stored {rows} options with Greeks to Prisma")

            # Compute daily features
            logger.info(f"  Computing aggregated features...")
            features = self.compute_and_store_features(underlying, datetime.now().date())
            logger.info(f"  Stored {features} feature records to Prisma")
        else:
            logger.warning(f"  No snapshot data available")
            rows = 0

        return len(contracts), len(snapshot) if snapshot else 0

    def verify_data(self):
        """Verify data in Prisma after ingestion."""
        cur = self.pg.cursor()

        logger.info("\n" + "="*60)
        logger.info("VERIFICATION")
        logger.info("="*60)

        # Count options_greeks
        cur.execute("SELECT COUNT(*) FROM options_greeks WHERE as_of_date = %s",
                    [datetime.now().date()])
        greeks_count = cur.fetchone()[0]
        logger.info(f"  options_greeks (today): {greeks_count} rows")

        # Count options_features
        cur.execute("SELECT COUNT(*) FROM options_features WHERE as_of_date = %s",
                    [datetime.now().date()])
        features_count = cur.fetchone()[0]
        logger.info(f"  options_features (today): {features_count} rows")

        # Breakdown by underlying
        cur.execute("""
            SELECT underlying, COUNT(*)
            FROM options_greeks
            WHERE as_of_date = %s
            GROUP BY underlying
        """, [datetime.now().date()])
        for row in cur.fetchall():
            logger.info(f"    {row[0]}: {row[1]} options")

        cur.close()

    def run(self):
        """Run full ingestion for all underlyings."""
        logger.info("="*60)
        logger.info("POLYGON OPTIONS INGESTION (Prisma-only)")
        logger.info(f"Time: {datetime.now().isoformat()}")
        logger.info(f"Underlyings: {UNDERLYINGS}")
        logger.info(f"Dry run: {self.dry_run}")
        logger.info("="*60)

        total_contracts = 0
        total_options = 0

        for underlying in UNDERLYINGS:
            contracts, options = self.ingest_underlying(underlying)
            total_contracts += contracts
            total_options += options

        # Verify
        if not self.dry_run:
            self.verify_data()

        # Summary
        logger.info("\n" + "="*60)
        logger.info("INGESTION COMPLETE")
        logger.info("="*60)
        logger.info(f"Total contracts processed: {total_contracts}")
        logger.info(f"Total options with Greeks: {total_options}")

        self.pg.close()


def main():
    parser = argparse.ArgumentParser(description="Ingest Polygon options to Prisma")
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch data but don't insert")
    parser.add_argument("--underlying", type=str,
                        help="Single underlying to ingest (ZL, ZS, ZM, CL)")

    args = parser.parse_args()

    ingester = PolygonOptionsIngester(dry_run=args.dry_run)

    if args.underlying:
        if args.underlying not in UNDERLYINGS:
            logger.error(f"Unknown underlying: {args.underlying}")
            sys.exit(1)
        # Override to single underlying
        global UNDERLYINGS
        UNDERLYINGS = [args.underlying]

    ingester.run()


if __name__ == "__main__":
    main()
