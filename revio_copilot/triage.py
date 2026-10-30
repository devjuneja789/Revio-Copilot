"""Offline rules engine: sentiment, aspect-level polarity, risk flags, language, risk tier.

Design notes
- Clause-level scoring (split on punctuation and contrast words) so "good food, but slow service"
  yields both a positive and a negative aspect rather than a washed-out neutral.
- Aspect polarity = polarity of the *nearest* sentiment word inside the clause (falls back to clause,
  then sentence polarity). This is what makes "good food and slow service" come out right.
- Risk flags are regex patterns gated on negativity so "my wife is allergic to nuts and they handled
  it beautifully" does not page a manager.
"""
from __future__ import annotations

import re

from . import lexicon as lx
from .schemas import Analysis, AspectSignal, Review

_TOKEN_RE = re.compile(r"[a-z\u0900-\u097f]+(?:'[a-z]+)?(?:-[a-z]+)?|\d+(?:[.,]\d+)?")
_SENT_SPLIT = re.compile(r"[.!?;\n]+")
_CLAUSE_SPLIT = re.compile(r",|\b(?:but|though|however|lekin|magar|although|yet)\b")
_DEVANAGARI = re.compile(r"[\u0900-\u097f]")
_MAX_PHRASE = max(len(p) for p in lx.PHRASES)


def _norm(text: str) -> str:
    return text.lower().replace("\u2019", "'").replace("\u2018", "'")


def _tokens(clause: str) -> list[str]:
    return _TOKEN_RE.findall(clause)


def _is_negator(tok: str) -> bool:
    return tok in lx.NEGATORS or tok.endswith("n't")


def sentiment_events(tokens: list[str]) -> list[tuple[int, float]]:
    """Return [(token_index, weight)] for every sentiment-bearing word/phrase in a clause."""
    events: list[tuple[int, float]] = []
    n, i = len(tokens), 0
    while i < n:
        # 1) multi-word phrases, longest first
        matched = False
        for L in range(min(_MAX_PHRASE, n - i), 1, -1):
            key = tuple(tokens[i : i + L])
            if key in lx.PHRASES:
                w = lx.PHRASES[key]
                if w != 0.0:
                    events.append((i, w))
                i += L
                matched = True
                break
        if matched:
            continue
        tok = tokens[i]
        base = 0.0
        if tok in lx.POS_STRONG:
            base = lx.STRONG
        elif tok in lx.POS:
            base = lx.NORMAL
        elif tok in lx.NEG_STRONG:
            base = -lx.STRONG
        elif tok in lx.NEG:
            base = -lx.NORMAL
        if base != 0.0:
            window = tokens[max(0, i - 3) : i]
            if i > 0 and tokens[i - 1] in lx.INTENSIFIERS:
                base *= 1.5
            elif i > 0 and tokens[i - 1] in lx.DIMINISHERS:
                base *= 0.5
            hedged = any(t in lx.HEDGES for t in window)
            negated = any(_is_negator(t) for t in window) or (i + 1 < n and tokens[i + 1] in lx.POST_NEGATORS)
            if base > 0 and hedged:
                base = -0.7 * base  # "could be faster", "should be cleaner" => mild complaint
            elif negated:
                base = -0.8 * base
            events.append((i, base))
        i += 1
    return events


def _clauses(text: str) -> list[tuple[int, list[str]]]:
    """[(sentence_index, tokens)] for each clause."""
    out: list[tuple[int, list[str]]] = []
    for s_idx, sent in enumerate(s for s in _SENT_SPLIT.split(text) if s.strip()):
        for clause in _CLAUSE_SPLIT.split(sent):
            toks = _tokens(clause)
            if toks:
                out.append((s_idx, toks))
    return out


def detect_language(text: str) -> str:
    letters = [c for c in text if c.isalpha()]
    if letters and sum(1 for c in letters if _DEVANAGARI.match(c)) / len(letters) > 0.3:
        return "hi"
    toks = _tokens(_norm(text))
    hits = sum(1 for t in toks if t in lx.HINGLISH_MARKERS)
    return "hinglish" if hits >= 2 else "en"


def _signal(weight: float) -> str:
    return "pos" if weight > 0.3 else "neg" if weight < -0.3 else "neu"


