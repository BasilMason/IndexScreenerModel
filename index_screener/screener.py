"""Runs the stages configured in STAGE_WEIGHTS and compiles a single final ranking.

To add a stage: implement a Stage subclass under stages/, register it in
AVAILABLE_STAGES below, and add it to STAGE_WEIGHTS in config.py (weights
across all included stages must sum to 1.0). To exclude a stage, remove it
from STAGE_WEIGHTS - no code changes needed.
"""

import pandas as pd

from .config import INDEX_UNIVERSE, STAGE_WEIGHTS
from .stages.breadth_confirmation import BreadthConfirmationStage
from .stages.ema_trend import EmaTrendStage
from .stages.weighted_returns import WeightedReturnsStage

AVAILABLE_STAGES = {
    stage.name: stage for stage in [WeightedReturnsStage(), EmaTrendStage(), BreadthConfirmationStage()]
}


def run_screen(stage_weights: dict[str, float] = STAGE_WEIGHTS) -> pd.DataFrame:
    """Run each configured stage, merge their scores onto the universe, and compute a weighted final_score."""
    table = pd.DataFrame([{"ticker": i.ticker, "name": i.name, "region": i.region} for i in INDEX_UNIVERSE])

    for stage_name in stage_weights:
        stage = AVAILABLE_STAGES[stage_name]
        table = table.merge(stage.run(INDEX_UNIVERSE), on="ticker", how="left")

    table["final_score"] = sum(
        weight * table[f"{stage_name}_score"] for stage_name, weight in stage_weights.items()
    )
    return table.sort_values("final_score", ascending=False, na_position="last").reset_index(drop=True)


if __name__ == "__main__":
    table = run_screen()

    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", None)
    print(f"\nStages run: {list(STAGE_WEIGHTS)}\n")
    print(table.round(4).to_string())

    table.to_csv("data/screening_results.csv", index=False)
    print("\nSaved to data/screening_results.csv")
