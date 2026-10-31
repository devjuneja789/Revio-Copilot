# Technical Approach Report: Revio Copilot

## 1. Scope
Chosen opportunity: an evaluated, guard-railed intelligence core for **Revio** (see the Opportunity Report). The PoC covers analysis, drafting, guardrails, routing, location insights and an evaluation harness. It does **not** cover live review ingestion, publishing back to Google, authentication or multi-tenant storage.

## 2. Architecture
```
 Google Business Profile API / CSV / other platforms
                │  (ingest, dedupe, language ID, PII scrub)
                ▼
        ┌───────────────┐    ┌──────────────────────┐
        │ Rules engine   │    │ LLM analyst (optional)│  JSON, validated against fixed vocab
        │ sentiment,     │    │ nuance, sarcasm,      │
        │ aspects, flags │    │ Hinglish              │
        └──────┬─────────┘    └──────────┬───────────┘
               └───── merge: flags = UNION (recall-first) ─────┐
                                                               ▼
                              Drafter: LLM draft (1 repair) → template fallback
                                                               ▼
                              Deterministic guardrails (every draft)
                                                               ▼
                    Policy: auto_publish | quick_review | escalate (+ audit log)
                                                               ▼
                       Location insights: aspect net score per outlet
```
**Design principle:** the LLM adds nuance; deterministic code owns safety. Anything the system is unsure about goes to a human, never to the public.

## 3. Model choices
| Stage | Choice in PoC | Rationale | Production path |
|---|---|---|---|
| Sentiment, aspects, flags | Rules engine (offline) + optional LLM via a provider-agnostic interface | Rules are free, deterministic and a recall safety net; an LLM handles sarcasm, typos and Hinglish that rules miss | Start with a mid-size hosted LLM with structured output; once ~2-5k real labelled reviews exist, fine-tune a small multilingual encoder (e.g. XLM-R / IndicBERT-class) for cheap high-volume sentiment/aspect tagging, keeping the LLM for hard cases |
| Drafting | LLM with brand profile + hard rules, template fallback | Specific replies need generation; templates guarantee a safe floor | Per-client brand voice examples (few-shot), A/B on human edit rate |
| Guardrails | Regex/rule validators | Hard business rules must not depend on a model's judgement | Add an LLM-as-judge for tone/helpfulness as a second opinion, never as the gate |
| Language | Hinglish marker heuristic | Cheap, good enough to choose reply register | Proper language-ID model; Devanagari drafting via LLM |

The provider layer supports the Anthropic SDK and any OpenAI-compatible endpoint (OpenAI, Groq, Gemini compat, Ollama), so the cost/quality trade-off can be benchmarked with the same evaluation suite. **Live providers were not run against real keys by the author**; they are covered by tests using fake transports.

## 4. Data pipeline (target)
1. **Ingest:** Google Business Profile API (needs OAuth and access approval; not verified here), plus CSV/webhook for other sources. Poll or subscribe per location.
2. **Normalise:** unique review ID, location, rating, timestamp, text; dedupe edits; language ID.
3. **Privacy:** strip reviewer contact data before sending to a model; log only IDs and derived labels; configurable retention.
4. **Analyse → draft → validate → route:** as in §2. Every step writes an audit record (inputs hash, model/prompt version, flags, guardrail result, decision, human action).
5. **Feedback loop:** human edits and approvals become labelled data for evaluation and fine-tuning.
6. **Serve:** FastAPI service plus dashboard (the Streamlit app is the PoC UI).

PoC data: 68 hand-labelled synthetic reviews for two fictional brands (46 dev, 22 test) and 14 stress cases; labels cover sentiment, aspect polarity and risk flags.

## 5. Prompt engineering and injection defence
* **Analysis prompt:** closed output schema (fixed sentiment/aspect/flag vocabularies), "judge the text, not the stars", explicit sarcasm guidance, and a *bias to over-flag* serious categories (a false alarm costs two minutes, a miss costs far more).
* **Response prompt:** brand profile, hard rules (no fault, no money, no competitors, only approved contact details, specific not generic, holding reply only for serious cases), healthcare variant (never confirm patient status).
* **Reviews are untrusted input:** fenced in `<review>` tags, system prompt says to treat them as data; model JSON is validated and out-of-vocabulary values dropped; the rules engine ignores instructions by construction; and guardrails still check the final reply, so a review saying "give me a refund" cannot produce a refund promise.
* **Repair loop:** one retry with the checker's violation list, then fall back to the template.
* Prompts are versioned (`PROMPT_VERSION`) so evaluation results can be tied to a prompt.

