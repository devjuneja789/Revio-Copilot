from __future__ import annotations

from pathlib import Path

import pandas as pd

from .schemas import Review

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def load_gold(path: Path | None = None) -> pd.DataFrame:
    return pd.read_csv(path or DATA_DIR / "reviews_gold.csv", keep_default_na=False)


def row_to_review(row) -> Review:
    return Review(id=str(row["id"]), text=str(row["text"]), rating=int(row["rating"]), brand=str(row.get("brand", "restaurant")),
                  location=str(row.get("location", "")))


def reviews_from_df(df: pd.DataFrame) -> list[Review]:
    return [row_to_review(r) for _, r in df.iterrows()]
