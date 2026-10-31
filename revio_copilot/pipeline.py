"""End-to-end pipeline: analyse -> draft -> guardrail -> decide.

Modes
- rules   : fully offline, deterministic.
- hybrid  : LLM reads the review (nuance, sarcasm, Hinglish) and drafts the reply; the rules engine runs in
            parallel as a safety net. Risk flags are the UNION of both (recall-first), and every draft must
            pass the same deterministic guardrails. Any LLM failure degrades silently to the offline path.
"""
from __future__ import annotations

from typing import Optional

from . import prompts
from .guardrails import validate
from .llm import LLMError, LLMProvider, extract_json
from .profiles import load_profiles
from .respond import draft_template
from .schemas import ASPECTS, FLAGS, POLARITIES, SENTIMENTS, Analysis, AspectSignal, Decision, Draft, Result, Review
from .triage import analyze as rules_analyze
from .triage import risk_tier


def decide(analysis: Analysis, draft: Draft, rating: int = 5) -> Decision:
    """Risk-tiered publishing policy. Serious cases are NEVER auto-published.

    Fail-safe rule added after the stress run: only clearly positive 4-5 star reviews skip a human. Neutral or
    low-star reviews are where missed risk hides (e.g. "the food made my kid very sick", 3 stars), and reviewing
    them costs seconds.
    """
    if analysis.tier in ("critical", "high"):
        return Decision("escalate", f"{analysis.tier} risk: {', '.join(analysis.flags)}; manager sign-off required")
    if not draft.guardrails.passed:
        return Decision("quick_review", "draft failed guardrails: " + ", ".join(draft.guardrails.violations))
    if analysis.rating_text_mismatch:
        return Decision("quick_review", "star rating contradicts the text (sarcasm or mis-click?)")
    if analysis.language == "hi":
        return Decision("quick_review", "native-script review: needs LLM drafting or a human")
    if analysis.tier == "medium":
        return Decision("quick_review", "negative review: service-recovery reply needs a human glance")
    if analysis.sentiment == "mixed":
        return Decision("quick_review", "mixed review: confirm the reply addresses the complaint")
    if analysis.sentiment != "positive" or rating < 4:
        return Decision("quick_review", "neutral or low-star review: not clearly positive, so a human confirms")
    return Decision("auto_publish", "clearly positive 4-5 star review, no risk flags, draft passed all guardrails")


def parse_llm_analysis(raw: str, review: Review, rules: Analysis) -> Analysis:
    """Validate model JSON against our vocabularies; anything outside them is dropped, never trusted."""
    data = extract_json(raw)
    sentiment = data.get("sentiment") if data.get("sentiment") in SENTIMENTS else rules.sentiment
    aspects = []
    for a in data.get("aspects", []) or []:
        if isinstance(a, dict) and a.get("aspect") in ASPECTS and a.get("polarity") in POLARITIES:
            aspects.append(AspectSignal(a["aspect"], a["polarity"]))
    llm_flags = [f for f in (data.get("flags") or []) if f in FLAGS]
    flags = sorted(set(llm_flags) | set(rules.flags))  # recall-first union
    language = data.get("language") if data.get("language") in ("en", "hinglish", "hi") else rules.language
    mismatch = (sentiment == "negative" and review.rating >= 4) or (sentiment == "positive" and review.rating <= 2)
    return Analysis(
        review_id=review.id, sentiment=sentiment, score=rules.score, aspects=aspects or rules.aspects, flags=flags,
        tier=risk_tier(flags, sentiment, review.rating), language=language, rating_text_mismatch=mismatch,
        engine="hybrid", rationale=str(data.get("rationale", ""))[:200],
    )


class ReviewCopilot:
    def __init__(self, profiles: Optional[dict] = None, llm: Optional[LLMProvider] = None):
        self.profiles = profiles or load_profiles()
        self.llm = llm
        self.notes: list[str] = []  # degradations (LLM errors etc.) surfaced to the UI

    # -- analysis
    def analyze(self, review: Review) -> Analysis:
        rules = rules_analyze(review)
        if not self.llm:
            return rules
        try:
            raw = self.llm.complete(prompts.ANALYSIS_SYSTEM, prompts.analysis_user(review), json_mode=True, max_tokens=400)
            return parse_llm_analysis(raw, review, rules)
        except LLMError as e:
            self.notes.append(f"{review.id}: LLM analysis failed, used rules ({e})")
            return rules

    # -- drafting
    def draft(self, review: Review, analysis: Analysis) -> Draft:
        profile = self.profiles[review.brand]
        template = draft_template(review, analysis, profile)
        if not self.llm:
            return Draft(template, analysis.language, "template", validate(template, analysis, profile))
        system = prompts.RESPONSE_SYSTEM.format(
            name=profile["name"], industry=profile["industry"], voice=profile["voice"], signoff=profile["signoff"],
            email=profile["contact_email"], phone=profile["contact_phone"],
            healthcare_rule=prompts.HEALTHCARE_RULE if profile["industry"] == "healthcare" else "",
        )
        try:
            text = self.llm.complete(system, prompts.response_user(review, analysis), max_tokens=300).strip()
            report = validate(text, analysis, profile)
            source = "llm"
            if not report.passed:  # one repair attempt, with the checker's feedback
                text = self.llm.complete(
                    system, prompts.REPAIR_USER.format(violations="; ".join(report.violations), draft=text), max_tokens=300
                ).strip()
                report, source = validate(text, analysis, profile), "llm_repaired"
            if report.passed:
                return Draft(text, analysis.language, source, report)
            self.notes.append(f"{review.id}: LLM draft still failing guardrails, fell back to template")
        except LLMError as e:
            self.notes.append(f"{review.id}: LLM drafting failed, used template ({e})")
        return Draft(template, analysis.language, "template", validate(template, analysis, profile))

    def process(self, review: Review) -> Result:
        analysis = self.analyze(review)
        draft = self.draft(review, analysis)
        return Result(review, analysis, draft, decide(analysis, draft, review.rating))

    def process_many(self, reviews: list[Review]) -> list[Result]:
        return [self.process(r) for r in reviews]
