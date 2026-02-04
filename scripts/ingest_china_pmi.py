#!/usr/bin/env python3
"""
ZINC-FUSION-V15: China Manufacturing PMI Ingestion (NBS, English)

Purpose:
- Populate `china_pmi` so China specialist strict mode can run.
- Store the monthly Manufacturing PMI headline into `econ.activity_1d` as a time series.

Source (official):
- National Bureau of Statistics of China (NBS) – Latest Releases
  https://www.stats.gov.cn/english/PressRelease/

Method:
- Scrape NBS "Latest Releases" list for entries titled "Purchasing Managers’ Index for <Month> <Year>".
- For each entry, fetch the release page and extract the headline Manufacturing PMI value.
- Store as:
  - series_id = 'china_pmi'
  - event_date = last calendar day of the reference month in the title
  - value = Manufacturing PMI (%)
  - source = 'NBS'
"""

from __future__ import annotations

import argparse
import calendar
import hashlib
import html as htmllib
import logging
import os
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

import psycopg2
import requests
from dotenv import load_dotenv


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

NBS_LIST_URL = "https://www.stats.gov.cn/english/PressRelease/"
SERIES_ID = "china_pmi"
SOURCE_NAME = "NBS"


@dataclass(frozen=True)
class PmiObservation:
    event_date: date
    value: float
    source_url: str
    published_at: Optional[date]


def get_connection():
    load_dotenv("/Volumes/Satechi Hub/ZINC-FUSION-V15/.env")
    load_dotenv("/Volumes/Satechi Hub/ZINC-FUSION-V15/.env.vercel")
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not set")
    return psycopg2.connect(database_url)


def _fetch(url: str, timeout_s: int = 60) -> str:
    headers = {"User-Agent": "Mozilla/5.0"}
    last_err: Optional[Exception] = None
    candidates = [url]
    if "www.stats.gov.cn" in url:
        candidates.append(url.replace("www.stats.gov.cn", "stats.gov.cn"))

    for attempt_url in candidates:
        for _ in range(2):
            try:
                res = requests.get(attempt_url, timeout=timeout_s, headers=headers)
                res.raise_for_status()
                return res.text
            except Exception as e:
                last_err = e
                continue

    raise last_err  # type: ignore[misc]


def _parse_list(html: str) -> List[str]:
    # List page has entries like:
    # * [13.Purchasing Managers’ Index for December 2025](./202601/t20260108_1962265.html)2026-01-01
    links = re.findall(
        r'href="(\./\d{6}/t\d{8}_\d+\.html)"[^>]*>\s*\d+\.\s*Purchasing Managers',
        html,
        flags=re.IGNORECASE,
    )
    # Deduplicate while preserving order
    seen = set()
    out: List[str] = []
    for href in links:
        if href in seen:
            continue
        seen.add(href)
        out.append("https://www.stats.gov.cn/english/PressRelease/" + href.lstrip("./"))
    return out


def _month_year_from_title(page_html: str) -> Tuple[int, int]:
    # Title line:
    # # Purchasing Managers’ Index for December 2025
    normalized = page_html.replace("\xa0", " ")
    m = re.search(
        r"Purchasing\s+Managers.{0,20}Index\s+for\s+([A-Za-z]+)\s+(\d{4})",
        normalized,
        flags=re.IGNORECASE,
    )
    if not m:
        raise ValueError("Could not parse PMI month/year from title")
    month_name = m.group(1).strip()
    year = int(m.group(2))
    month_map = {name: i for i, name in enumerate(calendar.month_name) if name}
    month = month_map.get(month_name)
    if not month:
        raise ValueError(f"Unknown month name in title: {month_name}")
    return year, month


def _published_date(page_html: str) -> Optional[date]:
    # Example: "2026-01-01 09:30"
    m = re.search(r"\n(\d{4}-\d{2}-\d{2})\s+\d{2}:\d{2}", page_html)
    if not m:
        return None
    return datetime.strptime(m.group(1), "%Y-%m-%d").date()


def _extract_manufacturing_pmi(page_html: str) -> float:
    # Example sentence:
    # "In December, the Purchasing Managers’ Index (PMI) of China’s manufacturing industry came in at 50.1%..."
    m = re.search(
        r"manufacturing\s+industry\s+came\s+in\s+at\s+(\d{1,3}\.\d)\s*%",
        page_html,
        flags=re.IGNORECASE,
    )
    if m:
        return float(m.group(1))

    # Fallback: try to pull the PMI value from the table section where the month appears as "December | 50.1 | ..."
    m2 = re.search(r"\|\s*December\s*\|\s*(\d{1,3}\.\d)\s*\|", page_html, flags=re.IGNORECASE)
    if m2:
        return float(m2.group(1))

    raise ValueError("Could not extract Manufacturing PMI value from page")


