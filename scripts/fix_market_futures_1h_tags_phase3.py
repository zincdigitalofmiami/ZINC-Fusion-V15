#!/usr/bin/env python3
"""
Phase 3: Fix `raw.market_futures_1h` "general" specialist_tags (prod-safe).

Surgical contract:
- Only updates rows where 'general' = ANY(specialist_tags)
- Only for explicitly-listed symbols in PHASE3_TAG_MAP
- Leaves all other rows untouched
- Verifies expected rowcounts before commit
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, List

import psycopg2
from dotenv import load_dotenv


@dataclass(frozen=True)
class UpdateSpec:
    symbol: str
    tags: List[str]


PHASE3_TAG_MAP: List[UpdateSpec] = [
    # Equity indices (risk sentiment)
    UpdateSpec(symbol="YM", tags=["core", "volatility"]),
    UpdateSpec(symbol="ES", tags=["core", "volatility"]),
    UpdateSpec(symbol="NQ", tags=["core", "volatility"]),
    UpdateSpec(symbol="EMD", tags=["core", "volatility"]),
    UpdateSpec(symbol="RTY", tags=["core", "volatility"]),
    # Micro equity indices
    UpdateSpec(symbol="MES", tags=["core", "volatility"]),
    UpdateSpec(symbol="MNQ", tags=["core", "volatility"]),
    UpdateSpec(symbol="M2K", tags=["core", "volatility"]),
    UpdateSpec(symbol="MYM", tags=["core", "volatility"]),
    # Energy
    UpdateSpec(symbol="QG", tags=["energy"]),
    # Crypto (risk proxy)
    UpdateSpec(symbol="BTC", tags=["volatility"]),
    UpdateSpec(symbol="ETH", tags=["volatility"]),
    UpdateSpec(symbol="MBT", tags=["volatility"]),
    UpdateSpec(symbol="MET", tags=["volatility"]),
    # Livestock (protein demand / substitutes)
    UpdateSpec(symbol="LE", tags=["substitutes", "volatility"]),
    UpdateSpec(symbol="HE", tags=["substitutes", "volatility"]),
    UpdateSpec(symbol="GF", tags=["substitutes", "volatility"]),
    # Commodities / misc
    UpdateSpec(symbol="LBR", tags=["substitutes"]),
    UpdateSpec(symbol="SIL", tags=["volatility"]),
    UpdateSpec(symbol="CU", tags=["substitutes", "volatility"]),
    UpdateSpec(symbol="CJ", tags=["substitutes"]),
    UpdateSpec(symbol="KT", tags=["substitutes"]),
    # Key finding: Mini Soybean Oil proxy
    UpdateSpec(symbol="YO", tags=["core", "crush"]),
]


def _require_database_url() -> str:
    load_dotenv()
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required (load from .env or env var)")
    return database_url


def _as_sorted_unique(tags: List[str]) -> List[str]:
    return sorted(set(tags), key=str)


def main() -> None:
    database_url = _require_database_url()

    # Normalize tags (unique + deterministic order)
    specs = [UpdateSpec(s.symbol, _as_sorted_unique(s.tags)) for s in PHASE3_TAG_MAP]
    spec_by_symbol: Dict[str, UpdateSpec] = {s.symbol: s for s in specs}
    if len(spec_by_symbol) != len(specs):
        raise SystemExit("Duplicate symbols detected in PHASE3_TAG_MAP")

    symbols = [s.symbol for s in specs]

    conn = psycopg2.connect(database_url)
    try:
        with conn:
            with conn.cursor() as cur:
                # Preflight: ensure table/column exist
                cur.execute(
                    """
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema='raw'
                      AND table_name='market_futures_1h'
                      AND column_name='specialist_tags'
                    """
                )
                if cur.fetchone() is None:
                    raise SystemExit("raw.market_futures_1h.specialist_tags not found")

                # Preflight: counts per symbol of rows currently tagged general
                cur.execute(
                    """
                    SELECT symbol, COUNT(*)::int AS rows
                    FROM raw.market_futures_1h
                    WHERE symbol = ANY(%s)
                      AND specialist_tags IS NOT NULL
                      AND 'general' = ANY(specialist_tags)
                    GROUP BY symbol
                    ORDER BY symbol
                    """,
                    (symbols,),
                )
                rows = cur.fetchall()
                current_general_by_symbol = {sym: n for sym, n in rows}

                # Guardrail: every mapped symbol must actually have at least 1 general row
                missing = [sym for sym in symbols if current_general_by_symbol.get(sym, 0) == 0]
                if missing:
                    raise SystemExit(
                        "Refusing to proceed: these symbols have 0 rows with 'general' tag in raw.market_futures_1h: "
                        + ", ".join(missing)
                    )

                total_target = sum(current_general_by_symbol.values())
                cur.execute(
                    """
                    SELECT COUNT(*)::int
                    FROM raw.market_futures_1h
                    WHERE specialist_tags IS NOT NULL
                      AND 'general' = ANY(specialist_tags)
                    """
                )
                total_general_before = int(cur.fetchone()[0])

                print("=== PHASE 3 PRECHECK: raw.market_futures_1h ===")
                print(f"Total rows with 'general' tag (before): {total_general_before:,}")
                print(f"Rows targeted by symbol map:            {total_target:,}")
                print("\nPer-symbol targeted counts:")
                for sym in sorted(symbols):
                    spec = spec_by_symbol[sym]
                    cnt = current_general_by_symbol[sym]
                    print(f"  {sym:6} {cnt:10,} -> {spec.tags}")

                if total_target != total_general_before:
                    raise SystemExit(
                        "Refusing to proceed: symbol map does not cover all 'general' rows in raw.market_futures_1h "
                        f"(target={total_target:,} vs total_general={total_general_before:,})."
                    )

                # Apply updates (symbol-by-symbol)
                print("\n=== APPLYING UPDATES ===")
                total_updated = 0
                for sym in sorted(symbols):
                    spec = spec_by_symbol[sym]
                    cur.execute(
                        """
                        UPDATE raw.market_futures_1h
                        SET specialist_tags = %s
                        WHERE symbol = %s
                          AND specialist_tags IS NOT NULL
                          AND 'general' = ANY(specialist_tags)
                        """,
                        (spec.tags, spec.symbol),
                    )
                    updated = cur.rowcount
                    total_updated += updated
                    print(f"  {sym:6} updated={updated:10,} tags={spec.tags}")

                print(f"\nTOTAL UPDATED: {total_updated:,}")

                # Post-verify: general tags should be zero
                cur.execute(
                    """
                    SELECT COUNT(*)::int
                    FROM raw.market_futures_1h
                    WHERE specialist_tags IS NOT NULL
                      AND 'general' = ANY(specialist_tags)
                    """
                )
                remaining = int(cur.fetchone()[0])
                if remaining != 0:
                    raise SystemExit(f"Post-check failed: remaining 'general' rows = {remaining:,} (expected 0)")

                # Spot-check YO tagged correctly
                cur.execute(
                    """
                    SELECT COUNT(*)::int
                    FROM raw.market_futures_1h
                    WHERE symbol='YO'
                      AND specialist_tags = %s
                    """,
                    (spec_by_symbol["YO"].tags,),
                )
                yo_ok = int(cur.fetchone()[0])
                print(f"\nPost-check: YO rows with tags {spec_by_symbol['YO'].tags}: {yo_ok:,}")
                print("✅ Phase 3 complete: raw.market_futures_1h has 0 rows tagged 'general'")

    finally:
        conn.close()


if __name__ == "__main__":
    main()

