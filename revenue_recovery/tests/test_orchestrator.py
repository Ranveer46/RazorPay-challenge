from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.audit import AuditLog
from core.guardrails import DiscountBudget, GuardrailContext
from core.models import Category, Language, RevenueEvent, Segment
from core.orchestrator import process_event, run_batch


def make_event(**overrides) -> RevenueEvent:
    base = dict(
        event_id="EVT-O-0001",
        category=Category.PAYMENT_FAILURE,
        account_id="ACC-O",
        customer_name="Test User",
        segment=Segment.CONSUMER,
        language_pref=Language.ENGLISH,
        payment_reliability_score=0.7,
        amount_at_risk=1000.0,
        created_at=datetime(2026, 8, 27, 10, 0, 0),
        attempt_count=0,
        decline_code="gateway_timeout",
        ground_truth_recoverable=True,
        ground_truth_recovery_probability=0.95,
        ground_truth_root_cause="gateway_timeout",
    )
    base.update(overrides)
    return RevenueEvent(**base)


def fresh_audit(tmp_path) -> AuditLog:
    return AuditLog(db_path=tmp_path / "audit_test.db", reset=True)


def test_process_event_writes_full_audit_trail(tmp_path):
    audit = fresh_audit(tmp_path)
    event = make_event()
    process_event(event, audit)
    trail = audit.get_trail(event.event_id)
    stages = [r["stage"] for r in trail]
    assert "detect" in stages
    assert "diagnose" in stages
    assert "decide" in stages
    assert "guardrail" in stages
    assert "act" in stages
    assert "measure" in stages
    audit.close()


def test_process_event_dnd_never_reaches_act_success(tmp_path):
    audit = fresh_audit(tmp_path)
    event = make_event(dnd=True)
    outcome = process_event(event, audit)
    assert outcome.amount_recovered == 0.0
    assert outcome.final_status == "blocked"
    audit.close()


def test_process_event_fraud_hold_escalates(tmp_path):
    audit = fresh_audit(tmp_path)
    event = make_event(fraud_hold=True, decline_code="fraud_suspected")
    outcome = process_event(event, audit)
    assert outcome.escalated
    assert outcome.amount_recovered == 0.0
    audit.close()


def test_process_event_high_probability_event_tends_to_recover(tmp_path):
    audit = fresh_audit(tmp_path)
    recovered_count = 0
    for i in range(20):
        event = make_event(event_id=f"EVT-O-{i:04d}", ground_truth_recovery_probability=0.97)
        outcome = process_event(event, audit)
        if outcome.recovered:
            recovered_count += 1
    assert recovered_count >= 14  # most should recover with a 0.97 base probability
    audit.close()


def test_run_batch_produces_scorecard_with_all_categories(tmp_path):
    audit = fresh_audit(tmp_path)
    events = [
        make_event(event_id="EVT-B-1", category=Category.PAYMENT_FAILURE, decline_code="gateway_timeout"),
        make_event(event_id="EVT-B-2", category=Category.CHECKOUT_ABANDONMENT, cart_value=500,
                    cart_items=1, abandonment_reason_note="price seemed too high compared to other site",
                    decline_code=None),
        make_event(event_id="EVT-B-3", category=Category.SUBSCRIPTION_RENEWAL, decline_code="card_expired",
                    dunning_attempt_count=0),
        make_event(event_id="EVT-B-4", category=Category.RECEIVABLE_OVERDUE, decline_code=None,
                    invoice_id="INV-9", invoice_terms="Net 30", days_overdue=10),
    ]
    scorecard = run_batch(events, audit)
    assert scorecard.total_events == 4
    assert set(scorecard.by_category.keys()) == {c.value for c in Category}
    assert scorecard.total_at_risk > 0
    audit.close()


def test_run_batch_discount_budget_is_shared_not_reset_per_event(tmp_path):
    audit = fresh_audit(tmp_path)
    ctx = GuardrailContext(batch_discount_budget=DiscountBudget(total=100.0))
    events = [
        make_event(event_id=f"EVT-D-{i}", category=Category.CHECKOUT_ABANDONMENT,
                    cart_value=2000, cart_items=1, amount_at_risk=2000,
                    abandonment_reason_note="price seemed too high compared to other site",
                    decline_code=None, ground_truth_recovery_probability=0.0)
        for i in range(5)
    ]
    run_batch(events, audit, ctx=ctx)
    assert ctx.batch_discount_budget.spent <= 100.0
    audit.close()
