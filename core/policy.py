"""Policy engine: a deterministic, inspectable decision table.

(category, root_cause, segment, attempt_number) -> Intervention

No LLM involved here, no randomness. Given the same inputs this always
returns the same intervention — that's what makes it auditable. Guardrails
(core/guardrails.py) run AFTER this and can veto/override the chosen
intervention; policy.py only decides what the agent *would like* to do next.
"""
from __future__ import annotations

from core.models import Category, Decision, Diagnosis, Intervention, RevenueEvent, Segment

# Root causes that should never receive automated outreach, regardless of
# attempt number — the policy table routes these straight to escalation/no-op.
# (Guardrails also enforce this independently as a hard stop; this is belt
# and suspenders so the "brain" itself never proposes contacting them.)
COMPLIANCE_ROOT_CAUSES = {"invoice_disputed", "fraud_hold"}


def _key(category: Category, root_cause: str, segment: Segment, attempt_number: int) -> str:
    return f"{category.value}/{root_cause}/{segment.value}/attempt{attempt_number}"


def decide_intervention(event: RevenueEvent, diagnosis: Diagnosis) -> Decision:
    category = event.category
    root_cause = diagnosis.root_cause
    segment = event.segment
    attempt_number = event.attempt_count

    if root_cause in COMPLIANCE_ROOT_CAUSES:
        intervention = Intervention.ESCALATE_TO_HUMAN_AGENT if root_cause == "invoice_disputed" \
            else Intervention.NO_ACTION
        return Decision(
            event_id=event.event_id,
            intervention=intervention,
            policy_key=_key(category, root_cause, segment, attempt_number),
            attempt_number=attempt_number,
            reason=f"root_cause={root_cause} is a compliance-sensitive cause; "
                   f"policy routes directly to {intervention.value}, never automated contact.",
        )

    if category == Category.PAYMENT_FAILURE:
        intervention, reason = _policy_payment_failure(root_cause, attempt_number)
    elif category == Category.CHECKOUT_ABANDONMENT:
        intervention, reason = _policy_abandonment(root_cause, attempt_number, segment)
    elif category == Category.SUBSCRIPTION_RENEWAL:
        intervention, reason = _policy_subscription(root_cause, attempt_number)
    elif category == Category.RECEIVABLE_OVERDUE:
        intervention, reason = _policy_receivable(root_cause, attempt_number, segment)
    else:  # pragma: no cover - exhaustive over Category enum
        intervention, reason = Intervention.NO_ACTION, "unhandled category"

    return Decision(
        event_id=event.event_id,
        intervention=intervention,
        policy_key=_key(category, root_cause, segment, attempt_number),
        attempt_number=attempt_number,
        reason=reason,
    )


def _policy_payment_failure(root_cause: str, attempt: int) -> tuple[Intervention, str]:
    if attempt >= 3:
        return Intervention.ESCALATE_TO_HUMAN_AGENT, "3+ prior attempts on a payment failure -> escalate"
    table = {
        "expired_card": Intervention.SEND_UPDATE_PAYMENT_METHOD_LINK,
        "user_input_error": Intervention.SEND_UPDATE_PAYMENT_METHOD_LINK,
        "gateway_timeout": Intervention.RETRY_PAYMENT_NOW,
        "issuer_declined": Intervention.RETRY_PAYMENT_DELAYED,
        "insufficient_funds": Intervention.RETRY_PAYMENT_DELAYED,
    }
    intervention = table.get(root_cause, Intervention.SEND_UPDATE_PAYMENT_METHOD_LINK)
    return intervention, f"root_cause={root_cause}, attempt={attempt} -> {intervention.value} (policy table)"


