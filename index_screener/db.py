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


def _fetch_and_store(conn: sqlite3.Connection, ticker: str, period: str) -> None:
    """Pull fresh OHLCV data from Yahoo Finance and upsert it into the cache."""
    history = yf.Ticker(ticker).history(period=period)
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


def get_price_history(ticker: str, force_refresh: bool = False, period: str = FETCH_PERIOD) -> pd.DataFrame:
    """Return cached daily OHLCV history for a ticker, oldest first (Date-indexed).

    Only calls Yahoo Finance if the ticker is missing from the cache, its cached
    data is missing recent trading days, or force_refresh=True. `period` only
    affects how much history is pulled on that external call (e.g. a smaller
    window for a first pass on a new batch of tickers).
    """
    conn = _connect()
    try:
        if force_refresh or _needs_fetch(conn, ticker):
            _fetch_and_store(conn, ticker, period)

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


def populate_tickers(tickers: list[str], period: str = FETCH_PERIOD, force_refresh: bool = False) -> None:
    """Warm the cache for a batch of tickers (e.g. a newly added index's constituents)."""
    for ticker in tickers:
        try:
            get_price_history(ticker, force_refresh=force_refresh, period=period)
        except Exception as exc:
            print(f"WARNING: {ticker} failed to populate: {exc}")


def get_cache_summary() -> pd.DataFrame:
    """Return per-ticker cache coverage: date range, row count, and staleness. Used for status/stats views."""
    conn = _connect()
    try:
        df = pd.read_sql(
            "SELECT ticker, MIN(date) AS first_date, MAX(date) AS last_date, COUNT(*) AS rows "
            "FROM prices GROUP BY ticker ORDER BY ticker",
            conn,
        )
    finally:
        conn.close()

    if df.empty:
        return df

    last_dates = pd.to_datetime(df["last_date"]).dt.date
    df["is_stale"] = last_dates.apply(lambda d: (date.today() - d).days > STALE_AFTER_DAYS)
    return df
