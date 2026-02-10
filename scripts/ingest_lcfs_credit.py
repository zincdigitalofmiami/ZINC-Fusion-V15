#!/usr/bin/env python3
"""
ZINC-FUSION-V15: LCFS Credit Price Ingestion (CARB)

Purpose:
- Populate LCFS credit price series for strict biofuel inputs.
- Land daily volume-weighted average LCFS credit price ($/MT) into supply.lcfs_1d.

Source (in-repo documented):
- CARB Weekly LCFS Credit Transfer Activity Reports page provides an XLSX activity log.
  https://ww2.arb.ca.gov/resources/documents/weekly-lcfs-credit-transfer-activity-reports

Approach:
- Download the latest "Weekly LCFS Credit Activity" XLSX (cumulative activity log).
- Parse transfer-level rows containing date completed, price, volume.
- Aggregate to daily VWAP: sum(price*volume)/sum(volume) by completion date.
- Upsert into supply.lcfs_1d.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import logging
import os
import re
import zipfile
import xml.etree.ElementTree as ET
from datetime import date, datetime
from typing import Dict, Optional

import pandas as pd
import psycopg2
import requests
from dotenv import load_dotenv


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

CARB_WEEKLY_PAGE = "https://ww2.arb.ca.gov/resources/documents/weekly-lcfs-credit-transfer-activity-reports"
SOURCE_NAME = "carb_weekly_activity_xlsx"


def get_connection():
    load_dotenv()
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not set")
    return psycopg2.connect(database_url)


def _find_activity_xlsx_url(html: str) -> str:
    # Example href:
    # https://ww2.arb.ca.gov/sites/default/files/2026-01/Weekly%20LCFS%20Credit%20Activity%20(upto%2011%20January,%202026).xlsx
    # Prefer the explicit activity log link.
    hrefs = re.findall(r'href="([^"]+\.xlsx)"', html, flags=re.IGNORECASE)
    for href in hrefs:
        if (
            "weekly" in href.lower()
            and "lcfs" in href.lower()
            and "credit" in href.lower()
            and "activity" in href.lower()
        ):
            if href.startswith("http"):
                return href
            return f"https://ww2.arb.ca.gov{href}"
    raise ValueError(
        "Could not find Weekly LCFS Credit Activity .xlsx link on CARB page"
    )


def _download(url: str, timeout_s: int = 60) -> bytes:
    res = requests.get(url, timeout=timeout_s)
    res.raise_for_status()
    return res.content


def _normalize_columns(cols) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for col in cols:
        key = str(col).strip().lower()
        key = re.sub(r"\\s+", " ", key)
        mapping[str(col)] = key
    return mapping


def _extract_activity_rows(xlsx_bytes: bytes) -> pd.DataFrame:
    sheets = _read_xlsx_as_dataframes(xlsx_bytes)

    best: Optional[pd.DataFrame] = None
    best_score = -1

    for name, df in sheets.items():
        if df is None or df.empty:
            continue
        colmap = _normalize_columns(df.columns)
        cols = set(colmap.values())
        # Heuristics: we need completion date + price + volume.
        score = 0
        if any("date completed" in c or c == "date completed" for c in cols):
            score += 2
        if any(c == "price" or "price" in c for c in cols):
            score += 1
        if any(c == "volume" or "volume" in c for c in cols):
            score += 1
        if score > best_score:
            best_score = score
            best = df

    if best is None or best_score < 3:
        raise ValueError(
            "Could not locate an activity log sheet with date/price/volume columns"
        )

    # Standardize common column names
    df = best.copy()
    df.columns = [str(c).strip() for c in df.columns]
    colmap = _normalize_columns(df.columns)

    def pick_col(pred) -> Optional[str]:
        for raw, norm in colmap.items():
            if pred(norm):
                return raw
        return None

    col_date = pick_col(
        lambda c: c == "date completed" or c.startswith("date completed")
    )
    col_price = pick_col(lambda c: c == "price" or c.endswith("price") or "price" in c)
    col_volume = pick_col(
        lambda c: c == "volume" or c.endswith("volume") or "volume" in c
    )

    if not col_date or not col_price or not col_volume:
        raise ValueError(
            f"Missing required columns in activity sheet: date={col_date}, price={col_price}, volume={col_volume}"
        )

    raw_dates = df[col_date]
    # CARB XLSX frequently encodes dates as Excel serial numbers.
    date_num = pd.to_numeric(raw_dates, errors="coerce")
    if date_num.notna().mean() > 0.5 and date_num.median(skipna=True) > 1000:
        event_date = pd.to_datetime(
            date_num, unit="D", origin="1899-12-30", errors="coerce"
        ).dt.date
    else:
        event_date = pd.to_datetime(raw_dates, errors="coerce").dt.date

    out = pd.DataFrame(
        {
            "event_date": event_date,
            "price": pd.to_numeric(df[col_price], errors="coerce"),
            "volume": pd.to_numeric(df[col_volume], errors="coerce"),
        }
    )
    out = out.dropna(subset=["event_date", "price", "volume"])
    out = out[(out["price"] > 0) & (out["volume"] > 0)]
    return out


def _read_xlsx_as_dataframes(xlsx_bytes: bytes) -> Dict[str, pd.DataFrame]:
    """
    Minimal XLSX reader (no openpyxl dependency).

    Reads sheets as DataFrames by parsing the XLSX zip contents:
    - sharedStrings.xml for string lookup
    - worksheets/sheetN.xml for cell data

    This is intentionally narrow to support CARB's activity log.
    """

    def _ns(tag: str) -> str:
        return f"{{http://schemas.openxmlformats.org/spreadsheetml/2006/main}}{tag}"

    def _col_to_index(cell_ref: str) -> int:
        # 'A'->0, 'B'->1, ... 'AA'->26
        letters = re.sub(r"[^A-Z]", "", cell_ref.upper())
        idx = 0
        for ch in letters:
            idx = idx * 26 + (ord(ch) - ord("A") + 1)
        return idx - 1

    with zipfile.ZipFile(io.BytesIO(xlsx_bytes)) as zf:  # type: ignore[name-defined]
        # shared strings
        shared_strings: list[str] = []
        try:
            ss_xml = zf.read("xl/sharedStrings.xml")
            root = ET.fromstring(ss_xml)
            for si in root.findall(_ns("si")):
                # concatenate all text nodes
                texts = []
                for t in si.iter(_ns("t")):
                    if t.text:
                        texts.append(t.text)
                shared_strings.append("".join(texts))
        except KeyError:
            shared_strings = []

        # workbook sheet names
        sheet_names: list[str] = []
        try:
            wb_xml = zf.read("xl/workbook.xml")
            wb_root = ET.fromstring(wb_xml)
            for sheet in wb_root.findall(f".//{_ns('sheet')}"):
                name = sheet.attrib.get("name", "")
                sheet_names.append(name or f"sheet{len(sheet_names) + 1}")
        except KeyError:
            sheet_names = []

        # worksheet files
        sheet_files = sorted(
            [
                p
                for p in zf.namelist()
                if p.startswith("xl/worksheets/sheet") and p.endswith(".xml")
            ]
        )
        if not sheet_files:
            raise ValueError("No worksheet XML files found in XLSX")

        result: Dict[str, pd.DataFrame] = {}
        for i, sheet_path in enumerate(sheet_files):
            name = sheet_names[i] if i < len(sheet_names) else f"sheet{i + 1}"
            ws_root = ET.fromstring(zf.read(sheet_path))

            row_dicts: list[Dict[int, Optional[str]]] = []
            max_col = 0
            for row in ws_root.findall(f".//{_ns('row')}"):
                row_values: Dict[int, Optional[str]] = {}
                for c in row.findall(_ns("c")):
                    r = c.attrib.get("r")
                    if not r:
                        continue
                    col_idx = _col_to_index(r)
                    max_col = max(max_col, col_idx)
                    cell_type = c.attrib.get("t")
                    v = c.find(_ns("v"))
                    if v is None or v.text is None:
                        continue
                    raw = v.text
                    if cell_type == "s" and raw.isdigit():
                        sidx = int(raw)
                        row_values[col_idx] = (
                            shared_strings[sidx] if sidx < len(shared_strings) else raw
                        )
                    else:
                        row_values[col_idx] = raw
                row_dicts.append(row_values)

            rows: list[list[Optional[str]]] = [
                [rd.get(ci) for ci in range(max_col + 1)] for rd in row_dicts
            ]

            # Try to find header row: first non-empty row
            header_row_idx = None
            for idx, r in enumerate(rows):
                if any((v is not None and str(v).strip() != "") for v in r):
                    header_row_idx = idx
                    break
            if header_row_idx is None:
                continue

            header = [
                str(v).strip() if v is not None else "" for v in rows[header_row_idx]
            ]
            data_rows = rows[header_row_idx + 1 :]
            df = pd.DataFrame(data_rows, columns=header)
            # Drop fully empty rows
            df = df.dropna(how="all")
            result[name] = df

        return result


def compute_daily_vwap(activity: pd.DataFrame) -> pd.DataFrame:
    df = activity.copy()
    df["dollar"] = df["price"] * df["volume"]
    agg = df.groupby("event_date", as_index=False).agg(
        volume_mt=("volume", "sum"), dollar=("dollar", "sum")
    )
    agg["price_usd_per_mt"] = agg["dollar"] / agg["volume_mt"].replace(0, pd.NA)
    agg = agg.drop(columns=["dollar"])
    agg["event_date"] = pd.to_datetime(agg["event_date"], errors="coerce").dt.date
    return agg[["event_date", "price_usd_per_mt", "volume_mt"]]


def upsert_prices(
    conn,
    df: pd.DataFrame,
    ingestion_batch_id: str,
    dry_run: bool = False,
):
    if df.empty:
        logger.warning("No LCFS rows to upsert")
        return 0

    if dry_run:
        logger.info(f"[DRY RUN] Would upsert {len(df)} rows into supply.lcfs_1d")
        logger.info(
            f"  Date range: {df['event_date'].min()} → {df['event_date'].max()}"
        )
        logger.info(f"  Sample: {df.head(3).to_dict(orient='records')}")
        return 0

    sql = """
        INSERT INTO supply.lcfs_1d (event_date, price_usd_per_mt, source, ingestion_batch_id)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (event_date) DO UPDATE SET
            price_usd_per_mt = EXCLUDED.price_usd_per_mt,
            source = EXCLUDED.source,
            ingestion_batch_id = EXCLUDED.ingestion_batch_id,
            created_at = NOW()
    """
    records = [
        (row.event_date, row.price_usd_per_mt, SOURCE_NAME, ingestion_batch_id)
        for row in df.itertuples(index=False)
    ]
    with conn.cursor() as cur:
        cur.executemany(sql, records)
    conn.commit()
    return len(records)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ingest LCFS credit price series from CARB activity log"
    )
    parser.add_argument("--dry-run", action="store_true", help="Do not write to DB")
    parser.add_argument(
        "--start", type=str, default=None, help="Start date (YYYY-MM-DD) filter"
    )
    parser.add_argument(
        "--end", type=str, default=None, help="End date (YYYY-MM-DD) filter"
    )
    args = parser.parse_args()

    start_d: Optional[date] = (
        datetime.strptime(args.start, "%Y-%m-%d").date() if args.start else None
    )
    end_d: Optional[date] = (
        datetime.strptime(args.end, "%Y-%m-%d").date() if args.end else None
    )

    logger.info("Fetching CARB weekly LCFS activity page...")
    page_html = _download(CARB_WEEKLY_PAGE, timeout_s=60).decode(
        "utf-8", errors="ignore"
    )
    xlsx_url = _find_activity_xlsx_url(page_html)
    logger.info(f"Found activity XLSX: {xlsx_url}")

    logger.info("Downloading activity XLSX...")
    xlsx_bytes = _download(xlsx_url, timeout_s=120)
    ingestion_batch_id = hashlib.sha256(
        f"{xlsx_url}|{len(xlsx_bytes)}".encode()
    ).hexdigest()[:16]

    logger.info("Parsing activity XLSX...")
    activity = _extract_activity_rows(xlsx_bytes)
    daily = compute_daily_vwap(activity)

    if start_d:
        daily = daily[daily["event_date"] >= start_d]
    if end_d:
        daily = daily[daily["event_date"] <= end_d]

    logger.info(
        f"Computed {len(daily)} daily LCFS price rows (batch {ingestion_batch_id})"
    )

    conn = get_connection()
    try:
        written = upsert_prices(
            conn, daily, ingestion_batch_id=ingestion_batch_id, dry_run=args.dry_run
        )
        if not args.dry_run:
            logger.info(f"Wrote {written} rows to supply.lcfs_1d")
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
