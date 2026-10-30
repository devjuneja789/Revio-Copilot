"""Template drafter: the offline fallback that also guarantees a safe holding reply for serious cases.

Templates are composed from reusable pieces (specific praise / specific apology / offline hand-off)
rather than monolithic canned replies, so each draft references what the guest actually mentioned.
"""
from __future__ import annotations

import zlib

from .schemas import Analysis, Review

POS_PHRASE = {
    "hospitality": {
        "quality": "the food", "staff": "our team", "wait_time": "the quick service", "cleanliness": "how clean the place felt",
        "price": "the value", "ambience": "the ambience", "billing": "the smooth billing", "access": "how easy we were to get to",
    },
    "healthcare": {
        "quality": "the quality of care", "staff": "our team", "wait_time": "the quick turnaround",
        "cleanliness": "our clean, hygienic space", "price": "the pricing", "ambience": "the clinic environment",
        "billing": "the smooth billing", "access": "the easy access",
    },
}
NEG_PHRASE = {
    "hospitality": {
        "quality": "the food not meeting your expectations", "staff": "the service from our team", "wait_time": "the long wait",
        "cleanliness": "the cleanliness not being up to standard", "price": "the pricing not feeling like good value",
        "ambience": "the ambience not working for you", "billing": "the confusion around the bill", "access": "the trouble with parking or booking",
    },
    "healthcare": {
        "quality": "your experience not meeting expectations", "staff": "the interaction with our team", "wait_time": "the long wait",
        "cleanliness": "the cleanliness not being up to standard", "price": "the pricing", "ambience": "the waiting environment",
        "billing": "the billing experience", "access": "the difficulty with booking or access",
    },
}
POS_HI = {"quality": "khana", "staff": "hamari team ka vyavhaar", "wait_time": "tez service", "cleanliness": "safai",
          "price": "daam", "ambience": "mahaul", "billing": "billing", "access": "location"}
POS_HI_CLINIC = {**POS_HI, "quality": "ilaaj"}


def _pick(options: list[str], key: str) -> str:
    return options[zlib.crc32(key.encode()) % len(options)]


def _join(items: list[str], conj: str = "and") -> str:
    return f" {conj} ".join(items[:2])


def _aspects(analysis: Analysis, polarity: str) -> list[str]:
    return [a.aspect for a in analysis.aspects if a.polarity == polarity and a.aspect != "safety"]


def _handoff(profile: dict, hi: bool = False) -> str:
    if hi:
        return (f"Kripya {profile['contact_email']} par ya {profile['contact_phone']} par likhiye taaki "
                f"{profile['manager_role_hi']} aapse seedha baat kar sakein.")
    return (f"Please contact {profile['manager_role']} directly at {profile['contact_email']} "
            f"or {profile['contact_phone']} so we can look into this properly.")


def _sign(profile: dict, review: Review) -> str:
    loc = f", {review.location}" if review.location else ""
    return f"— {profile['signoff']}{loc}"


def draft_template(review: Review, analysis: Analysis, profile: dict) -> str:
    ind = profile["industry"]
    hospitality = ind == "hospitality"
    sign = _sign(profile, review)
    pos = [POS_PHRASE[ind][a] for a in _aspects(analysis, "pos") if a in POS_PHRASE[ind]]
    neg = [NEG_PHRASE[ind][a] for a in _aspects(analysis, "neg") if a in NEG_PHRASE[ind]]
    seed = review.id + review.text

    # ---- Hinglish: mirror the guest's register (India-specific differentiator vs. English-first tools)
    if analysis.language in ("hinglish", "hi"):
        hi_map = POS_HI if hospitality else POS_HI_CLINIC
        pos_hi = [hi_map[a] for a in _aspects(analysis, "pos") if a in hi_map]
        if analysis.tier in ("critical", "high"):
            return (f"Humein is baare mein jaankar bahut khed hai aur hum ise poori gambhirta se le rahe hain. "
                    f"{_handoff(profile, hi=True)} {sign}")
        if analysis.sentiment == "positive":
            what = _join(pos_hi, "aur") if pos_hi else "hamari service"
            return (f"Dhanyavaad aapke review ke liye! Humein khushi hai ki {what} aapko pasand aaya. "
                    f"Hum aapka dobara swagat karne ke liye taiyaar hain. {sign}")
        return (f"Aapko jo pareshani hui uske liye hum kshama chahte hain. Hum aapke feedback ko gambhirta se le rahe hain "
                f"aur apni team ke saath share kar rahe hain. {_handoff(profile, hi=True)} {sign}")

    # ---- Serious cases: holding reply only. No facts, no fault, no money, no echo of the allegation.
    if analysis.tier in ("critical", "high"):
        flags = analysis.flags
        if "health_safety" in flags:
            lead = ("We're very sorry to hear this and hope you're feeling better. We take every concern like this extremely seriously."
                    if hospitality else
                    "We take concerns about care extremely seriously. For privacy reasons we can't discuss any individual case in a public forum.")
        elif "privacy" in flags:
            lead = ("We take privacy extremely seriously and want to look into this right away."
                    + ("" if hospitality else " For privacy reasons we can't discuss individual records in a public forum."))
        elif "discrimination_harassment" in flags:
            lead = "Treating everyone with respect is non-negotiable for us, and we're sorry to hear this."
        elif "fraud_billing" in flags:
            lead = "We're sorry about the concern with your bill and would like to review the details properly."
        else:
            lead = "We're sorry to hear about this experience and are treating it as a priority."
        return f"{lead} {_handoff(profile)} {sign}"

    # ---- Positive
    if analysis.sentiment == "positive":
        opener = _pick(["Thank you for the kind words!", "Thank you so much for taking the time to review us!",
                        "Thank you for the lovely feedback!"], seed)
        body = f"We're delighted that {_join(pos)} stood out." if pos else "We're delighted you had a good experience."
        close = ("We look forward to welcoming you again." if hospitality else "Wishing you good health and happy days ahead.")
        return f"{opener} {body} {close} {sign}"

    # ---- Neutral / mixed
    if analysis.sentiment in ("neutral", "mixed"):
        if pos and neg:
            body = f"We're glad {_join(pos)} worked for you, and we're sorry about {_join(neg)}."
        elif neg:
            body = f"We're sorry about {_join(neg)}."
        elif pos:
            body = f"We're glad {_join(pos)} worked for you."
        else:
            body = "We appreciate you taking the time to share your experience."
        return (f"Thank you for the honest feedback. {body} We've shared this with our {review.location or 'local'} team "
                f"so we can do better. You can also write to {profile['contact_email']}. {sign}")

    # ---- Negative (medium tier): service recovery without admitting liability or promising money
    what = _join(neg) if neg else "your experience"
    return (f"We're sorry about {what}. That isn't the experience we want anyone to have, and we've shared your feedback with the "
            f"{review.location or 'local'} team. {_handoff(profile)} {sign}")
