from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.guardrails import DiscountBudget, GuardrailContext, evaluate_guardrails
from core.models import (
    Category, Decision, Intervention, Language, RevenueEvent, Segment,
)


def make_event(**overrides) -> RevenueEvent:
    base = dict(
        event_id="EVT-G-0001",
        category=Category.CHECKOUT_ABANDONMENT,
        account_id="ACC-G",
        customer_name="Test User",
        segment=Segment.CONSUMER,
        language_pref=Language.ENGLISH,
        payment_reliability_score=0.7,
        amount_at_risk=1000.0,
        created_at=datetime(2026, 8, 27, 10, 0, 0),
        attempt_count=0,
        local_hour=12,
    )
    base.update(overrides)
    return RevenueEvent(**base)


def make_decision(event: RevenueEvent, intervention: Intervention, attempt=0) -> Decision:
    return Decision(
        event_id=event.event_id, intervention=intervention,
        policy_key="test/key", attempt_number=attempt, reason="test decision",
    )


def test_dnd_customer_hard_blocked_no_override():
    event = make_event(dnd=True)
    decision = make_decision(event, Intervention.SEND_CART_RECOVERY_NUDGE)
    result = evaluate_guardrails(event, decision)
    assert result.intervention == Intervention.NO_ACTION
    assert result.blocked
    dnd_check = next(c for c in result.guardrail_checks if c.name == "dnd_opt_out")
    assert dnd_check.blocked


def test_opt_out_customer_hard_blocked():
    event = make_event(opt_out=True)
    decision = make_decision(event, Intervention.SEND_INVOICE_REMINDER)
    result = evaluate_guardrails(event, decision)
    assert result.intervention == Intervention.NO_ACTION


def test_fraud_hold_escalates_never_automated_contact():
    event = make_event(category=Category.PAYMENT_FAILURE, fraud_hold=True)
    decision = make_decision(event, Intervention.RETRY_PAYMENT_NOW)
    result = evaluate_guardrails(event, decision)
    assert result.intervention == Intervention.ESCALATE_TO_HUMAN_AGENT
    assert result.intervention != Intervention.RETRY_PAYMENT_NOW


def test_disputed_invoice_escalates_never_automated_contact():
    event = make_event(category=Category.RECEIVABLE_OVERDUE, disputed=True)
    decision = make_decision(event, Intervention.SEND_INVOICE_REMINDER)
    result = evaluate_guardrails(event, decision)
    assert result.intervention == Intervention.ESCALATE_TO_HUMAN_AGENT


def test_legal_flagged_escalates():
    event = make_event(category=Category.RECEIVABLE_OVERDUE, legal_flagged=True)
    decision = make_decision(event, Intervention.SEND_INVOICE_REMINDER)
    result = evaluate_guardrails(event, decision)
    assert result.intervention == Intervention.ESCALATE_TO_HUMAN_AGENT


def test_max_attempts_exceeded_forces_escalation():
    ctx = GuardrailContext(max_attempts=3)
    event = make_event(attempt_count=3)
    decision = make_decision(event, Intervention.SEND_CART_RECOVERY_NUDGE, attempt=3)
    result = evaluate_guardrails(event, decision, ctx)
    assert result.intervention == Intervention.ESCALATE_TO_HUMAN_AGENT
    check = next(c for c in result.guardrail_checks if c.name == "max_attempts")
    assert check.blocked


def test_max_attempts_under_limit_passes_through():
    ctx = GuardrailContext(max_attempts=4)
    event = make_event(attempt_count=1)
    decision = make_decision(event, Intervention.SEND_CART_RECOVERY_NUDGE, attempt=1)
    result = evaluate_guardrails(event, decision, ctx)
    assert result.intervention == Intervention.SEND_CART_RECOVERY_NUDGE


def test_cooldown_window_blocks_recent_contact():
    ctx = GuardrailContext(cooldown_hours=12)
    event = make_event(last_contacted_hours_ago=2.0)
    decision = make_decision(event, Intervention.SEND_CART_RECOVERY_NUDGE)
    result = evaluate_guardrails(event, decision, ctx)
    assert result.intervention == Intervention.NO_ACTION
    check = next(c for c in result.guardrail_checks if c.name == "cooldown_window")
    assert check.blocked


def test_cooldown_window_allows_contact_after_window_clears():
    ctx = GuardrailContext(cooldown_hours=12)
    event = make_event(last_contacted_hours_ago=20.0)
    decision = make_decision(event, Intervention.SEND_CART_RECOVERY_NUDGE)
    result = evaluate_guardrails(event, decision, ctx)
    assert result.intervention == Intervention.SEND_CART_RECOVERY_NUDGE


def test_cooldown_does_not_apply_to_non_contact_interventions():
    ctx = GuardrailContext(cooldown_hours=12)
    event = make_event(category=Category.PAYMENT_FAILURE, last_contacted_hours_ago=0.5)
    decision = make_decision(event, Intervention.RETRY_PAYMENT_NOW)
    result = evaluate_guardrails(event, decision, ctx)
    assert result.intervention == Intervention.RETRY_PAYMENT_NOW


