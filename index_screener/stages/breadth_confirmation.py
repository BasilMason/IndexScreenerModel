"""Stage: breadth confirmation.

For each index, fetches every constituent stock's price data and checks whether
it's trading above its own 50-day SMA. The stage score is the percentage of
constituents that are above their SMA50 - a measure of how broad-based (vs.
narrow/top-heavy) an index's strength is.

Only indices with a populated entry in INDEX_CONSTITUENTS can be scored; others
are left NaN. Currently only FTSE 100 (^FTSE) is populated, as a first test round.
"""

import pandas as pd

from ..config import IndexMeta
from ..constituents import CONSTITUENT_NAMES, INDEX_CONSTITUENTS
from ..db import get_price_history
from .base import Stage

SMA_WINDOW = 50


def compute_stock_breadth(ticker: str) -> dict:
    """Fetch one stock's price data and check if its current price is above its SMA50."""
    closes = get_price_history(ticker)["Close"]
    if len(closes) < SMA_WINDOW:
        raise ValueError(f"only {len(closes)} rows of history, need at least {SMA_WINDOW}")

    current_price = closes.iloc[-1]
    sma_50 = closes.rolling(window=SMA_WINDOW).mean().iloc[-1]
    if pd.isna(current_price) or pd.isna(sma_50):
        raise ValueError("NaN in price or SMA50")

    return {"current_price": current_price, "sma_50": sma_50, "above_sma_50": current_price > sma_50}


def compute_breadth(tickers: list[str]) -> tuple[pd.DataFrame, float]:
    """Score every constituent stock and return (per-stock detail table, % above their SMA50)."""
    rows = []
    for ticker in tickers:
        row = {"ticker": ticker, "name": CONSTITUENT_NAMES.get(ticker, "")}
        try:
            row.update(compute_stock_breadth(ticker))
        except Exception as exc:
            print(f"WARNING: {ticker} failed, leaving as NaN: {exc}")
            row.update({"current_price": float("nan"), "sma_50": float("nan"), "above_sma_50": pd.NA})
        rows.append(row)

    table = pd.DataFrame(rows)
    # Nullable boolean dtype: a plain object column mixing True/False/None makes
    # pandas' sum()/mean() silently collapse to an any()-like result instead of
    # counting - "boolean" dtype keeps NA-aware sum/mean arithmetically correct.
    table["above_sma_50"] = table["above_sma_50"].astype("boolean")
    valid_checks = table["above_sma_50"].dropna()
    breadth_pct = valid_checks.mean() * 100 if len(valid_checks) else float("nan")
    return table, breadth_pct


class BreadthConfirmationStage(Stage):
    name = "breadth_confirmation"

    def run(self, universe: list[IndexMeta]) -> pd.DataFrame:
        """Score each index by the % of its constituents trading above their SMA50.

        Indices without a constituent list in INDEX_CONSTITUENTS are scored NaN.
        """
        rows = []
        for index in universe:
            tickers = INDEX_CONSTITUENTS.get(index.ticker)
            if not tickers:
                rows.append({"ticker": index.ticker, "breadth_confirmation_score": float("nan")})
                continue
            _, breadth_pct = compute_breadth(tickers)
            rows.append({"ticker": index.ticker, "breadth_confirmation_score": breadth_pct})

        return pd.DataFrame(rows)


if __name__ == "__main__":
    # First test round: FTSE 100 only. Display the full per-stock breakdown and the overall %.
    tickers = INDEX_CONSTITUENTS["^FTSE"]
    table, breadth_pct = compute_breadth(tickers)

    pd.set_option("display.width", 160)
    pd.set_option("display.max_columns", None)
    print(table.round(4).to_string())
    print(f"\n{int(table['above_sma_50'].notna().sum())}/{len(tickers)} stocks scored")
    print(f"FTSE 100 breadth (% of stocks above SMA50): {breadth_pct:.2f}%")

    table.to_csv("data/breadth_ftse100_results.csv", index=False)
    print("\nSaved to data/breadth_ftse100_results.csv")
