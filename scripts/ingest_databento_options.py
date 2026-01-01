#!/usr/bin/env python3
"""
!!! DEPRECATED - DO NOT USE !!!
================================
This script uses DuckDB which is ARCHIVE ONLY.

USE INSTEAD:
    # Options data should be ingested via Prisma-only pipeline
    # See scripts/ingest_options_prisma.py (to be created)

This script is kept for historical reference only.
It will raise an error if you try to run it.

Original description:
Databento Options Ingestion Pipeline - Pulls ZL, ZS, ZM, CL options from GLBX.MDP3
"""

import sys
print("=" * 70)
print("ERROR: This script is DEPRECATED!")
print("=" * 70)
print("")
print("DuckDB is ARCHIVE ONLY. All ingestion uses Prisma Postgres.")
print("")
print("This script needs to be rewritten to use Prisma only.")
print("See CLAUDE.md for the data architecture policy.")
print("=" * 70)
sys.exit(1)

# --- ORIGINAL CODE BELOW (disabled) ---

import os
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple
import math

import databento as db
import pandas as pd
import numpy as np
from scipy.stats import norm

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import duckdb
import psycopg2

# Configuration
DATABENTO_API_KEY = os.getenv("DATABENTO_API_KEY", "db-7wsFLKcFEx3VcXCFXhYWejcVdtC3d")
DATABASE_URL = os.getenv("DATABASE_URL", "postgres://d687a7ec267e124a21607a1e5dd9a89d60c9a122d219e499e32f3eee42a858c0:sk_NLg8ZV3VJ61FPM0F_QHMe@db.prisma.io:5432/postgres?sslmode=require")
DUCKDB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "fusion.db")

# Target underlyings
UNDERLYINGS = ["ZL", "ZS", "ZM", "CL"]  # Soy oil, Soybeans, Soy meal, Crude
RATE_PROXY_FUTURES = ["GE", "ZQ"]  # Eurodollar, Fed Funds for rate proxy

# Dataset
DATASET = "GLBX.MDP3"


class Black76:
    """Black-76 model for options on futures."""

    @staticmethod
    def d1(F: float, K: float, r: float, T: float, sigma: float) -> float:
        """Calculate d1 parameter."""
        if T <= 0 or sigma <= 0:
            return 0.0
        return (math.log(F / K) + (0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))

    @staticmethod
    def d2(F: float, K: float, r: float, T: float, sigma: float) -> float:
        """Calculate d2 parameter."""
        if T <= 0 or sigma <= 0:
            return 0.0
        return Black76.d1(F, K, r, T, sigma) - sigma * math.sqrt(T)

    @staticmethod
    def call_price(F: float, K: float, r: float, T: float, sigma: float) -> float:
        """Calculate call option price."""
        if T <= 0:
            return max(F - K, 0)
        d1 = Black76.d1(F, K, r, T, sigma)
        d2 = Black76.d2(F, K, r, T, sigma)
        return math.exp(-r * T) * (F * norm.cdf(d1) - K * norm.cdf(d2))

    @staticmethod
    def put_price(F: float, K: float, r: float, T: float, sigma: float) -> float:
        """Calculate put option price."""
        if T <= 0:
            return max(K - F, 0)
        d1 = Black76.d1(F, K, r, T, sigma)
        d2 = Black76.d2(F, K, r, T, sigma)
        return math.exp(-r * T) * (K * norm.cdf(-d2) - F * norm.cdf(-d1))

    @staticmethod
    def implied_volatility(price: float, F: float, K: float, r: float, T: float,
                           option_type: str, max_iter: int = 100, tol: float = 1e-6) -> Optional[float]:
        """Calculate implied volatility using Newton-Raphson."""
        if T <= 0 or price <= 0:
            return None

        # Initial guess
        sigma = 0.3

        for _ in range(max_iter):
            if option_type.upper() in ['C', 'CALL']:
                model_price = Black76.call_price(F, K, r, T, sigma)
            else:
                model_price = Black76.put_price(F, K, r, T, sigma)

            vega = Black76.vega(F, K, r, T, sigma)

            if abs(vega) < 1e-10:
                break

            diff = model_price - price
            if abs(diff) < tol:
                return sigma

            sigma = sigma - diff / vega
            if sigma <= 0:
                sigma = 0.01

        return sigma if 0.01 < sigma < 5.0 else None

    @staticmethod
    def delta(F: float, K: float, r: float, T: float, sigma: float, option_type: str) -> float:
        """Calculate delta."""
        if T <= 0 or sigma <= 0:
            if option_type.upper() in ['C', 'CALL']:
                return 1.0 if F > K else 0.0
            else:
                return -1.0 if F < K else 0.0

        d1 = Black76.d1(F, K, r, T, sigma)
        if option_type.upper() in ['C', 'CALL']:
            return math.exp(-r * T) * norm.cdf(d1)
        else:
            return math.exp(-r * T) * (norm.cdf(d1) - 1)

    @staticmethod
    def gamma(F: float, K: float, r: float, T: float, sigma: float) -> float:
        """Calculate gamma."""
        if T <= 0 or sigma <= 0:
            return 0.0
        d1 = Black76.d1(F, K, r, T, sigma)
        return math.exp(-r * T) * norm.pdf(d1) / (F * sigma * math.sqrt(T))

    @staticmethod
    def theta(F: float, K: float, r: float, T: float, sigma: float, option_type: str) -> float:
        """Calculate theta (per day)."""
        if T <= 0 or sigma <= 0:
            return 0.0
        d1 = Black76.d1(F, K, r, T, sigma)
        d2 = Black76.d2(F, K, r, T, sigma)

        term1 = -F * math.exp(-r * T) * norm.pdf(d1) * sigma / (2 * math.sqrt(T))

        if option_type.upper() in ['C', 'CALL']:
            term2 = r * math.exp(-r * T) * (F * norm.cdf(d1) - K * norm.cdf(d2))
        else:
            term2 = r * math.exp(-r * T) * (K * norm.cdf(-d2) - F * norm.cdf(-d1))

        return (term1 - term2) / 365  # Daily theta

    @staticmethod
    def vega(F: float, K: float, r: float, T: float, sigma: float) -> float:
        """Calculate vega (per 1% vol move)."""
        if T <= 0 or sigma <= 0:
            return 0.0
        d1 = Black76.d1(F, K, r, T, sigma)
        return F * math.exp(-r * T) * norm.pdf(d1) * math.sqrt(T) * 0.01


