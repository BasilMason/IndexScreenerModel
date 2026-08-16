"""Stage: breadth confirmation.

For each index, fetches every constituent stock's price data and checks whether
it's trading above its own 50-day SMA. breadth_pct is the % of constituents above
their SMA50 - a measure of how broad-based (vs. narrow/top-heavy) an index's
strength is. That percentage is then converted into points via BREADTH_SCORE_TIERS.

Only indices with a populated entry in INDEX_CONSTITUENTS can be scored; others
are left NaN.
"""

import numpy as np
import pandas as pd

from ..config import INDEX_UNIVERSE, IndexMeta
from ..constituents import CONSTITUENT_NAMES, INDEX_CONSTITUENTS
from ..db import get_price_history
from .base import Stage

SMA_WINDOW = 50

# Points awarded for a given breadth_pct, checked highest threshold first: the
# first tier whose minimum the breadth_pct clears applies. Adjust these to retune.
BREADTH_SCORE_TIERS: list[tuple[float, float]] = [
    (70, 12),
    (60, 10),
    (50, 6),
    (40, 3),
    (0, 0),
]


def score_breadth(breadth_pct: float) -> float:
    """Convert a breadth percentage into points per BREADTH_SCORE_TIERS."""
    if pd.isna(breadth_pct):
        return float("nan")
    for threshold, points in BREADTH_SCORE_TIERS:
        if breadth_pct >= threshold:
            return points
    return 0


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


# --- Advance/Decline Line (ADL) ---
#
# Each constituent scores +1 on a day it closed above its own open ("advanced"),
# -1 if it closed below its open ("declined"), 0 if unchanged. These are summed
# across all constituents for each day (the daily net-advances), then summed
# across the lookback window to get the 10-day ADL total. A positive total scores
# ADL_POSITIVE_SCORE, zero or negative scores ADL_NON_POSITIVE_SCORE.
#
# Note: this uses each day's own open-to-close move, as specified. The more
# traditional advance/decline convention compares each day's close to the
# *previous* day's close instead - a different, also-valid measure of breadth.
# Swap the comparison in daily_moves() below if you'd rather use that convention.
ADL_LOOKBACK_DAYS = 10
ADL_POSITIVE_SCORE = 4
ADL_NON_POSITIVE_SCORE = 0


def daily_moves(ticker: str, lookback_days: int = ADL_LOOKBACK_DAYS) -> pd.DataFrame:
    """Return the last `lookback_days` rows of Open/Close plus each day's +1/-1/0 move for one stock."""
    history = get_price_history(ticker)
    if len(history) < lookback_days:
        raise ValueError(f"only {len(history)} rows of history, need at least {lookback_days}")

    recent = history[["Open", "Close"]].tail(lookback_days).copy()
    recent["move"] = np.sign(recent["Close"] - recent["Open"]).astype(int)
    return recent


def compute_adl(tickers: list[str]) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    """Compute per-stock daily moves, the daily net-advances series, and the ADL score.

    Returns (per_stock_table, daily_summary, adl_score):
    - per_stock_table: one row per stock, with open/close/move columns per day
    - daily_summary: one row per day, with net_advances = sum of moves across all stocks
    - adl_score: ADL_POSITIVE_SCORE or ADL_NON_POSITIVE_SCORE
    """
    per_stock_rows = []
    moves_by_ticker = {}

    for ticker in tickers:
        row = {"ticker": ticker, "name": CONSTITUENT_NAMES.get(ticker, "")}
        try:
            moves = daily_moves(ticker)
            moves_by_ticker[ticker] = moves["move"]
            for date, day in moves.iterrows():
                label = date.date().isoformat()
                row[f"{label}_open"] = day["Open"]
                row[f"{label}_close"] = day["Close"]
                row[f"{label}_move"] = int(day["move"])
        except Exception as exc:
            print(f"WARNING: {ticker} failed, leaving as NaN: {exc}")
        per_stock_rows.append(row)

    per_stock_table = pd.DataFrame(per_stock_rows)

    # Assumes all constituents share a trading calendar (true within a single
    # exchange, e.g. FTSE) - dates may not align cleanly for cross-exchange indices.
    moves_matrix = pd.DataFrame(moves_by_ticker)
    daily_summary = moves_matrix.sum(axis=1).rename("net_advances").reset_index().rename(columns={"index": "date"})
    daily_summary["date"] = daily_summary["date"].dt.date

    adl_10day_total = int(daily_summary["net_advances"].sum())
    adl_score = ADL_POSITIVE_SCORE if adl_10day_total > 0 else ADL_NON_POSITIVE_SCORE

    return per_stock_table, daily_summary, adl_score


