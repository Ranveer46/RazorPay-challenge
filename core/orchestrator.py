"""Orchestrator: wires detect -> diagnose -> decide -> guardrails -> act ->
measure into one loop per event, and aggregates a batch scorecard.

Multi-step sequences (repeated dunning reminders, abandonment nudges,
receivables chasing) are the SAME loop run more than once with an
incrementing attempt_count — guardrails (cooldown, max_attempts, discount
budget) are re-evaluated on every iteration, not just the first.
"""
from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from datetime import datetime

from core.audit import AuditLog
from core.composer import compose_message
from core.detector import score_event
from core.diagnoser import diagnose
from core.executor import execute
from core.guardrails import GuardrailContext, evaluate_guardrails
from core.models import (
    AuditRecord, BatchScorecard, Category, Diagnosis, EventOutcome, Intervention, RevenueEvent,
)
from core.policy import decide_intervention

MAX_LOOP_STEPS = 8  # hard safety cap; guardrails' max_attempts should trigger escalation well before this


def process_event(
    event: RevenueEvent, audit: AuditLog, ctx: GuardrailContext | None = None,
    batch_id: str | None = None,
) -> EventOutcome:
    ctx = ctx or GuardrailContext()

    detection = score_event(event)
    audit.log(AuditRecord(
        event_id=event.event_id, stage="detect",
        input={"category": event.category.value, "amount_at_risk": event.amount_at_risk},
        output=detection.model_dump(),
    ), batch_id)

    diagnosis: Diagnosis = diagnose(event)
    audit.log(AuditRecord(
        event_id=event.event_id, stage="diagnose",
        input={"decline_code": event.decline_code, "abandonment_note": event.abandonment_reason_note},
        output=diagnosis.model_dump(),
        notes="LLM-assisted" if diagnosis.method == "llm" else "rule-based",
    ), batch_id)

    intervention_path: list[Intervention] = []
    total_recovered = 0.0
    total_steps = 0
    escalated = False
    guardrail_block_reasons: list[str] = []
    blocked_by_guardrail = False
    current = event
    step_index = 0

    for loop_iter in range(MAX_LOOP_STEPS):
        decision = decide_intervention(current, diagnosis)
        audit.log(AuditRecord(
            event_id=event.event_id, stage="decide",
            input={"attempt_number": decision.attempt_number, "root_cause": diagnosis.root_cause},
            output={"intervention": decision.intervention.value, "reason": decision.reason,
                    "policy_key": decision.policy_key},
        ), batch_id)

        decision = evaluate_guardrails(current, decision, ctx)
        audit.log(AuditRecord(
            event_id=event.event_id, stage="guardrail",
            input={"pre_guardrail_intervention": decision.policy_key},
            output={
                "final_intervention": decision.intervention.value,
                "blocked": decision.blocked,
                "discount_offered": decision.discount_offered,
                "checks": [c.model_dump() for c in decision.guardrail_checks],
            },
        ), batch_id)
        for check in decision.guardrail_checks:
            if check.blocked:
                guardrail_block_reasons.append(f"{check.name}: {check.reason}")

        intervention_path.append(decision.intervention)

        if decision.intervention == Intervention.NO_ACTION:
            blocked_by_guardrail = decision.blocked
            audit.log(AuditRecord(
                event_id=event.event_id, stage="act",
                input={"intervention": "no_action"},
                output={"outcome": "skipped"},
                notes="loop terminated: no_action",
            ), batch_id)
            total_steps += 1
            break

        message, llm_prompt, llm_response = compose_message(current, decision)
        steps = execute(current, decision, message, step_offset=step_index)
        step_index += len(steps)
        total_steps += len(steps)

        for s in steps:
            audit.log(AuditRecord(
                event_id=event.event_id, stage="act",
                input={"intervention": s.intervention.value, "channel": s.channel.value,
                       "llm_prompt": llm_prompt},
                output={"outcome": s.outcome, "amount_recovered": s.amount_recovered,
                        "message": s.message, "llm_response": llm_response},
            ), batch_id)
            total_recovered += s.amount_recovered

        last_step = steps[-1]
        if last_step.outcome == "success":
            break
        if last_step.outcome == "escalated":
            escalated = True
            break

        # Failure: loop again as the next attempt in the sequence, with
        # guardrails (cooldown, max_attempts, discount budget) re-checked.
        current = current.model_copy(update={
            "attempt_count": current.attempt_count + 1,
            "last_contacted_hours_ago": 0.0,
        })
    else:
        pass  # hit MAX_LOOP_STEPS safety cap; treat as unresolved

    final_status = (
        "recovered" if total_recovered > 0 else
        "escalated" if escalated else
        "blocked" if blocked_by_guardrail else
        "unresolved"
    )

    outcome = EventOutcome(
        event_id=event.event_id, category=event.category, amount_at_risk=event.amount_at_risk,
        amount_recovered=round(total_recovered, 2), recovered=total_recovered > 0,
        steps_taken=total_steps, intervention_path=intervention_path, escalated=escalated,
        blocked_by_guardrail=blocked_by_guardrail, guardrail_block_reasons=guardrail_block_reasons,
        final_status=final_status,
    )
    audit.log(AuditRecord(
        event_id=event.event_id, stage="measure", input={},
        output=outcome.model_dump(),
    ), batch_id)
    return outcome


