"""Dashboard: summary stats and per-index cache status."""

from fastapi import APIRouter, Request

from webapp.services.dashboard_service import get_dashboard_stats
from webapp.templating import templates

router = APIRouter()


@router.get("/")
def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request, "stats": get_dashboard_stats()})