# --- 20-day new high / new low check ---
#
# Each constituent scores +1 if its last close is the highest close in the
# trailing NEW_HIGH_LOW_WINDOW days (a new high), -1 if it's the lowest (a new
# low), 0 otherwise. Scores are summed across all constituents, then expressed
# as a percentage of the full constituent count - including any that failed to
# fetch, which count toward the denominator but contribute 0 to the numerator,
# matching "percentage of total stocks in the index" as specified.
#
# Interpretation note: "the last close vs. the previous 20 days" is read here as
# a 20-day window that includes the last close itself (the standard "N-day high/
# low" convention, like a 52-week high). Reading it as the last close vs. a
# separate prior 20-day window (excluding today) would be a breakout-style check
# instead - a valid alternative, but not what's implemented here.
NEW_HIGH_LOW_WINDOW = 20

# Points for the aggregate %, checked highest threshold first. The spec only
# defined tiers for percentages > 0 (>=30 / [10,30) / (0,10)); it didn't say what
# happens at or below 0%. Filled that gap with 0 points, consistent with every
# other "no signal" case in this stage.
NEW_HIGH_LOW_SCORE_TIERS: list[tuple[float, float]] = [
    (30, 4),
    (10, 3),
    (0, 2),
]


def stock_new_high_low(ticker: str, window: int = NEW_HIGH_LOW_WINDOW) -> int:
    """+1 if the last close is a new `window`-day high, -1 if a new low, 0 otherwise."""
    closes = get_price_history(ticker)["Close"]
    if len(closes) < window:
        raise ValueError(f"only {len(closes)} rows of history, need at least {window}")

    recent = closes.tail(window)
    last_close = recent.iloc[-1]
    if last_close == recent.max():
        return 1
    if last_close == recent.min():
        return -1
    return 0


def score_new_high_low_pct(pct: float) -> float:
    """Convert the aggregate new-high/low percentage into points per NEW_HIGH_LOW_SCORE_TIERS."""
    if pd.isna(pct):
        return float("nan")
    if pct <= 0:
        return 0
    for threshold, points in NEW_HIGH_LOW_SCORE_TIERS:
        if pct >= threshold:
            return points
    return 0


def compute_new_high_low(tickers: list[str]) -> tuple[pd.DataFrame, float, float]:
    """Score every constituent stock and return (per-stock table, aggregate %, score)."""
    rows = []
    for ticker in tickers:
        row = {"ticker": ticker, "name": CONSTITUENT_NAMES.get(ticker, "")}
        try:
            row["new_high_low_score"] = stock_new_high_low(ticker)
        except Exception as exc:
            print(f"WARNING: {ticker} failed, leaving as NaN: {exc}")
            row["new_high_low_score"] = float("nan")
        rows.append(row)

    table = pd.DataFrame(rows)
    aggregate_pct = table["new_high_low_score"].sum(skipna=True) / len(tickers) * 100
    score = score_new_high_low_pct(aggregate_pct)
    return table, aggregate_pct, score


