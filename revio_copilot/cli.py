"""python -m revio_copilot.cli --brand restaurant --rating 1 --text "..." [--llm] [--location "C-Scheme"]"""
import argparse
import json
import sys

from .llm import provider_from_env
from .pipeline import ReviewCopilot
from .schemas import Review


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="revio_copilot")
    ap.add_argument("--text", required=True)
    ap.add_argument("--rating", type=int, default=3)
    ap.add_argument("--brand", choices=["restaurant", "clinic"], default="restaurant")
    ap.add_argument("--location", default="Malviya Nagar")
    ap.add_argument("--llm", action="store_true", help="hybrid mode; needs ANTHROPIC_API_KEY or REVIO_BASE_URL+REVIO_API_KEY")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    llm = provider_from_env() if a.llm else None
    if a.llm and not llm:
        sys.exit("No LLM credentials in the environment (see README).")
    cp = ReviewCopilot(llm=llm)
    res = cp.process(Review("cli", a.text, a.rating, a.brand, a.location))
    if a.json:
        print(json.dumps({"analysis": res.analysis.to_dict(), "draft": res.draft.text, "guardrails": vars(res.draft.guardrails),
                          "decision": vars(res.decision)}, indent=2, default=str))
        return
    an = res.analysis
    print(f"sentiment : {an.sentiment}  (tier={an.tier}, language={an.language}, engine={an.engine})")
    print(f"aspects   : {', '.join(f'{x.aspect}:{x.polarity}' for x in an.aspects) or '-'}")
    print(f"flags     : {', '.join(an.flags) or '-'}")
    print(f"decision  : {res.decision.action}  - {res.decision.reason}")
    print(f"guardrails: {'PASS' if res.draft.guardrails.passed else 'FAIL ' + str(res.draft.guardrails.violations)}")
    print(f"\n{res.draft.text}")


if __name__ == "__main__":
    main()
