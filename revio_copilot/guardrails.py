"""Deterministic post-generation checks. They run on EVERY draft, template or LLM.

Why deterministic: an LLM judge is a good second opinion but an unreliable last line of defence.
Hard business rules (never admit liability, never promise money, never echo an allegation, never
confirm someone is a patient) are cheap to encode as rules and must never depend on a model's mood.
"""
from __future__ import annotations

import re

from .schemas import Analysis, GuardrailReport

LIABILITY = [
    r"\bour fault\b", r"\bwe (?:are|were) (?:legally )?(?:liable|responsible)\b", r"\bwe admit\b",
    r"\bwe were wrong\b", r"\bnegligen\w*", r"\bwe made a mistake\b", r"\bit was our mistake\b",
]
COMPENSATION = [
    r"\brefund\w*", r"\bcompensat\w*", r"\bfree (?:meal|dessert|consultation|of charge)\b", r"\bcomplimentary\b",
    r"\bvoucher\w*", r"\bdiscount\w*", r"\breimburs\w*", r"\bon the house\b", r"\bcredit(?:ed)?\b",
]
DEFENSIVE = [
    r"\bthat(?:'s| is) not true\b", r"\bnever happened\b", r"\bfake review\b", r"\byou(?:'re| are) lying\b",
    r"\bliar\b", r"\bour records show\b", r"\byou should have\b", r"\bwe disagree\b",
]
OVERPROMISE = [r"\bguarantee\w*", r"\b100%", r"\balways\b", r"\bnever again\b"]
# Words that would repeat or confirm a serious allegation in public
ECHO = [
    r"poison\w*", r"hospital\w*", r"vomit\w*", r"allerg\w*", r"lawyer\w*", r"\blegal\w*", r"\bcourt\b", r"\bpolice\b",
    r"\bscam\w*", r"\bcheat\w*", r"\bfraud\w*", r"\bfatal\b", r"\bfir\b", r"\bfssai\b", r"\bviral\b", r"\bmedia\b",
    r"\binstagram\b", r"\btwitter\b", r"\bleak\w*", r"\bracis\w*", r"\bdiscriminat\w*", r"\bharass\w*", r"\bmisdiagnos\w*",
]
PATIENT_CONFIRMATION = [
    r"\byour (?:visit|appointment|treatment|diagnosis|prescription|consultation|report|reports|test|tests|case|condition|records?)\b",
    r"\bwe (?:treated|saw|examined) you\b", r"\bas your (?:doctor|physician)\b", r"\bas (?:a|our) patient\b",
]
HINGLISH_REPLY_MARKERS = {"dhanyavaad", "shukriya", "aapke", "aapko", "aapki", "aap", "hum", "humein", "kripya", "hamare", "hamari"}

_PHONE = re.compile(r"(?<!\d)(?:\+?\d[\d\s-]{7,}\d)(?!\d)")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_EMOJI = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF]")


def _any(patterns: list[str], text: str) -> list[str]:
    return [m.group(0) for p in patterns for m in [re.search(p, text, re.I)] if m]


def validate(text: str, analysis: Analysis, profile: dict) -> GuardrailReport:
    v: list[str] = []
    w: list[str] = []
    t = text or ""
    words = re.findall(r"\b[\w'-]+\b", t)
    serious = analysis.tier in ("critical", "high")

    # structural
    if re.search(r"[{}]|\[(?:name|location|brand)\]|TODO|lorem", t, re.I):
        v.append("unfilled_placeholder")
    if not 15 <= len(words) <= 110:
        v.append(f"length_out_of_range({len(words)} words; allowed 15-110)")
    if profile["signoff"].lower() not in t.lower():
        v.append("missing_signoff")

    # PII: only the business's own contact details may appear
    approved = {profile["contact_email"].lower(), re.sub(r"\D", "", profile["contact_phone"])}
    for e in _EMAIL.findall(t):
        if e.lower() not in approved:
            v.append("pii_email_not_approved")
    for ph in _PHONE.findall(t):
        if re.sub(r"\D", "", ph) not in approved:
            v.append("pii_phone_not_approved")

    # business rules
    if hits := _any(LIABILITY, t):
        v.append(f"admits_liability({hits[0]})")
    if not profile.get("allow_compensation_language") and (hits := _any(COMPENSATION, t)):
        v.append(f"promises_compensation({hits[0]})")
    if hits := _any(DEFENSIVE, t):
        v.append(f"defensive_or_blaming({hits[0]})")
    if hits := _any(OVERPROMISE, t):
        v.append(f"overpromise({hits[0]})")
    for c in profile.get("competitors", []):
        if c.lower() in t.lower():
            v.append(f"mentions_competitor({c})")
    if profile.get("industry") == "healthcare" and (hits := _any(PATIENT_CONFIRMATION, t)):
        v.append(f"confirms_patient_relationship({hits[0]})")

    if serious:
        if hits := _any(ECHO, t):
            v.append(f"echoes_allegation({hits[0]})")
        if profile["contact_email"].lower() not in t.lower() and profile["contact_phone"] not in t:
            v.append("missing_offline_contact_for_serious_case")

    # language / tone
    if analysis.language == "hinglish" and not (HINGLISH_REPLY_MARKERS & {x.lower() for x in words}):
        v.append("language_mismatch(guest wrote Hinglish)")
    if analysis.language == "hi":
        w.append("native_script_reply_needs_llm_or_human")
    if t.count("!") > 2:
        w.append("too_many_exclamation_marks")
    if len(_EMOJI.findall(t)) > 1:
        w.append("too_many_emoji")
    if len([x for x in words if len(x) > 3 and x.isupper()]) > 1:
        w.append("shouting_in_caps")

    # specificity (anti-"templated" check; BrightLocal: ~50% of consumers are put off by generic replies)
    if not serious:
        specific = {"food", "team", "wait", "clean", "value", "ambience", "bill", "billing", "parking", "care", "service",
                    "khana", "safai", "daam", "mahaul", "ilaaj", "staff", "pricing", "access", "turnaround", "environment"}
        if any(a.polarity != "neu" for a in analysis.aspects) and not (specific & {x.lower() for x in words}):
            w.append("generic_reply_templated_risk")

    return GuardrailReport(passed=not v, violations=sorted(set(v)), warnings=w)
