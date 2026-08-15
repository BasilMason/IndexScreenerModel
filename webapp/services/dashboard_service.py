"""Aggregates data across the model layer (config, db, constituents, screener) for the dashboard view."""

from index_screener.config import INDEX_UNIVERSE, STAGE_WEIGHTS
from index_screener.constituents import INDEX_CONSTITUENTS
from index_screener.db import get_cache_summary
from index_screener.screener import AVAILABLE_STAGES


def get_dashboard_stats() -> dict:
    """Summary stats and per-index cache status for the dashboard."""
    cache = get_cache_summary()
    cache_by_ticker = cache.set_index("ticker").to_dict("index") if not cache.empty else {}

    index_rows = []
    for index in INDEX_UNIVERSE:
        info = cache_by_ticker.get(index.ticker)
        index_rows.append(
            {
                "ticker": index.ticker,
                "name": index.name,
                "region": index.region,
                "cached": info is not None,
                "last_date": info["last_date"] if info else None,
                "rows": int(info["rows"]) if info else 0,
                "is_stale": bool(info["is_stale"]) if info else True,
                "has_constituents": index.ticker in INDEX_CONSTITUENTS,
                "constituent_count": len(INDEX_CONSTITUENTS.get(index.ticker, [])),
            }
        )

    cached_count = sum(1 for r in index_rows if r["cached"])
    stale_count = sum(1 for r in index_rows if r["cached"] and r["is_stale"])
    active_stages = list(STAGE_WEIGHTS)

    return {
        "universe_count": len(INDEX_UNIVERSE),
        "cached_index_count": cached_count,
        "stale_index_count": stale_count,
        "total_tickers_cached": int(cache["ticker"].nunique()) if not cache.empty else 0,
        "total_price_rows": int(cache["rows"].sum()) if not cache.empty else 0,
        "indices_with_constituents": len(INDEX_CONSTITUENTS),
        "available_stages": list(AVAILABLE_STAGES),
        "active_stages": active_stages,
        "inactive_stages": [s for s in AVAILABLE_STAGES if s not in active_stages],
        "index_rows": index_rows,
    }
