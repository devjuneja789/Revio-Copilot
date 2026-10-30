"""Plain dataclasses shared across the pipeline (no heavy dependencies)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional

SENTIMENTS = ("positive", "neutral", "negative", "mixed")
POLARITIES = ("pos", "neu", "neg")
ASPECTS = ("quality", "staff", "wait_time", "cleanliness", "price", "ambience", "billing", "access", "safety")
FLAGS = (
    "health_safety",
    "legal_threat",
    "discrimination_harassment",
    "fraud_billing",
    "privacy",
    "viral_press",
)
TIERS = ("critical", "high", "medium", "low")
ACTIONS = ("auto_publish", "quick_review", "escalate")


@dataclass
class Review:
    id: str
    text: str
    rating: int
    brand: str = "restaurant"
    location: str = ""
    author: Optional[str] = None


@dataclass
class AspectSignal:
    aspect: str
    polarity: str  # pos | neu | neg


@dataclass
class Analysis:
    review_id: str
    sentiment: str
    score: float  # -1 .. +1 text-derived polarity
    aspects: list[AspectSignal] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    tier: str = "low"
    language: str = "en"  # en | hinglish | hi
    rating_text_mismatch: bool = False
    engine: str = "rules"
    rationale: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class GuardrailReport:
    passed: bool
    violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class Draft:
    text: str
    language: str
    source: str  # template | llm | llm_repaired
    guardrails: GuardrailReport


@dataclass
class Decision:
    action: str  # auto_publish | quick_review | escalate
    reason: str


@dataclass
class Result:
    review: Review
    analysis: Analysis
    draft: Draft
    decision: Decision
