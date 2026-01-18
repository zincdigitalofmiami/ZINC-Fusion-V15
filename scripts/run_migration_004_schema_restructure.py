# ⚠️ DEPRECATED: Historical migration script from v1 to v2 schema.
# This script was used during the initial migration and should not be run again.
# Kept for reference only.

#!/usr/bin/env python3
"""
Migration 004: Schema Restructure
=================================
Replace raw.* catch-all with domain-specific schemas:
- mkt: Market data (futures, options, fx)
- econ: Economic indicators (rates, inflation, labor, activity, vol, commodities, fx)
- pos: Positioning (CFTC)
- supply: Supply/demand (USDA, EPA)
- alt: Alternative data (news, weather, legislation)
- features: ML features (elite, options, weather)

NO MEDALLION. Just clean domain organization.
"""

import os
import sys
from datetime import datetime

import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set")
    sys.exit(1)


# FRED series categorization
FRED_CATEGORIES = {
    "rates": [
        "DFF", "FEDFUNDS", "SOFR", "DPRIME", "MPRIME",
        "DGS1MO", "DGS3MO", "DGS6MO", "DGS1", "DGS2", "DGS3", "DGS5", "DGS7", "DGS10", "DGS20", "DGS30",
        "DFII5", "DFII7", "DFII10", "DFII20", "DFII30",
        "T10Y2Y", "T10Y3M", "T10YIE", "T5YIE",
        "BAMLH0A0HYM2", "BAMLC0A0CM", "BAMLC0A4CBBB", "BAMLC0A1CAAA",
        "TEDRATE", "AAA", "BAA", "MORTGAGE30US", "MORTGAGE15US",
    ],
    "inflation": [
        "CPIAUCSL", "CPILFESL", "CPIUFDSL",
        "PCEPI", "PCEPILFE",
        "PPIFIS", "PPIACO",
    ],
    "labor": [
        "UNRATE", "PAYEMS", "ICSA", "CCSA",
        "CES0500000003", "AHETPI",
        "CIVPART", "EMRATIO", "U6RATE",
        "JTSJOL", "JTSQUR",
    ],
    "activity": [
        "GDP", "GDPC1", "GDPPOT",
        "INDPRO", "IPMAN", "IPMANSICS",
        "UMCSENT", "UMCSENT1",
        "RSXFS", "RSAFS",
        "HOUST", "PERMIT", "HSN1F",
        "DGORDER", "NEWORDER",
        "BOPTEXP", "BOPTIMP",
    ],
    "vol_indices": [
        "VIXCLS", "OVXCLS", "GVZCLS",
        "NFCI", "STLFSI4", "ANFCI", "KCFSI",
        "CFNAI", "DSPIC96",
    ],
    "commodities": [
        "PSOILUSDM", "PSOYBUSDM", "PMAIZMTUSDM",
        "PWHEAMTUSDM", "PRICEPUSDM", "PSALMUSDM",
        "DCOILWTICO", "DCOILBRENTEU",
        "DHOILNYH", "DHHNGSP", "DJFUELUSGULF",
        "GASREGW", "GASALLW",
        "WPU0561", "PCU325311325311",
    ],
    "fx": [
        "DEXBZUS", "DEXCHUS", "DEXUSEU", "DEXJPUS", "DEXMXUS",
        "DEXCAUS", "DEXKOUS", "DEXINUS", "DEXTAUS", "DEXUSAL",
        "DTWEXBGS", "DTWEXAFEGS", "DTWEXEMEGS", "DTWEXM",
    ],
    "money": [
        "M1SL", "M2SL", "WALCL", "WTREGEN", "RRPONTSYD",
        "TOTRESNS", "BOGMBASE",
    ],
}


def get_connection():
    return psycopg2.connect(DATABASE_URL)


def step_1_create_schemas(conn):
    """Create new domain schemas."""
    print("\n=== Step 1: Creating new schemas ===")
    schemas = ["mkt", "econ", "pos", "supply", "alt"]

    with conn.cursor() as cur:
        for schema in schemas:
            cur.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
            print(f"  Created schema: {schema}")
    conn.commit()
    print("  Done.")


