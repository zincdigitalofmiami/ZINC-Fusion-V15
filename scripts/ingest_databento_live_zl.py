#!/usr/bin/env python3
"""
Databento Live (Raw/TCP) -> DB + Inngest connector for ZL.

Subscribes to ohlcv-1m for ZL continuous:
- Updates latest_price with every bar (live price)
- Emits Inngest 1m events on every bar so frontend 1m/5m tables stay hot
- Emits completed-bar events (15m/1h/1d)

Tables updated directly:
  - analytics.latest_price (every 1m - latest price)
  - analytics.price_1m (every 1m)
  - analytics.price_5m (derived from 1m buckets)

Inngest events:
  - zl.bar.1m
  - zl.bar.15m
  - zl.bar.1h
  - zl.bar.1d
"""

from __future__ import annotations

import argparse
import logging
import os
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import databento as db
import psycopg2
import requests
from dotenv import load_dotenv

# Load environment from project root.
# Fallback to frontend/.env.local for local development keys.
PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PROJECT_ROOT / "frontend" / ".env.local")

DATABENTO_API_KEY = os.getenv("DATABENTO_API_KEY")
INNGEST_EVENT_KEY = os.getenv("INNGEST_EVENT_KEY") or os.getenv(
    "WORKFLOW_INNGEST_EVENT_KEY"
)
INNGEST_EVENT_ENV = os.getenv("INNGEST_EVENT_ENV") or os.getenv("INNGEST_ENV")
DATABASE_URL = os.getenv("DATABASE_URL")
SEND_INNGEST_EVENTS = os.getenv("DATABENTO_SEND_INNGEST_EVENTS", "1").lower() not in (
    "0",
    "false",
    "no",
)
EVENT_FORWARDING_ENABLED = SEND_INNGEST_EVENTS

DATASET = "GLBX.MDP3"
SCHEMA = "ohlcv-1m"
SYMBOL = "ZL.n.0"
PRICE_SCALE = 1_000_000_000  # Databento fixed-point price divisor

EVENT_URL = f"https://inn.gs/e/{INNGEST_EVENT_KEY}" if INNGEST_EVENT_KEY else None

logger = logging.getLogger("databento_live_zl")
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)


def require_env() -> None:
    if not DATABENTO_API_KEY:
        raise ValueError("DATABENTO_API_KEY not set")
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL not set")
    if SEND_INNGEST_EVENTS and not INNGEST_EVENT_KEY:
        logger.warning(
            "INNGEST_EVENT_KEY not set; continuing with direct DB writes only."
        )


def to_datetime(ts_event) -> datetime:
    if isinstance(ts_event, datetime):
        return ts_event.astimezone(timezone.utc)
    if isinstance(ts_event, int):
        return datetime.fromtimestamp(ts_event / 1_000_000_000, tz=timezone.utc)
    if isinstance(ts_event, float):
        return datetime.fromtimestamp(ts_event, tz=timezone.utc)
    return datetime.fromisoformat(str(ts_event)).astimezone(timezone.utc)


def send_event(name: str, data: dict) -> bool:
    global EVENT_FORWARDING_ENABLED
    if not EVENT_FORWARDING_ENABLED:
        return False
    if not EVENT_URL:
        logger.warning("Event URL not configured; skipping event '%s'", name)
        return False
    payload = {"name": name, "data": data}
    headers = {"Content-Type": "application/json"}
    if INNGEST_EVENT_ENV:
        headers["x-inngest-env"] = INNGEST_EVENT_ENV
    try:
        resp = requests.post(EVENT_URL, json=payload, headers=headers, timeout=10)
    except Exception as exc:
        logger.warning("Event send transport failure for '%s': %s", name, exc)
        return False
    if resp.status_code >= 400:
        # Avoid logging key-containing URLs.
        body = (resp.text or "").strip().replace("\n", " ")[:300]
        if "env_unspecified" in body or "env_not_found" in body:
            EVENT_FORWARDING_ENABLED = False
            logger.warning(
                "Disabling event forwarding for this run due to Inngest environment routing error."
            )
        logger.warning(
            "Event send rejected for '%s': status=%s body=%s",
            name,
            resp.status_code,
            body,
        )
        return False
    return True


