"""Runs the screening pipeline and displays ranked results."""

import json

from fastapi import APIRouter, Request

from index_screener.config import STAGE_WEIGHTS
from index_screener.db import populate_tickers
from index_screener.screener import SCREENING_UNIVERSE, run_screen
from webapp.templating import templates

router = APIRouter()


def _context(request: Request) -> dict:
    table = run_screen()
    # Show the ranking result (identity + each stage's score + final_score), not every
    # intermediate calculation column - those stay available in the CSV exports for review.
    score_cols = [c for c in table.columns if c.endswith("_score") and c != "final_score"]
    display = table[["ticker", "name", "region", *score_cols, "final_score"]].round(2)
    return {
        "request": request,
        "rows": json.loads(display.to_json(orient="records")),  # NaN -> null, not the string "nan"
        "score_cols": score_cols,
        "active_stages": list(STAGE_WEIGHTS),
    }


@router.get("/screener")
def screener(request: Request):
    return templates.TemplateResponse("screener.html", _context(request))


@router.post("/screener/refresh")
def refresh_and_rerun(request: Request):
    """Force-refresh every index currently being screened from Yahoo Finance, then re-run (htmx partial)."""
    populate_tickers([i.ticker for i in SCREENING_UNIVERSE], force_refresh=True)
    return templates.TemplateResponse("partials/screener_table.html", _context(request))
