"""Run the evaluation and write eval/results.json + eval/errors.csv.

    python eval/run_eval.py                 # offline rules pipeline (no API key needed)
    python eval/run_eval.py --llm           # hybrid pipeline using ANTHROPIC_API_KEY or REVIO_BASE_URL/REVIO_API_KEY/REVIO_MODEL

Tuning policy: the lexicon was tuned on the `dev` split only. `test` was scored once after freezing.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from revio_copilot.data import load_gold  # noqa: E402
from revio_copilot.evaluate import run  # noqa: E402
from revio_copilot.llm import provider_from_env  # noqa: E402
from revio_copilot.pipeline import ReviewCopilot  # noqa: E402


def fmt(m: dict) -> str:
    s, e, a = m["sentiment"], m["escalation"], m["automation"]
    return (
        f"  n={m['n']}\n"
        f"  sentiment      pipeline acc {s['pipeline']['accuracy']:.2f} / macro-F1 {s['pipeline']['macro_f1']:.2f}"
        f"   | stars-only acc {s['stars_only']['accuracy']:.2f} / macro-F1 {s['stars_only']['macro_f1']:.2f}\n"
        f"  aspects        P {m['aspects']['precision']:.2f} R {m['aspects']['recall']:.2f} F1 {m['aspects']['f1']:.2f}"
        f" (polarity acc on matched {m['aspects']['polarity_accuracy_on_matched']:.2f})\n"
        f"  risk flags     P {m['flags']['precision']:.2f} R {m['flags']['recall']:.2f} F1 {m['flags']['f1']:.2f}\n"
        f"  escalation     pipeline recall {e['pipeline']['recall']:.2f} (missed {e['pipeline']['missed']}/{e['pipeline']['gold_positives']}, "
        f"workload {e['pipeline']['workload_pct_of_reviews']}%)"
        f" | stars-only recall {e['stars_only']['recall']:.2f} (missed {e['stars_only']['missed']}, workload {e['stars_only']['workload_pct_of_reviews']}%)\n"
        f"  auto-publish   pipeline {a['pipeline']['auto_publish_pct']}% with {a['pipeline']['unsafe_auto_publishes']} unsafe"
        f" | stars-only {a['stars_only']['auto_publish_pct']}% with {a['stars_only']['unsafe_auto_publishes']} unsafe\n"
        f"  guardrails     draft pass rate {m['guardrails']['draft_pass_rate']:.2f}  warnings {m['guardrails']['warnings']}"
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true", help="use hybrid mode (needs an API key in the environment)")
    args = ap.parse_args()
    llm = provider_from_env() if args.llm else None
    if args.llm and not llm:
        sys.exit("No LLM credentials found. Set ANTHROPIC_API_KEY, or REVIO_BASE_URL + REVIO_API_KEY (+ REVIO_MODEL).")
    copilot = ReviewCopilot(llm=llm)
    df = load_gold()
    import pandas as pd
    stress = pd.read_csv(ROOT / "data" / "reviews_stress.csv", keep_default_na=False)
    df = pd.concat([df, stress], ignore_index=True)
    core = df[df["split"] != "stress"]
    out, errs = {}, []
    for split in ("dev", "test", "all", "stress"):
        sub = core if split == "all" else df[df["split"] == split]
        metrics, err = run(sub, copilot)
        out[split] = metrics
        if split != "all":
            errs.append(err)
        print(f"[{split}] engine={'hybrid:' + llm.name if llm else 'rules'}\n{fmt(metrics)}\n")
    suffix = "hybrid" if llm else "rules"
    (ROOT / "eval" / f"results_{suffix}.json").write_text(json.dumps(out, indent=2))
    pd.concat(errs).to_csv(ROOT / "eval" / f"errors_{suffix}.csv", index=False)
    if copilot.notes:
        print("Degradations:", *copilot.notes, sep="\n  ")


if __name__ == "__main__":
    main()
