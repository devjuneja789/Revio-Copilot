"""Location-level intelligence: what is going wrong WHERE (the part a star average hides)."""
from __future__ import annotations

import pandas as pd

from .schemas import ASPECTS, Result


def results_frame(results: list[Result]) -> pd.DataFrame:
    rows = []
    for r in results:
        rows.append({
            "id": r.review.id, "brand": r.review.brand, "location": r.review.location, "rating": r.review.rating,
            "sentiment": r.analysis.sentiment, "tier": r.analysis.tier, "flags": "|".join(r.analysis.flags),
            "action": r.decision.action, "aspects": "|".join(f"{a.aspect}:{a.polarity}" for a in r.analysis.aspects),
            "language": r.analysis.language, "text": r.review.text, "draft": r.draft.text,
        })
    return pd.DataFrame(rows)


def aspect_net_scores(frame: pd.DataFrame, brand: str | None = None) -> pd.DataFrame:
    """Rows = location, columns = aspect, value = (pos - neg) / mentions in [-1, 1]; NaN if never mentioned."""
    df = frame if brand is None else frame[frame["brand"] == brand]
    acc: dict[tuple[str, str], list[int]] = {}
    for _, row in df.iterrows():
        for token in filter(None, row["aspects"].split("|")):
            aspect, pol = token.split(":")
            acc.setdefault((row["location"], aspect), []).append({"pos": 1, "neg": -1, "neu": 0}[pol])
    table = pd.DataFrame(index=sorted(df["location"].unique()), columns=list(ASPECTS), dtype=float)
    for (loc, aspect), vals in acc.items():
        table.loc[loc, aspect] = sum(vals) / len(vals)
    return table


def location_summary(frame: pd.DataFrame, brand: str | None = None) -> pd.DataFrame:
    df = frame if brand is None else frame[frame["brand"] == brand]
    g = df.groupby("location")
    return pd.DataFrame({
        "reviews": g.size(),
        "avg_rating": g["rating"].mean().round(2),
        "pct_negative": (g["sentiment"].apply(lambda s: (s == "negative").mean()) * 100).round(0),
        "escalations": g["action"].apply(lambda s: (s == "escalate").sum()),
        "auto_publishable": g["action"].apply(lambda s: (s == "auto_publish").sum()),
    })
