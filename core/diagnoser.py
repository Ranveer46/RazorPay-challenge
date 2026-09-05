"""Diagnoser: assigns a root cause to each event.

Rule-based wherever the signal is unambiguous (decline codes, invoice state).
Falls back to an LLM call only for checkout-abandonment free-text notes,
where classification genuinely benefits from language understanding. The
LLM call (prompt + response) is returned on the Diagnosis object so the
orchestrator can persist it into the audit trail.
"""
from __future__ import annotations

from core.llm_client import LLMUnavailable, call as llm_call
from core.models import Category, Diagnosis, RevenueEvent

DECLINE_CODE_ROOT_CAUSE = {
    "insufficient_funds": "insufficient_funds",
    "card_expired": "expired_card",
    "do_not_honor": "issuer_declined",
    "gateway_timeout": "gateway_timeout",
    "fraud_suspected": "fraud_hold",
    "issuer_unavailable": "gateway_timeout",
    "incorrect_cvv": "user_input_error",
}

ABANDON_KEYWORDS = {
    "price_sensitivity": ["price", "expensive", "cheaper", "compare"],
    "technical_friction": ["spinning", "did not load", "error", "crash", "glitch"],
    "hidden_cost_surprise": ["shipping", "extra cost", "surprise", "hidden fee"],
    "promo_failure": ["coupon", "promo", "code did not apply", "discount code"],
    "low_intent_or_distraction": ["distracted", "browsing", "spouse", "save for later", "phone call"],
}

ABANDON_SYSTEM_PROMPT = (
    "You classify why an e-commerce customer abandoned checkout, from a short "
    "free-text note. Respond with ONLY one label from this exact set: "
    "price_sensitivity, technical_friction, hidden_cost_surprise, promo_failure, "
    "low_intent_or_distraction, other. No punctuation, no explanation, just the label."
)


def diagnose_payment_failure(event: RevenueEvent) -> Diagnosis:
    root_cause = DECLINE_CODE_ROOT_CAUSE.get(event.decline_code or "", "unknown")
    return Diagnosis(
        event_id=event.event_id,
        root_cause=root_cause,
        confidence=0.95 if root_cause != "unknown" else 0.3,
        method="rule",
        evidence=f"decline_code={event.decline_code}",
    )


def diagnose_subscription_renewal(event: RevenueEvent) -> Diagnosis:
    root_cause = DECLINE_CODE_ROOT_CAUSE.get(event.decline_code or "", "unknown")
    return Diagnosis(
        event_id=event.event_id,
        root_cause=root_cause,
        confidence=0.9 if root_cause != "unknown" else 0.3,
        method="rule",
        evidence=f"decline_code={event.decline_code}, dunning_attempt={event.dunning_attempt_count}",
    )


def diagnose_receivable_overdue(event: RevenueEvent) -> Diagnosis:
    if event.disputed:
        return Diagnosis(
            event_id=event.event_id, root_cause="invoice_disputed", confidence=1.0,
            method="rule", evidence="disputed=True",
        )
    if event.promise_to_pay_date:
        return Diagnosis(
            event_id=event.event_id, root_cause="promise_to_pay_pending", confidence=0.95,
            method="rule", evidence=f"promise_to_pay_date={event.promise_to_pay_date}",
        )
    overdue = event.days_overdue or 0
    if overdue >= 60 and event.payment_reliability_score < 0.5:
        root_cause, conf = "chronic_late_payer", 0.75
    else:
        root_cause, conf = "cashflow_delay", 0.6
    return Diagnosis(
        event_id=event.event_id, root_cause=root_cause, confidence=conf,
        method="rule", evidence=f"days_overdue={overdue}, reliability={event.payment_reliability_score}",
    )


def _keyword_fallback(note: str) -> str:
    note_l = note.lower()
    for label, keywords in ABANDON_KEYWORDS.items():
        if any(k in note_l for k in keywords):
            return label
    return "other"


def diagnose_checkout_abandonment(event: RevenueEvent) -> Diagnosis:
    note = event.abandonment_reason_note or ""
    if not note:
        return Diagnosis(
            event_id=event.event_id, root_cause="unknown", confidence=0.2,
            method="rule", evidence="no abandonment note available",
        )

    keyword_guess = _keyword_fallback(note)
    if keyword_guess != "other":
        # Unambiguous enough for a rule match — skip the LLM call.
        return Diagnosis(
            event_id=event.event_id, root_cause=keyword_guess, confidence=0.7,
            method="rule", evidence=f"keyword match on note: '{note}'",
        )

    # Ambiguous free text: ask the LLM.
    prompt = f'Customer abandonment note: "{note}"'
    try:
        response = llm_call(ABANDON_SYSTEM_PROMPT, prompt, max_tokens=20)
        label = response.strip().lower().split()[0].strip(".,") if response else "other"
        valid_labels = set(ABANDON_KEYWORDS.keys()) | {"other"}
        if label not in valid_labels:
            label = "other"
        return Diagnosis(
            event_id=event.event_id, root_cause=label, confidence=0.65, method="llm",
            evidence=f"LLM classification of note: '{note}'",
            llm_prompt=f"SYSTEM: {ABANDON_SYSTEM_PROMPT}\nUSER: {prompt}",
            llm_response=response,
        )
    except LLMUnavailable:
        return Diagnosis(
            event_id=event.event_id, root_cause="other", confidence=0.3, method="rule",
            evidence=f"LLM unavailable, keyword match inconclusive on note: '{note}'",
        )


DIAGNOSERS = {
    Category.PAYMENT_FAILURE: diagnose_payment_failure,
    Category.CHECKOUT_ABANDONMENT: diagnose_checkout_abandonment,
    Category.SUBSCRIPTION_RENEWAL: diagnose_subscription_renewal,
    Category.RECEIVABLE_OVERDUE: diagnose_receivable_overdue,
}


def diagnose(event: RevenueEvent) -> Diagnosis:
    return DIAGNOSERS[event.category](event)
