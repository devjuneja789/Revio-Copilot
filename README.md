# Revio Copilot: an evaluated, guard-railed review-intelligence core for Cynbit

Submission for **Cynbit, AI/ML Engineer Intern: "Identify an AI Opportunity for Cynbit"**.

| Deliverable | Where |
|---|---|
| AI Opportunity Report | [`docs/01_AI_Opportunity_Report.md`](docs/01_AI_Opportunity_Report.md) |
| Proof of concept | this repo (`app.py` Streamlit demo, `revio_copilot/` package, CLI, tests) |
| Technical Approach Report | [`docs/02_Technical_Approach_Report.md`](docs/02_Technical_Approach_Report.md) |

## The opportunity in one paragraph
Cynbit already sells **Revio**, an "AI-first" review-management product, and runs SEO/digital-marketing work for local
businesses. The opportunity I chose is to turn Revio's AI from a reply generator into a **measured, safe decision system**:
read each review (sentiment, aspects, Hinglish), detect legal/health/privacy/fraud/harassment/press threats, draft a
specific on-brand reply, run deterministic guardrails, and route it by risk (auto-publish / quick review / manager
escalation). It also yields per-location insight ("what is going wrong where").

## Run it (offline, no API key needed)
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py                 # interactive demo
python -m revio_copilot.cli --brand restaurant --rating 1 --text "Waited 55 minutes and the waiter was rude"
python eval/run_eval.py              # reproduces the numbers below -> eval/results_rules.json, eval/errors_rules.csv
pytest -q                            # 18 tests
```
**Hybrid mode (LLM + rules safety net):** set `ANTHROPIC_API_KEY` (and `pip install anthropic`), or
`REVIO_BASE_URL` + `REVIO_API_KEY` + `REVIO_MODEL` for any OpenAI-compatible endpoint (OpenAI, Groq, Gemini's compat
endpoint, local Ollama), then `python eval/run_eval.py --llm` or pick "Hybrid" in the app sidebar.

## How it works
```
review ──► analyse ──► draft ──► guardrails ──► decide
           rules (always) + LLM (optional)       auto_publish | quick_review | escalate
           flags = UNION of both (recall-first)
```
* `triage.py`: clause-level sentiment, nearest-word aspect polarity, risk-flag patterns, EN/Hinglish detection.
* `llm.py`, `prompts.py`: provider-agnostic LLM layer; reviews fenced as untrusted data; model JSON validated against fixed vocabularies.
* `respond.py`: composable template drafter (offline fallback and guaranteed-safe holding replies).
* `guardrails.py`: no liability admission, no compensation promises, no unapproved PII, no competitor names, no echo of an allegation,
  clinic replies never confirm someone is a patient, language match, length/tone checks.
* `pipeline.py`: hybrid orchestration, one repair attempt on guardrail failure, then fallback; risk-tiered publishing policy.
* `evaluate.py`, `eval/run_eval.py`: metrics against a **stars-only baseline**.

## Results (offline rules engine; reproduce with `python eval/run_eval.py`)
Data: 68 hand-labelled synthetic reviews for two fictional brands (restaurant chain, clinic), English + Hinglish, split into
`dev` (46, used to tune) and `test` (22, scored once after freezing), plus a separate 14-review `stress` set of hard cases.

| Split | Sentiment macro-F1 (pipeline vs stars-only) | Risk-flag recall | Serious cases missed | Escalation workload (pipeline vs stars-only) | Unsafe auto-publishes (pipeline vs stars-only) |
|---|---|---|---|---|---|
| dev (n=46) | 0.88 vs 0.65 | 1.00 | 0/8 | 17% vs 41% | 0 vs 2 |
| test (n=22) | 0.90 vs 0.65 | 1.00 | 0/7 | 32% vs 55% | 0 vs 0 |
| **stress (n=14)** | 0.89 vs 0.46 | **0.56** | **4/8** | 29% vs 36% | 1 vs 3 |

**Read these numbers carefully.** One person wrote the lexicon, the patterns *and* the labels, and all flagged core reviews are
1-star, so the dev/test results mostly show the plumbing works, not that it generalises. The stress set is the honest
picture: the rules engine misses typos (`fod poisning`), Hindi-in-Roman-script threats (`vakeel`), indirect threats
(`50k followers`) and understated health claims (`made my kid very sick`), and mis-reads sarcasm. Those misses are the argument
for the hybrid design (LLM reads nuance, rules are a recall safety net, humans see anything not clearly positive). The
hybrid path is implemented and unit-tested with fake transports, but **I have not run it against a live model, so I report no
LLM metrics.** The stress run also led me to tighten the publishing policy (only clearly positive 4-5★ reviews can skip a human);
the stress row above is *after* that change (before it: 3 unsafe auto-publishes).

## Known limitations
* Small, synthetic, single-annotator data; some label ambiguity (see `eval/errors_rules.csv`).
* No live review ingestion (Google Business Profile API needs access approval); the demo reads CSV.
* Rules engine is English/Hinglish only; Devanagari reviews are routed to a human.
* Live LLM providers untested with real credentials.
* Business profiles, contact details and brands are fictional.
