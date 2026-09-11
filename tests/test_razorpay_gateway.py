"""Tests for the Razorpay Gateway client, fallback behavior, and webhook handling."""
from __future__ import annotations

import hmac
import hashlib
import json
from datetime import datetime

from fastapi.testclient import TestClient

from api.server import app
from core.models import (
    Category, Decision, Intervention, RevenueEvent, Segment,
)
from core.executor import execute
from core.razorpay_gateway import RazorpayGateway


def test_gateway_offline_mode_when_no_keys():
    """Without keys, gateway.is_configured() must be False and methods return None gracefully."""
    gw = RazorpayGateway(key_id="", key_secret="")
    assert not gw.is_configured()
    assert gw.create_payment_link(100.0, "Test", "Desc", "REF1") is None
    assert gw.create_invoice("Test", 500.0, "Desc", "REF2") is None


def test_webhook_signature_verification():
    """Tests cryptographic HMAC-SHA256 signature verification."""
    secret = "test_webhook_secret_xyz"
    body = json.dumps({"event": "payment.failed", "id": "evt_123"}).encode("utf-8")
    expected_sig = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()

    gw = RazorpayGateway(key_id="", key_secret="", webhook_secret=secret)
    assert gw.verify_webhook_signature(body, expected_sig)
    assert not gw.verify_webhook_signature(body, "invalid_signature")


def test_executor_enriches_message_with_demo_link_when_offline():
    """When offline, executor should replace [cart-link] with realistic demo rzp link."""
    event = RevenueEvent(
        event_id="EVT-TEST-001",
        category=Category.CHECKOUT_ABANDONMENT,
        account_id="acc_test",
        customer_name="Aarav Sharma",
        segment=Segment.CONSUMER,
        payment_reliability_score=0.8,
        amount_at_risk=2500.0,
        created_at=datetime.utcnow(),
    )
    decision = Decision(
        event_id=event.event_id,
        intervention=Intervention.SEND_CART_RECOVERY_NUDGE,
        policy_key="test_policy",
        attempt_number=1,
        reason="abandoned cart",
    )
    raw_message = "Hi Aarav, finish checkout: [cart-link]"
    steps = execute(event, decision, raw_message)
    assert len(steps) == 1
    assert "https://rzp.io/l/evt-test-001" in steps[0].message


def test_api_razorpay_webhook_ingests_failed_payment():
    """Tests the /webhook/razorpay endpoint ingests a payment.failed payload."""
    client = TestClient(app)
    payload = {
        "event": "payment.failed",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_test123",
                    "amount": 250000,  # 2500 INR in paise
                    "email": "riya.verma@example.com",
                    "error_code": "BAD_REQUEST_ERROR",
                }
            }
        },
    }
    response = client.post("/webhook/razorpay", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ingested_and_processed"
    assert data["event_type"] == "payment.failed"
    assert data["event_id"].startswith("RZP-")
