"""Per-index detail aggregation: cache status, constituents, and breadth confirmation if available."""

import json

import pandas as pd

from index_screener.config import INDEX_UNIVERSE, IndexMeta
from index_screener.constituents import CONSTITUENTS_SOURCE, INDEX_CONSTITUENTS
from index_screener.db import get_cache_summary
from index_screener.stages.breadth_confirmation import (
    compute_adl,
    compute_breadth,
    compute_new_high_low,
    score_breadth,
)


def find_index(ticker: str) -> IndexMeta | None:
    return next((i for i in INDEX_UNIVERSE if i.ticker == ticker), None)


def get_index_detail(ticker: str) -> dict | None:
    """Cache status + constituent breadth confirmation detail for one index, or None if not in the universe.

    Values are plain Python types (not numpy/pandas), so this dict is safe for
    both Jinja2 templates and direct JSON serialization by the REST API.
    """
    index = find_index(ticker)
    if index is None:
        return None

    cache = get_cache_summary()
    own_cache = cache[cache["ticker"] == ticker] if not cache.empty else cache
    cache_info = None
    if not own_cache.empty:
        row = own_cache.iloc[0]
        cache_info = {
            "first_date": row["first_date"],
            "last_date": row["last_date"],
            "rows": int(row["rows"]),
            "is_stale": bool(row["is_stale"]),
        }

    constituent_tickers = INDEX_CONSTITUENTS.get(ticker)
    breadth = None
    if constituent_tickers:
        sma_table, breadth_pct = compute_breadth(constituent_tickers)
        _, daily_adl, adl_score = compute_adl(constituent_tickers)
        nhl_table, nhl_pct, nhl_score = compute_new_high_low(constituent_tickers)
        sma50_score = score_breadth(breadth_pct)

        # Merge the SMA50 and new-high/low per-stock results into one table for display;
        # the full per-day ADL detail (100 stocks x 10 days) stays CSV-only - too wide for the UI.
        stocks = sma_table.merge(nhl_table[["ticker", "new_high_low_score"]], on="ticker")
        stocks = stocks.sort_values("above_sma_50", ascending=False, na_position="last")

        breadth = {
            "source": CONSTITUENTS_SOURCE.get(ticker, "unknown"),
            "constituent_count": len(constituent_tickers),
            "scored_count": int(sma_table["above_sma_50"].notna().sum()),
            "breadth_pct": None if pd.isna(breadth_pct) else round(float(breadth_pct), 2),
            "sma50_score": sma50_score,
            "adl_total": int(daily_adl["net_advances"].sum()),
            "adl_score": adl_score,
            "new_high_low_pct": None if pd.isna(nhl_pct) else round(float(nhl_pct), 2),
            "new_high_low_score": nhl_score,
            "total_score": sma50_score + adl_score + nhl_score,
            "stocks": json.loads(stocks.to_json(orient="records")),
        }

    return {"index": index, "cache": cache_info, "breadth": breadth}
