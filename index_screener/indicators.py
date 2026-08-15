"""Fetch price history from Yahoo Finance and rank indices by weighted return percentile.

For each index: return_Nd = (prev_close - close_N_trading_days_ago) / close_N_trading_days_ago
Indices are then ranked 1 (highest) to N (lowest) on each return_Nd, the rank is converted
to a 0-100 percentile, and RETURN_WEIGHTS is applied to the percentiles (not the raw returns)
to give a single weighted_percentile composite score.
"""

import time

import pandas as pd
import yfinance as yf

from .config import INDEX_UNIVERSE, RETURN_WEIGHTS

# 1 year of calendar days comfortably covers the 60 trading days we need,
# with a buffer for weekends/holidays.
HISTORY_PERIOD = "1y"

# Small pause between requests so a 20-ticker loop doesn't trip Yahoo's rate limiting.
REQUEST_DELAY_SECONDS = 0.5


def fetch_close_prices(ticker: str) -> pd.Series:
    """Return the daily Close price series for a ticker, oldest first."""
    history = yf.Ticker(ticker).history(period=HISTORY_PERIOD)
    if history.empty:
        raise ValueError("no price history returned")
    return history["Close"]


def compute_returns(closes: pd.Series) -> dict:
    """Compute the previous-close-based raw return for each configured window."""
    max_window = max(RETURN_WEIGHTS)
    if len(closes) < max_window + 1:
        raise ValueError(f"only {len(closes)} rows of history, need at least {max_window + 1}")

    prev_close_date = closes.index[-1]
    prev_close = closes.iloc[-1]
    if pd.isna(prev_close) or prev_close <= 0:
        raise ValueError(f"invalid previous close: {prev_close}")

    row = {"prev_close_date": prev_close_date.date(), "prev_close": prev_close}

    for window in RETURN_WEIGHTS:
        close_n_ago = closes.iloc[-1 - window]
        if pd.isna(close_n_ago) or close_n_ago <= 0:
            raise ValueError(f"invalid close {window}d ago: {close_n_ago}")
        row[f"close_{window}d_ago"] = close_n_ago
        row[f"return_{window}d"] = (prev_close - close_n_ago) / close_n_ago

    return row


def _nan_metrics() -> dict:
    """Metric columns filled with NaN, used when a ticker's data can't be fetched/validated."""
    metrics = {"prev_close_date": pd.NaT, "prev_close": float("nan")}
    for window in RETURN_WEIGHTS:
        metrics[f"close_{window}d_ago"] = float("nan")
        metrics[f"return_{window}d"] = float("nan")
    return metrics


def add_rankings(table: pd.DataFrame) -> pd.DataFrame:
    """Rank indices per return window, convert rank to a percentile, then apply RETURN_WEIGHTS to the percentiles.

    rank 1 = highest return in that window. Percentile scales that rank to 0-100
    over the indices with valid data (best = 100, worst = 0), so weighting is
    done on relative standing rather than the raw return magnitude.
    """
    for window in RETURN_WEIGHTS:
        returns = table[f"return_{window}d"]
        n_valid = returns.notna().sum()
        rank = returns.rank(ascending=False, method="min")
        table[f"rank_{window}d"] = rank
        table[f"percentile_{window}d"] = (n_valid - rank) / (n_valid - 1) * 100

    table["weighted_percentile"] = sum(
        weight * table[f"percentile_{window}d"] for window, weight in RETURN_WEIGHTS.items()
    )
    return table


def build_return_table() -> pd.DataFrame:
    """Iterate the index universe, fetch data, and assemble the indicator table.

    A ticker that fails to fetch or fails validation is kept in the table with
    NaN metrics (rather than dropped) so the full 20-index universe is always
    visible for review, with bad data flagged instead of hidden.
    """
    rows = []
    failed = []
    for i, index in enumerate(INDEX_UNIVERSE):
        row = {"ticker": index.ticker, "name": index.name, "region": index.region}
        try:
            closes = fetch_close_prices(index.ticker)
            row.update(compute_returns(closes))
        except Exception as exc:
            print(f"WARNING: {index.ticker} ({index.name}) failed, leaving as NaN: {exc}")
            row.update(_nan_metrics())
            failed.append(index.ticker)
        rows.append(row)

        if i < len(INDEX_UNIVERSE) - 1:
            time.sleep(REQUEST_DELAY_SECONDS)

    table = pd.DataFrame(rows)
    table = add_rankings(table)
    table = table.sort_values("weighted_percentile", ascending=False, na_position="last").reset_index(drop=True)
    return table, failed


if __name__ == "__main__":
    table, failed = build_return_table()

    pd.set_option("display.width", 160)
    pd.set_option("display.max_columns", None)
    print(f"\n{len(INDEX_UNIVERSE) - len(failed)}/{len(INDEX_UNIVERSE)} indices collected successfully"
          f" ({len(failed)} flagged as NaN: {failed})\n")
    print(table.round(4).to_string())

    table.to_csv("data/return_indicators.csv", index=False)
    print("\nSaved to data/return_indicators.csv")
