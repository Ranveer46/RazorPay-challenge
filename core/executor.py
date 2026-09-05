"""Executor: simulates actually carrying out the chosen intervention.

Nothing here touches a real payment gateway or messaging provider — this is
a prototype. Outcomes are drawn probabilistically from the event's hidden
ground_truth_recovery_probability (never seen by detector/diagnoser/policy/
guardrails) plus noise, so batch-level recovery numbers are meaningful without
being deterministic replays of the ground truth.
"""
from __future__ import annotations

import random

from core.composer import channel_for
from core.models import ActionStep, Channel, Decision, Intervention, RevenueEvent

NOISE_SD = 0.08


def _draw_outcome(event: RevenueEvent, decay: float = 1.0) -> bool:
    p = event.ground_truth_recovery_probability * decay
    p += random.gauss(0, NOISE_SD)
    p = max(0.0, min(1.0, p))
    return random.random() < p


def execute(
    event: RevenueEvent, decision: Decision, message: str | None, step_offset: int = 0,
) -> list[ActionStep]:
    """Executes one decided intervention. Returns one ActionStep for
    single-shot interventions, or multiple for the mandate retry sequence."""
    channel = channel_for(decision.intervention)

    if decision.intervention == Intervention.NO_ACTION:
        return [ActionStep(
            event_id=event.event_id, step_index=step_offset, channel=Channel.NONE,
            intervention=decision.intervention, message=None, outcome="skipped",
            amount_recovered=0.0,
        )]

    if decision.intervention == Intervention.ESCALATE_TO_HUMAN_AGENT:
        return [ActionStep(
            event_id=event.event_id, step_index=step_offset, channel=Channel.NONE,
            intervention=decision.intervention, message=None, outcome="escalated",
            amount_recovered=0.0,
        )]

    if decision.intervention == Intervention.MANDATE_RETRY_SEQUENCE:
        return _run_mandate_retry_sequence(event, decision, step_offset)

    # Single-shot interventions: payment retries or a customer message.
    success = _draw_outcome(event)
    recovered = 0.0
    if success:
        recovered = round(max(0.0, event.amount_at_risk - decision.discount_offered), 2)

    return [ActionStep(
        event_id=event.event_id, step_index=step_offset, channel=channel,
        intervention=decision.intervention, message=message,
        message_language=event.language_pref if message else None,
        outcome="success" if success else "failure",
        amount_recovered=recovered,
        discount_offered=decision.discount_offered,
    )]


def _run_mandate_retry_sequence(event: RevenueEvent, decision: Decision, step_offset: int) -> list[ActionStep]:
    """retry -> wait -> retry -> escalate, each step less likely to succeed
    than the last (customer already failed once to get here)."""
    steps: list[ActionStep] = []

    for i, decay in enumerate([0.9, 0.6]):
        success = _draw_outcome(event, decay=decay)
        steps.append(ActionStep(
            event_id=event.event_id, step_index=step_offset + i, channel=Channel.PAYMENT_RETRY,
            intervention=Intervention.MANDATE_RETRY_SEQUENCE,
            message=f"mandate retry attempt {i+1}",
            outcome="success" if success else "failure",
            amount_recovered=round(event.amount_at_risk, 2) if success else 0.0,
        ))
        if success:
            return steps

    steps.append(ActionStep(
        event_id=event.event_id, step_index=step_offset + len(steps), channel=Channel.NONE,
        intervention=Intervention.ESCALATE_TO_HUMAN_AGENT,
        message="mandate retry sequence exhausted", outcome="escalated", amount_recovered=0.0,
    ))
    return steps
