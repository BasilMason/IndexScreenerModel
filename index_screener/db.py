"""SQLite-backed cache for daily OHLCV price history.

Stages read price data through get_price_history(), which serves cached data from
data/market_data.db and only calls Yahoo Finance when a ticker has no cached data,
its cached data is missing recent trading days, or a refresh is explicitly forced
(e.g. to correct bad data). Otherwise, no external call is made.
"""

import sqlite3
import time
from datetime import date
from pathlib import Path

import pandas as pd
import yfinance as yf

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "market_data.db"

# If the newest cached trading day is older than this many calendar days, treat
# the cache as missing recent data and re-fetch (buffer covers weekends/holidays).
STALE_AFTER_DAYS = 4

# History fetched per ticker on a cache miss - covers the longest lookback any
# stage currently needs (EMA trend's 200-day SMA), with room to spare.
FETCH_PERIOD = "2y"

# Pause after each live Yahoo Finance call so a big batch of cache misses doesn't trip rate limiting.
REQUEST_DELAY_SECONDS = 0.5

_SCHEMA = """
CREATE TABLE IF NOT EXISTS prices (
    ticker TEXT NOT NULL,
    date TEXT NOT NULL,
    open REAL, high REAL, low REAL, close REAL, volume INTEGER,
    PRIMARY KEY (ticker, date)
);
"""


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(_SCHEMA)
    return conn


def _latest_cached_date(conn: sqlite3.Connection, ticker: str) -> date | None:
    row = conn.execute("SELECT MAX(date) FROM prices WHERE ticker = ?", (ticker,)).fetchone()
    return date.fromisoformat(row[0]) if row and row[0] else None


def _needs_fetch(conn: sqlite3.Connection, ticker: str) -> bool:
    latest = _latest_cached_date(conn, ticker)
    return latest is None or (date.today() - latest).days > STALE_AFTER_DAYS


def _fetch_and_store(conn: sqlite3.Connection, ticker: str) -> None:
    """Pull fresh OHLCV data from Yahoo Finance and upsert it into the cache."""
    history = yf.Ticker(ticker).history(period=FETCH_PERIOD)
    if history.empty:
        raise ValueError("no price history returned")

    records = [
        (ticker, dt.date().isoformat(), r.Open, r.High, r.Low, r.Close, int(r.Volume))
        for dt, r in history.iterrows()
    ]
    conn.executemany(
        "INSERT OR REPLACE INTO prices (ticker, date, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?)",
        records,
    )
    conn.commit()
    time.sleep(REQUEST_DELAY_SECONDS)


def get_price_history(ticker: str, force_refresh: bool = False) -> pd.DataFrame:
    """Return cached daily OHLCV history for a ticker, oldest first (Date-indexed).

    Only calls Yahoo Finance if the ticker is missing from the cache, its cached
    data is missing recent trading days, or force_refresh=True.
    """
    conn = _connect()
    try:
        if force_refresh or _needs_fetch(conn, ticker):
            _fetch_and_store(conn, ticker)

        df = pd.read_sql(
            "SELECT date, open, high, low, close, volume FROM prices WHERE ticker = ? ORDER BY date",
            conn,
            params=(ticker,),
            parse_dates=["date"],
        )
    finally:
        conn.close()

    if df.empty:
        raise ValueError("no price history in cache")

    return df.set_index("date").rename(columns=str.title)
