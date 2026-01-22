#!/usr/bin/env python3
"""
Auto-run Monte Carlo after meta-ensemble is updated.
"""
import os
import time
import argparse
from datetime import datetime

import psycopg2
from dotenv import load_dotenv

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

HORIZONS = [5, 21, 63, 126]


def get_connection():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise SystemExit("DATABASE_URL not found")
    return psycopg2.connect(db_url)


def meta_ready(conn, since: datetime) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT horizon, COUNT(*)
            FROM model.meta_ensemble
            WHERE trained_at >= %s
            GROUP BY horizon
            """,
            (since,),
        )
        rows = cur.fetchall()
    seen = {r[0] for r in rows if r[1] > 0}
    return all(h in seen for h in HORIZONS)


def main():
    parser = argparse.ArgumentParser(description="Autorun Monte Carlo after meta-ensemble")
    parser.add_argument("--since", required=True, help="ISO timestamp to wait for")
    parser.add_argument("--poll-seconds", type=int, default=300)
    args = parser.parse_args()

    since = datetime.fromisoformat(args.since)
    print(f"[MC] Waiting for meta_ensemble updates since {since.isoformat()} ...")

    while True:
        conn = get_connection()
        try:
            if meta_ready(conn, since):
                break
        finally:
            conn.close()
        time.sleep(args.poll_seconds)

    print("[MC] Meta-ensemble ready. Running Monte Carlo for all horizons...")
    os.execvp(
        os.path.join(PROJECT_ROOT, ".venv", "bin", "python"),
        [
            os.path.join(PROJECT_ROOT, ".venv", "bin", "python"),
            os.path.join(PROJECT_ROOT, "scripts", "run_monte_carlo.py"),
            "--horizon",
            "all",
        ],
    )


if __name__ == "__main__":
    main()