def step_2_create_mkt_tables(conn):
    """Create market data tables."""
    print("\n=== Step 2: Creating mkt.* tables ===")

    with conn.cursor() as cur:
        # mkt.futures_1d
        cur.execute("""
            CREATE TABLE IF NOT EXISTS mkt.futures_1d (
                event_date DATE NOT NULL,
                symbol VARCHAR(20) NOT NULL,
                open DOUBLE PRECISION,
                high DOUBLE PRECISION,
                low DOUBLE PRECISION,
                close DOUBLE PRECISION,
                volume BIGINT,
                open_interest BIGINT,
                source VARCHAR(50),
                ingested_at TIMESTAMPTZ DEFAULT NOW(),
                knowledge_time TIMESTAMPTZ DEFAULT NOW(),
                row_hash VARCHAR(64),
                PRIMARY KEY (event_date, symbol)
            )
        """)
        print("  Created mkt.futures_1d")

        # mkt.futures_1h
        cur.execute("""
            CREATE TABLE IF NOT EXISTS mkt.futures_1h (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(20) NOT NULL,
                event_time TIMESTAMP NOT NULL,
                open DOUBLE PRECISION,
                high DOUBLE PRECISION,
                low DOUBLE PRECISION,
                close DOUBLE PRECISION,
                volume BIGINT,
                open_interest BIGINT,
                source VARCHAR(50),
                ingested_at TIMESTAMPTZ DEFAULT NOW(),
                knowledge_time TIMESTAMPTZ DEFAULT NOW(),
                row_hash VARCHAR(64)
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_mkt_futures_1h_symbol_time ON mkt.futures_1h(symbol, event_time)")
        print("  Created mkt.futures_1h")

        # mkt.options_1d
        cur.execute("""
            CREATE TABLE IF NOT EXISTS mkt.options_1d (
                id SERIAL PRIMARY KEY,
                underlying VARCHAR(20) NOT NULL,
                event_date DATE NOT NULL,
                expiration DATE NOT NULL,
                strike DOUBLE PRECISION NOT NULL,
                option_type VARCHAR(4) NOT NULL,
                open DOUBLE PRECISION,
                high DOUBLE PRECISION,
                low DOUBLE PRECISION,
                close DOUBLE PRECISION,
                volume BIGINT,
                open_interest BIGINT,
                source VARCHAR(50),
                ingested_at TIMESTAMPTZ DEFAULT NOW(),
                knowledge_time TIMESTAMPTZ DEFAULT NOW(),
                row_hash VARCHAR(64)
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_mkt_options_1d_underlying_date ON mkt.options_1d(underlying, event_date)")
        print("  Created mkt.options_1d")

        # mkt.fx_1d
        cur.execute("""
            CREATE TABLE IF NOT EXISTS mkt.fx_1d (
                id SERIAL PRIMARY KEY,
                pair VARCHAR(10) NOT NULL,
                event_date DATE NOT NULL,
                rate DOUBLE PRECISION NOT NULL,
                source VARCHAR(50),
                ingested_at TIMESTAMPTZ DEFAULT NOW(),
                knowledge_time TIMESTAMPTZ DEFAULT NOW(),
                row_hash VARCHAR(64),
                UNIQUE(pair, event_date)
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_mkt_fx_1d_pair_date ON mkt.fx_1d(pair, event_date)")
        print("  Created mkt.fx_1d")

    conn.commit()
    print("  Done.")


def step_3_create_econ_tables(conn):
    """Create economic indicator tables."""
    print("\n=== Step 3: Creating econ.* tables ===")

    # Common column structure for all econ tables
    econ_columns = """
        id SERIAL PRIMARY KEY,
        series_id VARCHAR(50) NOT NULL,
        event_date DATE NOT NULL,
        value DOUBLE PRECISION,
        source VARCHAR(50) DEFAULT 'FRED',
        ingested_at TIMESTAMPTZ DEFAULT NOW(),
        knowledge_time TIMESTAMPTZ DEFAULT NOW(),
        row_hash VARCHAR(64),
        UNIQUE(series_id, event_date)
    """

    tables = ["rates_1d", "inflation_1d", "labor_1d", "activity_1d", "vol_indices_1d", "commodities_1d", "fx_1d", "money_1d"]

    with conn.cursor() as cur:
        for table in tables:
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS econ.{table} (
                    {econ_columns}
                )
            """)
            cur.execute(f"CREATE INDEX IF NOT EXISTS idx_econ_{table.replace('_1d', '')}_series_date ON econ.{table}(series_id, event_date)")
            print(f"  Created econ.{table}")

    conn.commit()
    print("  Done.")


def step_4_create_pos_tables(conn):
    """Create positioning tables."""
    print("\n=== Step 4: Creating pos.* tables ===")

    with conn.cursor() as cur:
        # pos.cftc_1w
        cur.execute("""
            CREATE TABLE IF NOT EXISTS pos.cftc_1w (
                id SERIAL PRIMARY KEY,
                event_date DATE NOT NULL,
                symbol VARCHAR(20) NOT NULL,
                open_interest BIGINT,
                prod_merc_long BIGINT,
                prod_merc_short BIGINT,
                prod_merc_net BIGINT,
                swap_long BIGINT,
                swap_short BIGINT,
                swap_net BIGINT,
                managed_money_long BIGINT,
                managed_money_short BIGINT,
                managed_money_net BIGINT,
                other_rept_long BIGINT,
                other_rept_short BIGINT,
                other_rept_net BIGINT,
                nonrept_long BIGINT,
                nonrept_short BIGINT,
                nonrept_net BIGINT,
                managed_money_net_pct_oi DOUBLE PRECISION,
                prod_merc_net_pct_oi DOUBLE PRECISION,
                source VARCHAR(50),
                ingested_at TIMESTAMPTZ DEFAULT NOW(),
                knowledge_time TIMESTAMPTZ DEFAULT NOW(),
                row_hash VARCHAR(64),
                UNIQUE(symbol, event_date)
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_pos_cftc_1w_symbol_date ON pos.cftc_1w(symbol, event_date)")
        print("  Created pos.cftc_1w")

        # pos.cftc_cits_1w
        cur.execute("""
            CREATE TABLE IF NOT EXISTS pos.cftc_cits_1w (
                id SERIAL PRIMARY KEY,
                event_date DATE NOT NULL,
                symbol VARCHAR(20) NOT NULL,
                cit_long BIGINT,
                cit_short BIGINT,
                cit_net BIGINT,
                cit_pct_oi DOUBLE PRECISION,
                source VARCHAR(50),
                ingested_at TIMESTAMPTZ DEFAULT NOW(),
                knowledge_time TIMESTAMPTZ DEFAULT NOW(),
                row_hash VARCHAR(64),
                UNIQUE(symbol, event_date)
            )
        """)
        print("  Created pos.cftc_cits_1w")

    conn.commit()
    print("  Done.")


def step_5_create_supply_tables(conn):
    """Create supply/demand tables."""
    print("\n=== Step 5: Creating supply.* tables ===")

    with conn.cursor() as cur:
        # supply.usda_wasde_1m
        cur.execute("""
            CREATE TABLE IF NOT EXISTS supply.usda_wasde_1m (
                id SERIAL PRIMARY KEY,
                event_date DATE NOT NULL,
                commodity VARCHAR(50) NOT NULL,
                attribute VARCHAR(100) NOT NULL,
                region VARCHAR(50),
                value DOUBLE PRECISION,
                unit VARCHAR(20),
                marketing_year VARCHAR(20),
                source VARCHAR(50) DEFAULT 'USDA',
                ingested_at TIMESTAMPTZ DEFAULT NOW(),
                knowledge_time TIMESTAMPTZ DEFAULT NOW(),
                row_hash VARCHAR(64)
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_supply_usda_wasde_commodity_date ON supply.usda_wasde_1m(commodity, event_date)")
        print("  Created supply.usda_wasde_1m")

        # supply.usda_exports_1w
        cur.execute("""
            CREATE TABLE IF NOT EXISTS supply.usda_exports_1w (
                id SERIAL PRIMARY KEY,
                event_date DATE NOT NULL,
                commodity VARCHAR(50) NOT NULL,
                country VARCHAR(100),
                weekly_exports DOUBLE PRECISION,
                accumulated_exports DOUBLE PRECISION,
                outstanding_sales DOUBLE PRECISION,
                marketing_year VARCHAR(20),
                source VARCHAR(50) DEFAULT 'USDA',
                ingested_at TIMESTAMPTZ DEFAULT NOW(),
                knowledge_time TIMESTAMPTZ DEFAULT NOW(),
                row_hash VARCHAR(64)
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_supply_usda_exports_commodity_date ON supply.usda_exports_1w(commodity, event_date)")
        print("  Created supply.usda_exports_1w")

        # supply.epa_rin_1d
        cur.execute("""
            CREATE TABLE IF NOT EXISTS supply.epa_rin_1d (
                id SERIAL PRIMARY KEY,
                event_date DATE NOT NULL,
                rin_type VARCHAR(20) NOT NULL,
                price DOUBLE PRECISION,
                source VARCHAR(50) DEFAULT 'EPA',
                ingested_at TIMESTAMPTZ DEFAULT NOW(),
                knowledge_time TIMESTAMPTZ DEFAULT NOW(),
                row_hash VARCHAR(64),
                UNIQUE(rin_type, event_date)
            )
        """)
        print("  Created supply.epa_rin_1d")

    conn.commit()
    print("  Done.")


def step_6_create_alt_tables(conn):
    """Create alternative data tables."""
    print("\n=== Step 6: Creating alt.* tables ===")

    with conn.cursor() as cur:
        # alt.news_1d
        cur.execute("""
            CREATE TABLE IF NOT EXISTS alt.news_1d (
                id SERIAL PRIMARY KEY,
                event_date DATE NOT NULL,
                headline TEXT NOT NULL,
                source VARCHAR(100),
                url TEXT,
                sentiment_score DOUBLE PRECISION,
                relevance_score DOUBLE PRECISION,
                specialist_tags TEXT[],
                ingested_at TIMESTAMPTZ DEFAULT NOW(),
                knowledge_time TIMESTAMPTZ DEFAULT NOW(),
                row_hash VARCHAR(64)
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_alt_news_1d_date ON alt.news_1d(event_date)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_alt_news_1d_tags ON alt.news_1d USING GIN(specialist_tags)")
        print("  Created alt.news_1d")

        # alt.weather_1d
        cur.execute("""
            CREATE TABLE IF NOT EXISTS alt.weather_1d (
                id SERIAL PRIMARY KEY,
                event_date DATE NOT NULL,
                station_id VARCHAR(20) NOT NULL,
                region VARCHAR(50),
                temp_max DOUBLE PRECISION,
                temp_min DOUBLE PRECISION,
                temp_avg DOUBLE PRECISION,
                precip DOUBLE PRECISION,
                snow DOUBLE PRECISION,
                source VARCHAR(50) DEFAULT 'NOAA',
                ingested_at TIMESTAMPTZ DEFAULT NOW(),
                knowledge_time TIMESTAMPTZ DEFAULT NOW(),
                row_hash VARCHAR(64)
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_alt_weather_1d_region_date ON alt.weather_1d(region, event_date)")
        print("  Created alt.weather_1d")

        # alt.legislation_1d
        cur.execute("""
            CREATE TABLE IF NOT EXISTS alt.legislation_1d (
                id SERIAL PRIMARY KEY,
                event_date DATE NOT NULL,
                document_number VARCHAR(50),
                title TEXT,
                agency VARCHAR(200),
                document_type VARCHAR(50),
                action VARCHAR(50),
                specialist_tags TEXT[],
                source VARCHAR(50) DEFAULT 'FEDERAL_REGISTER',
                ingested_at TIMESTAMPTZ DEFAULT NOW(),
                knowledge_time TIMESTAMPTZ DEFAULT NOW(),
                row_hash VARCHAR(64)
            )
        """)
        print("  Created alt.legislation_1d")

    conn.commit()
    print("  Done.")


def step_7_rename_features_tables(conn):
    """Rename gold.* to features.* (already exists, just verify)."""
    print("\n=== Step 7: Verifying features schema ===")

    with conn.cursor() as cur:
        # Check if features schema exists
        cur.execute("SELECT schema_name FROM information_schema.schemata WHERE schema_name = 'features'")
        if cur.fetchone():
            print("  features schema already exists")
        else:
            cur.execute("CREATE SCHEMA features")
            print("  Created features schema")

        # Check existing tables in gold schema
        cur.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'gold'
        """)
        gold_tables = [row[0] for row in cur.fetchall()]
        print(f"  Gold tables to migrate: {gold_tables}")

        # We'll keep gold.* for now and just ensure features schema exists
        # The actual rename will happen after we verify everything works

    conn.commit()
    print("  Done.")


def step_8_migrate_futures(conn):
    """Migrate raw.market_futures_1d to mkt.futures_1d."""
    print("\n=== Step 8: Migrating futures data ===")

    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM raw.market_futures_1d")
        count = cur.fetchone()[0]
        print(f"  Source rows: {count:,}")

        if count == 0:
            print("  No data to migrate")
            return

        cur.execute("""
            INSERT INTO mkt.futures_1d (event_date, symbol, open, high, low, close, volume, source, ingested_at, knowledge_time, row_hash)
            SELECT event_date, symbol, open, high, low, close, volume, source, ingested_at, knowledge_time, row_hash
            FROM raw.market_futures_1d
            ON CONFLICT (event_date, symbol) DO NOTHING
        """)
        migrated = cur.rowcount
        print(f"  Migrated rows: {migrated:,}")

    conn.commit()
    print("  Done.")


def step_9_migrate_futures_1h(conn):
    """Migrate raw.market_futures_1h to mkt.futures_1h."""
    print("\n=== Step 9: Migrating intraday futures data ===")

    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM raw.market_futures_1h")
        count = cur.fetchone()[0]
        print(f"  Source rows: {count:,}")

        if count == 0:
            print("  No data to migrate")
            return

        # Batch migrate to avoid memory issues
        batch_size = 100000
        offset = 0
        total_migrated = 0

        while True:
            cur.execute(f"""
                INSERT INTO mkt.futures_1h (symbol, event_time, open, high, low, close, volume, open_interest, source, ingested_at, knowledge_time, row_hash)
                SELECT symbol, event_time, open, high, low, close, volume, open_interest, source, created_at, knowledge_time, row_hash
                FROM raw.market_futures_1h
                ORDER BY id
                LIMIT {batch_size} OFFSET {offset}
            """)
            migrated = cur.rowcount
            if migrated == 0:
                break
            total_migrated += migrated
            offset += batch_size
            print(f"    Migrated batch: {total_migrated:,} / {count:,}")
            conn.commit()

        print(f"  Total migrated: {total_migrated:,}")

    print("  Done.")


def step_10_migrate_options(conn):
    """Migrate raw.options_futures_1d to mkt.options_1d."""
    print("\n=== Step 10: Migrating options data ===")

    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM raw.options_futures_1d")
        count = cur.fetchone()[0]
        print(f"  Source rows: {count:,}")

        if count == 0:
            print("  No data to migrate")
            return

        cur.execute("""
            INSERT INTO mkt.options_1d (underlying, event_date, expiration, strike, option_type, open, high, low, close, volume, open_interest, source, ingested_at, knowledge_time, row_hash)
            SELECT underlying, event_date, expiration, strike, option_type, open, high, low, close, volume, open_interest, source, ingested_at, knowledge_time, row_hash
            FROM raw.options_futures_1d
        """)
        migrated = cur.rowcount
        print(f"  Migrated rows: {migrated:,}")

    conn.commit()
    print("  Done.")


def step_11_migrate_fx(conn):
    """Migrate raw.fx_spot_1d to mkt.fx_1d."""
    print("\n=== Step 11: Migrating FX data ===")

    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM raw.fx_spot_1d")
        count = cur.fetchone()[0]
        print(f"  Source rows: {count:,}")

        if count == 0:
            print("  No data to migrate")
            return

        cur.execute("""
            INSERT INTO mkt.fx_1d (pair, event_date, rate, source, ingested_at, knowledge_time, row_hash)
            SELECT pair, event_date, rate, source, created_at, knowledge_time, row_hash
            FROM raw.fx_spot_1d
            ON CONFLICT (pair, event_date) DO NOTHING
        """)
        migrated = cur.rowcount
        print(f"  Migrated rows: {migrated:,}")

    conn.commit()
    print("  Done.")


def step_12_migrate_fred(conn):
    """Migrate raw.fred_observations_1d to categorized econ.* tables."""
    print("\n=== Step 12: Migrating FRED data to econ.* tables ===")

    # Build reverse mapping: series_id -> category
    series_to_category = {}
    for category, series_list in FRED_CATEGORIES.items():
        for series in series_list:
            series_to_category[series] = category

    # Map category to table
    # NOTE: FX now routes to mkt.fx_1d (consolidated)
    category_to_table = {
        "rates": "econ.rates_1d",
        "inflation": "econ.inflation_1d",
        "labor": "econ.labor_1d",
        "activity": "econ.activity_1d",
        "vol_indices": "econ.vol_indices_1d",
        "commodities": "econ.commodities_1d",
        "fx": "mkt.fx_1d",  # Consolidated - FRED FX goes to mkt schema
        "money": "econ.money_1d",
    }

    # FRED series_id to FX pair mapping
    FRED_FX_TO_PAIR = {
        "DEXBZUS": "BRL/USD",
        "DEXCHUS": "CNY/USD",
        "DEXUSEU": "EUR/USD",
        "DEXJPUS": "USD/JPY",
        "DEXMXUS": "MXN/USD",
        "DEXCAUS": "CAD/USD",
        "DEXKOUS": "KRW/USD",
        "DEXINUS": "INR/USD",
        "DEXTAUS": "TWD/USD",
        "DEXUSAL": "AUD/USD",
        "DTWEXBGS": "DXY_BROAD",
        "DTWEXAFEGS": "DXY_AFE",
        "DTWEXEMEGS": "DXY_EME",
        "DTWEXM": "DXY_MAJOR",
    }

    with conn.cursor() as cur:
        # Get all unique series_ids
        cur.execute("SELECT DISTINCT series_id FROM raw.fred_observations_1d ORDER BY series_id")
        all_series = [row[0] for row in cur.fetchall()]
        print(f"  Found {len(all_series)} unique FRED series")

        # Categorize each series
        categorized = {cat: [] for cat in category_to_table.keys()}
        uncategorized = []

        for series in all_series:
            found = False
            for known_series, category in series_to_category.items():
                # Exact match or prefix match (for DGS10, etc.)
                if series == known_series or series.startswith(known_series.rstrip("*")):
                    categorized[category].append(series)
                    found = True
                    break
            if not found:
                uncategorized.append(series)

        # Print summary
        for category, series_list in categorized.items():
            if series_list:
                print(f"    {category}: {len(series_list)} series")
        if uncategorized:
            print(f"    uncategorized: {len(uncategorized)} series: {uncategorized[:10]}...")

        # Migrate each category
        for category, series_list in categorized.items():
            if not series_list:
                continue

            table = category_to_table[category]
            series_tuple = tuple(series_list)

            # FX has different schema - maps series_id to pair, value to rate
            if category == "fx":
                # Migrate FX to mkt.fx_1d with series_id -> pair mapping
                for series_id in series_list:
                    pair = FRED_FX_TO_PAIR.get(series_id, series_id)  # Fallback to series_id if not mapped
                    cur.execute("""
                        INSERT INTO mkt.fx_1d (pair, event_date, rate, source, ingested_at, knowledge_time, row_hash)
                        SELECT %s, event_date, value, 'FRED', created_at, knowledge_time, row_hash
                        FROM raw.fred_observations_1d
                        WHERE series_id = %s
                        ON CONFLICT (pair, event_date) DO NOTHING
                    """, (pair, series_id))
                migrated = cur.rowcount
                print(f"    Migrated FX series to mkt.fx_1d with pair mapping")
                conn.commit()
            else:
                # Standard econ tables have series_id/value schema
                cur.execute(f"""
                    INSERT INTO {table} (series_id, event_date, value, source, ingested_at, knowledge_time, row_hash)
                    SELECT series_id, event_date, value, source, created_at, knowledge_time, row_hash
                    FROM raw.fred_observations_1d
                    WHERE series_id IN %s
                    ON CONFLICT (series_id, event_date) DO NOTHING
                """, (series_tuple,))
                migrated = cur.rowcount
                print(f"    Migrated {migrated:,} rows to {table}")
                conn.commit()

        # Put uncategorized in activity (catch-all for now)
        if uncategorized:
            cur.execute("""
                INSERT INTO econ.activity_1d (series_id, event_date, value, source, ingested_at, knowledge_time, row_hash)
                SELECT series_id, event_date, value, source, created_at, knowledge_time, row_hash
                FROM raw.fred_observations_1d
                WHERE series_id IN %s
                ON CONFLICT (series_id, event_date) DO NOTHING
            """, (tuple(uncategorized),))
            migrated = cur.rowcount
            print(f"    Migrated {migrated:,} uncategorized rows to econ.activity_1d")
            conn.commit()

    print("  Done.")


def step_13_migrate_cftc(conn):
    """Migrate raw.cftc_cot_1w to pos.cftc_1w."""
    print("\n=== Step 13: Migrating CFTC data ===")

    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM raw.cftc_cot_1w")
        count = cur.fetchone()[0]
        print(f"  Source rows: {count:,}")

        if count == 0:
            print("  No data to migrate")
            return

        cur.execute("""
            INSERT INTO pos.cftc_1w (
                event_date, symbol, open_interest,
                prod_merc_long, prod_merc_short, prod_merc_net,
                swap_long, swap_short, swap_net,
                managed_money_long, managed_money_short, managed_money_net,
                other_rept_long, other_rept_short, other_rept_net,
                nonrept_long, nonrept_short, nonrept_net,
                managed_money_net_pct_oi, prod_merc_net_pct_oi,
                source, ingested_at, knowledge_time, row_hash
            )
            SELECT
                event_date, symbol, open_interest,
                prod_merc_long, prod_merc_short, prod_merc_net,
                swap_long, swap_short, swap_net,
                managed_money_long, managed_money_short, managed_money_net,
                other_rept_long, other_rept_short, other_rept_net,
                nonrept_long, nonrept_short, nonrept_net,
                managed_money_net_pct_oi, prod_merc_net_pct_oi,
                source, ingested_at, knowledge_time, row_hash
            FROM raw.cftc_cot_1w
            ON CONFLICT (symbol, event_date) DO NOTHING
        """)
        migrated = cur.rowcount
        print(f"  Migrated rows: {migrated:,}")

    conn.commit()
    print("  Done.")


def step_14_migrate_usda(conn):
    """Migrate USDA tables to supply.*"""
    print("\n=== Step 14: Migrating USDA data ===")

    with conn.cursor() as cur:
        # WASDE
        cur.execute("SELECT COUNT(*) FROM raw.usda_wasde_1m")
        count = cur.fetchone()[0]
        print(f"  WASDE source rows: {count:,}")

        if count > 0:
            cur.execute("""
                INSERT INTO supply.usda_wasde_1m (
                    event_date, commodity, attribute, region, value, unit, marketing_year,
                    source, ingested_at, knowledge_time, row_hash
                )
                SELECT
                    event_date, commodity, attribute, region, value, unit, marketing_year,
                    source, ingested_at, knowledge_time, row_hash
                FROM raw.usda_wasde_1m
            """)
            print(f"    Migrated {cur.rowcount:,} WASDE rows")

        # Export Sales
        cur.execute("SELECT COUNT(*) FROM raw.usda_export_sales_1w")
        count = cur.fetchone()[0]
        print(f"  Export Sales source rows: {count:,}")

        if count > 0:
            cur.execute("""
                INSERT INTO supply.usda_exports_1w (
                    event_date, commodity, country, weekly_exports, accumulated_exports,
                    outstanding_sales, marketing_year, source, ingested_at, knowledge_time, row_hash
                )
                SELECT
                    event_date, commodity, country, weekly_exports, accumulated_exports,
                    outstanding_sales, marketing_year, source, ingested_at, knowledge_time, row_hash
                FROM raw.usda_export_sales_1w
            """)
            print(f"    Migrated {cur.rowcount:,} Export Sales rows")

    conn.commit()
    print("  Done.")


def step_15_migrate_epa(conn):
    """Migrate EPA RIN data to supply.*"""
    print("\n=== Step 15: Migrating EPA RIN data ===")

    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM raw.epa_rin_prices_1d")
        count = cur.fetchone()[0]
        print(f"  Source rows: {count:,}")

        if count == 0:
            print("  No data to migrate")
            return

        cur.execute("""
            INSERT INTO supply.epa_rin_1d (event_date, rin_type, price, source, ingested_at, knowledge_time, row_hash)
            SELECT event_date, rin_type, price, source, created_at, knowledge_time, row_hash
            FROM raw.epa_rin_prices_1d
            ON CONFLICT (rin_type, event_date) DO NOTHING
        """)
        migrated = cur.rowcount
        print(f"  Migrated rows: {migrated:,}")

    conn.commit()
    print("  Done.")


def step_16_migrate_news(conn):
    """Migrate news data to alt.*"""
    print("\n=== Step 16: Migrating news data ===")

    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM raw.news_articles_1d")
        count = cur.fetchone()[0]
        print(f"  Source rows: {count:,}")

        if count == 0:
            print("  No data to migrate")
            return

        cur.execute("""
            INSERT INTO alt.news_1d (event_date, headline, source, url, specialist_tags, ingested_at, knowledge_time, row_hash)
            SELECT event_date, headline, source, url, specialist_tags, ingested_at, knowledge_time, row_hash
            FROM raw.news_articles_1d
        """)
        migrated = cur.rowcount
        print(f"  Migrated rows: {migrated:,}")

    conn.commit()
    print("  Done.")


def step_17_migrate_weather(conn):
    """Migrate weather data to alt.*"""
    print("\n=== Step 17: Migrating weather data ===")

    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM raw.weather_noaa_1d")
        count = cur.fetchone()[0]
        print(f"  Source rows: {count:,}")

        if count == 0:
            print("  No data to migrate")
            return

        cur.execute("""
            INSERT INTO alt.weather_1d (event_date, station_id, region, temp_max, temp_min, temp_avg, precip, snow, source, ingested_at, knowledge_time, row_hash)
            SELECT event_date, station_id, region, temp_max, temp_min, temp_avg, precip, snow, source, ingested_at, knowledge_time, row_hash
            FROM raw.weather_noaa_1d
        """)
        migrated = cur.rowcount
        print(f"  Migrated rows: {migrated:,}")

    conn.commit()
    print("  Done.")


def step_18_verify_counts(conn):
    """Verify row counts match."""
    print("\n=== Step 18: Verifying migration ===")

    checks = [
        ("raw.market_futures_1d", "mkt.futures_1d"),
        ("raw.market_futures_1h", "mkt.futures_1h"),
        ("raw.options_futures_1d", "mkt.options_1d"),
        ("raw.fx_spot_1d", "mkt.fx_1d"),
        ("raw.cftc_cot_1w", "pos.cftc_1w"),
        ("raw.epa_rin_prices_1d", "supply.epa_rin_1d"),
        ("raw.news_articles_1d", "alt.news_1d"),
        ("raw.weather_noaa_1d", "alt.weather_1d"),
    ]

    with conn.cursor() as cur:
        for old, new in checks:
            cur.execute(f"SELECT COUNT(*) FROM {old}")
            old_count = cur.fetchone()[0]
            cur.execute(f"SELECT COUNT(*) FROM {new}")
            new_count = cur.fetchone()[0]
            status = "✓" if new_count >= old_count * 0.99 else "✗"  # Allow 1% tolerance for dedup
            print(f"  {status} {old}: {old_count:,} → {new}: {new_count:,}")

        # FRED special check (sum of all econ tables)
        cur.execute("SELECT COUNT(*) FROM raw.fred_observations_1d")
        old_count = cur.fetchone()[0]

        cur.execute("""
            SELECT
                (SELECT COUNT(*) FROM econ.rates_1d) +
                (SELECT COUNT(*) FROM econ.inflation_1d) +
                (SELECT COUNT(*) FROM econ.labor_1d) +
                (SELECT COUNT(*) FROM econ.activity_1d) +
                (SELECT COUNT(*) FROM econ.vol_indices_1d) +
                (SELECT COUNT(*) FROM econ.commodities_1d) +
                (SELECT COUNT(*) FROM econ.fx_1d) +
                (SELECT COUNT(*) FROM econ.money_1d)
        """)
        new_count = cur.fetchone()[0]
        status = "✓" if new_count >= old_count * 0.99 else "✗"
        print(f"  {status} raw.fred_observations_1d: {old_count:,} → econ.*: {new_count:,}")

    print("  Done.")


def main():
    print("=" * 60)
    print("ZINC-FUSION-V15 Schema Migration 004")
    print("=" * 60)
    print(f"Started at: {datetime.now().isoformat()}")

    conn = get_connection()

    try:
        step_1_create_schemas(conn)
        step_2_create_mkt_tables(conn)
        step_3_create_econ_tables(conn)
        step_4_create_pos_tables(conn)
        step_5_create_supply_tables(conn)
        step_6_create_alt_tables(conn)
        step_7_rename_features_tables(conn)
        step_8_migrate_futures(conn)
        step_9_migrate_futures_1h(conn)
        step_10_migrate_options(conn)
        step_11_migrate_fx(conn)
        step_12_migrate_fred(conn)
        step_13_migrate_cftc(conn)
        step_14_migrate_usda(conn)
        step_15_migrate_epa(conn)
        step_16_migrate_news(conn)
        step_17_migrate_weather(conn)
        step_18_verify_counts(conn)

        print("\n" + "=" * 60)
        print("Migration completed successfully!")
        print("=" * 60)
        print(f"Finished at: {datetime.now().isoformat()}")
        print("\nNext steps:")
        print("  1. Update Prisma schema to point to new tables")
        print("  2. Update ingestion scripts")
        print("  3. Update training pipeline")
        print("  4. After verification, drop old raw.* tables")

    except Exception as e:
        print(f"\nERROR: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