def run_batch(
    events: list[RevenueEvent], audit: AuditLog, ctx: GuardrailContext | None = None,
    batch_id: str | None = None,
) -> BatchScorecard:
    ctx = ctx or GuardrailContext()
    batch_id = batch_id or f"BATCH-{uuid.uuid4().hex[:8]}"

    outcomes: list[EventOutcome] = [process_event(e, audit, ctx, batch_id) for e in events]

    total_at_risk = sum(e.amount_at_risk for e in events)
    total_recovered = sum(o.amount_recovered for o in outcomes)

    by_category: dict[str, dict] = {}
    for cat in Category:
        cat_events = [e for e in events if e.category == cat]
        cat_outcomes = [o for o in outcomes if o.category == cat]
        cat_at_risk = sum(e.amount_at_risk for e in cat_events)
        cat_recovered = sum(o.amount_recovered for o in cat_outcomes)
        n_recovered = sum(1 for o in cat_outcomes if o.recovered)
        by_category[cat.value] = dict(
            events=len(cat_events),
            at_risk=round(cat_at_risk, 2),
            recovered=round(cat_recovered, 2),
            recovery_rate_pct=round(100 * cat_recovered / cat_at_risk, 2) if cat_at_risk else 0.0,
            events_recovered=n_recovered,
            events_recovered_pct=round(100 * n_recovered / len(cat_events), 2) if cat_events else 0.0,
        )

    guardrail_blocked = [o for o in outcomes if o.blocked_by_guardrail]
    block_reason_counter: Counter = Counter()
    for o in outcomes:
        for reason in o.guardrail_block_reasons:
            block_reason_counter[reason.split(":")[0]] += 1

    escalated_outcomes = [o for o in outcomes if o.escalated]
    escalation_reason_counter: Counter = Counter()
    for o in escalated_outcomes:
        escalation_reason_counter[o.category.value] += 1

    recovered_outcomes = [o for o in outcomes if o.recovered]
    avg_steps = (
        sum(o.steps_taken for o in recovered_outcomes) / len(recovered_outcomes)
        if recovered_outcomes else 0.0
    )

    sample_trails = []
    for cat in Category:
        cat_events_by_id = {e.event_id: e for e in events if e.category == cat}
        cat_outcomes = [o for o in outcomes if o.category == cat]
        picks = sorted(cat_outcomes, key=lambda o: o.amount_recovered, reverse=True)[:3]
        for o in picks:
            sample_trails.append(dict(
                event_id=o.event_id, category=cat.value,
                customer=cat_events_by_id[o.event_id].customer_name,
                amount_at_risk=o.amount_at_risk, amount_recovered=o.amount_recovered,
                final_status=o.final_status,
                intervention_path=[i.value for i in o.intervention_path],
                trail=audit.get_trail(o.event_id),
            ))

    return BatchScorecard(
        batch_id=batch_id,
        total_events=len(events),
        total_at_risk=round(total_at_risk, 2),
        total_recovered=round(total_recovered, 2),
        recovery_rate_overall=round(100 * total_recovered / total_at_risk, 2) if total_at_risk else 0.0,
        by_category=by_category,
        guardrail_blocked_count=len(guardrail_blocked),
        guardrail_block_reasons=dict(block_reason_counter),
        escalation_count=len(escalated_outcomes),
        escalation_reasons=dict(escalation_reason_counter),
        avg_steps_to_recovery=round(avg_steps, 2),
        sample_audit_trails=sample_trails,
    )
