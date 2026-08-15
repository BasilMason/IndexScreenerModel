"""Shared Jinja2 templates instance, imported by every controller that renders HTML."""

from pathlib import Path

from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
