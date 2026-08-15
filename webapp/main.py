"""IndexScreenerModel web app: FastAPI (controllers) + Jinja2 (views) over the index_screener package (model).

Run with: uvicorn webapp.main:app --reload
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from webapp.controllers import api, dashboard, indices, screener

app = FastAPI(title="Index Screener")

app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

app.include_router(dashboard.router)
app.include_router(screener.router)
app.include_router(indices.router)
app.include_router(api.router)
