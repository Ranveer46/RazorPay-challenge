"""Executor: simulates or carries out the chosen intervention.

If Razorpay credentials are set in the environment (RAZORPAY_KEY_ID & RAZORPAY_KEY_SECRET),
it generates real Razorpay Payment Links / Invoices and embeds them into outbound copy.
Otherwise, it executes in 100% offline simulated mode.

Outcomes are drawn probabilistically from the event's hidden
ground_truth_recovery_probability (never seen by detector/diagnoser/policy/
guardrails) plus noise, so batch-level recovery numbers are meaningful without
being deterministic replays of the ground truth.
"""
from __future__ import annotations

import random
from typing import Optional

from core.composer import channel_for
from core.models import ActionStep, Channel, Decision, Intervention, RevenueEvent
from core.razorpay_gateway import gateway

NOISE_SD = 0.08


def _draw_outcome(event: RevenueEvent, decay: float = 1.0) -> bool:
    p = event.ground_truth_recovery_probability * decay
    p += random.gauss(0, NOISE_SD)
    p = max(0.0, min(1.0, p))
    return random.random() < p


def _attach_razorpay_links(
    event: RevenueEvent, decision: Decision, message: Optional[str]
) -> Optional[str]:
    """Enriches outbound customer messages with real Razorpay links if available,
    or realistic demo links if running offline."""
    if not message:
        return message

    link_url: Optional[str] = None

    if gateway.is_configured():
        if decision.intervention in (
            Intervention.SEND_UPDATE_PAYMENT_METHOD_LINK,
            Intervention.SEND_CART_RECOVERY_NUDGE,
            Intervention.OFFER_BOUNDED_DISCOUNT,
            Intervention.SEND_DUNNING_REMINDER,
        ):
            net_amount = max(1.0, event.amount_at_risk - decision.discount_offered)
            res = gateway.create_payment_link(
                amount=net_amount,
                customer_name=event.customer_name,
                description=f"Recovery for {event.category.value} ({event.event_id})",
                reference_id=event.event_id,
            )
            if res and res.get("short_url"):
                link_url = res["short_url"]

        elif decision.intervention in (
            Intervention.SEND_INVOICE_REMINDER,
            Intervention.SEND_PROMISE_TO_PAY_REQUEST,
        ):
            res = gateway.create_invoice(
                customer_name=event.customer_name,
                amount=event.amount_at_risk,
                description=f"Invoice {event.invoice_id or event.event_id}",
                reference_id=event.event_id,
            )
            if res and res.get("short_url"):
                link_url = res["short_url"]

    # Fallback to realistic demo URL if offline
    if not link_url:
        link_url = f"https://rzp.io/l/{event.event_id.lower()}"

    # Replace placeholders
    for tag in ("[update-link]", "[cart-link]", "[retry-link]"):
        if tag in message:
            message = message.replace(tag, link_url)

    return message


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

    # Enrich customer copy with Razorpay gateway link
    final_message = _attach_razorpay_links(event, decision, message)

    # Single-shot interventions: payment retries or a customer message.
    success = _draw_outcome(event)
    recovered = 0.0
    if success:
        recovered = round(max(0.0, event.amount_at_risk - decision.discount_offered), 2)

    return [ActionStep(
        event_id=event.event_id, step_index=step_offset, channel=channel,
        intervention=decision.intervention, message=final_message,
        message_language=event.language_pref if final_message else None,
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
