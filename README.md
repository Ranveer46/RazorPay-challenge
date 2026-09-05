# AI Revenue Recovery Agent (Prototype)

Detects revenue at risk, diagnoses the root cause, picks a **bounded, rule-driven**
intervention, executes a simulated recovery workflow, and proves with numbers
and an audit trail how much money it recovered — across four leak categories:

1. Payment failure / degradation (declines, timeouts, fraud holds)
2. Checkout abandonment
3. Failed subscription renewal (dunning)
4. Overdue B2B receivables (invoice chasing, promise-to-pay)

This is a hackathon prototype: real end-to-end loop, real numbers on synthetic
data, real audit trail. Nothing touches a live payment gateway or messaging
provider.

## The core loop

```
Detect -> Diagnose -> Decide (policy) -> Act (simulated) -> Log (audit) -> Measure
```

- **Detect / Diagnose / Decide / Guardrails are plain, deterministic Python.**
  Same inputs always produce the same intervention — that's what makes this
  auditable. No LLM call ever decides *whether* or *how much* to act.
- **The LLM is used for exactly two things**: classifying ambiguous free-text
  abandonment reasons, and writing the actual customer-facing message
  (English or Hinglish). Every prompt + response is logged into the audit
  trail. If no API key is configured, both fall back to deterministic rules /
  templates, so the whole pipeline still runs end-to-end offline.
- **Provider**: `core/llm_client.py` picks Gemini (`google-genai`) if
  `GEMINI_API_KEY` is set, else Anthropic if `ANTHROPIC_API_KEY` is set, else
  raises `LLMUnavailable` and every caller degrades to its offline fallback.
  A live API failure (rate limit, network, bad model name) is caught the same
  way — it never crashes a batch run, it just downgrades that one message.
  Gemini's free tier is rate-limited to 5 requests/min per model, so on a
  240-event batch only the first handful of messages get live-composed and
  the rest fall back to templates — that's the fallback working as designed,
  not a bug. `gemini-3.6-flash` also spends real token budget on internal
  "thinking" even at `thinking_level="low"` (~340 tokens observed for a
  one-line message), so `llm_client.py` floors every Gemini call's
  `max_output_tokens` at 600 regardless of what the caller asked for.

## Architecture

```
                    ┌─────────────────────────────────────────────────────┐
                    │                     orchestrator.py                  │
                    │   process_event() / run_batch()  — drives the loop   │
                    └───┬───────┬──────────┬────────────┬─────────┬───────┘
                        │       │          │            │         │
                   ┌────▼──┐ ┌──▼──────┐ ┌─▼─────────┐ ┌▼──────┐ ┌▼───────┐
                   │detector│ │diagnoser│ │  policy   │ │compose│ │executor│
                   │ (risk, │ │(rules + │ │(det. table│ │ + LLM │ │(sim.   │
                   │recover-│ │LLM      │ │ + guard-  │ │message│ │outcome,│
                   │able Rs)│ │fallback)│ │  rails)   │ │ gen)  │ │seqs)   │
                   └────────┘ └─────────┘ └───────────┘ └───────┘ └────────┘
                        │                                              │
                        └──────────────────► audit.py ◄────────────────┘
                                        (SQLite, one row per
                                         step per event, every
                                         guardrail check logged)
                                              │
                          ┌───────────────────┼───────────────────┐
                          ▼                   ▼                   ▼
                    api/server.py     batch/run_batch.py     dashboard/app.py
                     (FastAPI)          (CLI scorecard)         (Streamlit)
```

`policy.py` is the "brain" — a plain `(category, root_cause, segment,
attempt_number) -> intervention` table, trivial to print and explain.
`guardrails.py` runs after it and can only make the action *more*
conservative (downgrade a discount, force an escalation, force `no_action`) —
it never adds contact the policy didn't already ask for. Every guardrail is
evaluated and logged on every call, blocked or not.

