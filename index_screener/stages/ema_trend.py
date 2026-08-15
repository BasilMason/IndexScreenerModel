"""Stage: EMA trend structure.

Computes EMA21, EMA50 (exponential) and SMA200 (simple) from daily close prices,
then scores four trend checks against the last close price. Each check is worth
+POINTS_PER_CHECK if true, 0 if false - except the EMA50 trend check, which is
+POINTS_PER_CHECK if the EMA50 has risen over the lookback window and
-POINTS_PER_CHECK if it has fallen. ema_trend_score is the raw sum of the four
(no rescaling).
"""

import pandas as pd

from ..config import INDEX_UNIVERSE, IndexMeta
from ..db import get_price_history
from .base import Stage

EMA_SHORT_SPAN = 21
EMA_LONG_SPAN = 50
SMA_SPAN = 200
TREND_LOOKBACK_DAYS = 10  # how far back to check the EMA50 has trended up
POINTS_PER_CHECK = 5

CHECK_COLUMNS = [
    "points_price_above_ema21",
    "points_ema21_above_ema50",
    "points_ema50_trend_positive",
    "points_price_above_sma200",
]


def compute_trend_metrics(closes: pd.Series) -> dict:
    """Compute EMA21/EMA50/SMA200 and score the four trend checks against the last close."""
    if len(closes) < SMA_SPAN:
        raise ValueError(f"only {len(closes)} rows of history, need at least {SMA_SPAN}")

    ema21 = closes.ewm(span=EMA_SHORT_SPAN, adjust=False).mean()
    ema50 = closes.ewm(span=EMA_LONG_SPAN, adjust=False).mean()
    sma200 = closes.rolling(window=SMA_SPAN).mean()

    last_close = closes.iloc[-1]
    ema21_last = ema21.iloc[-1]
    ema50_last = ema50.iloc[-1]
    ema50_prior = ema50.iloc[-1 - TREND_LOOKBACK_DAYS]
    sma200_last = sma200.iloc[-1]

    if any(pd.isna(v) for v in [last_close, ema21_last, ema50_last, ema50_prior, sma200_last]):
        raise ValueError("NaN in computed trend metrics")

    points = [
        POINTS_PER_CHECK if last_close > ema21_last else 0,
        POINTS_PER_CHECK if ema21_last > ema50_last else 0,
        POINTS_PER_CHECK if ema50_last > ema50_prior else -POINTS_PER_CHECK,
        POINTS_PER_CHECK if last_close > sma200_last else 0,
    ]

    row = {
        "last_close": last_close,
        "ema_21": ema21_last,
        "ema_50": ema50_last,
        f"ema_50_{TREND_LOOKBACK_DAYS}d_ago": ema50_prior,
        "sma_200": sma200_last,
        **dict(zip(CHECK_COLUMNS, points)),
    }
    row["ema_trend_score"] = sum(points)
    return row


def _nan_metrics() -> dict:
    """Metric columns filled with NaN, used when a ticker's data can't be fetched/validated."""
    metrics = {
        "last_close": float("nan"),
        "ema_21": float("nan"),
        "ema_50": float("nan"),
        f"ema_50_{TREND_LOOKBACK_DAYS}d_ago": float("nan"),
        "sma_200": float("nan"),
    }
    metrics.update({col: float("nan") for col in CHECK_COLUMNS})
    metrics["ema_trend_score"] = float("nan")
    return metrics


class EmaTrendStage(Stage):
    name = "ema_trend"

    def run(self, universe: list[IndexMeta]) -> pd.DataFrame:
        """Iterate the universe, fetch price data, and score each index. Bad data is kept as NaN, not dropped."""
        rows = []
        for index in universe:
            row = {"ticker": index.ticker}
            try:
                closes = get_price_history(index.ticker)["Close"]
                row.update(compute_trend_metrics(closes))
            except Exception as exc:
                print(f"WARNING: {index.ticker} ({index.name}) failed, leaving as NaN: {exc}")
                row.update(_nan_metrics())
            rows.append(row)

        return pd.DataFrame(rows)


if __name__ == "__main__":
    identity = pd.DataFrame([{"ticker": i.ticker, "name": i.name, "region": i.region} for i in INDEX_UNIVERSE])
    table = identity.merge(EmaTrendStage().run(INDEX_UNIVERSE), on="ticker")
    table = table.sort_values("ema_trend_score", ascending=False, na_position="last").reset_index(drop=True)

    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", None)
    print(table.round(4).to_string())

    table.to_csv("data/ema_trend_results.csv", index=False)
    print("\nSaved to data/ema_trend_results.csv")