def analyze_aspects(clauses: list[tuple[int, list[str]]], sent_scores: dict[int, float]) -> dict[str, float]:
    """aspect -> signed weight (largest-magnitude evidence wins)."""
    found: dict[str, float] = {}
    for s_idx, toks in clauses:
        events = sentiment_events(toks)
        clause_score = sum(w for _, w in events)

        def polarity_for(idx: int) -> float:
            if events:
                nearest = min(events, key=lambda e: (abs(e[0] - idx), e[0]))
                if abs(nearest[0] - idx) <= 5:
                    return nearest[1]
            if abs(clause_score) > 0.01:
                return clause_score
            return sent_scores.get(s_idx, 0.0)

        hits: list[tuple[str, int]] = []
        for i, tok in enumerate(toks):
            for key, aspect in lx.ASPECT_PHRASES.items():
                if tuple(toks[i : i + len(key)]) == key:
                    hits.append((aspect, i))
            if tok == "service":
                nxt = toks[i + 1] if i + 1 < len(toks) else ""
                if nxt == "charge":
                    continue
                near = toks[max(0, i - 3) : i + 4]
                hits.append(("wait_time" if any(t in lx.SPEED_TOKENS for t in near) else "staff", i))
                continue
            for aspect, vocab in lx.ASPECT_TOKENS.items():
                if tok in vocab:
                    hits.append((aspect, i))
        for aspect, i in hits:
            w = polarity_for(i)
            if aspect not in found or abs(w) > abs(found[aspect]):
                found[aspect] = w
    return found


def detect_flags(text: str, negative_mass: float, rating: int) -> list[str]:
    if negative_mass < 0.75 and rating > 2:
        return []  # risk phrases only matter inside a negative review
    t = _norm(text)
    flags = [f for f, pats in lx.FLAG_PATTERNS.items() if any(re.search(p, t) for p in pats)]
    return flags


def risk_tier(flags: list[str], sentiment: str, rating: int) -> str:
    if flags:
        order = ["critical", "high", "medium", "low"]
        return min((lx.TIER_BY_FLAG[f] for f in flags), key=order.index)
    if sentiment == "negative":
        return "medium"
    return "low"


def analyze(review: Review) -> Analysis:
    text = _norm(review.text)
    clauses = _clauses(text)

    pos_mass = neg_mass = 0.0
    neutral_cues = 0
    sent_scores: dict[int, float] = {}
    for s_idx, toks in clauses:
        ev = sentiment_events(toks)
        for _, w in ev:
            if w > 0:
                pos_mass += w
            else:
                neg_mass += -w
        sent_scores[s_idx] = sent_scores.get(s_idx, 0.0) + sum(w for _, w in ev)
        neutral_cues += sum(1 for t in toks if t in lx.NEUTRAL_CUES)
        joined = tuple(toks)
        for ph in lx.NEUTRAL_PHRASES:
            L = len(ph)
            neutral_cues += sum(1 for i in range(len(joined) - L + 1) if joined[i : i + L] == ph)

    total = pos_mass + neg_mass
    minority, majority = min(pos_mass, neg_mass), max(pos_mass, neg_mass)
    all_toks = [t for _, toks in clauses for t in toks]
    has = lambda phrases: any(tuple(all_toks[i : i + len(p)]) == p for p in phrases for i in range(len(all_toks)))
    verdict_neg, verdict_pos = has(lx.VERDICT_NEG), has(lx.VERDICT_POS)
    if verdict_neg and not verdict_pos:
        sentiment, basis = "negative", "explicit negative verdict"
    elif verdict_pos and not verdict_neg and neg_mass < 2.5:
        sentiment, basis = "positive", "explicit positive verdict"
    elif neutral_cues and abs(pos_mass - neg_mass) < 1.5 and max(pos_mass, neg_mass) < 3:
        sentiment, basis = "neutral", "lukewarm wording, small net polarity"
    elif total < 0.75:
        if neutral_cues:
            sentiment = "neutral"
        else:
            sentiment = "positive" if review.rating >= 4 else "negative" if review.rating <= 2 else "neutral"
        basis = "rating prior (little textual signal)"
    elif minority >= 0.75 and minority / majority >= 0.4:
        sentiment, basis = "mixed", "both positive and negative clauses"
    else:
        sentiment = "positive" if pos_mass > neg_mass else "negative"
        basis = "text polarity"

    mismatch = (sentiment == "negative" and review.rating >= 4) or (sentiment == "positive" and review.rating <= 2)
    score = round((pos_mass - neg_mass) / (total + 1.0), 3)

    aspect_weights = analyze_aspects(clauses, sent_scores)
    aspects = [AspectSignal(a, _signal(w)) for a, w in sorted(aspect_weights.items())]

    flags = detect_flags(review.text, neg_mass, review.rating)
    tier = risk_tier(flags, sentiment, review.rating)
    rationale = f"{basis}; +{pos_mass:.1f}/-{neg_mass:.1f}" + ("; rating contradicts text" if mismatch else "")
    return Analysis(
        review_id=review.id,
        sentiment=sentiment,
        score=score,
        aspects=aspects,
        flags=flags,
        tier=tier,
        language=detect_language(review.text),
        rating_text_mismatch=mismatch,
        engine="rules",
        rationale=rationale,
    )