### Guardrails implemented (core/guardrails.py)

- **Compliance short-circuit** — disputed invoice / fraud hold / legal flag
  -> `no_action` on the automated channel, routed straight to a human agent.
  Non-overridable, checked first.
- **DND / opt-out** — hard stop, `no_action`, no override, ever.
- **Max attempts** — beyond the configured ceiling, force escalation instead
  of another automated try.
- **Cooldown window** — no repeat contact inside the configured hours.
- **Quiet hours** — regions flagged `quiet_hours_only_region` only get
  contacted inside the allowed local-hour window.
- **Discount / waiver cap** — per-event cap (min of a % of amount and a flat
  ceiling) *and* a shared batch-wide budget that depletes across the whole
  run, not just per event.

## Repo layout

```
revenue_recovery/
  data/generate_dataset.py   synthetic events across 4 categories + hidden ground truth
  core/
    models.py                 pydantic models for the whole pipeline
    detector.py                explainable weighted-rule risk/recoverable-amount scoring
    diagnoser.py                rule-based root cause, LLM fallback for free text
    policy.py                   deterministic decision table (the "brain")
    guardrails.py               stopping rules (the module that gets scrutinized most)
    composer.py                  LLM message generation, English + Hinglish
    executor.py                   simulated outcome model, multi-step mandate retry sequence
    audit.py                       append-only SQLite audit log
    orchestrator.py                 wires it all together, single event + batch
    llm_client.py                    thin Gemini/Anthropic wrapper, graceful offline fallback
  api/server.py                FastAPI surface
  batch/run_batch.py           one-command batch demo + scorecard
  dashboard/app.py             Streamlit dashboard
  tests/                       test_policy.py, test_guardrails.py, test_orchestrator.py, ...
```

## Running it

```bash
cd revenue_recovery
pip install --break-system-packages -r requirements.txt
cp .env.example .env   # fill in GEMINI_API_KEY (or ANTHROPIC_API_KEY) to enable LLM
                        # composition/diagnosis — optional, pipeline runs fully offline
                        # with template/rule fallbacks if neither key is set

# One command: generate data (if missing) -> run the full loop -> print scorecard
python -m batch.run_batch
```

Runs in ~4 seconds for 240 events end to end, well under the "one command,
under a minute" bar.

Individual phases, if you want to inspect them separately:

```bash
python -m data.generate_dataset --count 240 --seed 7   # regenerate synthetic data
python -m pytest tests/ -v                              # 43 tests, policy + guardrails + orchestrator
uvicorn api.server:app --reload --port 8000              # API
streamlit run dashboard/app.py                            # dashboard (run batch first)
```

### API quickstart

```bash
curl http://127.0.0.1:8000/                              # service info + event count
curl "http://127.0.0.1:8000/risk/queue?limit=10"          # top at-risk events by priority score
curl -X POST http://127.0.0.1:8000/recover/EVT-0020-70885f/execute
curl http://127.0.0.1:8000/audit/EVT-0020-70885f          # full step-by-step audit trail
curl -X POST http://127.0.0.1:8000/batch/run -H "Content-Type: application/json" -d '{"discount_budget": 50000}'
curl http://127.0.0.1:8000/metrics/batch/BATCH-xxxxxxxx
```

All six endpoints (`POST /events/ingest`, `GET /risk/queue`,
`POST /recover/{event_id}/execute`, `GET /audit/{event_id}`,
`POST /batch/run`, `GET /metrics/batch/{batch_id}`) were exercised manually
against a live server during development — see the phase-8 output in the
build history for the exact request/response pairs.

## Sample scorecard (real run, `python -m batch.run_batch`, seed 7, 240 events)

