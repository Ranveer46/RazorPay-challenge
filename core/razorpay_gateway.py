"""Razorpay Gateway Client & Adapter.

Provides live sandbox/production capabilities:
- Payment Links creation (for failed payment retries, abandoned cart recovery nudges)
- Invoices creation (for B2B overdue receivables)
- Webhook signature verification

Gracefully degrades:
If RAZORPAY_KEY_ID or RAZORPAY_KEY_SECRET are unset, or if API calls fail,
it safely reports is_configured() == False, allowing callers to seamlessly
fall back to simulated execution.
"""
from __future__ import annotations

import hmac
import hashlib
import logging
import os
import time
from typing import Any, Optional

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

try:
    import razorpay
    RAZORPAY_SDK_AVAILABLE = True
except ImportError:
    razorpay = None  # type: ignore
    RAZORPAY_SDK_AVAILABLE = False


class RazorpayGateway:
    """Thin, fault-tolerant wrapper around the official Razorpay Python SDK."""

    def __init__(
        self,
        key_id: Optional[str] = None,
        key_secret: Optional[str] = None,
        webhook_secret: Optional[str] = None,
    ) -> None:
        self.key_id = key_id or os.getenv("RAZORPAY_KEY_ID", "").strip()
        self.key_secret = key_secret or os.getenv("RAZORPAY_KEY_SECRET", "").strip()
        self.webhook_secret = webhook_secret or os.getenv("RAZORPAY_WEBHOOK_SECRET", "").strip()

        self._client: Optional[Any] = None
        if RAZORPAY_SDK_AVAILABLE and self.key_id and self.key_secret:
            try:
                self._client = razorpay.Client(auth=(self.key_id, self.key_secret))
            except Exception as e:
                logger.warning("Failed to initialize Razorpay Client: %s", e)
                self._client = None

    def is_configured(self) -> bool:
        """Returns True if the Razorpay client is initialized with credentials."""
        return self._client is not None

    def create_payment_link(
        self,
        amount: float,
        customer_name: str,
        description: str,
        reference_id: str,
        customer_email: Optional[str] = None,
        customer_contact: Optional[str] = None,
        expire_hours: int = 48,
    ) -> Optional[dict[str, Any]]:
        """Creates a Razorpay Payment Link in paise (INR).
        Returns a dict with 'short_url', 'id', 'amount', 'status', or None on failure.
        """
        if not self.is_configured():
            return None

        amount_paise = int(round(amount * 100))
        if amount_paise <= 0:
            amount_paise = 100  # Minimum 1 INR for payment link

        payload: dict[str, Any] = {
            "amount": amount_paise,
            "currency": "INR",
            "accept_partial": False,
            "description": description[:250],
            "reference_id": reference_id[:40],
            "customer": {
                "name": customer_name,
                "email": customer_email or f"{reference_id.lower()}@customer.example.com",
                "contact": customer_contact or "+919876543210",
            },
            "notify": {"sms": True, "email": True, "whatsapp": True},
            "reminder_enable": True,
            "expire_by": int(time.time()) + (expire_hours * 3600),
        }

        try:
            assert self._client is not None
            resp = self._client.payment_link.create(payload)
            return {
                "id": resp.get("id"),
                "short_url": resp.get("short_url"),
                "amount": amount,
                "status": resp.get("status"),
                "reference_id": reference_id,
            }
        except Exception as err:
            logger.warning("Razorpay create_payment_link failed for %s: %s", reference_id, err)
            return None

    def create_invoice(
        self,
        customer_name: str,
        amount: float,
        description: str,
        reference_id: str,
        customer_email: Optional[str] = None,
        customer_contact: Optional[str] = None,
        expire_days: int = 7,
    ) -> Optional[dict[str, Any]]:
        """Creates a Razorpay Invoice for B2B receivable recovery.
        Returns dict with 'short_url', 'id', 'status', or None on failure.
        """
        if not self.is_configured():
            return None

        amount_paise = int(round(amount * 100))
        if amount_paise <= 0:
            amount_paise = 100

        payload: dict[str, Any] = {
            "type": "invoice",
            "description": description[:250],
            "customer": {
                "name": customer_name,
                "email": customer_email or f"{reference_id.lower()}@b2b.example.com",
                "contact": customer_contact or "+919876543210",
            },
            "line_items": [
                {
                    "name": description[:40] or "Outstanding Invoice",
                    "amount": amount_paise,
                    "currency": "INR",
                    "quantity": 1,
                }
            ],
            "expire_by": int(time.time()) + (expire_days * 86400),
            "sms_notify": 1,
            "email_notify": 1,
        }

        try:
            assert self._client is not None
            resp = self._client.invoice.create(payload)
            return {
                "id": resp.get("id"),
                "short_url": resp.get("short_url"),
                "amount": amount,
                "status": resp.get("status"),
                "reference_id": reference_id,
            }
        except Exception as err:
            logger.warning("Razorpay create_invoice failed for %s: %s", reference_id, err)
            return None

    def verify_webhook_signature(
        self,
        body: bytes | str,
        signature: str,
        secret: Optional[str] = None,
    ) -> bool:
        """Verifies Razorpay Webhook HMAC-SHA256 signature."""
        webhook_secret = secret or self.webhook_secret
        if not webhook_secret:
            # If no secret configured, fail verification for safety
            return False

        body_bytes = body.encode("utf-8") if isinstance(body, str) else body

        if RAZORPAY_SDK_AVAILABLE and self._client is not None:
            try:
                self._client.utility.verify_webhook_signature(
                    body_bytes.decode("utf-8"), signature, webhook_secret
                )
                return True
            except Exception:
                pass

        # Native HMAC-SHA256 fallback
        expected = hmac.new(
            webhook_secret.encode("utf-8"),
            body_bytes,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)


# Global default instance
gateway = RazorpayGateway()
