"""Per-index detail aggregation: cache status, constituents, and breadth confirmation if available."""

import json

import pandas as pd

from index_screener.config import INDEX_UNIVERSE, IndexMeta
from index_screener.constituents import CONSTITUENTS_SOURCE, INDEX_CONSTITUENTS
from index_screener.db import get_cache_summary
from index_screener.stages.breadth_confirmation import compute_breadth


def find_index(ticker: str) -> IndexMeta | None:
    return next((i for i in INDEX_UNIVERSE if i.ticker == ticker), None)


def get_index_detail(ticker: str) -> dict | None:
    """Cache status + constituent breadth detail for one index, or None if ticker isn't in the universe.

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
        table, breadth_pct = compute_breadth(constituent_tickers)
        table = table.sort_values("above_sma_50", ascending=False, na_position="last")
        breadth = {
            "source": CONSTITUENTS_SOURCE.get(ticker, "unknown"),
            "breadth_pct": None if pd.isna(breadth_pct) else round(float(breadth_pct), 2),
            "constituent_count": len(constituent_tickers),
            "scored_count": int(table["above_sma_50"].notna().sum()),
            "stocks": json.loads(table.to_json(orient="records")),
        }

    return {"index": index, "cache": cache_info, "breadth": breadth}