```
========================================================================
BATCH SCORECARD  (BATCH-4ff0ce5d)
========================================================================
Total events processed:     240
Total revenue at risk:      Rs 31,990,889.09
Total revenue recovered:    Rs 10,123,480.37
Overall recovery rate:      31.64%

Recovery rate by category:
  category                  events          at_risk        recovered    rate%  ev.recov.
  payment_failure               60     1,444,518.30       512,066.89    35.45         20
  checkout_abandonment          60       688,200.13       206,001.46    29.93         20
  subscription_renewal          60       320,056.80       119,346.66    37.29         21
  receivable_overdue            60    29,538,113.86     9,286,065.36    31.44         20

Guardrail-blocked events:   77
    - cooldown_window              50
    - dnd_opt_out                  24
    - compliance_short_circuit     13
    - quiet_hours                  3
    - max_attempts                 1

Escalations:                74
    - subscription_renewal         29
    - payment_failure              27
    - receivable_overdue           17
    - checkout_abandonment         1

Avg steps to recovery:      1.26

Sample audit trails (top recovered per category):
  - EVT-0201-a06808 [payment_failure] Sundial Analytics: Rs 44,042.04 at risk -> Rs 44,042.04 recovered (recovered, path=['retry_payment_now'])
  - EVT-0037-2bc809 [payment_failure] Ishaan Joshi: Rs 42,709.58 at risk -> Rs 42,709.58 recovered (recovered, path=['retry_payment_now'])
  - EVT-0081-f1db7f [payment_failure] Amber Traders: Rs 41,159.42 at risk -> Rs 41,159.42 recovered (recovered, path=['retry_payment_delayed'])
  - EVT-0122-d77ca8 [checkout_abandonment] Vertex Components: Rs 23,669.71 at risk -> Rs 23,669.71 recovered (recovered, path=['send_cart_recovery_nudge'])
  - EVT-0010-07a1be [checkout_abandonment] Meera Patel: Rs 24,742.16 at risk -> Rs 22,742.16 recovered (recovered, path=['offer_bounded_discount'])
  - EVT-0198-f31b71 [checkout_abandonment] Aarav Singh: Rs 20,630.63 at risk -> Rs 20,630.63 recovered (recovered, path=['send_cart_recovery_nudge'])
  - EVT-0027-fa509e [subscription_renewal] Aditya Chatterjee: Rs 9,939.88 at risk -> Rs 9,939.88 recovered (recovered, path=['retry_payment_now'])
  - EVT-0171-0a198f [subscription_renewal] Greenleaf Foods: Rs 9,881.78 at risk -> Rs 9,881.78 recovered (recovered, path=['mandate_retry_sequence'])
  - EVT-0083-9bf7bd [subscription_renewal] Bluewave Textiles: Rs 9,868.15 at risk -> Rs 9,868.15 recovered (recovered, path=['send_dunning_reminder'])
  - EVT-0016-3753a2 [receivable_overdue] Pixel Forge Studios: Rs 857,966.15 at risk -> Rs 857,966.15 recovered (recovered, path=['send_invoice_reminder'])
  - EVT-0076-6a1f69 [receivable_overdue] Vertex Components: Rs 806,112.59 at risk -> Rs 806,112.59 recovered (recovered, path=['send_promise_to_pay_request'])
  - EVT-0020-70885f [receivable_overdue] Greenleaf Foods: Rs 795,506.39 at risk -> Rs 795,506.39 recovered (recovered, path=['send_promise_to_pay_request'])
========================================================================
```

Note the run is probabilistic (executor draws outcomes from each event's
hidden recoverability + noise), so exact numbers vary run to run within a
similar band — the guardrail-block and escalation *reasons*, and the
deterministic policy paths, are what stay reproducible.

## What's deliberately out of scope

- No real payment gateway / messaging integration — `executor.py` simulates
  outcomes from a probabilistic model seeded by (hidden) ground-truth
  recoverability, which the agent itself never sees.
- No auth/multi-tenancy on the API — single in-memory event store per process.
- No persistence layer beyond SQLite for the audit log and JSON for the
  dataset/scorecard — enough to be queryable and exportable for the demo.
