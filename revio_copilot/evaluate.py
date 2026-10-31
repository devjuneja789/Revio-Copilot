"""Evaluation harness: compares the pipeline with the 'stars only' status quo on the hand-labelled set.

Metrics that matter for this product (in priority order)
1. escalation recall      - do we ever miss a legal / health / privacy / fraud / harassment / press threat?
2. unsafe auto-publish    - how many reviews would be auto-replied that a human should have seen? (target: 0)
3. automation rate        - share of reviews that need no human time at all
4. sentiment macro-F1 and aspect F1 - analytics quality
5. guardrail pass rate    - are the drafts safe to post?
"""
from __future__ import annotations

from collections import Counter

import pandas as pd

from .pipeline import ReviewCopilot
from .schemas import SENTIMENTS, Result
from .data import reviews_from_df


def _prf(tp: int, fp: int, fn: int) -> dict:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return {"precision": round(p, 3), "recall": round(r, 3), "f1": round(f, 3)}


def macro_f1(y_true: list[str], y_pred: list[str]) -> float:
    scores = []
    for lab in sorted(set(y_true)):  # classes with support only
        tp = sum(t == lab and p == lab for t, p in zip(y_true, y_pred))
        fp = sum(t != lab and p == lab for t, p in zip(y_true, y_pred))
        fn = sum(t == lab and p != lab for t, p in zip(y_true, y_pred))
        scores.append(_prf(tp, fp, fn)["f1"])
    return round(sum(scores) / len(scores), 3) if scores else 0.0


def _star_sentiment(r: int) -> str:
    return "positive" if r >= 4 else "negative" if r <= 2 else "neutral"


def _set(s: str) -> set[str]:
    return set(filter(None, str(s).split("|")))


def evaluate(df: pd.DataFrame, results: list[Result]) -> dict:
    by_id = {r.review.id: r for r in results}
    rows = [(row, by_id[str(row["id"])]) for _, row in df.iterrows()]
    n = len(rows)

    # sentiment
    gold_s = [r["sentiment"] for r, _ in rows]
    pred_s = [res.analysis.sentiment for _, res in rows]
    star_s = [_star_sentiment(int(r["rating"])) for r, _ in rows]
    sentiment = {
        "pipeline": {"accuracy": round(sum(g == p for g, p in zip(gold_s, pred_s)) / n, 3), "macro_f1": macro_f1(gold_s, pred_s)},
        "stars_only": {"accuracy": round(sum(g == p for g, p in zip(gold_s, star_s)) / n, 3), "macro_f1": macro_f1(gold_s, star_s)},
    }

    # aspects (name-level micro P/R/F1, then polarity accuracy on correctly found aspects)
    tp = fp = fn = pol_ok = pol_n = 0
    for r, res in rows:
        gold = {a.split(":")[0]: a.split(":")[1] for a in _set(r["aspects"])}
        pred = {a.aspect: a.polarity for a in res.analysis.aspects}
        tp += len(gold.keys() & pred.keys()); fp += len(pred.keys() - gold.keys()); fn += len(gold.keys() - pred.keys())
        for k in gold.keys() & pred.keys():
            pol_n += 1; pol_ok += gold[k] == pred[k]
    aspects = {**_prf(tp, fp, fn), "polarity_accuracy_on_matched": round(pol_ok / pol_n, 3) if pol_n else 0.0}

    # risk flags
    ftp = ffp = ffn = 0
    per_flag: dict[str, Counter] = {}
    for r, res in rows:
        g, p = _set(r["flags"]), set(res.analysis.flags)
        ftp += len(g & p); ffp += len(p - g); ffn += len(g - p)
        for f in g | p:
            c = per_flag.setdefault(f, Counter())
            c["tp"] += f in g and f in p; c["fp"] += f in p and f not in g; c["fn"] += f in g and f not in p
    flags = {**_prf(ftp, ffp, ffn), "per_flag": {f: {**_prf(c["tp"], c["fp"], c["fn"]), "support": c["tp"] + c["fn"]} for f, c in sorted(per_flag.items())}}

    # escalation: the metric that protects the business
    g_esc = [bool(_set(r["flags"])) for r, _ in rows]
    p_esc = [res.analysis.tier in ("critical", "high") for _, res in rows]
    star_esc = [int(r["rating"]) <= 2 for r, _ in rows]

    def esc(pred):
        tp_ = sum(g and p for g, p in zip(g_esc, pred)); fp_ = sum(p and not g for g, p in zip(g_esc, pred)); fn_ = sum(g and not p for g, p in zip(g_esc, pred))
        return {**_prf(tp_, fp_, fn_), "missed": fn_, "workload_pct_of_reviews": round(100 * sum(pred) / n, 1), "gold_positives": sum(g_esc)}

    # automation safety
    unsafe = lambda r: bool(_set(r["flags"])) or r["sentiment"] == "negative"
    auto_rows = [(r, res) for r, res in rows if res.decision.action == "auto_publish"]
    star_auto = [r for r, _ in rows if int(r["rating"]) >= 4]
    automation = {
        "pipeline": {"auto_publish_pct": round(100 * len(auto_rows) / n, 1), "unsafe_auto_publishes": sum(unsafe(r) for r, _ in auto_rows)},
        "stars_only": {"auto_publish_pct": round(100 * len(star_auto) / n, 1), "unsafe_auto_publishes": sum(unsafe(r) for r in star_auto)},
        "actions": dict(Counter(res.decision.action for _, res in rows)),
    }

    # drafts
    guard = {
        "draft_pass_rate": round(sum(res.draft.guardrails.passed for _, res in rows) / n, 3),
        "violations": dict(Counter(v.split("(")[0] for _, res in rows for v in res.draft.guardrails.violations)),
        "warnings": dict(Counter(w for _, res in rows for w in res.draft.guardrails.warnings)),
    }
    return {"n": n, "sentiment": sentiment, "aspects": aspects, "flags": flags,
            "escalation": {"pipeline": esc(p_esc), "stars_only": esc(star_esc)}, "automation": automation, "guardrails": guard}


def errors_frame(df: pd.DataFrame, results: list[Result]) -> pd.DataFrame:
    """Every row where sentiment or flags disagree with the gold label, for error analysis."""
    by_id = {r.review.id: r for r in results}
    out = []
    for _, r in df.iterrows():
        res = by_id[str(r["id"])]
        g_flags, p_flags = _set(r["flags"]), set(res.analysis.flags)
        if r["sentiment"] != res.analysis.sentiment or g_flags != p_flags:
            out.append({"id": r["id"], "split": r["split"], "text": r["text"], "rating": r["rating"],
                        "gold_sentiment": r["sentiment"], "pred_sentiment": res.analysis.sentiment,
                        "gold_flags": "|".join(sorted(g_flags)), "pred_flags": "|".join(sorted(p_flags)), "rationale": res.analysis.rationale})
    return pd.DataFrame(out)


def run(df: pd.DataFrame, copilot: ReviewCopilot | None = None) -> tuple[dict, pd.DataFrame]:
    copilot = copilot or ReviewCopilot()
    results = copilot.process_many(reviews_from_df(df))
    return evaluate(df, results), errors_frame(df, results)
