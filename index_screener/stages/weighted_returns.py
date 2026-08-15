"""Stage: rank indices by a weighted blend of N-day return percentiles.

For each index: return_Nd = (prev_close - close_N_trading_days_ago) / close_N_trading_days_ago
Indices are then ranked 1 (highest) to N (lowest) on each return_Nd, the rank is converted
to a 0-100 percentile, and RETURN_WEIGHTS is applied to the percentiles (not the raw returns)
to give this stage's weighted_returns_score.
"""

import time

import pandas as pd

from ..config import IndexMeta
from ..data import REQUEST_DELAY_SECONDS, fetch_price_history
from .base import Stage

# Lookback windows (trading days) and the weight applied to each when combining
# them into this stage's score. Must sum to 1.0.
RETURN_WEIGHTS: dict[int, float] = {
    10: 0.10,
    20: 0.40,
    30: 0.20,
    60: 0.30,
}
assert abs(sum(RETURN_WEIGHTS.values()) - 1.0) < 1e-9, "RETURN_WEIGHTS must sum to 1.0"


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


def _add_rankings(table: pd.DataFrame) -> pd.DataFrame:
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

    table["weighted_returns_score"] = sum(
        weight * table[f"percentile_{window}d"] for window, weight in RETURN_WEIGHTS.items()
    )
    return table


def _reorder_columns(table: pd.DataFrame) -> pd.DataFrame:
    """Group columns by return window (close/return/rank/percentile) instead of by calculation step."""
    identity_cols = ["ticker", "prev_close_date", "prev_close"]
    window_cols = [
        f"{prefix}_{window}d{suffix}"
        for window in RETURN_WEIGHTS
        for prefix, suffix in [("close", "_ago"), ("return", ""), ("rank", ""), ("percentile", "")]
    ]
    return table[identity_cols + window_cols + ["weighted_returns_score"]]


class WeightedReturnsStage(Stage):
    name = "weighted_returns"

    def run(self, universe: list[IndexMeta]) -> pd.DataFrame:
        """Iterate the universe, fetch price data, and score each index. Bad data is kept as NaN, not dropped."""
        rows = []
        for i, index in enumerate(universe):
            row = {"ticker": index.ticker}
            try:
                closes = fetch_price_history(index.ticker)["Close"]
                row.update(compute_returns(closes))
            except Exception as exc:
                print(f"WARNING: {index.ticker} ({index.name}) failed, leaving as NaN: {exc}")
                row.update(_nan_metrics())
            rows.append(row)

            if i < len(universe) - 1:
                time.sleep(REQUEST_DELAY_SECONDS)

        table = pd.DataFrame(rows)
        table = _add_rankings(table)
        return _reorder_columns(table)