def update_zl_latest(ts: datetime, price: float, volume: int) -> None:
    """Update the latest price table (single row, always current)."""
    if not DATABASE_URL:
        return
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO analytics.latest_price (id, price, timestamp, volume, updated_at)
                VALUES (1, %s, %s, %s, NOW())
                ON CONFLICT (id) DO UPDATE SET
                    price = EXCLUDED.price,
                    timestamp = EXCLUDED.timestamp,
                    volume = EXCLUDED.volume,
                    updated_at = NOW()
                """,
                (price, ts, volume),
            )
        conn.commit()
    finally:
        conn.close()


def upsert_price_1m(
    ts: datetime,
    open_px: float,
    high_px: float,
    low_px: float,
    close_px: float,
    volume: int,
    previous_close: Optional[float],
    day_high: Optional[float],
    day_low: Optional[float],
    source: str,
) -> None:
    """Directly maintain analytics.price_1m for dashboard live charting."""
    if not DATABASE_URL:
        return
    change = close_px - previous_close if previous_close is not None else None
    change_pct = (
        (change / previous_close) * 100
        if previous_close is not None and previous_close != 0
        else None
    )
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO analytics.price_1m
                    (timestamp, open, high, low, close, volume, previous_close,
                     change, change_percent, day_high, day_low, source, created_at)
                VALUES
                    (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (symbol, timestamp) DO UPDATE SET
                    open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    close = EXCLUDED.close,
                    volume = EXCLUDED.volume,
                    previous_close = EXCLUDED.previous_close,
                    change = EXCLUDED.change,
                    change_percent = EXCLUDED.change_percent,
                    day_high = EXCLUDED.day_high,
                    day_low = EXCLUDED.day_low,
                    source = EXCLUDED.source
                """,
                (
                    ts,
                    open_px,
                    high_px,
                    low_px,
                    close_px,
                    volume,
                    previous_close,
                    change,
                    change_pct,
                    day_high,
                    day_low,
                    source,
                ),
            )
        conn.commit()
    finally:
        conn.close()


def upsert_price_5m(
    bucket_start_ts_ms: int,
    bar: "AggBar",
    previous_close: Optional[float],
    day_high: Optional[float],
    day_low: Optional[float],
    source: str,
) -> None:
    """Directly maintain analytics.price_5m for dashboard live charting."""
    if not DATABASE_URL:
        return
    ts = datetime.fromtimestamp(bucket_start_ts_ms / 1000, tz=timezone.utc)
    change = bar.close - previous_close if previous_close is not None else None
    change_pct = (
        (change / previous_close) * 100
        if previous_close is not None and previous_close != 0
        else None
    )
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO analytics.price_5m
                    (timestamp, open, high, low, close, volume, previous_close,
                     change, change_percent, day_high, day_low, source, created_at)
                VALUES
                    (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (symbol, timestamp) DO UPDATE SET
                    open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    close = EXCLUDED.close,
                    volume = EXCLUDED.volume,
                    previous_close = EXCLUDED.previous_close,
                    change = EXCLUDED.change,
                    change_percent = EXCLUDED.change_percent,
                    day_high = EXCLUDED.day_high,
                    day_low = EXCLUDED.day_low,
                    source = EXCLUDED.source
                """,
                (
                    ts,
                    bar.open,
                    bar.high,
                    bar.low,
                    bar.close,
                    bar.volume,
                    previous_close,
                    change,
                    change_pct,
                    day_high,
                    day_low,
                    source,
                ),
            )
        conn.commit()
    finally:
        conn.close()


@dataclass
class AggBar:
    start_ts: int
    open: float
    high: float
    low: float
    close: float
    volume: int


def bucket_start(ts_ms: int, bucket_ms: int) -> int:
    return (ts_ms // bucket_ms) * bucket_ms


def get_latest_ts_from_db() -> Optional[datetime]:
    if not DATABASE_URL:
        return None
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT GREATEST(
                  COALESCE((SELECT MAX(timestamp) FROM analytics.price_1m), '1970-01-01'::timestamptz),
                  COALESCE((SELECT MAX(timestamp) FROM analytics.price_5m), '1970-01-01'::timestamptz),
                  COALESCE((SELECT MAX(timestamp) FROM analytics.price_15m), '1970-01-01'::timestamptz),
                  COALESCE((SELECT MAX(timestamp) FROM analytics.price_1h), '1970-01-01'::timestamptz)
                ) AS max_ts
                """
            )
            row = cur.fetchone()
            if not row or not row[0]:
                return None
            max_ts = row[0]
            if isinstance(max_ts, datetime):
                return max_ts.astimezone(timezone.utc)
            return None
    finally:
        conn.close()


