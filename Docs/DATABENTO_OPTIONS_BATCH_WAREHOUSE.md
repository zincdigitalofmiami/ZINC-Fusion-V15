# Databento Options: Warehouse Batch Jobs (All 15 Stat Types)

Use the **warehouse / batch download** flow so you can **see jobs in the portal** and download files to verify options data and all 15 stat types.

## What Gets Queued

The script `scripts/databento_options_batch_submit.py` submits **3 batch jobs** to Databento:

| Job        | Schema       | Contents |
|-----------|--------------|----------|
| 1         | `definition` | Instrument reference: strike, expiration, option type (C/P), raw_symbol |
| 2         | `ohlcv-1d`   | Daily OHLCV bars (open, high, low, close, volume) |
| 3         | `statistics` | **All 15 stat_type values** (see below) |

The **statistics** schema is a single schema; each row has a `stat_type` field. The 15 values are:

| stat_type | Meaning            | DB column (mkt.options_1d) |
|-----------|--------------------|----------------------------|
| 1         | Opening Price      | opening_price_stat         |
| 2         | Indicative Opening | indicative_opening         |
| 3         | Settlement Price   | premium (we map it)         |
| 4         | Session Low        | session_low_stat           |
| 5         | Session High       | session_high_stat          |
| 6         | Cleared Volume     | cleared_volume             |
| 7         | Ask                | ask                        |
| 8         | Bid                | bid                        |
| 9         | Open Interest      | open_interest              |
| 10        | Fixing Price       | fixing_price               |
| 11        | Close              | close_stat                 |
| 12        | Net Change         | change                     |
| 13        | VWAP               | vwap                       |
| 14        | Implied Volatility | implied_volatility         |
| 15        | Delta              | delta                      |

## How to Run

```bash
# Load .env (DATABENTO_API_KEY)
cd /path/to/ZINC-FUSION-V15

# Dry run (no API call)
.venv/bin/python scripts/databento_options_batch_submit.py --dry-run

# Submit 3 jobs: definition + ohlcv-1d + statistics (default: 2010-06-06 to today, DBN + zstd)
.venv/bin/python scripts/databento_options_batch_submit.py

# Shorter range
.venv/bin/python scripts/databento_options_batch_submit.py --start 2025-01-01 --end 2025-02-01

# Only the statistics job (to verify all 15 stat types)
.venv/bin/python scripts/databento_options_batch_submit.py --schema statistics
```

## Where to See the Jobs

1. Log in to **Databento Portal**: https://databento.com (or your account URL).
2. Open **Download Center** / **Batch downloads** (or **Warehouse**).
3. You should see the submitted jobs (definition, ohlcv-1d, statistics) with status (e.g. queued, processing, ready).
4. When ready, download the files (DBN + zstd by default; use `--encoding csv` only if you need human-readable).

## How to Verify All 15 Stat Types

1. Download the **statistics** job output (DBN: use `databento` Python client or `dbn` tools to read; or re-run with `--encoding csv` to inspect).
2. DBN is Databento’s native binary format (fast, zstd-compressed); CSV is only for ad-hoc inspection.
3. Confirm the statistics data contains **stat_type** values 1 through 15 (opening price, bid, ask, OI, IV, delta, etc.).

No fake data: everything comes from Databento’s API; the batch job returns the same data you would get from `timeseries.get_range(..., schema="statistics")`, in file form.