class BreadthConfirmationStage(Stage):
    name = "breadth_confirmation"

    def run(self, universe: list[IndexMeta]) -> pd.DataFrame:
        """Score each index on three breadth signals and sum them into breadth_confirmation_score
        (max 12 + 4 + 4 = 20 points): SMA50 %, the 10-day ADL, and the 20-day new high/low check.

        Indices without a constituent list in INDEX_CONSTITUENTS are scored NaN throughout.
        """
        rows = []
        for index in universe:
            tickers = INDEX_CONSTITUENTS.get(index.ticker)
            if not tickers:
                row = {
                    "breadth_pct": float("nan"),
                    "sma50_score": float("nan"),
                    "adl_total": float("nan"),
                    "adl_score": float("nan"),
                    "new_high_low_pct": float("nan"),
                    "new_high_low_score": float("nan"),
                }
            else:
                _, breadth_pct = compute_breadth(tickers)
                _, daily, adl_score = compute_adl(tickers)
                _, nhl_pct, nhl_score = compute_new_high_low(tickers)
                row = {
                    "breadth_pct": breadth_pct,
                    "sma50_score": score_breadth(breadth_pct),
                    "adl_total": int(daily["net_advances"].sum()),
                    "adl_score": adl_score,
                    "new_high_low_pct": nhl_pct,
                    "new_high_low_score": nhl_score,
                }
            row["breadth_confirmation_score"] = (
                row["sma50_score"] + row["adl_score"] + row["new_high_low_score"]
            )
            rows.append({"ticker": index.ticker, **row})

        return pd.DataFrame(rows)


if __name__ == "__main__":
    # Breadth + score summary across every index with constituents populated.
    for index_ticker, tickers in INDEX_CONSTITUENTS.items():
        table, breadth_pct = compute_breadth(tickers)
        scored = int(table["above_sma_50"].notna().sum())
        print(
            f"{index_ticker}: {breadth_pct:.2f}% breadth ({scored}/{len(tickers)} scored) "
            f"-> {score_breadth(breadth_pct)} points"
        )

    # ADL: first test round, FTSE 100 only.
    per_stock, daily, adl_score = compute_adl(INDEX_CONSTITUENTS["^FTSE"])

    print(f"\nFTSE 100 ADL daily net advances (last {ADL_LOOKBACK_DAYS} days):")
    print(daily.to_string(index=False))
    print(f"\n10-day ADL total: {int(daily['net_advances'].sum())} -> {adl_score} points")

    per_stock.to_csv("data/adl_ftse100_per_stock.csv", index=False)
    daily.to_csv("data/adl_ftse100_daily_summary.csv", index=False)
    print("\nSaved to data/adl_ftse100_per_stock.csv and data/adl_ftse100_daily_summary.csv")

    # 20-day new high/low: first test round, FTSE 100 only.
    nhl_table, nhl_pct, nhl_score = compute_new_high_low(INDEX_CONSTITUENTS["^FTSE"])

    new_highs = int((nhl_table["new_high_low_score"] == 1).sum())
    new_lows = int((nhl_table["new_high_low_score"] == -1).sum())
    print(
        f"\nFTSE 100 20-day new highs/lows: {new_highs} new highs, {new_lows} new lows "
        f"(of {len(nhl_table)} stocks) -> {nhl_pct:.2f}% -> {nhl_score} points"
    )

    nhl_table.to_csv("data/new_high_low_ftse100.csv", index=False)
    print("Saved to data/new_high_low_ftse100.csv")

    # Final aggregate: run the full stage (all 3 indicators, summed) on FTSE only.
    ftse = next(i for i in INDEX_UNIVERSE if i.ticker == "^FTSE")
    aggregate = BreadthConfirmationStage().run([ftse])

    print("\nFTSE 100 breadth confirmation - final aggregate (max 20 points):")
    print(aggregate.to_string(index=False))

    aggregate.to_csv("data/breadth_confirmation_aggregate_ftse.csv", index=False)
    print("\nSaved to data/breadth_confirmation_aggregate_ftse.csv")
