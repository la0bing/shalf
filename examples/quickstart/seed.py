"""Create the quickstart SQLite source database with synthetic data."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np

DEFAULT_PATH = Path(__file__).parent / "feature_repo" / "data" / "source.db"


def seed(path: str | Path = DEFAULT_PATH, *, now: datetime | None = None, seed: int = 7) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    now = (now or datetime.now(UTC)).replace(minute=0, second=0, microsecond=0)
    rng = np.random.default_rng(seed)

    def iso(ts: datetime) -> str:
        return ts.isoformat()

    customers = [
        (
            cid,
            int(rng.integers(18, 80)),
            str(rng.choice(["SG", "MY", "ID"])),
            bool(rng.random() < 0.3),
            iso(now - timedelta(days=int(rng.integers(30, 300)))),
        )
        for cid in range(1, 51)
    ]
    merchants = [
        (
            mid,
            round(float(rng.random()), 3),
            str(rng.choice(["grocery", "travel", "gaming"])),
            iso(now - timedelta(days=90)),
        )
        for mid in range(1, 11)
    ]
    transactions = [
        (
            tid,
            int(rng.integers(1, 51)),
            int(rng.integers(1, 11)),
            round(float(rng.gamma(2.0, 30.0)), 2),
            iso(now - timedelta(minutes=int(rng.integers(1, 60 * 24 * 30)))),
        )
        for tid in range(1, 3001)
    ]

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
        conn.executemany("INSERT INTO customers VALUES (?, ?, ?, ?, ?)", customers)
        conn.executemany("INSERT INTO merchants VALUES (?, ?, ?, ?)", merchants)
        conn.executemany("INSERT INTO transactions VALUES (?, ?, ?, ?, ?)", transactions)
    return path


if __name__ == "__main__":
    print(f"Seeded {seed()}")