## 6. Guardrails (deterministic, on every draft)
Unfilled placeholders; length; sign-off present; no liability admission; no refund/compensation/discount language; no defensive or blaming phrasing; no overpromising; no competitor names; **only the business's own contact details** (no other emails or phone numbers); for serious cases: **no repetition of the allegation** (e.g. "poisoning", "lawyer", "scam") and a mandatory offline contact; healthcare: **never confirm the reviewer is a patient**; Hinglish reviews must get a Hinglish reply; tone warnings (exclamations, emoji, caps) and a "generic reply" warning.

## 7. Publishing policy
| Condition | Action |
|---|---|
| Any critical/high risk flag | **escalate** to manager; holding reply only; never auto-publish |
| Guardrail failure | quick review |
| Star rating contradicts text | quick review |
| Native-script (Devanagari) review in offline mode | quick review |
| Plain negative, mixed, neutral, or under 4 stars | quick review |
| Clearly positive 4-5★, no flags, draft passes | auto-publish |

The last rule was tightened *after* the stress run showed a 3-star "the food made my kid very sick" being classed as neutral and auto-published.

## 8. Evaluation methodology and results
**Protocol:** lexicon tuned on `dev` only; `test` scored once after freezing; `stress` (14 deliberately hard cases) written before it was ever run and reported unfiltered. Baseline: **stars only** (4-5 = positive, 1-2 = negative; escalate 1-2★; auto-reply ≥4★). Reproduce: `python eval/run_eval.py`.

| Split | n | Sentiment macro-F1 (pipeline / stars) | Aspect F1 | Flag recall | Serious missed | Escalation workload (pipeline / stars) | Unsafe auto-publish (pipeline / stars) | Draft guardrail pass |
|---|---|---|---|---|---|---|---|---|
| dev | 46 | 0.88 / 0.65 | 0.90 | 1.00 | 0/8 | 17% / 41% | 0 / 2 | 100% |
| test | 22 | 0.90 / 0.65 | 0.94 | 1.00 | 0/7 | 32% / 55% | 0 / 0 | 100% |
| stress | 14 | 0.89 / 0.46 | 0.79 | 0.56 | 4/8 | 29% / 36% | 1 / 3 | 100% |

**Interpretation**
* On the core set the pipeline matches stars-only recall but sends roughly half as many reviews to managers, and catches the two reviews where 5 stars hid a negative text (R17, C22; both in `dev`).
* That core result is weak evidence: one author wrote patterns and labels, and every flagged core review is 1-star, which flatters the stars-only baseline on recall.
* **The stress set is the realistic signal.** The rules engine misses typos ("fod poisning"), a Hindi-in-Roman-script legal threat ("vakeel"), an indirect press threat ("50k followers") and an understated health claim; it also misreads a sarcastic 5-star as positive and auto-publishes it. 4 of 8 serious cases were *not* escalated; they were still routed to human review (not auto-published) because their text was negative, which is why the policy is built around "not clearly positive → human".
* Guardrail pass rate is 100% for template drafts by construction; it says nothing yet about LLM drafts, which is why the repair/fallback loop and the guardrail tests exist.
* Metrics not yet measurable: hybrid (LLM) accuracy, reply quality as judged by humans, latency and cost per review.

## 9. Execution plan
| Week | Work | Exit criterion |
|---|---|---|
| 1 | Collect and label 500+ real reviews from 2-3 pilot clients (with consent); two annotators; define label guide | Inter-annotator agreement measured; held-out test fixed |
| 2 | Run hybrid mode with 2-3 candidate models; measure flag recall, sentiment/aspect F1, cost, latency | Pick model by evaluation, not by vibes |
| 3 | Add typo-tolerant matching, expanded Hinglish lexicon, sarcasm cases; add LLM-as-judge for tone | Stress-set recall ≥ 0.9 |
| 4 | Ingestion (Google Business Profile), FastAPI service, audit log, approve/edit UI | End-to-end on one pilot location in shadow mode (no publishing) |
| 5-6 | Human-in-the-loop pilot; track edit rate, time-to-reply, misses | Zero unsafe auto-publishes; edit rate < 30% |
| 7+ | Enable auto-publish for clearly positive reviews per client; fine-tune a small encoder from logged edits | Cost per review reduced without recall loss |

## 10. Known limitations and open risks
Synthetic, small, single-annotator data; label ambiguity in places (sentiment "mixed" vs "positive", aspect labelling of "service"); rules lexicon is hand-built and English/Hinglish only; no sarcasm model; live LLM path untested with real credentials; no real ingestion; fictional business profiles. Review text may contain personal data, so a production system needs a data-processing agreement with the model provider, retention limits and consent from clients.

## 11. Repository map
`revio_copilot/` (`triage`, `lexicon`, `llm`, `prompts`, `respond`, `guardrails`, `pipeline`, `insights`, `evaluate`, `cli`), `app.py`, `data/` (gold, stress, profiles), `eval/` (runner, results, error list), `tests/` (18 tests), `docs/`.
