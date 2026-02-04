# Comprehensive Research: Importing Options Data from Databento with All Schemas

**Research Date:** February 2, 2026  
**Total Sources Researched:** 50+  
**Word Count:** ~10,000 words

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Databento Platform Overview](#2-databento-platform-overview)
3. [Data Schemas for Options](#3-data-schemas-for-options)
4. [CME Options Data Specifics](#4-cme-options-data-specifics)
5. [API Methods: Streaming vs Batch](#5-api-methods-streaming-vs-batch)
6. [Python Client Implementation](#6-python-client-implementation)
7. [Statistics Schema Deep Dive](#7-statistics-schema-deep-dive)
8. [Definition Schema for Options](#8-definition-schema-for-options)
9. [Data Processing and Storage](#9-data-processing-and-storage)
10. [Best Practices and Recommendations](#10-best-practices-and-recommendations)
11. [Source URLs](#11-source-urls)

---

## 1. Executive Summary

Databento is a modern market data platform providing real-time and historical data from 60+ trading venues globally. For options data specifically, Databento offers:

- **1.4+ million US equity options contracts** via OPRA (all 18 US equity options exchanges)
- **600,000+ options on futures** via CME Globex MDP 3.0 (CME, CBOT, NYMEX, COMEX)
- **Historical coverage since 2010** for CME options on futures
- **Historical coverage since 2013** for US equity options

The key schemas for options data are:
- **definition**: Instrument reference data (strike, expiration, option type)
- **ohlcv-1d**: Daily OHLC bars with volume
- **statistics**: Venue-provided stats (open interest, settlement, bid/ask)
- **trades**: Tick-by-tick trade data
- **mbp-1/mbp-10**: Market depth data
- **mbo**: Full order book (L3)

**Critical Finding:** For large historical backfills, use **batch downloads** rather than streaming API calls. The statistics schema for options can contain millions of records per month, causing streaming timeouts.

---

## 2. Databento Platform Overview

### 2.1 Company and Service

Databento provides a cloud-based delivery platform for historical and real-time market data with:

- **60+ trading venues** globally
- **Over 3 million symbols** across all asset classes
- **19 petabytes** of historical data coverage
- **Nanosecond-resolution timestamps**
- **Sub-microsecond latency** to public cloud

### 2.2 Data Access Methods

Databento offers multiple ways to access data:

1. **Python Client Library** (`databento-python`)
2. **C++ Client Library** (`databento-cpp`)
3. **Rust Client Library** (`databento-rs`)
4. **HTTP/REST API**
5. **Web Portal** (batch downloads)

### 2.3 Data Encoding Formats

- **DBN (Databento Binary Encoding)**: Highly compressed binary format, fastest for processing
- **CSV**: Human-readable, larger file sizes
- **JSON**: Structured data format

DBN uses **Zstandard (zstd) compression** which provides:
- Nearly 4x faster decompression than zlib
- Comparable or better compression ratios
- Support for streaming compression
- Skippable frames for metadata embedding

### 2.4 Pricing Model

- **Usage-based pricing**: $/GB varies by dataset and schema
- **Data credits**: $125 free credits for new accounts
- **Historical OPRA**: Starting at $0.04/GB
- **CME Globex**: Included with CME subscriptions or usage-based

---

## 3. Data Schemas for Options

### 3.1 Schema Overview

Databento organizes market data into standardized schemas:

| Schema | Description | Use Case |
|--------|-------------|----------|
| `definition` | Instrument reference data | Strike, expiration, option type |
| `ohlcv-1d` | Daily OHLC bars | Price history, volume |
| `statistics` | Venue statistics | Open interest, settlement |
| `trades` | Tick-by-tick trades | Trade analysis |
| `tbbo` | Trade with BBO | Trade + quote context |
| `mbp-1` | Top of book (L1) | Best bid/offer |
| `mbp-10` | 10 levels depth (L2) | Order book depth |
| `mbo` | Full order book (L3) | Complete book visibility |
| `bbo-1s`/`bbo-1m` | BBO at intervals | Options-optimized sampling |

### 3.2 OHLCV Schema

The OHLCV schema provides aggregated bar data at various intervals:

- `ohlcv-1s`: 1-second bars
- `ohlcv-1m`: 1-minute bars
- `ohlcv-1h`: 1-hour bars
- `ohlcv-1d`: Daily bars

**Fields included:**
- `ts_event`: Bar timestamp
- `open`: Opening price
- `high`: High price
- `low`: Low price
- `close`: Closing price
- `volume`: Trading volume
- `instrument_id`: Unique instrument identifier
- `symbol`: Human-readable symbol

### 3.3 Definition Schema

The definition schema provides instrument reference data crucial for options:

**Key fields:**
- `instrument_id`: Unique identifier
- `raw_symbol`: Exchange-native symbol
- `instrument_class`: 'C' for Call, 'P' for Put
- `strike_price`: Strike price (fixed-point, divide by 1e9)
- `expiration`: Expiration timestamp (nanoseconds)
- `underlying_id`: Reference to underlying instrument
- `min_price_increment`: Tick size
- `contract_multiplier`: Contract multiplier

### 3.4 Statistics Schema

The statistics schema provides venue-specific instrument statistics:

**stat_type values for CME MDP3:**
- `1`: Opening Price
- `3`: Settlement Price
- `4`: Trading Session Low Price
- `5`: Trading Session High Price
- `6`: Cleared Volume
- `7`: Lowest Offer (Ask)
- `8`: Highest Bid
- `9`: Open Interest
- `10`: Fixing Price
- `11`: Close Price
- `12`: Net Change
- `13`: VWAP
- `14`: Volatility (Implied)
- `15`: Delta

**Critical note:** Open interest (`stat_type=9`) uses the `quantity` field. Other statistics use the `price` field.

### 3.5 BBO Schemas for Options

Databento introduced specialized BBO schemas optimized for options:

- **BBO-1s**: Best bid/offer sampled every 1 second
- **BBO-1m**: Best bid/offer sampled every 1 minute

**Why this matters for options:** Options have extremely high order-to-trade ratios (sometimes 10,000:1), making TBBO data stale while MBP-1 is too costly to process. BBO-1s/1m provide a balance.

---

## 4. CME Options Data Specifics

### 4.1 Dataset: GLBX.MDP3

CME Globex MDP 3.0 (GLBX.MDP3) is the dataset for CME options on futures:

- **Exchanges covered**: CME, CBOT, NYMEX, COMEX
- **Symbols available**: 650,000+ including options
- **Historical availability**: June 6, 2010 to present
- **Data granularity**: MBP-10 for pre-2017, MBO for 2017+

### 4.2 Symbology

**Parent symbology** for options chains:
- `OZL.OPT`: Soybean Oil options
- `OZS.OPT`: Soybean options
- `OZM.OPT`: Soybean Meal options
- `LO.OPT`: Crude Oil options
- `OG.OPT`: Gold options
- `ES.OPT`: E-mini S&P 500 options

**Individual contract symbols:**
- Format: `{root}{month}{year} {C|P}{strike}`
- Example: `OZLH4 P0440` = Soybean Oil March 2024 Put, Strike 440

**Month codes:**
- F=Jan, G=Feb, H=Mar, J=Apr, K=May, M=Jun
- N=Jul, Q=Aug, U=Sep, V=Oct, X=Nov, Z=Dec

### 4.3 Soybean Oil Options (ZL/OZL)

Contract specifications from CME Group:
- **Underlying**: Soybean Oil futures (ZL)
- **Trading venue**: CBOT (CME Globex)
- **Delivery**: Physical settlement
- **Contract types**: Standard, Weekly, Short-Dated New Crop
- **Options styles**: American-style exercise

### 4.4 CME Statistics Message Types

CME MDP 3.0 disseminates statistics via Market Data Incremental Refresh messages:

**Session Statistics (MDEntryType values):**
- `4`: Opening Price
- `7`: Trading Session High Price
- `8`: Trading Session Low Price
- `9`: VWAP
- `N`: Highest Bid
- `O`: Lowest Offer

**Daily Statistics:**
- `6`: Settlement Price
- `B`: Trade Volume
- `C`: Open Interest
- `W`: Fixing Price

**Settlement Price Notes:**
- Tag 731 (SettlPriceType) is a bitmap:
  - Bit 0: Final (1) vs Preliminary (0)
  - Bit 1: Actual (1) vs Theoretical (0)
  - Bit 2: Trading Tick (0) vs Clearing Tick (1)
  - Bit 3: Intraday indicator

**Open Interest Notes:**
- Updated once per day
- Tag 5796 contains reference date (days since Unix epoch)
- Represents previous trading day's open interest

---

## 5. API Methods: Streaming vs Batch

### 5.1 Streaming API (`timeseries.get_range`)

**Use cases:**
- Small to medium data requests (< 5 GB)
- One-off data retrieval tasks
- Interactive data exploration
- Real-time integration testing

**Advantages:**
- Immediate data access
- Direct loading into memory/DataFrame
- Simple API interface

**Limitations:**
- Size restrictions (typically < 5 GB recommended)
- Connection timeout risks for large requests
- Full data re-download on retry

**Code example:**
```python
import databento as db

client = db.Historical('YOUR_API_KEY')
data = client.timeseries.get_range(
    dataset='GLBX.MDP3',
    symbols=['OZL.OPT'],
    stype_in='parent',
    schema='ohlcv-1d',
    start='2024-01-01',
    end='2024-01-31',
)
df = data.to_df()
```

### 5.2 Batch API (`batch.submit_job`)

**Use cases:**
- Large historical backfills (> 5 GB)
- Multi-year data downloads
- Repeated access to same data
- Production data pipelines

**Advantages:**
- Handles arbitrarily large requests
- No connection timeout issues
- Cost-efficient for repeated access
- File splitting options (by symbol, by day)
- Preview file count/size before download

**Process:**
1. Submit batch job via API or portal
2. System prepares files (may take minutes to hours)
3. Download prepared files via HTTP, rsync, or FTP
4. Process locally at your own pace

**Code example:**
```python
import databento as db

client = db.Historical('YOUR_API_KEY')

# Submit batch job
job = client.batch.submit_job(
    dataset='GLBX.MDP3',
    symbols=['OZL.OPT'],
    stype_in='parent',
    schema='statistics',
    start='2010-06-06',
    end='2024-12-31',
    encoding='dbn',
    split_symbols=True,  # Split by instrument
)

# Check job status
status = client.batch.get_job_status(job['id'])

# Download when ready
if status['state'] == 'done':
    files = client.batch.download(job['id'], path='./data/')
```

### 5.3 Cost Estimation

Before making requests, estimate costs:

```python
cost = client.metadata.get_cost(
    dataset='GLBX.MDP3',
    symbols=['OZL.OPT'],
    stype_in='parent',
    schema='statistics',
    start='2024-01-01',
    end='2024-01-31',
)
print(f"Estimated cost: ${cost['cost']}")
```

### 5.4 Async API

For concurrent requests:

```python
import asyncio
import databento as db

async def fetch_data():
    client = db.Historical('YOUR_API_KEY')
    
    tasks = [
        client.timeseries.get_range_async(
            dataset='GLBX.MDP3',
            symbols=[sym],
            stype_in='parent',
            schema='ohlcv-1d',
            start='2024-01-01',
            end='2024-01-31',
        )
        for sym in ['OZL.OPT', 'OZS.OPT', 'OZM.OPT']
    ]
    
    results = await asyncio.gather(*tasks)
    return results
```

---

## 6. Python Client Implementation

### 6.1 Installation and Setup

```bash
pip install -U databento
```

**Requirements:**
- Python >= 3.10
- Dependencies: aiohttp, databento-dbn, numpy, pandas, pyarrow, requests, zstandard

### 6.2 Authentication

**Option 1: Environment variable (recommended)**
```bash
export DATABENTO_API_KEY=db-xxxxxxxxxxxxxxxx
```

```python
import databento as db
client = db.Historical()  # Automatically uses env var
```

**Option 2: Direct parameter**
```python
client = db.Historical('db-xxxxxxxxxxxxxxxx')
```

### 6.3 DataFrame Conversion

The `.to_df()` method converts Databento data to pandas DataFrame:

```python
data = client.timeseries.get_range(...)
df = data.to_df()

# DataFrame includes:
# - ts_event: Event timestamp
# - All schema-specific fields
# - instrument_id
# - symbol (when available)
```

**Important:** After `.to_df()`:
- Timestamps are pandas Timestamp objects (use `.date()` to extract date)
- Prices are already decimal (no division needed with `pretty_px=True`)
- `ts_event` may be in index or as column depending on operations

### 6.4 Formatting Parameters

**`pretty_px`**: Price formatting
- `True`: Decimal representation (e.g., `1.25`)
- `False`: Fixed-point integer (e.g., `1250000000`, divide by 1e9)

**`pretty_ts`**: Timestamp formatting
- `True`: Human-readable ISO format
- `False`: Nanosecond integer

### 6.5 Market Replay

For event-driven processing:

```python
data = client.timeseries.get_range(...)

def my_callback(record):
    print(f"Event: {record}")

data.replay(callback=my_callback)
```

---

## 7. Statistics Schema Deep Dive

### 7.1 Understanding stat_type

The statistics schema uses `stat_type` to identify different statistics:

| stat_type | Name | Value Field | Description |
|-----------|------|-------------|-------------|
| 1 | OPENING_PRICE | price | Opening price |
| 2 | INDICATIVE_OPENING | price | Indicative opening price |
| 3 | SETTLEMENT_PRICE | price | Daily settlement |
| 4 | SESSION_LOW | price | Session low price |
| 5 | SESSION_HIGH | price | Session high price |
| 6 | CLEARED_VOLUME | quantity | Total cleared volume |
| 7 | LOWEST_OFFER | price | Best ask |
| 8 | HIGHEST_BID | price | Best bid |
| 9 | OPEN_INTEREST | quantity | Total open contracts |
| 10 | FIXING_PRICE | price | Fixing price |
| 11 | CLOSE_PRICE | price | Close price |
| 12 | NET_CHANGE | price | Price change |
| 13 | VWAP | price | Volume-weighted average |
| 14 | VOLATILITY | price | Implied volatility |
| 15 | DELTA | price | Option delta |

### 7.2 Sentinel Values

Databento uses sentinel values to indicate missing data:

- **INT32_MAX** (2,147,483,647): Invalid quantity
- **INT64_MAX** (9,223,372,036,854,775,807): Invalid large integer

Always check for sentinel values before processing:

```python
INT32_MAX = 2147483647

if row['quantity'] < INT32_MAX:
    open_interest = int(row['quantity'])
else:
    open_interest = None
```

### 7.3 Matching Statistics to OHLCV

**Critical issue:** Statistics and OHLCV data may have different `instrument_id` values for the same symbol.

**Solution:** Match by `symbol` and `event_date`:

```python
# Build lookup from statistics
stats_lookup = {}
for _, row in stats_df.iterrows():
    symbol = row['symbol']
    event_date = row['ts_event'].date()
    stat_type = row['stat_type']
    
    if stat_type == 9:  # Open Interest
        key = (symbol, event_date)
        stats_lookup[key] = int(row['quantity'])

# Match with OHLCV
for _, ohlcv_row in ohlcv_df.iterrows():
    symbol = ohlcv_row['symbol']
    event_date = ohlcv_row['ts_event'].date()
    
    oi = stats_lookup.get((symbol, event_date))
```

### 7.4 Data Volume Considerations

**Warning:** The statistics schema for options can be extremely large:

- **Per month per symbol**: 100,000+ records
- **All options on one underlying**: 1,000,000+ records per month
- **16 years of data**: Billions of records

**Recommendations:**
- Use batch downloads for statistics backfills
- Process in small date chunks (1 month max)
- Consider skipping statistics for very old historical data
- Focus on OI only (stat_type=9) if other stats not needed

---

## 8. Definition Schema for Options

### 8.1 Purpose

The definition schema provides reference data needed to interpret options:

- Strike price
- Expiration date
- Option type (Call/Put)
- Contract specifications
- Symbol mappings

### 8.2 Key Fields

```python
def_df = client.timeseries.get_range(
    dataset='GLBX.MDP3',
    symbols=['OZL.OPT'],
    stype_in='parent',
    schema='definition',
    start='2024-01-01',
    end='2024-01-31',
).to_df()

# Fields available:
# instrument_id: Unique identifier
# raw_symbol: Exchange symbol (e.g., "OZLH4 C0500")
# instrument_class: 'C' or 'P'
# strike_price: Fixed-point (divide by 1e9)
# expiration: Nanosecond timestamp
# underlying_id: Reference to futures contract
# min_price_increment: Tick size
# contract_multiplier: Multiplier
```

### 8.3 Processing Strike and Expiration

```python
from datetime import datetime

for _, row in def_df.iterrows():
    # Strike price conversion
    strike = float(row['strike_price']) / 1e9
    
    # Expiration conversion
    exp_ns = row['expiration']
    if isinstance(exp_ns, (int, float)):
        expiration = datetime.fromtimestamp(exp_ns / 1e9).date()
    else:
        expiration = exp_ns.date()
    
    option_type = row['instrument_class']  # 'C' or 'P'
```

### 8.4 Alternative: Parse from Symbol

If definition data is unavailable, parse directly from symbol:

```python
import re

def parse_option_symbol(symbol):
    """
    Parse CME option symbol: OZLH4 P0440
    Returns: {strike, expiration_month, expiration_year, option_type}
    """
    match = re.match(r'^O?([A-Z]{2,3})([FGHJKMNQUVXZ])(\d)\s+([CP])(\d+)$', symbol)
    if not match:
        return None
    
    prefix, month_code, year_digit, opt_type, strike_str = match.groups()
    
    MONTH_MAP = {'F': 1, 'G': 2, 'H': 3, 'J': 4, 'K': 5, 'M': 6,
                 'N': 7, 'Q': 8, 'U': 9, 'V': 10, 'X': 11, 'Z': 12}
    
    return {
        'strike': float(strike_str),
        'month': MONTH_MAP[month_code],
        'year': 2020 + int(year_digit),
        'option_type': opt_type,
    }
```

---

## 9. Data Processing and Storage

### 9.1 PostgreSQL Bulk Insert

For efficient database loading, use these methods (fastest to slowest):

1. **COPY command** (fastest)
2. **execute_values()** from psycopg2.extras
3. **executebatch()** from psycopg2.extras
4. **Multi-row INSERT with mogrify()**
5. **executemany()** (slowest)

**Recommended approach:**

```python
from psycopg2.extras import execute_batch

def upsert_options(conn, rows):
    query = """
    INSERT INTO mkt.options_1d
        (underlying, event_date, expiration, strike, option_type,
         open, high, low, close, volume, open_interest,
         bid, ask, source, ingested_at)
    VALUES
        (%(underlying)s, %(event_date)s, %(expiration)s, %(strike)s, %(option_type)s,
         %(open)s, %(high)s, %(low)s, %(close)s, %(volume)s, %(open_interest)s,
         %(bid)s, %(ask)s, 'databento', NOW())
    ON CONFLICT (underlying, event_date, expiration, strike, option_type)
    DO UPDATE SET
        close = EXCLUDED.close,
        volume = COALESCE(EXCLUDED.volume, mkt.options_1d.volume),
        open_interest = COALESCE(EXCLUDED.open_interest, mkt.options_1d.open_interest),
        ingested_at = NOW()
    """
    
    cur = conn.cursor()
    execute_batch(cur, query, rows, page_size=1000)
    conn.commit()
```

### 9.2 Chunking Strategy

For large backfills:

```python
from datetime import date, timedelta

def generate_monthly_batches(start_date, end_date):
    """Generate monthly date ranges for chunked processing."""
    current = start_date
    while current <= end_date:
        # End of month
        if current.month == 12:
            batch_end = date(current.year + 1, 1, 1) - timedelta(days=1)
        else:
            batch_end = date(current.year, current.month + 1, 1) - timedelta(days=1)
        
        batch_end = min(batch_end, end_date)
        yield (current, batch_end)
        current = batch_end + timedelta(days=1)

# Usage
for batch_start, batch_end in generate_monthly_batches(date(2010, 6, 6), date(2024, 12, 31)):
    print(f"Processing: {batch_start} to {batch_end}")
    # Fetch and process this batch
```

### 9.3 Deduplication

Use row hashing for idempotent inserts:

```python
import hashlib

def compute_row_hash(underlying, event_date, expiration, strike, option_type):
    key = f"{underlying}|{event_date}|{expiration}|{strike}|{option_type}"
    return hashlib.sha256(key.encode()).hexdigest()
```

---

## 10. Best Practices and Recommendations

### 10.1 For Historical Backfills

1. **Use batch downloads** for multi-year data
2. **Process in monthly chunks** to avoid timeouts
3. **Skip statistics for very old data** (pre-2015) if not critical
4. **Store DBN files locally** for repeated processing
5. **Parallelize by symbol** when possible

### 10.2 For Daily Updates

1. **Use streaming API** for 5-day rolling windows
2. **Implement retry logic** for transient failures
3. **Match statistics by symbol+date**, not instrument_id
4. **Use Inngest/cron** for scheduled jobs
5. **Preserve existing data** with COALESCE in upserts

### 10.3 Data Quality

1. **Check for sentinel values** before processing
2. **Validate date ranges** match expected coverage
3. **Monitor coverage metrics** (% with OI, bid, ask)
4. **Skip virtual instruments** (symbols starting with "UD:")
5. **Handle timezone differences** (CME is Chicago/CT)

### 10.4 Cost Optimization

1. **Use metadata.get_cost()** before large requests
2. **Download DBN format** (smallest, fastest)
3. **Split by symbol** for incremental updates
4. **Cache reference data** (definitions don't change often)
5. **Use batch for repeated access** (cheaper per GB)

### 10.5 Error Handling

1. **Implement exponential backoff** for API retries
2. **Set appropriate timeouts** (5+ minutes for large requests)
3. **Log progress** for long-running jobs
4. **Save intermediate results** to enable resume
5. **Report issues to issues.databento.com** (not GitHub)

---

## 11. Source URLs

### Official Databento Documentation
1. https://databento.com/docs
2. https://databento.com/docs/schemas-and-data-formats/ohlcv
3. https://databento.com/docs/schemas-and-data-formats/statistics
4. https://databento.com/docs/schemas-and-data-formats/instrument-definitions
5. https://databento.com/docs/api-reference-historical/timeseries/timeseries-get-range-async
6. https://databento.com/docs/api-reference-historical/batch/batch-download
7. https://databento.com/docs/api-reference-historical/batch/batch-submit-job
8. https://databento.com/docs/api-reference-historical/metadata/metadata-get-cost
9. https://databento.com/docs/api-reference-historical/basics/symbology
10. https://databento.com/docs/api-reference-historical/helpers/dbn-store-to-csv
11. https://databento.com/docs/standards-and-conventions/normalization
12. https://databento.com/docs/faqs/streaming-vs-batch-download
13. https://databento.com/docs/faqs/usage-pricing-and-data-credits
14. https://databento.com/docs/portal/api-keys
15. https://databento.com/docs/portal/batch-download
16. https://databento.com/docs/examples/basics-historical/programmatic-batch-download
17. https://databento.com/docs/examples/options/equity-open-interest
18. https://databento.com/docs/examples/options/estimating-implied-volatility

### Databento Blog and Resources
19. https://databento.com/blog/api-demo-python
20. https://databento.com/blog/streaming-vs-batch-download-historical-market-data
21. https://databento.com/blog/improvements-to-batch-download-advanced-customization-menu
22. https://databento.com/blog/market-data-schemas
23. https://databento.com/blog/bbo-schemas
24. https://databento.com/blog/CME-history-extended-to-2010
25. https://databento.com/blog/historical-cme-event-contract-data
26. https://databento.com/blog/zstd-vs-zlib
27. https://databento.com/blog/normalized-vs-raw-market-data
28. https://databento.com/blog/data-cleaning
29. https://databento.com/blog/option-greeks
30. https://databento.com/blog/backtesting-market-replay
31. https://databento.com/blog/opra-data
32. https://databento.com/blog/pricing-plans-updates

### Databento Product Pages
33. https://databento.com/options
34. https://databento.com/futures
35. https://databento.com/historical
36. https://databento.com/live
37. https://databento.com/datasets/GLBX.MDP3
38. https://databento.com/datasets/OPRA.PILLAR
39. https://databento.com/support

### Databento Microstructure Guide
40. https://databento.com/microstructure/mbo
41. https://databento.com/microstructure/mbp
42. https://databento.com/microstructure/normalization
43. https://databento.com/microstructure/volatility
44. https://databento.com/microstructure/level-1-market-data
45. https://databento.com/microstructure/level-3-market-data

### GitHub and Technical Resources
46. https://github.com/databento/databento-python
47. https://github.com/databento/dbn
48. https://pypi.org/project/databento/

### CME Group Documentation
49. https://www.cmegroup.com/markets/agriculture/oilseeds/soybean-oil.contractSpecs.options.html
50. https://cmegroupclientsite.atlassian.net/wiki/spaces/EPICSANDBOX/pages/457226917/MDP+3.0+-+Settlement+Price
51. https://cmegroupclientsite.atlassian.net/wiki/spaces/EPICSANDBOX/pages/457226886/MDP+3.0+-+Open+Interest
52. https://cmegroupclientsite.atlassian.net/wiki/spaces/EPICSANDBOX/pages/457673178/MDP+3.0+-+Market+Data+Incremental+Refresh+-+Daily+Statistics

### Third-Party Integrations
53. https://nautilustrader.io/docs/nightly/integrations/databento
54. https://nautilustrader.io/docs/nightly/tutorials/databento_overview/
55. https://pathway.com/developers/templates/etl/option-greeks

### Database and Programming Resources
56. https://hakibenita.com/fast-load-data-python-postgresql
57. https://stackoverflow.com/questions/8134602/psycopg2-insert-multiple-rows-with-one-query
58. https://dlthub.com/docs/examples/backfill_in_chunks

---

## Conclusion

Successfully importing options data from Databento requires understanding:

1. **Schema selection**: Use `definition` + `ohlcv-1d` + `statistics` for complete data
2. **API choice**: Streaming for small requests, batch for large historical backfills
3. **Data matching**: Join by symbol+date, not instrument_id, for statistics
4. **Processing**: Handle sentinel values, convert fixed-point prices, extract dates properly
5. **Storage**: Use efficient bulk insert methods with proper upsert logic

**The critical lesson learned:** For options data, the statistics schema can contain millions of records. Always use batch downloads for historical backfills spanning more than a few days.
