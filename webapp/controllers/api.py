"""JSON REST API over the same model-layer functions the HTML views use.

Exists so future clients (a JS frontend, a scheduled job, another tool) can consume
this data without scraping HTML. Auto-documented at /docs via FastAPI's OpenAPI support.
"""

import json

from fastapi import APIRouter, HTTPException

from index_screener.screener import run_screen
from webapp.services.dashboard_service import get_dashboard_stats
from webapp.services.index_service import get_index_detail

router = APIRouter(prefix="/api")


@router.get("/dashboard")
def api_dashboard():
    return get_dashboard_stats()


@router.get("/screener")
def api_screener():
    # to_json/json.loads (rather than to_dict) turns NaN into proper JSON null.
    return json.loads(run_screen().to_json(orient="records"))


@router.get("/indices/{ticker}")
def api_index_detail(ticker: str):
    detail = get_index_detail(ticker)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"'{ticker}' is not in the index universe")
    return detail
