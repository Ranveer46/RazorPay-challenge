"""Detector: scores each event for risk and estimates a recoverable amount.

Deliberately simple, explainable weighted-rule scoring — every number in the
output can be traced back to a named reason. Never reads the event's hidden
ground_truth_* fields; only observable signals a real system would have.
"""
from __future__ import annotations

from datetime import datetime

from core.models import Category, Detection, RevenueEvent

# Observable (non-hidden) base recoverability by decline code / root signal.
# These are business heuristics, not the ground truth used for simulation.
DECLINE_CODE_RECOVERABILITY = {
    "insufficient_funds": 0.40,
    "card_expired": 0.55,
    "do_not_honor": 0.30,
    "gateway_timeout": 0.75,
    "fraud_suspected": 0.05,
    "issuer_unavailable": 0.65,
    "incorrect_cvv": 0.70,
}

CATEGORY_BASE_URGENCY = {
    Category.PAYMENT_FAILURE: 0.55,
    Category.CHECKOUT_ABANDONMENT: 0.35,
    Category.SUBSCRIPTION_RENEWAL: 0.50,
    Category.RECEIVABLE_OVERDUE: 0.45,
}


def _clip(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def score_event(event: RevenueEvent, now: datetime | None = None) -> Detection:
    now = now or datetime.utcnow()
    reasons: list[str] = []

    risk = CATEGORY_BASE_URGENCY[event.category]
    reasons.append(f"base urgency for {event.category.value} = {risk:.2f}")

    # Unreliable payers / low historical reliability raise risk.
    unreliability = 1 - event.payment_reliability_score
    risk += 0.20 * unreliability
    reasons.append(f"+{0.20*unreliability:.2f} for payment unreliability ({unreliability:.2f})")

    # Compliance-hard-stop signals still raise "risk" (money is at risk) even
    # though guardrails will later prevent automated action on them.
    if event.fraud_hold:
        risk += 0.15
        reasons.append("+0.15 fraud hold flagged")
    if event.disputed:
        risk += 0.10
        reasons.append("+0.10 invoice disputed")

    recoverability = 0.5  # baseline before category-specific adjustment

    if event.category == Category.PAYMENT_FAILURE:
        code_recov = DECLINE_CODE_RECOVERABILITY.get(event.decline_code or "", 0.4)
        recoverability = code_recov
        reasons.append(f"decline_code={event.decline_code} -> base recoverability {code_recov:.2f}")
        attempt_penalty = 0.08 * event.attempt_count
        recoverability -= attempt_penalty
        risk += 0.05 * event.attempt_count
        if attempt_penalty:
            reasons.append(f"-{attempt_penalty:.2f} recoverability per {event.attempt_count} prior attempt(s)")

    elif event.category == Category.CHECKOUT_ABANDONMENT:
        hours_since = max(0.0, (now - event.created_at).total_seconds() / 3600)
        recency_factor = _clip(1 - hours_since / 72)
        recoverability = 0.30 + 0.35 * recency_factor
        reasons.append(f"abandoned {hours_since:.1f}h ago -> recency factor {recency_factor:.2f}")
        if event.cart_value and event.cart_value > 5000:
            risk += 0.10
            reasons.append("+0.10 high cart value (>Rs 5,000)")

    elif event.category == Category.SUBSCRIPTION_RENEWAL:
        code_recov = DECLINE_CODE_RECOVERABILITY.get(event.decline_code or "", 0.4)
        dunning = event.dunning_attempt_count or 0
        decay = max(0.3, 1 - 0.15 * dunning)
        recoverability = code_recov * decay
        risk += 0.06 * dunning
        reasons.append(f"dunning_attempt={dunning} decay={decay:.2f} -> recoverability {recoverability:.2f}")

    elif event.category == Category.RECEIVABLE_OVERDUE:
        overdue = event.days_overdue or 0
        age_penalty = _clip(overdue / 120)
        recoverability = _clip(0.75 - 0.5 * age_penalty)
        risk += 0.15 * age_penalty
        reasons.append(f"days_overdue={overdue} -> age_penalty {age_penalty:.2f}, recoverability {recoverability:.2f}")
        if event.promise_to_pay_date:
            recoverability = _clip(recoverability + 0.20)
            reasons.append("+0.20 recoverability: open promise-to-pay on file")

    # Hard-zero observable signals (mirrors guardrail logic at scoring time,
    # so the risk queue doesn't rank uncontactable accounts highly).
    if event.dnd or event.opt_out:
        recoverability = 0.0
        reasons.append("recoverability forced to 0: DND/opt-out")
    if event.fraud_hold:
        recoverability = 0.0
        reasons.append("recoverability forced to 0: fraud hold")
    if event.disputed:
        recoverability = 0.0
        reasons.append("recoverability forced to 0: disputed invoice")
    if event.legal_flagged:
        recoverability = 0.0
        reasons.append("recoverability forced to 0: legal flagged")

    risk = _clip(risk)
    recoverability = _clip(recoverability)
    recoverable_amount = round(event.amount_at_risk * recoverability, 2)
    priority_score = round(risk * recoverable_amount, 2)

    return Detection(
        event_id=event.event_id,
        risk_score=round(risk, 3),
        recoverable_amount=recoverable_amount,
        priority_score=priority_score,
        reasons=reasons,
    )


def score_batch(events: list[RevenueEvent], now: datetime | None = None) -> list[Detection]:
    return [score_event(e, now) for e in events]
