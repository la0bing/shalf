"""Create the quickstart's "application database" with synthetic data.

python seed.py                                  # SQLite at data/source.db
python seed.py --postgres postgresql://...      # Postgres (docker compose PoC)
python seed.py --postgres ... --if-empty        # skip when already seeded
"""

from __future__ import annotations

import argparse
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np

DEFAULT_PATH = Path(__file__).parent / "data" / "source.db"


def _rows(now: datetime, seed: int) -> dict[str, list[tuple]]:
    now = now.replace(minute=0, second=0, microsecond=0)
    rng = np.random.default_rng(seed)
    customers = [
        (
            cid,
            int(rng.integers(18, 80)),
            str(rng.choice(["SG", "MY", "ID"])),
            bool(rng.random() < 0.3),
            now - timedelta(days=int(rng.integers(30, 300))),
        )
        for cid in range(1, 51)
    ]
    merchants = [
        (mid, round(float(rng.random()), 3), str(rng.choice(["grocery", "travel", "gaming"])),
         now - timedelta(days=90))
        for mid in range(1, 11)
    ]  # fmt: skip
    transactions = [
        (
            tid,
            int(rng.integers(1, 51)),
            int(rng.integers(1, 11)),
            round(float(rng.gamma(2.0, 30.0)), 2),
            now - timedelta(minutes=int(rng.integers(1, 60 * 24 * 30))),
        )
        for tid in range(1, 3001)
    ]
    return {"customers": customers, "merchants": merchants, "transactions": transactions}


def seed(path: str | Path = DEFAULT_PATH, *, now: datetime | None = None, seed: int = 7) -> Path:
    """SQLite: timestamps stored as ISO-8601 text."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    rows = _rows(now or datetime.now(UTC), seed)
    iso = {name: [(*r[:-1], r[-1].isoformat()) for r in data] for name, data in rows.items()}
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE customers (customer_id INTEGER, age INTEGER, country TEXT,
                                    is_premium BOOLEAN, updated_at TEXT);
            CREATE TABLE merchants (merchant_id INTEGER, risk_score REAL, category TEXT,
                                    updated_at TEXT);
            CREATE TABLE transactions (txn_id INTEGER PRIMARY KEY, customer_id INTEGER,
                                       merchant_id INTEGER, amount REAL, created_at TEXT);
            """
        )
        conn.executemany("INSERT INTO customers VALUES (?, ?, ?, ?, ?)", iso["customers"])
        conn.executemany("INSERT INTO merchants VALUES (?, ?, ?, ?)", iso["merchants"])
        conn.executemany("INSERT INTO transactions VALUES (?, ?, ?, ?, ?)", iso["transactions"])
    return path


def seed_postgres(
    dsn: str, *, if_empty: bool = False, now: datetime | None = None, seed: int = 7
) -> bool:
    """Postgres with native types. Returns False when skipped (``if_empty``)."""
    import psycopg  # shalf-data[postgres]

    rows = _rows(now or datetime.now(UTC), seed)
    with psycopg.connect(dsn) as conn:
        exists = conn.execute("SELECT to_regclass('public.transactions') IS NOT NULL").fetchone()[0]
        if exists and if_empty:
            return False
        conn.execute("DROP TABLE IF EXISTS customers, merchants, transactions")
        conn.execute(
            """
            CREATE TABLE customers (customer_id INTEGER, age INTEGER, country TEXT,
                                    is_premium BOOLEAN, updated_at TIMESTAMPTZ);
            CREATE TABLE merchants (merchant_id INTEGER, risk_score DOUBLE PRECISION, category TEXT,
                                    updated_at TIMESTAMPTZ);
            CREATE TABLE transactions (txn_id INTEGER PRIMARY KEY, customer_id INTEGER,
                                       merchant_id INTEGER, amount DOUBLE PRECISION,
                                       created_at TIMESTAMPTZ);
            """
        )
        with conn.cursor() as cur:
            cur.executemany("INSERT INTO customers VALUES (%s, %s, %s, %s, %s)", rows["customers"])
            cur.executemany("INSERT INTO merchants VALUES (%s, %s, %s, %s)", rows["merchants"])
            insert = "INSERT INTO transactions VALUES (%s, %s, %s, %s, %s)"
            cur.executemany(insert, rows["transactions"])
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--postgres", metavar="DSN", help="seed this Postgres instead of SQLite")
    parser.add_argument("--if-empty", action="store_true", help="do nothing if already seeded")
    args = parser.parse_args()
    if args.postgres:
        seeded = seed_postgres(args.postgres, if_empty=args.if_empty)
        print("Seeded Postgres" if seeded else "Postgres already seeded; skipping")
    else:
        print(f"Seeded {seed()}")
