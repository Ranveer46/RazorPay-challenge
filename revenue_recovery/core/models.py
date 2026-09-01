"""Pydantic data models shared across the revenue recovery pipeline."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class Category(str, Enum):
    PAYMENT_FAILURE = "payment_failure"
    CHECKOUT_ABANDONMENT = "checkout_abandonment"
    SUBSCRIPTION_RENEWAL = "subscription_renewal"
    RECEIVABLE_OVERDUE = "receivable_overdue"


class Segment(str, Enum):
    CONSUMER = "consumer"
    SMB = "smb"
    ENTERPRISE = "enterprise"


class Language(str, Enum):
    ENGLISH = "english"
    HINGLISH = "hinglish"


class Intervention(str, Enum):
    RETRY_PAYMENT_NOW = "retry_payment_now"
    RETRY_PAYMENT_DELAYED = "retry_payment_delayed"
    SEND_UPDATE_PAYMENT_METHOD_LINK = "send_update_payment_method_link"
    SEND_CART_RECOVERY_NUDGE = "send_cart_recovery_nudge"
    OFFER_BOUNDED_DISCOUNT = "offer_bounded_discount"
    SEND_DUNNING_REMINDER = "send_dunning_reminder"
    ESCALATE_TO_HUMAN_AGENT = "escalate_to_human_agent"
    SEND_INVOICE_REMINDER = "send_invoice_reminder"
    SEND_PROMISE_TO_PAY_REQUEST = "send_promise_to_pay_request"
    MANDATE_RETRY_SEQUENCE = "mandate_retry_sequence"
    NO_ACTION = "no_action"


class Channel(str, Enum):
    EMAIL = "email"
    SMS = "sms"
    WHATSAPP = "whatsapp"
    VOICE = "voice"
    PAYMENT_RETRY = "payment_retry"
    NONE = "none"


class RevenueEvent(BaseModel):
    """A single revenue-at-risk event fed into the agent. No hidden/ground-truth
    fields are read by detector/diagnoser/policy/guardrails — only by the
    executor's outcome simulator and the scoring/measurement layer."""

    event_id: str
    category: Category
    account_id: str
    customer_name: str
    segment: Segment
    language_pref: Language = Language.ENGLISH
    payment_reliability_score: float = Field(ge=0, le=1)
    amount_at_risk: float
    currency: str = "INR"
    created_at: datetime

    # Compliance / contactability flags
    dnd: bool = False
    opt_out: bool = False
    disputed: bool = False
    fraud_hold: bool = False
    legal_flagged: bool = False
    quiet_hours_only_region: bool = False
    local_hour: int = Field(default=12, ge=0, le=23)

    # Attempt history
    attempt_count: int = 0
    last_contacted_hours_ago: Optional[float] = None

    # Category-specific optional fields
    decline_code: Optional[str] = None
    gateway: Optional[str] = None
    card_last4: Optional[str] = None
    card_expiry: Optional[str] = None

    cart_value: Optional[float] = None
    cart_items: Optional[int] = None
    abandonment_reason_note: Optional[str] = None

    dunning_attempt_count: Optional[int] = None
    plan_name: Optional[str] = None
    renewal_date: Optional[str] = None

    invoice_id: Optional[str] = None
    days_overdue: Optional[int] = None
    invoice_terms: Optional[str] = None
    promise_to_pay_date: Optional[str] = None

    # Hidden ground truth — used only by executor's outcome model & scorer
    ground_truth_recoverable: bool = True
    ground_truth_recovery_probability: float = Field(default=0.5, ge=0, le=1)
    ground_truth_root_cause: str = "unknown"


class Detection(BaseModel):
    event_id: str
    risk_score: float
    recoverable_amount: float
    priority_score: float
    reasons: list[str] = Field(default_factory=list)


class Diagnosis(BaseModel):
    event_id: str
    root_cause: str
    confidence: float
    method: str  # "rule" | "llm"
    evidence: str = ""
    llm_prompt: Optional[str] = None
    llm_response: Optional[str] = None


class GuardrailCheck(BaseModel):
    name: str
    blocked: bool
    reason: str


class Decision(BaseModel):
    event_id: str
    intervention: Intervention
    policy_key: str
    attempt_number: int
    reason: str
    guardrail_checks: list[GuardrailCheck] = Field(default_factory=list)
    blocked: bool = False
    discount_offered: float = 0.0


class ActionStep(BaseModel):
    event_id: str
    step_index: int
    channel: Channel
    intervention: Intervention
    message: Optional[str] = None
    message_language: Optional[Language] = None
    outcome: str  # "success" | "failure" | "no_response" | "escalated" | "skipped"
    amount_recovered: float = 0.0
    discount_offered: float = 0.0
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class AuditRecord(BaseModel):
    id: Optional[int] = None
    event_id: str
    stage: str  # detect | diagnose | decide | guardrail | act | measure
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    notes: str = ""


class EventOutcome(BaseModel):
    event_id: str
    category: Category
    amount_at_risk: float
    amount_recovered: float
    recovered: bool
    steps_taken: int
    intervention_path: list[Intervention] = Field(default_factory=list)
    escalated: bool = False
    blocked_by_guardrail: bool = False
    guardrail_block_reasons: list[str] = Field(default_factory=list)
    final_status: str = "unresolved"  # recovered | escalated | blocked | unresolved


class BatchScorecard(BaseModel):
    batch_id: str
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    total_events: int
    total_at_risk: float
    total_recovered: float
    recovery_rate_overall: float
    by_category: dict[str, dict[str, Any]] = Field(default_factory=dict)
    guardrail_blocked_count: int
    guardrail_block_reasons: dict[str, int] = Field(default_factory=dict)
    escalation_count: int
    escalation_reasons: dict[str, int] = Field(default_factory=dict)
    avg_steps_to_recovery: float
    sample_audit_trails: list[dict[str, Any]] = Field(default_factory=list)
