#!/usr/bin/env python3
"""
Ingest CFTC Commitments of Index Traders Supplemental (CITS) data.
Uses FREE CFTC.gov direct download - NO Quandl/Nasdaq required.

CITS is DIFFERENT from standard COT:
- Separates INDEX TRADERS (passive funds) from other categories
- Index traders are LONG-ONLY and price-insensitive (pension funds, ETFs)
- Covers 13 agricultural markets including soybean oil

Data Source: https://www.cftc.gov/MarketReports/CommitmentsofTraders/HistoricalViewable/index.htm
"""

import os
import sys
import io
import zipfile
import requests
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# CFTC direct URLs (FREE!)
CFTC_CITS_URLS = {
    '2006-2016': 'https://www.cftc.gov/files/dea/history/dea_cit_txt_2006_2016.zip',
}

# Add individual years from 2017 onwards
for year in range(2017, datetime.now().year + 1):
    CFTC_CITS_URLS[str(year)] = f'https://www.cftc.gov/files/dea/history/dea_cit_txt_{year}.zip'

# Contract Market Code to symbol mapping (from CFTC_Contract_Market_Code column)
CONTRACT_MARKET_CODES = {
    1602: 'WHEAT_SRW',
    1612: 'WHEAT_HRW',
    2602: 'CORN',
    5602: 'SOYBEANS',
    7601: 'SOYBEAN_OIL',     # ZL - our target!
    26603: 'SOYBEAN_MEAL',
    33661: 'COTTON',
    54642: 'LEAN_HOGS',
    57642: 'LIVE_CATTLE',
    61641: 'FEEDER_CATTLE',
    73732: 'COCOA',
    80732: 'SUGAR_11',
    83731: 'COFFEE',
}


def download_cits_data(year_key: str) -> pd.DataFrame:
    """Download CITS data from CFTC for a specific year/range."""
    url = CFTC_CITS_URLS.get(year_key)
    if not url:
        raise ValueError(f"No URL for year: {year_key}")
    
    print(f"  Downloading {year_key} from CFTC.gov...")
    
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    
    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        txt_files = [f for f in zf.namelist() if f.endswith('.txt')]
        if not txt_files:
            raise ValueError(f"No .txt file found in {url}")
        
        txt_file = txt_files[0]
        
        with zf.open(txt_file) as f:
            df = pd.read_csv(f, low_memory=False)
    
    print(f"    Raw rows: {len(df):,}")
    return df


def transform_cits_data(df: pd.DataFrame) -> pd.DataFrame:
    """Transform raw CFTC CITS data to match existing table schema."""
    
    # Filter to target commodities
    df = df[df['CFTC_Contract_Market_Code'].isin(CONTRACT_MARKET_CODES.keys())].copy()
    
    if df.empty:
        return pd.DataFrame()
    
    df['symbol'] = df['CFTC_Contract_Market_Code'].map(CONTRACT_MARKET_CODES)
    
    # Parse date
    if 'As_of_Date_In_Form_YYYY-MM-DD' in df.columns:
        df['report_date'] = pd.to_datetime(df['As_of_Date_In_Form_YYYY-MM-DD'])
    else:
        df['report_date'] = pd.to_datetime(df['As_of_Date_In_Form_YYMMDD'].astype(str), format='%y%m%d')
    
    df['event_date'] = df['report_date']
    
    # Index trader positions (the key unique data!)
    df['index_trader_longs'] = pd.to_numeric(df.get('CIT_Positions_Long_All', 0), errors='coerce').fillna(0).astype(int)
    df['index_trader_shorts'] = pd.to_numeric(df.get('CIT_Positions_Short_All', 0), errors='coerce').fillna(0).astype(int)
    df['index_trader_net'] = df['index_trader_longs'] - df['index_trader_shorts']
    
    # Non-commercial (NoCIT = excluding index traders)
    df['non_commercial_longs'] = pd.to_numeric(df.get('NComm_Positions_Long_All_NoCIT', 0), errors='coerce').fillna(0).astype(int)
    df['non_commercial_shorts'] = pd.to_numeric(df.get('NComm_Positions_Short_All_NoCIT', 0), errors='coerce').fillna(0).astype(int)
    df['non_commercial_spreads'] = pd.to_numeric(df.get('NComm_Postions_Spread_All_NoCIT', 0), errors='coerce').fillna(0).astype(int)
    df['non_commercial_net'] = df['non_commercial_longs'] - df['non_commercial_shorts']
    
    # Commercial (NoCIT)
    df['commercial_longs'] = pd.to_numeric(df.get('Comm_Positions_Long_All_NoCIT', 0), errors='coerce').fillna(0).astype(int)
    df['commercial_shorts'] = pd.to_numeric(df.get('Comm_Positions_Short_All_NoCIT', 0), errors='coerce').fillna(0).astype(int)
    df['commercial_net'] = df['commercial_longs'] - df['commercial_shorts']
    
    # Non-reportable
    df['non_reportable_longs'] = pd.to_numeric(df.get('NonRept_Positions_Long_All', 0), errors='coerce').fillna(0).astype(int)
    df['non_reportable_shorts'] = pd.to_numeric(df.get('NonRept_Positions_Short_All', 0), errors='coerce').fillna(0).astype(int)
    
    # Total reportable
    df['total_reportable_longs'] = pd.to_numeric(df.get('Tot_Rept_Positions_Long_All', 0), errors='coerce').fillna(0).astype(int)
    df['total_reportable_shorts'] = pd.to_numeric(df.get('Tot_Rept_Positions_Short_All', 0), errors='coerce').fillna(0).astype(int)
    
    # Market participation (open interest)
    df['market_participation'] = pd.to_numeric(df.get('Open_Interest_All', 0), errors='coerce').fillna(0).astype(int)
    
    # Build result matching existing schema
    result = pd.DataFrame({
        'report_date': df['report_date'],
        'event_date': df['event_date'],
        'contract_code': df['CFTC_Contract_Market_Code'].astype(int),
        'symbol': df['symbol'],
        'report_type': 'CITS_ALL',  # Existing schema expects this
        'market_participation': df['market_participation'],
        'non_commercial_longs': df['non_commercial_longs'],
        'non_commercial_shorts': df['non_commercial_shorts'],
        'non_commercial_spreads': df['non_commercial_spreads'],
        'commercial_longs': df['commercial_longs'],
        'commercial_shorts': df['commercial_shorts'],
        'total_reportable_longs': df['total_reportable_longs'],
        'total_reportable_shorts': df['total_reportable_shorts'],
        'non_reportable_longs': df['non_reportable_longs'],
        'non_reportable_shorts': df['non_reportable_shorts'],
        'index_trader_longs': df['index_trader_longs'],
        'index_trader_shorts': df['index_trader_shorts'],
        'index_trader_net': df['index_trader_net'],
        'non_commercial_net': df['non_commercial_net'],
        'commercial_net': df['commercial_net'],
    })
    
    print(f"    Filtered rows: {len(result):,} ({result['symbol'].nunique()} symbols)")
    return result


