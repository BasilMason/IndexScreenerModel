"""Shared Yahoo Finance price fetching, used by any stage that needs OHLCV data."""

import pandas as pd
import yfinance as yf

# 1 year of calendar days comfortably covers a 60 trading-day lookback,
# with a buffer for weekends/holidays. Stages can override if they need more.
HISTORY_PERIOD = "1y"

# Small pause between requests so a 20-ticker loop doesn't trip Yahoo's rate limiting.
REQUEST_DELAY_SECONDS = 0.5


def fetch_price_history(ticker: str, period: str = HISTORY_PERIOD) -> pd.DataFrame:
    """Return daily OHLCV history for a ticker, oldest first. Raises if no data is returned."""
    history = yf.Ticker(ticker).history(period=period)
    if history.empty:
        raise ValueError("no price history returned")
    return history
