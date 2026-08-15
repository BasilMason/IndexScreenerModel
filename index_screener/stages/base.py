"""Common interface every screening stage implements."""

from abc import ABC, abstractmethod

import pandas as pd

from ..config import IndexMeta


class Stage(ABC):
    """A single screening step: scores every index in the universe from 0 (worst) to 100 (best)."""

    name: str  # short id; used as the score column name and as the STAGE_WEIGHTS key

    @abstractmethod
    def run(self, universe: list[IndexMeta]) -> pd.DataFrame:
        """Return one row per index: 'ticker', any stage-specific detail columns, and f'{self.name}_score'."""
