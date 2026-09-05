"""Sanity tests for detector + diagnoser on synthetic data (not in the
minimum-required test set, but useful smoke coverage for phase 3)."""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.detector import score_event
from core.diagnoser import diagnose
from core.models import Category, Language, RevenueEvent, Segment


def make_event(**overrides) -> RevenueEvent:
    base = dict(
        event_id="EVT-TEST-0001",
        category=Category.PAYMENT_FAILURE,
        account_id="ACC-TEST",
        customer_name="Test User",
        segment=Segment.CONSUMER,
        language_pref=Language.ENGLISH,
        payment_reliability_score=0.7,
        amount_at_risk=1000.0,
        created_at=datetime(2026, 8, 27, 10, 0, 0),
    )
    base.update(overrides)
    return RevenueEvent(**base)


def test_detector_dnd_zeroes_recoverable_amount():
    event = make_event(dnd=True, decline_code="insufficient_funds")
    detection = score_event(event, now=datetime(2026, 8, 28, 10, 0, 0))
    assert detection.recoverable_amount == 0.0


def test_detector_fraud_hold_zeroes_recoverable_amount():
    event = make_event(fraud_hold=True, decline_code="fraud_suspected")
    detection = score_event(event, now=datetime(2026, 8, 28, 10, 0, 0))
    assert detection.recoverable_amount == 0.0
    assert detection.risk_score > 0  # still flagged as at-risk, just not actionable


def test_detector_gateway_timeout_more_recoverable_than_fraud():
    timeout_event = make_event(decline_code="gateway_timeout")
    fraud_event = make_event(decline_code="fraud_suspected")
    now = datetime(2026, 8, 28, 10, 0, 0)
    d1 = score_event(timeout_event, now=now)
    d2 = score_event(fraud_event, now=now)
    assert d1.recoverable_amount > d2.recoverable_amount


def test_diagnoser_payment_rule_based():
    event = make_event(decline_code="card_expired")
    diag = diagnose(event)
    assert diag.root_cause == "expired_card"
    assert diag.method == "rule"
    assert diag.confidence > 0.9


def test_diagnoser_receivable_disputed_short_circuits():
    event = make_event(category=Category.RECEIVABLE_OVERDUE, disputed=True, days_overdue=40,
                        invoice_id="INV-1", invoice_terms="Net 30")
    diag = diagnose(event)
    assert diag.root_cause == "invoice_disputed"
    assert diag.confidence == 1.0


def test_diagnoser_abandonment_keyword_rule_path():
    event = make_event(
        category=Category.CHECKOUT_ABANDONMENT,
        abandonment_reason_note="price seemed too high compared to other site",
        cart_value=1000.0, cart_items=2,
    )
    diag = diagnose(event)
    assert diag.root_cause == "price_sensitivity"
    assert diag.method == "rule"


def test_diagnoser_abandonment_ambiguous_falls_back_gracefully_without_key():
    # Note text designed to dodge every keyword bucket -> forces LLM path,
    # which should degrade gracefully to "other" when no API key is set.
    event = make_event(
        category=Category.CHECKOUT_ABANDONMENT,
        abandonment_reason_note="changed my mind after seeing a review video",
        cart_value=500.0, cart_items=1,
    )
    diag = diagnose(event)
    assert diag.root_cause in {"other", "price_sensitivity", "technical_friction",
                                "hidden_cost_surprise", "promo_failure", "low_intent_or_distraction"}
