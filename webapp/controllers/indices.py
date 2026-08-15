"""Index detail pages and data-refresh actions."""

from fastapi import APIRouter, HTTPException, Request
from starlette.responses import RedirectResponse

from index_screener.constituents import INDEX_CONSTITUENTS
from index_screener.db import get_price_history, populate_tickers
from webapp.services.dashboard_service import get_dashboard_stats
from webapp.services.index_service import find_index, get_index_detail
from webapp.templating import templates

router = APIRouter(prefix="/indices")


@router.get("/{ticker}")
def index_detail(request: Request, ticker: str):
    detail = get_index_detail(ticker)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"'{ticker}' is not in the index universe")
    return templates.TemplateResponse("index_detail.html", {"request": request, **detail})


@router.post("/{ticker}/refresh")
def refresh_index(request: Request, ticker: str):
    """Force-refresh this index's own price series.

    Used two ways: as an htmx-powered inline row refresh from the dashboard
    (returns just the updated `<tr>`), and as a plain form submission from the
    detail page (redirects back, since a full-batch-style page reload is fine
    for a single ticker).
    """
    if find_index(ticker) is None:
        raise HTTPException(status_code=404, detail=f"'{ticker}' is not in the index universe")

    get_price_history(ticker, force_refresh=True)

    if request.headers.get("HX-Request"):
        row = next(r for r in get_dashboard_stats()["index_rows"] if r["ticker"] == ticker)
        return templates.TemplateResponse("partials/index_row.html", {"request": request, "row": row})

    return RedirectResponse(url=f"/indices/{ticker}", status_code=303)


@router.post("/{ticker}/refresh-constituents")
def refresh_constituents(ticker: str):
    """Force-refresh every constituent of this index (can take a while for large indices), then redirect back."""
    tickers = INDEX_CONSTITUENTS.get(ticker)
    if tickers is None:
        raise HTTPException(status_code=404, detail=f"No constituent list is populated for '{ticker}'")

    populate_tickers(tickers, force_refresh=True)
    return RedirectResponse(url=f"/indices/{ticker}", status_code=303)