def upsert_cits_data(conn, df: pd.DataFrame) -> int:
    """Upsert CITS data into database."""
    if df.empty:
        return 0
    
    cur = conn.cursor()
    
    columns = [
        'report_date', 'event_date', 'contract_code', 'symbol', 'report_type',
        'market_participation', 'non_commercial_longs', 'non_commercial_shorts',
        'non_commercial_spreads', 'commercial_longs', 'commercial_shorts',
        'total_reportable_longs', 'total_reportable_shorts',
        'non_reportable_longs', 'non_reportable_shorts',
        'index_trader_longs', 'index_trader_shorts',
        'index_trader_net', 'non_commercial_net', 'commercial_net',
        'source', 'ingested_at'
    ]
    
    now = datetime.now()
    data = []
    for _, row in df.iterrows():
        data.append((
            row['report_date'],
            row['event_date'],
            row['contract_code'],
            row['symbol'],
            row['report_type'],
            row['market_participation'],
            row['non_commercial_longs'],
            row['non_commercial_shorts'],
            row['non_commercial_spreads'],
            row['commercial_longs'],
            row['commercial_shorts'],
            row['total_reportable_longs'],
            row['total_reportable_shorts'],
            row['non_reportable_longs'],
            row['non_reportable_shorts'],
            row['index_trader_longs'],
            row['index_trader_shorts'],
            row['index_trader_net'],
            row['non_commercial_net'],
            row['commercial_net'],
            'cftc_direct',
            now,
        ))
    
    insert_sql = f"""
        INSERT INTO pos.cftc_cits_1w ({', '.join(columns)})
        VALUES %s
        ON CONFLICT (report_date, contract_code, report_type) DO UPDATE SET
            event_date = EXCLUDED.event_date,
            market_participation = EXCLUDED.market_participation,
            non_commercial_longs = EXCLUDED.non_commercial_longs,
            non_commercial_shorts = EXCLUDED.non_commercial_shorts,
            non_commercial_spreads = EXCLUDED.non_commercial_spreads,
            commercial_longs = EXCLUDED.commercial_longs,
            commercial_shorts = EXCLUDED.commercial_shorts,
            total_reportable_longs = EXCLUDED.total_reportable_longs,
            total_reportable_shorts = EXCLUDED.total_reportable_shorts,
            non_reportable_longs = EXCLUDED.non_reportable_longs,
            non_reportable_shorts = EXCLUDED.non_reportable_shorts,
            index_trader_longs = EXCLUDED.index_trader_longs,
            index_trader_shorts = EXCLUDED.index_trader_shorts,
            index_trader_net = EXCLUDED.index_trader_net,
            non_commercial_net = EXCLUDED.non_commercial_net,
            commercial_net = EXCLUDED.commercial_net,
            source = EXCLUDED.source,
            ingested_at = NOW()
    """
    
    execute_values(cur, insert_sql, data, page_size=1000)
    conn.commit()
    
    return len(data)