def _policy_abandonment(root_cause: str, attempt: int, segment: Segment) -> tuple[Intervention, str]:
    if attempt >= 2:
        return Intervention.NO_ACTION, "2+ nudges already sent for this cart -> stop (diminishing returns)"
    if root_cause == "price_sensitivity" and attempt == 0:
        return Intervention.OFFER_BOUNDED_DISCOUNT, "price-sensitive abandonment, first attempt -> bounded discount"
    if root_cause == "technical_friction":
        return Intervention.SEND_CART_RECOVERY_NUDGE, "technical friction -> reassurance nudge, no discount needed"
    if root_cause == "low_intent_or_distraction":
        return Intervention.SEND_CART_RECOVERY_NUDGE, "low intent -> gentle nudge only"
    return Intervention.SEND_CART_RECOVERY_NUDGE, f"root_cause={root_cause}, attempt={attempt} -> standard nudge"


def _policy_subscription(root_cause: str, attempt: int) -> tuple[Intervention, str]:
    if attempt >= 3:
        return Intervention.ESCALATE_TO_HUMAN_AGENT, "3+ dunning attempts -> escalate to human agent"
    if root_cause in {"expired_card", "user_input_error"}:
        return Intervention.SEND_UPDATE_PAYMENT_METHOD_LINK, f"root_cause={root_cause} -> ask to update payment method"
    if root_cause == "gateway_timeout" and attempt == 0:
        return Intervention.RETRY_PAYMENT_NOW, "transient gateway issue, first attempt -> immediate retry"
    if attempt >= 1:
        return Intervention.MANDATE_RETRY_SEQUENCE, f"attempt={attempt} -> start mandate retry sequence"
    return Intervention.SEND_DUNNING_REMINDER, f"root_cause={root_cause}, attempt={attempt} -> dunning reminder"


def _policy_receivable(root_cause: str, attempt: int, segment: Segment) -> tuple[Intervention, str]:
    if root_cause == "promise_to_pay_pending":
        return Intervention.SEND_PROMISE_TO_PAY_REQUEST, "open promise-to-pay -> track/confirm, no new pressure"
    if attempt >= 4 or (segment == Segment.ENTERPRISE and attempt >= 2):
        return Intervention.ESCALATE_TO_HUMAN_AGENT, f"attempt={attempt} segment={segment.value} -> escalate to AR team"
    if attempt == 0:
        return Intervention.SEND_INVOICE_REMINDER, "first overdue touch -> polite invoice reminder"
    return Intervention.SEND_PROMISE_TO_PAY_REQUEST, f"attempt={attempt} -> request a promise-to-pay commitment"


# --- Introspection helpers, for the demo / judge review -------------------

def explain_table() -> list[dict]:
    """Materializes the full policy table for a representative attempt range
    so it can be printed/inspected without invoking the LLM or guardrails."""
    from core.models import Language
    rows = []
    sample_root_causes = {
        Category.PAYMENT_FAILURE: ["expired_card", "gateway_timeout", "issuer_declined",
                                    "insufficient_funds", "user_input_error", "fraud_hold"],
        Category.CHECKOUT_ABANDONMENT: ["price_sensitivity", "technical_friction",
                                         "hidden_cost_surprise", "promo_failure",
                                         "low_intent_or_distraction"],
        Category.SUBSCRIPTION_RENEWAL: ["expired_card", "gateway_timeout", "issuer_declined",
                                         "insufficient_funds", "user_input_error"],
        Category.RECEIVABLE_OVERDUE: ["cashflow_delay", "chronic_late_payer",
                                       "promise_to_pay_pending", "invoice_disputed"],
    }
    dummy = dict(
        event_id="X", account_id="X", customer_name="X", segment=Segment.CONSUMER,
        language_pref=Language.ENGLISH, payment_reliability_score=0.7, amount_at_risk=1000,
        created_at=__import__("datetime").datetime.utcnow(),
    )
    for category, causes in sample_root_causes.items():
        for cause in causes:
            for attempt in range(0, 4):
                event = RevenueEvent(category=category, **dummy, attempt_count=attempt)
                diag = Diagnosis(event_id="X", root_cause=cause, confidence=1.0, method="rule")
                decision = decide_intervention(event, diag)
                rows.append(dict(category=category.value, root_cause=cause, attempt=attempt,
                                  intervention=decision.intervention.value, reason=decision.reason))
    return rows