def _extract_monthly_pmi_from_table(page_html: str, source_url: str) -> List[PmiObservation]:
    """
    Extract a year of monthly PMI values from the embedded table on the PMI release page.

    NBS pages commonly include a table with rows like:
    - 2024-December | 50.1 | ...
    - 2025-January  | 49.1 | ...
    - February      | 50.2 | ...
    """
    published = _published_date(page_html)

    # Find the PMI table block and parse rows/cells.
    anchor = "China\u2019s Manufacturing PMI and Sub-indexes"
    idx = page_html.find(anchor)
    if idx == -1:
        # try plain apostrophe variant
        idx = page_html.find("China's Manufacturing PMI and Sub-indexes")
    if idx == -1:
        return []

    after = page_html[idx:]
    table_match = re.search(r"(<table[^>]*>.*?</table>)", after, flags=re.IGNORECASE | re.DOTALL)
    if not table_match:
        # Fallback: some fetchers provide a pipe-delimited table (markdown-ish),
        # not raw <table> HTML. Parse rows like:
        #   2024-December | 50.1 | ...
        #   2025-January  | 49.1 | ...
        #   February      | 50.2 | ...
        month_map = {name: i for i, name in enumerate(calendar.month_name) if name}
        current_year: Optional[int] = None
        obs: List[PmiObservation] = []

        # Scan only a limited window after the anchor (avoid picking up other tables).
        lines = after.splitlines()
        for line in lines[:400]:
            if "|" not in line:
                continue
            parts = [p.strip() for p in line.split("|")]
            # Expected: ["", "2025-January", "", "49.1", "", ...] OR ["2025-January", "49.1", ...]
            parts = [p for p in parts if p]
            if len(parts) < 2:
                continue
            token = parts[0]
            pmi_str = parts[1]
            if not token or not pmi_str:
                continue
            if token.lower() in {"pmi", "unit:", "unit"}:
                continue

            if "-" in token and token.split("-", 1)[0].isdigit():
                y_str, m_str = token.split("-", 1)
                m = month_map.get(m_str)
                if not m:
                    continue
                current_year = int(y_str)
                event_date = _event_date_for_reference_month(current_year, m)
            else:
                m = month_map.get(token)
                if not m or current_year is None:
                    continue
                event_date = _event_date_for_reference_month(current_year, m)

            try:
                value = float(pmi_str)
            except ValueError:
                continue
            obs.append(
                PmiObservation(
                    event_date=event_date,
                    value=value,
                    source_url=source_url,
                    published_at=published,
                )
            )

        return sorted({o.event_date: o for o in obs}.values(), key=lambda o: o.event_date)

    table_html = table_match.group(1)
    rows_html = re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, flags=re.IGNORECASE | re.DOTALL)
    if not rows_html:
        return []

    month_map = {name: i for i, name in enumerate(calendar.month_name) if name}
    current_year: Optional[int] = None
    obs: List[PmiObservation] = []

    def clean(cell_html: str) -> str:
        txt = re.sub(r"<[^>]+>", " ", cell_html)
        txt = htmllib.unescape(txt)
        txt = re.sub(r"\s+", " ", txt).strip()
        return txt

    for row_html in rows_html:
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, flags=re.IGNORECASE | re.DOTALL)
        if len(cells) < 2:
            continue
        token = clean(cells[0])
        pmi_str = clean(cells[1])
        if not token or not pmi_str:
            continue
        # Skip header rows
        if token.lower() in {"pmi", "unit:", "unit"}:
            continue

        # token may be "2025-January" or "February" or "2024-December"
        if "-" in token and token.split("-", 1)[0].isdigit():
            y_str, m_str = token.split("-", 1)
            m = month_map.get(m_str)
            if not m:
                continue
            current_year = int(y_str)
            event_date = _event_date_for_reference_month(current_year, m)
        else:
            m = month_map.get(token)
            if not m or current_year is None:
                continue
            event_date = _event_date_for_reference_month(current_year, m)

        try:
            value = float(pmi_str)
        except ValueError:
            continue

        obs.append(PmiObservation(event_date=event_date, value=value, source_url=source_url, published_at=published))

    return sorted({o.event_date: o for o in obs}.values(), key=lambda o: o.event_date)


def _event_date_for_reference_month(year: int, month: int) -> date:
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, last_day)