class DatabentoOptionsIngester:
    """Ingest options data from Databento with Greeks calculation."""

    def __init__(self):
        self.client = db.Historical(key=DATABENTO_API_KEY)
        self.duck = duckdb.connect(DUCKDB_PATH)
        self.pg = psycopg2.connect(DATABASE_URL) if DATABASE_URL else None
        self._ensure_schema()

    def _ensure_schema(self):
        """Create options tables in DuckDB."""
        self.duck.execute("CREATE SCHEMA IF NOT EXISTS options")

        # Options contracts metadata
        self.duck.execute("""
            CREATE TABLE IF NOT EXISTS options.contracts (
                instrument_id BIGINT,
                raw_symbol VARCHAR,
                underlying VARCHAR,
                security_type VARCHAR,
                strike_price DECIMAL(12,4),
                expiration DATE,
                option_type VARCHAR,  -- C/P
                exchange VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (instrument_id)
            )
        """)

        # Options daily OHLCV with Greeks
        self.duck.execute("""
            CREATE TABLE IF NOT EXISTS options.daily_greeks (
                instrument_id BIGINT,
                raw_symbol VARCHAR,
                underlying VARCHAR,
                as_of_date DATE,
                expiration DATE,
                strike_price DECIMAL(12,4),
                option_type VARCHAR,
                open DECIMAL(10,4),
                high DECIMAL(10,4),
                low DECIMAL(10,4),
                close DECIMAL(10,4),
                volume BIGINT,
                open_interest BIGINT,
                underlying_price DECIMAL(10,4),
                risk_free_rate DECIMAL(8,6),
                implied_volatility DECIMAL(8,6),
                delta DECIMAL(8,6),
                gamma DECIMAL(10,8),
                theta DECIMAL(10,6),
                vega DECIMAL(10,6),
                days_to_expiry INTEGER,
                moneyness VARCHAR,
                expiry_bucket VARCHAR,
                source VARCHAR DEFAULT 'databento',
                ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (instrument_id, as_of_date)
            )
        """)

        # Aggregated daily features
        self.duck.execute("""
            CREATE TABLE IF NOT EXISTS options.features_daily (
                underlying VARCHAR,
                as_of_date DATE,
                expiry_bucket VARCHAR,
                iv_atm_call DECIMAL(8,6),
                iv_atm_put DECIMAL(8,6),
                iv_skew DECIMAL(8,6),
                iv_term_structure DECIMAL(8,6),
                iv_rank DECIMAL(5,2),
                delta_weighted_oi_call DECIMAL(18,4),
                delta_weighted_oi_put DECIMAL(18,4),
                gamma_exposure DECIMAL(18,4),
                net_gamma DECIMAL(18,4),
                vega_exposure DECIMAL(18,4),
                theta_decay DECIMAL(18,4),
                put_call_ratio_volume DECIMAL(8,4),
                put_call_ratio_oi DECIMAL(8,4),
                total_volume BIGINT,
                total_open_interest BIGINT,
                max_pain_strike DECIMAL(10,4),
                PRIMARY KEY (underlying, as_of_date, expiry_bucket)
            )
        """)

        self.duck.commit()
        print("DuckDB options schema ready")

    def get_definitions(self, start_date: str = None, end_date: str = None) -> pd.DataFrame:
        """
        Pull definition schema to get all options contracts.
        Filter for Options on Futures (OOF) for our target underlyings.
        """
        if start_date is None:
            start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")

        print(f"\n=== Fetching Definitions from {DATASET} ===")
        print(f"Date range: {start_date} to {end_date}")

        try:
            # Get definitions for all symbols
            data = self.client.timeseries.get_range(
                dataset=DATASET,
                schema="definition",
                symbols="ALL_SYMBOLS",
                start=start_date,
                end=end_date,
            )

            df = data.to_df()
            print(f"Retrieved {len(df)} instrument definitions")

            if df.empty:
                return df

            # Filter for options on futures
            if 'security_type' in df.columns:
                options_df = df[df['security_type'].isin(['OOF', 'FOP', 'OPT'])]
                print(f"Options on Futures: {len(options_df)}")
            else:
                options_df = df

            # Filter for our target underlyings
            target_options = pd.DataFrame()
            for underlying in UNDERLYINGS:
                if 'underlying' in df.columns:
                    matches = options_df[options_df['underlying'].str.contains(underlying, na=False)]
                elif 'raw_symbol' in df.columns:
                    matches = options_df[options_df['raw_symbol'].str.startswith(underlying, na=False)]
                else:
                    matches = pd.DataFrame()

                if not matches.empty:
                    print(f"  {underlying}: {len(matches)} options")
                    target_options = pd.concat([target_options, matches])

            return target_options

        except Exception as e:
            print(f"Error fetching definitions: {e}")
            return pd.DataFrame()

    def get_futures_prices(self, symbols: List[str], start_date: str, end_date: str) -> Dict[str, pd.DataFrame]:
        """Get underlying futures prices for Greeks calculation."""
        print(f"\n=== Fetching Underlying Futures Prices ===")

        futures_data = {}

        for symbol in symbols:
            try:
                data = self.client.timeseries.get_range(
                    dataset=DATASET,
                    schema="ohlcv-1d",
                    symbols=[symbol],
                    start=start_date,
                    end=end_date,
                )

                df = data.to_df()
                if not df.empty:
                    futures_data[symbol] = df
                    print(f"  {symbol}: {len(df)} days")

            except Exception as e:
                print(f"  {symbol}: Error - {e}")

        return futures_data

    def get_risk_free_rate(self, date: datetime) -> float:
        """
        Get risk-free rate from FRED data in DuckDB.
        Falls back to 5% if not available.
        """
        try:
            result = self.duck.execute("""
                SELECT value / 100.0 as rate
                FROM raw.fred_observations_1d
                WHERE series_id = 'DGS3MO'
                  AND as_of_date <= ?
                  AND value IS NOT NULL
                ORDER BY as_of_date DESC
                LIMIT 1
            """, [date]).fetchone()

            if result:
                return result[0]
        except:
            pass

        return 0.05  # Default 5%

    def get_options_ohlcv(self, symbols: List[str], start_date: str, end_date: str) -> pd.DataFrame:
        """Pull options OHLCV data."""
        print(f"\n=== Fetching Options OHLCV ===")

        all_data = []

        # Process in batches
        batch_size = 100
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i + batch_size]

            try:
                data = self.client.timeseries.get_range(
                    dataset=DATASET,
                    schema="ohlcv-1d",
                    symbols=batch,
                    start=start_date,
                    end=end_date,
                )

                df = data.to_df()
                if not df.empty:
                    all_data.append(df)
                    print(f"  Batch {i // batch_size + 1}: {len(df)} rows")

            except Exception as e:
                print(f"  Batch {i // batch_size + 1}: Error - {e}")

        if all_data:
            return pd.concat(all_data, ignore_index=True)
        return pd.DataFrame()

    def calculate_greeks(self, options_df: pd.DataFrame, futures_prices: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        """Calculate Greeks for all options using Black-76."""
        print(f"\n=== Calculating Greeks ===")

        results = []

        for idx, row in options_df.iterrows():
            try:
                # Get underlying price
                underlying = row.get('underlying', '')
                if not underlying:
                    # Try to extract from symbol
                    raw_symbol = row.get('raw_symbol', '')
                    for u in UNDERLYINGS:
                        if raw_symbol.startswith(u):
                            underlying = u
                            break

                as_of_date = row.get('ts_event', row.get('as_of_date'))
                if isinstance(as_of_date, pd.Timestamp):
                    as_of_date = as_of_date.date()

                # Get futures price
                F = None
                if underlying in futures_prices:
                    fut_df = futures_prices[underlying]
                    mask = fut_df['ts_event'].dt.date == as_of_date
                    if mask.any():
                        F = fut_df.loc[mask, 'close'].values[0]

                if F is None:
                    continue

                # Option parameters
                K = row.get('strike_price', 0)
                expiry = row.get('expiration')
                if isinstance(expiry, pd.Timestamp):
                    expiry = expiry.date()

                T = (expiry - as_of_date).days / 365.0 if expiry else 0
                if T <= 0:
                    continue

                option_type = row.get('option_type', 'C')
                price = row.get('close', 0)
                r = self.get_risk_free_rate(as_of_date)

                # Calculate IV
                iv = Black76.implied_volatility(price, F, K, r, T, option_type)
                if iv is None:
                    iv = 0.3  # Default

                # Calculate Greeks
                delta = Black76.delta(F, K, r, T, iv, option_type)
                gamma = Black76.gamma(F, K, r, T, iv)
                theta = Black76.theta(F, K, r, T, iv, option_type)
                vega = Black76.vega(F, K, r, T, iv)

                # Moneyness
                if abs(K - F) / F < 0.02:
                    moneyness = 'ATM'
                elif (option_type.upper() == 'C' and K < F) or (option_type.upper() == 'P' and K > F):
                    moneyness = 'ITM'
                else:
                    moneyness = 'OTM'

                # Expiry bucket
                days_to_expiry = int(T * 365)
                if days_to_expiry <= 45:
                    expiry_bucket = '1M'
                elif days_to_expiry <= 100:
                    expiry_bucket = '3M'
                else:
                    expiry_bucket = '6M'

                results.append({
                    'instrument_id': row.get('instrument_id'),
                    'raw_symbol': row.get('raw_symbol'),
                    'underlying': underlying,
                    'as_of_date': as_of_date,
                    'expiration': expiry,
                    'strike_price': K,
                    'option_type': option_type,
                    'open': row.get('open'),
                    'high': row.get('high'),
                    'low': row.get('low'),
                    'close': price,
                    'volume': row.get('volume'),
                    'open_interest': row.get('open_interest', 0),
                    'underlying_price': F,
                    'risk_free_rate': r,
                    'implied_volatility': iv,
                    'delta': delta,
                    'gamma': gamma,
                    'theta': theta,
                    'vega': vega,
                    'days_to_expiry': days_to_expiry,
                    'moneyness': moneyness,
                    'expiry_bucket': expiry_bucket,
                })

            except Exception as e:
                continue

        print(f"Calculated Greeks for {len(results)} options")
        return pd.DataFrame(results)

    def compute_daily_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute aggregated daily options features."""
        print(f"\n=== Computing Daily Features ===")

        features = []

        for (underlying, date, bucket), group in df.groupby(['underlying', 'as_of_date', 'expiry_bucket']):
            calls = group[group['option_type'].str.upper() == 'C']
            puts = group[group['option_type'].str.upper() == 'P']

            # IV metrics
            atm_calls = calls[calls['moneyness'] == 'ATM']
            atm_puts = puts[puts['moneyness'] == 'ATM']

            iv_atm_call = atm_calls['implied_volatility'].mean() if len(atm_calls) > 0 else None
            iv_atm_put = atm_puts['implied_volatility'].mean() if len(atm_puts) > 0 else None

            otm_calls = calls[calls['moneyness'] == 'OTM']
            otm_puts = puts[puts['moneyness'] == 'OTM']

            iv_skew = None
            if len(otm_puts) > 0 and len(otm_calls) > 0:
                iv_skew = otm_puts['implied_volatility'].mean() - otm_calls['implied_volatility'].mean()

            # Greek aggregates
            delta_oi_call = (calls['delta'] * calls['open_interest'].fillna(0)).sum()
            delta_oi_put = (puts['delta'] * puts['open_interest'].fillna(0)).sum()

            spot = group['underlying_price'].iloc[0] if len(group) > 0 else None
            gamma_exp = (group['gamma'] * group['open_interest'].fillna(0) * (spot ** 2) * 0.01).sum() if spot else None

            vega_exp = (group['vega'] * group['open_interest'].fillna(0)).sum()
            theta_decay = group['theta'].sum()

            # Volume/OI ratios
            call_vol = calls['volume'].sum()
            put_vol = puts['volume'].sum()
            call_oi = calls['open_interest'].fillna(0).sum()
            put_oi = puts['open_interest'].fillna(0).sum()

            pc_ratio_vol = put_vol / call_vol if call_vol > 0 else None
            pc_ratio_oi = put_oi / call_oi if call_oi > 0 else None

            features.append({
                'underlying': underlying,
                'as_of_date': date,
                'expiry_bucket': bucket,
                'iv_atm_call': iv_atm_call,
                'iv_atm_put': iv_atm_put,
                'iv_skew': iv_skew,
                'delta_weighted_oi_call': delta_oi_call,
                'delta_weighted_oi_put': delta_oi_put,
                'gamma_exposure': gamma_exp,
                'vega_exposure': vega_exp,
                'theta_decay': theta_decay,
                'put_call_ratio_volume': pc_ratio_vol,
                'put_call_ratio_oi': pc_ratio_oi,
                'total_volume': call_vol + put_vol,
                'total_open_interest': call_oi + put_oi,
            })

        print(f"Computed {len(features)} daily feature records")
        return pd.DataFrame(features)

    def store_to_duckdb(self, greeks_df: pd.DataFrame, features_df: pd.DataFrame):
        """Store data to DuckDB."""
        print(f"\n=== Storing to DuckDB ===")

        if not greeks_df.empty:
            # Register and insert
            self.duck.register('greeks_temp', greeks_df)
            self.duck.execute("""
                INSERT OR REPLACE INTO options.daily_greeks
                SELECT * FROM greeks_temp
            """)
            print(f"  Stored {len(greeks_df)} Greeks records")

        if not features_df.empty:
            self.duck.register('features_temp', features_df)
            self.duck.execute("""
                INSERT OR REPLACE INTO options.features_daily
                SELECT * FROM features_temp
            """)
            print(f"  Stored {len(features_df)} feature records")

        self.duck.commit()

    def sync_to_prisma(self, greeks_df: pd.DataFrame):
        """Sync options data to Prisma."""
        if not self.pg or greeks_df.empty:
            return

        print(f"\n=== Syncing to Prisma ===")

        cur = self.pg.cursor()

        # Create table if not exists
        cur.execute("""
            CREATE TABLE IF NOT EXISTS options_greeks (
                id SERIAL PRIMARY KEY,
                instrument_id BIGINT,
                raw_symbol VARCHAR(50),
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
                underlying_price DECIMAL(10,4),
                risk_free_rate DECIMAL(8,6),
                implied_volatility DECIMAL(8,6),
                delta DECIMAL(8,6),
                gamma DECIMAL(10,8),
                theta DECIMAL(10,6),
                vega DECIMAL(10,6),
                days_to_expiry INTEGER,
                moneyness VARCHAR(10),
                expiry_bucket VARCHAR(5),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(instrument_id, as_of_date)
            );
            CREATE INDEX IF NOT EXISTS idx_options_greeks_underlying ON options_greeks(underlying);
            CREATE INDEX IF NOT EXISTS idx_options_greeks_date ON options_greeks(as_of_date);
            CREATE INDEX IF NOT EXISTS idx_options_greeks_expiry ON options_greeks(expiry_bucket);
        """)
        self.pg.commit()

        # Insert data
        inserted = 0
        for _, row in greeks_df.iterrows():
            try:
                cur.execute("""
                    INSERT INTO options_greeks (
                        instrument_id, raw_symbol, underlying, as_of_date, expiration_date,
                        strike_price, option_type, open, high, low, close,
                        volume, open_interest, underlying_price, risk_free_rate,
                        implied_volatility, delta, gamma, theta, vega,
                        days_to_expiry, moneyness, expiry_bucket
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (instrument_id, as_of_date) DO UPDATE SET
                        implied_volatility = EXCLUDED.implied_volatility,
                        delta = EXCLUDED.delta,
                        gamma = EXCLUDED.gamma,
                        theta = EXCLUDED.theta,
                        vega = EXCLUDED.vega,
                        open_interest = EXCLUDED.open_interest
                """, (
                    row.get('instrument_id'),
                    row.get('raw_symbol'),
                    row.get('underlying'),
                    row.get('as_of_date'),
                    row.get('expiration'),
                    row.get('strike_price'),
                    row.get('option_type'),
                    row.get('open'),
                    row.get('high'),
                    row.get('low'),
                    row.get('close'),
                    row.get('volume'),
                    row.get('open_interest'),
                    row.get('underlying_price'),
                    row.get('risk_free_rate'),
                    row.get('implied_volatility'),
                    row.get('delta'),
                    row.get('gamma'),
                    row.get('theta'),
                    row.get('vega'),
                    row.get('days_to_expiry'),
                    row.get('moneyness'),
                    row.get('expiry_bucket'),
                ))
                inserted += 1
            except Exception as e:
                continue

        self.pg.commit()
        print(f"  Synced {inserted} records to Prisma")
        cur.close()

    def run(self, start_date: str = None, end_date: str = None):
        """Run full ingestion pipeline."""
        print("=" * 60)
        print("DATABENTO OPTIONS INGESTION")
        print(f"Time: {datetime.now().isoformat()}")
        print(f"Dataset: {DATASET}")
        print(f"Underlyings: {UNDERLYINGS}")
        print("=" * 60)

        if start_date is None:
            start_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")

        # 1. Get definitions
        definitions = self.get_definitions(start_date, end_date)
        if definitions.empty:
            print("No options definitions found!")
            return

        # 2. Get underlying futures prices
        futures_prices = self.get_futures_prices(UNDERLYINGS, start_date, end_date)

        # 3. Get options OHLCV
        option_symbols = definitions['raw_symbol'].unique().tolist() if 'raw_symbol' in definitions.columns else []
        if not option_symbols:
            print("No option symbols to fetch!")
            return

        options_ohlcv = self.get_options_ohlcv(option_symbols[:500], start_date, end_date)  # Limit for testing
        if options_ohlcv.empty:
            print("No options OHLCV data retrieved!")
            return

        # 4. Calculate Greeks
        greeks_df = self.calculate_greeks(options_ohlcv, futures_prices)

        # 5. Compute daily features
        features_df = self.compute_daily_features(greeks_df)

        # 6. Store to DuckDB
        self.store_to_duckdb(greeks_df, features_df)

        # 7. Sync to Prisma
        self.sync_to_prisma(greeks_df)

        # Summary
        print("\n" + "=" * 60)
        print("INGESTION COMPLETE")
        print("=" * 60)
        print(f"Options with Greeks: {len(greeks_df)}")
        print(f"Daily features: {len(features_df)}")

        self.duck.close()
        if self.pg:
            self.pg.close()


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Ingest Databento options with Greeks")
    parser.add_argument("--start", help="Start date (YYYY-MM-DD)", default=None)
    parser.add_argument("--end", help="End date (YYYY-MM-DD)", default=None)
    parser.add_argument("--test", action="store_true", help="Run in test mode (last 7 days)")

    args = parser.parse_args()

    if args.test:
        start = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        end = datetime.now().strftime("%Y-%m-%d")
    else:
        start = args.start
        end = args.end

    ingester = DatabentoOptionsIngester()
    ingester.run(start_date=start, end_date=end)


if __name__ == "__main__":
    main()