def test_quiet_hours_blocks_contact_outside_window():
    ctx = GuardrailContext(quiet_hours_start=9, quiet_hours_end=20)
    event = make_event(quiet_hours_only_region=True, local_hour=23)
    decision = make_decision(event, Intervention.SEND_CART_RECOVERY_NUDGE)
    result = evaluate_guardrails(event, decision, ctx)
    assert result.intervention == Intervention.NO_ACTION
    check = next(c for c in result.guardrail_checks if c.name == "quiet_hours")
    assert check.blocked


def test_quiet_hours_allows_contact_inside_window():
    ctx = GuardrailContext(quiet_hours_start=9, quiet_hours_end=20)
    event = make_event(quiet_hours_only_region=True, local_hour=14)
    decision = make_decision(event, Intervention.SEND_CART_RECOVERY_NUDGE)
    result = evaluate_guardrails(event, decision, ctx)
    assert result.intervention == Intervention.SEND_CART_RECOVERY_NUDGE


def test_quiet_hours_not_enforced_when_region_flag_unset():
    ctx = GuardrailContext(quiet_hours_start=9, quiet_hours_end=20)
    event = make_event(quiet_hours_only_region=False, local_hour=2)
    decision = make_decision(event, Intervention.SEND_CART_RECOVERY_NUDGE)
    result = evaluate_guardrails(event, decision, ctx)
    assert result.intervention == Intervention.SEND_CART_RECOVERY_NUDGE


def test_discount_capped_below_flat_ceiling():
    ctx = GuardrailContext(per_event_discount_cap_pct=0.15, per_event_discount_cap_abs=2000.0,
                            batch_discount_budget=DiscountBudget(total=50000.0))
    event = make_event(amount_at_risk=1000.0)
    decision = make_decision(event, Intervention.OFFER_BOUNDED_DISCOUNT)
    result = evaluate_guardrails(event, decision, ctx)
    assert result.intervention == Intervention.OFFER_BOUNDED_DISCOUNT
    assert result.discount_offered == 150.0  # 15% of 1000, below the Rs 2000 flat cap


def test_discount_capped_at_flat_ceiling_for_large_cart():
    ctx = GuardrailContext(per_event_discount_cap_pct=0.15, per_event_discount_cap_abs=2000.0,
                            batch_discount_budget=DiscountBudget(total=50000.0))
    event = make_event(amount_at_risk=50000.0)
    decision = make_decision(event, Intervention.OFFER_BOUNDED_DISCOUNT)
    result = evaluate_guardrails(event, decision, ctx)
    assert result.discount_offered == 2000.0  # flat cap, since 15% of 50k would be 7500


def test_discount_budget_exhausted_downgrades_to_plain_nudge():
    ctx = GuardrailContext(batch_discount_budget=DiscountBudget(total=0.0))
    event = make_event(amount_at_risk=1000.0)
    decision = make_decision(event, Intervention.OFFER_BOUNDED_DISCOUNT)
    result = evaluate_guardrails(event, decision, ctx)
    assert result.intervention == Intervention.SEND_CART_RECOVERY_NUDGE
    assert result.discount_offered == 0.0
    check = next(c for c in result.guardrail_checks if c.name == "discount_cap")
    assert check.blocked


def test_discount_budget_shared_across_calls_in_a_batch():
    ctx = GuardrailContext(per_event_discount_cap_pct=0.5, per_event_discount_cap_abs=1000.0,
                            batch_discount_budget=DiscountBudget(total=1500.0))
    event1 = make_event(event_id="EVT-A", amount_at_risk=2000.0)
    event2 = make_event(event_id="EVT-B", amount_at_risk=2000.0)
    d1 = evaluate_guardrails(event1, make_decision(event1, Intervention.OFFER_BOUNDED_DISCOUNT), ctx)
    assert d1.discount_offered == 1000.0
    assert ctx.batch_discount_budget.remaining == 500.0
    d2 = evaluate_guardrails(event2, make_decision(event2, Intervention.OFFER_BOUNDED_DISCOUNT), ctx)
    # second event's cap (1000) exceeds remaining budget (500) -> downgraded
    assert d2.intervention == Intervention.SEND_CART_RECOVERY_NUDGE
    assert d2.discount_offered == 0.0


def test_every_guardrail_is_logged_even_when_nothing_blocks():
    event = make_event()
    decision = make_decision(event, Intervention.SEND_CART_RECOVERY_NUDGE)
    result = evaluate_guardrails(event, decision)
    names = {c.name for c in result.guardrail_checks}
    assert names == {
        "compliance_short_circuit", "dnd_opt_out", "max_attempts",
        "cooldown_window", "quiet_hours", "discount_cap",
    }
    assert not result.blocked


def test_compliance_short_circuit_takes_priority_over_dnd():
    event = make_event(category=Category.RECEIVABLE_OVERDUE, disputed=True, dnd=True)
    decision = make_decision(event, Intervention.SEND_INVOICE_REMINDER)
    result = evaluate_guardrails(event, decision)
    assert result.intervention == Intervention.ESCALATE_TO_HUMAN_AGENT
    compliance_check = next(c for c in result.guardrail_checks if c.name == "compliance_short_circuit")
    assert compliance_check.blocked