def compute_replay_start(
    explicit_start: Optional[str],
    buffer_minutes: int,
    max_replay_hours: int,
    default_hours: int,
) -> Optional[datetime]:
    if explicit_start:
        return datetime.fromisoformat(explicit_start).astimezone(timezone.utc)
    latest = get_latest_ts_from_db()
    now = datetime.now(timezone.utc)
    if latest is None:
        return now - timedelta(hours=default_hours)
    buffered = latest - timedelta(minutes=buffer_minutes)
    min_start = now - timedelta(hours=max_replay_hours)
    return max(buffered, min_start)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Databento Live connector for ZL with replay."
    )
    parser.add_argument(
        "--run-seconds",
        type=int,
        default=120,
        help="Duration to keep live connection open.",
    )
    parser.add_argument(
        "--start", type=str, default=None, help="ISO start timestamp for replay."
    )
    parser.add_argument(
        "--buffer-minutes", type=int, default=15, help="Replay buffer before last bar."
    )
    parser.add_argument(
        "--max-replay-hours",
        type=int,
        default=72,
        help="Clamp replay window to last N hours.",
    )
    parser.add_argument(
        "--default-hours", type=int, default=6, help="Replay window if DB is empty."
    )
    args = parser.parse_args()

    require_env()

    retry_count = 0
    max_retries = 10
    base_sleep = 5

    current_5m: AggBar | None = None
    current_15m: AggBar | None = None
    current_1h: AggBar | None = None
    current_day: date | None = None
    day_open = day_high = day_low = day_close = None
    day_volume = 0
    prev_day_close: float | None = None

    bucket_5m = 5 * 60 * 1000
    bucket_15m = 15 * 60 * 1000
    bucket_1h = 60 * 60 * 1000

    while True:
        try:
            replay_start = compute_replay_start(
                explicit_start=args.start,
                buffer_minutes=args.buffer_minutes,
                max_replay_hours=args.max_replay_hours,
                default_hours=args.default_hours,
            )
            client = db.Live(key=DATABENTO_API_KEY)
            if replay_start is not None:
                client.subscribe(
                    dataset=DATASET,
                    schema=SCHEMA,
                    symbols=[SYMBOL],
                    stype_in="continuous",
                    start=replay_start,
                )
                logger.info(
                    "Subscribed to live feed: %s %s %s (start=%s)",
                    DATASET,
                    SCHEMA,
                    SYMBOL,
                    replay_start.isoformat(),
                )
            else:
                client.subscribe(
                    dataset=DATASET,
                    schema=SCHEMA,
                    symbols=[SYMBOL],
                    stype_in="continuous",
                )
                logger.info(
                    "Subscribed to live feed: %s %s %s", DATASET, SCHEMA, SYMBOL
                )

            stop_at = time.time() + max(1, args.run_seconds)

            for record in client:
                if time.time() >= stop_at:
                    logger.info("Run window complete; exiting.")
                    break
                # Skip non-OHLCV records (e.g., system/symbology messages).
                if not hasattr(record, "open"):
                    continue
                ts = to_datetime(record.ts_event)
                ts_ms = int(ts.timestamp() * 1000)
                # Convert from Databento fixed-point to decimal
                o = float(record.open) / PRICE_SCALE
                h = float(record.high) / PRICE_SCALE
                l = float(record.low) / PRICE_SCALE
                c = float(record.close) / PRICE_SCALE
                v = (
                    int(record.volume)
                    if hasattr(record, "volume") and record.volume is not None
                    else 0
                )

                # Daily aggregation
                bar_day = ts.date()
                if current_day is None:
                    current_day = bar_day
                    day_open = o
                    day_high = h
                    day_low = l
                    day_close = c
                    day_volume = v
                elif bar_day != current_day:
                    # emit previous day
                    send_event(
                        "zl.bar.1d",
                        {
                            "eventDate": current_day.isoformat(),
                            "open": day_open,
                            "high": day_high,
                            "low": day_low,
                            "close": day_close,
                            "volume": day_volume,
                            "source": "databento_live",
                        },
                    )
                    prev_day_close = day_close
                    # reset for new day
                    current_day = bar_day
                    day_open = o
                    day_high = h
                    day_low = l
                    day_close = c
                    day_volume = v
                else:
                    day_high = max(day_high, h)
                    day_low = min(day_low, l)
                    day_close = c
                    day_volume += v

                # 5m aggregation (direct table + optional event forwarding)
                b5 = bucket_start(ts_ms, bucket_5m)
                if current_5m is None:
                    current_5m = AggBar(b5, o, h, l, c, v)
                elif b5 != current_5m.start_ts:
                    upsert_price_5m(
                        bucket_start_ts_ms=current_5m.start_ts,
                        bar=current_5m,
                        previous_close=prev_day_close,
                        day_high=day_high,
                        day_low=day_low,
                        source="databento_live",
                    )
                    send_event(
                        "zl.bar.5m",
                        {
                            "timestamp": datetime.fromtimestamp(
                                current_5m.start_ts / 1000, tz=timezone.utc
                            ).isoformat(),
                            "open": current_5m.open,
                            "high": current_5m.high,
                            "low": current_5m.low,
                            "close": current_5m.close,
                            "volume": current_5m.volume,
                            "previousClose": prev_day_close,
                            "dayHigh": day_high,
                            "dayLow": day_low,
                            "source": "databento_live",
                        },
                    )
                    current_5m = AggBar(b5, o, h, l, c, v)
                else:
                    current_5m.high = max(current_5m.high, h)
                    current_5m.low = min(current_5m.low, l)
                    current_5m.close = c
                    current_5m.volume += v

                # 15m aggregation
                b15 = bucket_start(ts_ms, bucket_15m)
                if current_15m is None:
                    current_15m = AggBar(b15, o, h, l, c, v)
                elif b15 != current_15m.start_ts:
                    send_event(
                        "zl.bar.15m",
                        {
                            "timestamp": datetime.fromtimestamp(
                                current_15m.start_ts / 1000, tz=timezone.utc
                            ).isoformat(),
                            "open": current_15m.open,
                            "high": current_15m.high,
                            "low": current_15m.low,
                            "close": current_15m.close,
                            "volume": current_15m.volume,
                            "previousClose": prev_day_close,
                            "dayHigh": day_high,
                            "dayLow": day_low,
                            "source": "databento_live",
                        },
                    )
                    current_15m = AggBar(b15, o, h, l, c, v)
                else:
                    current_15m.high = max(current_15m.high, h)
                    current_15m.low = min(current_15m.low, l)
                    current_15m.close = c
                    current_15m.volume += v

                # 1h aggregation
                b1h = bucket_start(ts_ms, bucket_1h)
                if current_1h is None:
                    current_1h = AggBar(b1h, o, h, l, c, v)
                elif b1h != current_1h.start_ts:
                    send_event(
                        "zl.bar.1h",
                        {
                            "timestamp": datetime.fromtimestamp(
                                current_1h.start_ts / 1000, tz=timezone.utc
                            ).isoformat(),
                            "open": current_1h.open,
                            "high": current_1h.high,
                            "low": current_1h.low,
                            "close": current_1h.close,
                            "volume": current_1h.volume,
                            "source": "databento_live",
                        },
                    )
                    current_1h = AggBar(b1h, o, h, l, c, v)
                else:
                    current_1h.high = max(current_1h.high, h)
                    current_1h.low = min(current_1h.low, l)
                    current_1h.close = c
                    current_1h.volume += v

                # ========== LIVE UPDATES (every 1m bar) ==========
                # Update latest price
                update_zl_latest(ts, c, v)
                # Update 1m chart table directly
                upsert_price_1m(
                    ts=ts,
                    open_px=o,
                    high_px=h,
                    low_px=l,
                    close_px=c,
                    volume=v,
                    previous_close=prev_day_close,
                    day_high=day_high,
                    day_low=day_low,
                    source="databento_live",
                )

                # Emit every 1m bar; frontend zl-live-1m ingester writes:
                #   analytics.price_1m
                # and derives:
                #   analytics.price_5m
                send_event(
                    "zl.bar.1m",
                    {
                        "timestamp": ts.isoformat(),
                        "open": o,
                        "high": h,
                        "low": l,
                        "close": c,
                        "volume": v,
                        "previousClose": prev_day_close,
                        "dayHigh": day_high,
                        "dayLow": day_low,
                        "source": "databento_live",
                    },
                )

            retry_count = 0
            break
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            break
        except Exception as exc:
            retry_count += 1
            wait_time = min(base_sleep * (2**retry_count), 300)
            logger.error("Live feed error (%s/%s): %s", retry_count, max_retries, exc)
            if retry_count >= max_retries:
                logger.critical("Max retries reached. Exiting.")
                break
            time.sleep(wait_time)


if __name__ == "__main__":
    main()