def update_specialist_tags(conn):
    """Update specialist_tags for CITS data."""
    cur = conn.cursor()
    
    # Soy complex → crush
    cur.execute("""
        UPDATE pos.cftc_cits_1w 
        SET specialist_tags = ARRAY['crush']
        WHERE symbol IN ('SOYBEAN_OIL', 'SOYBEANS', 'SOYBEAN_MEAL')
        AND (specialist_tags IS NULL OR specialist_tags = '{}')
    """)
    
    # Other ags → substitutes
    cur.execute("""
        UPDATE pos.cftc_cits_1w 
        SET specialist_tags = ARRAY['substitutes']
        WHERE symbol IN ('CORN', 'WHEAT_SRW', 'WHEAT_HRW', 'COTTON', 'SUGAR_11', 'COFFEE', 'COCOA')
        AND (specialist_tags IS NULL OR specialist_tags = '{}')
    """)
    
    # Livestock → crush + substitutes (feed demand)
    cur.execute("""
        UPDATE pos.cftc_cits_1w 
        SET specialist_tags = ARRAY['crush', 'substitutes']
        WHERE symbol IN ('LEAN_HOGS', 'LIVE_CATTLE', 'FEEDER_CATTLE')
        AND (specialist_tags IS NULL OR specialist_tags = '{}')
    """)
    
    conn.commit()
    print("  ✅ Specialist tags updated")


def verify_data(conn):
    """Verify ingestion results."""
    cur = conn.cursor()
    
    print("\n" + "="*70)
    print("VERIFICATION")
    print("="*70)
    
    cur.execute("SELECT COUNT(*), MIN(event_date), MAX(event_date) FROM pos.cftc_cits_1w")
    total, min_dt, max_dt = cur.fetchone()
    print(f"\nTotal rows: {total:,}")
    print(f"Date range: {min_dt} to {max_dt}")
    
    cur.execute("""
        SELECT symbol, COUNT(*), MIN(event_date), MAX(event_date)
        FROM pos.cftc_cits_1w
        GROUP BY symbol
        ORDER BY symbol
    """)
    print("\nBy symbol:")
    for sym, cnt, min_d, max_d in cur.fetchall():
        print(f"  {sym}: {cnt:,} rows | {min_d} to {max_d}")
    
    cur.execute("""
        SELECT event_date, index_trader_net, index_trader_longs, index_trader_shorts
        FROM pos.cftc_cits_1w
        WHERE symbol = 'SOYBEAN_OIL'
        ORDER BY event_date DESC
        LIMIT 5
    """)
    print("\nSoybean Oil (ZL) recent index trader data:")
    for dt, idx_net, idx_l, idx_s in cur.fetchall():
        print(f"  {dt}: Net={idx_net:+,} (Longs={idx_l:,} Shorts={idx_s:,})")


def main():
    """Main ingestion function."""
    print("="*70)
    print("CFTC CITS INGESTION (Free CFTC.gov Source)")
    print("="*70)
    
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not set")
        sys.exit(1)
    
    conn = psycopg2.connect(database_url)
    
    try:
        total_inserted = 0
        
        for year_key in sorted(CFTC_CITS_URLS.keys()):
            try:
                print(f"\nProcessing {year_key}...")
                df_raw = download_cits_data(year_key)
                df = transform_cits_data(df_raw)
                
                if not df.empty:
                    inserted = upsert_cits_data(conn, df)
                    total_inserted += inserted
                    print(f"  ✅ Upserted {inserted:,} rows")
                else:
                    print(f"  ⚠️ No matching data for {year_key}")
                    
            except requests.exceptions.HTTPError as e:
                if '404' in str(e):
                    print(f"  ⚠️ File not found for {year_key}")
                else:
                    print(f"  ❌ HTTP Error for {year_key}: {e}")
                continue
            except Exception as e:
                conn.rollback()  # Reset transaction on error
                print(f"  ❌ Error for {year_key}: {e}")
                continue
        
        print("\nUpdating specialist tags...")
        update_specialist_tags(conn)
        
        print(f"\n{'='*70}")
        print(f"Total rows processed: {total_inserted:,}")
        
        verify_data(conn)
        
        print("\n✅ CITS ingestion complete!")
        
    except Exception as e:
        conn.rollback()
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