def fetch_observations(
    min_event_date: Optional[date] = None,
    source_url: Optional[str] = None,
    html_path: Optional[Path] = None,
) -> List[PmiObservation]:
    # NBS list page shows only recent releases, but each PMI release includes a full-year monthly table.
    if html_path is not None:
        page = html_path.read_text(encoding="utf-8", errors="ignore")
        url = source_url or "file://" + str(html_path)
    else:
        if source_url:
            url = source_url
        else:
            # Try multiple list pages (index.html, index_1.html, etc.)
            base = NBS_LIST_URL.rstrip("/") + "/"
            candidate_pages = [base, base + "index.html"] + [
                base + f"index_{i}.html" for i in range(1, 8)
            ]
            urls: List[str] = []
            for list_url in candidate_pages:
                try:
                    list_html = _fetch(list_url, timeout_s=60)
                except Exception:
                    continue
                urls = _parse_list(list_html)
                if urls:
                    break
            if not urls:
                raise ValueError("No PMI release links found on NBS Latest Releases pages")
            url = urls[0]
        page = _fetch(url, timeout_s=60)

    obs: List[PmiObservation] = []
    # Use the newest PMI page; parse the monthly table for a 12+ month backfill.
    table_obs = _extract_monthly_pmi_from_table(page, source_url=url)
    if table_obs:
        obs.extend(table_obs)
    else:
        # Fallback: single headline PMI (for the reference month in the title)
        ref_year, ref_month = _month_year_from_title(page)
        event_date = _event_date_for_reference_month(ref_year, ref_month)
        value = _extract_manufacturing_pmi(page)
        obs.append(PmiObservation(event_date=event_date, value=value, source_url=url, published_at=_published_date(page)))

    if min_event_date:
        obs = [o for o in obs if o.event_date >= min_event_date]

    # sort ascending
    obs.sort(key=lambda o: o.event_date)
    return obs


def upsert_observations(conn, observations: Iterable[PmiObservation], dry_run: bool = False) -> int:
    rows = list(observations)
    if not rows:
        logger.warning("No PMI observations to upsert")
        return 0

    if dry_run:
        logger.info(f"[DRY RUN] Would upsert {len(rows)} rows into econ.activity_1d (series_id={SERIES_ID})")
        logger.info(f"  Date range: {rows[0].event_date} → {rows[-1].event_date}")
        logger.info(f"  Sample: {[{'event_date': r.event_date.isoformat(), 'value': r.value, 'url': r.source_url} for r in rows[-3:]]}")
        return 0

    sql = """
        INSERT INTO econ.activity_1d (series_id, event_date, value, source, ingested_at, knowledge_time, row_hash)
        VALUES (%s, %s, %s, %s, NOW(), NOW(), %s)
        ON CONFLICT (series_id, event_date) DO UPDATE SET
            value = EXCLUDED.value,
            source = EXCLUDED.source,
            ingested_at = NOW(),
            knowledge_time = NOW(),
            row_hash = EXCLUDED.row_hash
    """

    def row_hash(event_date: date, value: float, url: str) -> str:
        payload = f"{SERIES_ID}|{event_date.isoformat()}|{value:.3f}|{url}"
        return hashlib.sha256(payload.encode()).hexdigest()[:64]  # type: ignore[name-defined]

    records = [
        (SERIES_ID, r.event_date, r.value, SOURCE_NAME, row_hash(r.event_date, r.value, r.source_url))
        for r in rows
    ]

    with conn.cursor() as cur:
        cur.executemany(sql, records)
    conn.commit()
    return len(records)


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest China Manufacturing PMI (NBS) into econ.activity_1d")
    parser.add_argument("--dry-run", action="store_true", help="Do not write to DB")
    parser.add_argument("--start", type=str, default=None, help="Minimum event_date (YYYY-MM-DD) filter")
    parser.add_argument("--url", type=str, default=None, help="Override source PMI release URL (optional)")
    parser.add_argument("--html-path", type=str, default=None, help="Parse PMI from a saved HTML file (optional)")
    args = parser.parse_args()

    min_event_date: Optional[date] = None
    if args.start:
        min_event_date = datetime.strptime(args.start, "%Y-%m-%d").date()

    html_path = Path(args.html_path) if args.html_path else None
    obs = fetch_observations(min_event_date=min_event_date, source_url=args.url, html_path=html_path)
    logger.info(f"Fetched {len(obs)} PMI observations from NBS")

    conn = get_connection()
    try:
        written = upsert_observations(conn, obs, dry_run=args.dry_run)
        if not args.dry_run:
            logger.info(f"Wrote {written} rows to econ.activity_1d (series_id={SERIES_ID})")
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
