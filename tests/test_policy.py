from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.models import Category, Diagnosis, Intervention, Language, RevenueEvent, Segment
from core.policy import decide_intervention


def make_event(**overrides) -> RevenueEvent:
    base = dict(
        event_id="EVT-P-0001",
        category=Category.PAYMENT_FAILURE,
        account_id="ACC-P",
        customer_name="Test User",
        segment=Segment.CONSUMER,
        language_pref=Language.ENGLISH,
        payment_reliability_score=0.7,
        amount_at_risk=1000.0,
        created_at=datetime(2026, 8, 27, 10, 0, 0),
        attempt_count=0,
    )
    base.update(overrides)
    return RevenueEvent(**base)


def diag(root_cause: str, confidence=0.9, method="rule") -> Diagnosis:
    return Diagnosis(event_id="EVT-P-0001", root_cause=root_cause, confidence=confidence, method=method)


def test_policy_is_deterministic_same_inputs_same_output():
    event = make_event(decline_code="card_expired")
    d = diag("expired_card")
    r1 = decide_intervention(event, d)
    r2 = decide_intervention(event, d)
    assert r1.intervention == r2.intervention
    assert r1.policy_key == r2.policy_key


def test_policy_payment_expired_card_sends_update_link():
    event = make_event()
    decision = decide_intervention(event, diag("expired_card"))
    assert decision.intervention == Intervention.SEND_UPDATE_PAYMENT_METHOD_LINK


def test_policy_payment_gateway_timeout_retries_now():
    event = make_event()
    decision = decide_intervention(event, diag("gateway_timeout"))
    assert decision.intervention == Intervention.RETRY_PAYMENT_NOW


def test_policy_payment_escalates_after_three_attempts():
    event = make_event(attempt_count=3)
    decision = decide_intervention(event, diag("insufficient_funds"))
    assert decision.intervention == Intervention.ESCALATE_TO_HUMAN_AGENT


def test_policy_fraud_hold_never_automated_contact():
    event = make_event()
    decision = decide_intervention(event, diag("fraud_hold"))
    assert decision.intervention == Intervention.NO_ACTION
    assert "compliance" in decision.reason.lower()


def test_policy_invoice_disputed_routes_to_escalation_not_contact():
    event = make_event(category=Category.RECEIVABLE_OVERDUE, disputed=True,
                        invoice_id="INV-1", invoice_terms="Net 30", days_overdue=20)
    decision = decide_intervention(event, diag("invoice_disputed", confidence=1.0))
    assert decision.intervention == Intervention.ESCALATE_TO_HUMAN_AGENT
    assert decision.intervention != Intervention.SEND_INVOICE_REMINDER


def test_policy_abandonment_price_sensitivity_first_attempt_offers_discount():
    event = make_event(category=Category.CHECKOUT_ABANDONMENT, cart_value=2000, cart_items=1, attempt_count=0)
    decision = decide_intervention(event, diag("price_sensitivity"))
    assert decision.intervention == Intervention.OFFER_BOUNDED_DISCOUNT


def test_policy_abandonment_stops_after_two_nudges():
    event = make_event(category=Category.CHECKOUT_ABANDONMENT, cart_value=2000, cart_items=1, attempt_count=2)
    decision = decide_intervention(event, diag("technical_friction"))
    assert decision.intervention == Intervention.NO_ACTION


def test_policy_subscription_escalates_after_three_dunning_attempts():
    event = make_event(category=Category.SUBSCRIPTION_RENEWAL, attempt_count=3, dunning_attempt_count=3)
    decision = decide_intervention(event, diag("insufficient_funds"))
    assert decision.intervention == Intervention.ESCALATE_TO_HUMAN_AGENT


def test_policy_receivable_enterprise_escalates_earlier_than_smb():
    enterprise_event = make_event(category=Category.RECEIVABLE_OVERDUE, segment=Segment.ENTERPRISE,
                                   attempt_count=2, days_overdue=30, invoice_id="INV-2", invoice_terms="Net 30")
    smb_event = make_event(category=Category.RECEIVABLE_OVERDUE, segment=Segment.SMB,
                            attempt_count=2, days_overdue=30, invoice_id="INV-3", invoice_terms="Net 30")
    d_ent = decide_intervention(enterprise_event, diag("cashflow_delay"))
    d_smb = decide_intervention(smb_event, diag("cashflow_delay"))
    assert d_ent.intervention == Intervention.ESCALATE_TO_HUMAN_AGENT
    assert d_smb.intervention != Intervention.ESCALATE_TO_HUMAN_AGENT


def test_policy_receivable_promise_to_pay_pending_tracks_not_pressures():
    event = make_event(category=Category.RECEIVABLE_OVERDUE, attempt_count=1,
                        days_overdue=10, invoice_id="INV-4", invoice_terms="Net 15",
                        promise_to_pay_date="2026-09-05")
    decision = decide_intervention(event, diag("promise_to_pay_pending"))
    assert decision.intervention == Intervention.SEND_PROMISE_TO_PAY_REQUEST
