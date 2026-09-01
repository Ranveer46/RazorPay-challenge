"""Guardrails: deterministic stopping rules that run after the policy engine
picks an intervention, and can veto/downgrade/reroute it. Nothing here calls
the LLM. Every guardrail is evaluated and logged on every call, even when it
does not block anything — the audit trail must show the negative results too.

Order of evaluation matters: compliance short-circuits are checked first and
are non-overridable; everything else can only ever make the action *more*
conservative (downgrade/escalate), never add contact the policy didn't ask for.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from core.models import Decision, GuardrailCheck, Intervention, RevenueEvent

# Interventions that put a message in front of the customer (email/SMS/
# WhatsApp/voice). Cooldown and quiet-hours rules only apply to these —
# ESCALATE_TO_HUMAN_AGENT and NO_ACTION never contact the customer directly,
# and PAYMENT retries are silent/system-side.
CUSTOMER_CONTACT_INTERVENTIONS = {
    Intervention.SEND_UPDATE_PAYMENT_METHOD_LINK,
    Intervention.SEND_CART_RECOVERY_NUDGE,
    Intervention.OFFER_BOUNDED_DISCOUNT,
    Intervention.SEND_DUNNING_REMINDER,
    Intervention.SEND_INVOICE_REMINDER,
    Intervention.SEND_PROMISE_TO_PAY_REQUEST,
}

DISCOUNT_INTERVENTIONS = {Intervention.OFFER_BOUNDED_DISCOUNT}


@dataclass
class DiscountBudget:
    """Mutable, shared across a batch run so the discount cap is enforced
    cumulatively, not just per event."""
    total: float
    spent: float = 0.0

    @property
    def remaining(self) -> float:
        return max(0.0, self.total - self.spent)

    def try_spend(self, amount: float) -> bool:
        if amount <= self.remaining:
            self.spent += amount
            return True
        return False


@dataclass
class GuardrailContext:
    max_attempts: int = 4
    cooldown_hours: float = 6.0
    quiet_hours_start: int = 9
    quiet_hours_end: int = 20
    per_event_discount_cap_pct: float = 0.15
    per_event_discount_cap_abs: float = 2000.0
    batch_discount_budget: DiscountBudget = field(
        default_factory=lambda: DiscountBudget(total=50000.0)
    )
    now_hour: int | None = None  # override for testing; else uses event.local_hour


def evaluate_guardrails(
    event: RevenueEvent, decision: Decision, ctx: GuardrailContext | None = None,
) -> Decision:
    """Runs every guardrail against (event, decision) and returns a new
    Decision — same intervention if nothing fired, or a downgraded/escalated
    one if something did. `decision.guardrail_checks` always lists every
    check that ran, blocked or not."""
    ctx = ctx or GuardrailContext()
    checks: list[GuardrailCheck] = []
    intervention = decision.intervention
    blocked = False

    # 1. Compliance short-circuit — hard, non-overridable, checked first.
    compliance_reason = None
    if event.disputed:
        compliance_reason = "invoice disputed"
    elif event.fraud_hold:
        compliance_reason = "fraud hold on account"
    elif event.legal_flagged:
        compliance_reason = "account legal-flagged"

    if compliance_reason:
        checks.append(GuardrailCheck(
            name="compliance_short_circuit", blocked=True,
            reason=f"{compliance_reason} -> no automated contact, routed to human agent",
        ))
        intervention = Intervention.ESCALATE_TO_HUMAN_AGENT
        blocked = True
    else:
        checks.append(GuardrailCheck(
            name="compliance_short_circuit", blocked=False,
            reason="no dispute/fraud/legal flag set",
        ))

    # 2. DND / opt-out — hard stop, no override, no escalation (nothing wrong
    #    with the account, the customer just asked not to be contacted).
    if not blocked:
        if event.dnd or event.opt_out:
            checks.append(GuardrailCheck(
                name="dnd_opt_out", blocked=True,
                reason="customer is on DND list or has opted out of contact",
            ))
            intervention = Intervention.NO_ACTION
            blocked = True
        else:
            checks.append(GuardrailCheck(
                name="dnd_opt_out", blocked=False, reason="customer is contactable",
            ))
    else:
        checks.append(GuardrailCheck(
            name="dnd_opt_out", blocked=False, reason="skipped: already short-circuited above",
        ))

    # 3. Max attempts — force escalation instead of yet another automated try.
    if not blocked:
        if event.attempt_count >= ctx.max_attempts and intervention not in (
            Intervention.NO_ACTION, Intervention.ESCALATE_TO_HUMAN_AGENT,
        ):
            checks.append(GuardrailCheck(
                name="max_attempts", blocked=True,
                reason=f"attempt_count={event.attempt_count} >= max_attempts={ctx.max_attempts} "
                       f"-> escalate instead of retrying",
            ))
            intervention = Intervention.ESCALATE_TO_HUMAN_AGENT
            blocked = True
        else:
            checks.append(GuardrailCheck(
                name="max_attempts", blocked=False,
                reason=f"attempt_count={event.attempt_count} < max_attempts={ctx.max_attempts}",
            ))
    else:
        checks.append(GuardrailCheck(name="max_attempts", blocked=False, reason="skipped: already blocked above"))

    # 4. Cooldown window — only relevant for customer-contact interventions.
    if not blocked and intervention in CUSTOMER_CONTACT_INTERVENTIONS:
        if event.last_contacted_hours_ago is not None and event.last_contacted_hours_ago < ctx.cooldown_hours:
            checks.append(GuardrailCheck(
                name="cooldown_window", blocked=True,
                reason=f"last contacted {event.last_contacted_hours_ago}h ago, "
                       f"cooldown is {ctx.cooldown_hours}h -> hold, no contact yet",
            ))
            intervention = Intervention.NO_ACTION
            blocked = True
        else:
            checks.append(GuardrailCheck(
                name="cooldown_window", blocked=False,
                reason=f"last_contacted_hours_ago={event.last_contacted_hours_ago} clears "
                       f"{ctx.cooldown_hours}h cooldown",
            ))
    else:
        checks.append(GuardrailCheck(
            name="cooldown_window", blocked=False,
            reason="not applicable: intervention doesn't contact the customer, or already blocked",
        ))

    # 5. Quiet hours / DND time window — regional flag + local hour.
    if not blocked and intervention in CUSTOMER_CONTACT_INTERVENTIONS:
        local_hour = ctx.now_hour if ctx.now_hour is not None else event.local_hour
        in_quiet_window = not (ctx.quiet_hours_start <= local_hour < ctx.quiet_hours_end)
        if event.quiet_hours_only_region and in_quiet_window:
            checks.append(GuardrailCheck(
                name="quiet_hours", blocked=True,
                reason=f"local_hour={local_hour} outside allowed window "
                       f"[{ctx.quiet_hours_start}-{ctx.quiet_hours_end}) for a quiet-hours-enforced region -> hold",
            ))
            intervention = Intervention.NO_ACTION
            blocked = True
        else:
            checks.append(GuardrailCheck(
                name="quiet_hours", blocked=False,
                reason=f"local_hour={local_hour} within allowed contact window "
                       f"or region has no quiet-hours restriction",
            ))
    else:
        checks.append(GuardrailCheck(
            name="quiet_hours", blocked=False,
            reason="not applicable: intervention doesn't contact the customer, or already blocked",
        ))

    # 6. Discount / waiver cap — per-event cap and shared batch budget.
    discount_offered = 0.0
    if not blocked and intervention in DISCOUNT_INTERVENTIONS:
        per_event_cap = min(
            event.amount_at_risk * ctx.per_event_discount_cap_pct,
            ctx.per_event_discount_cap_abs,
        )
        if ctx.batch_discount_budget.remaining <= 0:
            checks.append(GuardrailCheck(
                name="discount_cap", blocked=True,
                reason=f"batch discount budget exhausted (remaining=Rs {ctx.batch_discount_budget.remaining:.2f}) "
                       f"-> downgrade to plain nudge, no discount",
            ))
            intervention = Intervention.SEND_CART_RECOVERY_NUDGE
        elif ctx.batch_discount_budget.try_spend(per_event_cap):
            discount_offered = per_event_cap
            checks.append(GuardrailCheck(
                name="discount_cap", blocked=False,
                reason=f"discount capped at Rs {per_event_cap:.2f} "
                       f"(min of {ctx.per_event_discount_cap_pct*100:.0f}% of amount and "
                       f"Rs {ctx.per_event_discount_cap_abs:.2f} flat cap); "
                       f"batch budget remaining after: Rs {ctx.batch_discount_budget.remaining:.2f}",
            ))
        else:
            checks.append(GuardrailCheck(
                name="discount_cap", blocked=True,
                reason=f"full per-event cap of Rs {per_event_cap:.2f} exceeds remaining batch budget "
                       f"(Rs {ctx.batch_discount_budget.remaining:.2f}) -> downgrade to plain nudge, no discount",
            ))
            intervention = Intervention.SEND_CART_RECOVERY_NUDGE
    else:
        checks.append(GuardrailCheck(
            name="discount_cap", blocked=False,
            reason="not applicable: intervention does not include a discount",
        ))

    reason = decision.reason
    if intervention != decision.intervention:
        reason = f"{decision.reason} | overridden by guardrails to {intervention.value}"

    return Decision(
        event_id=decision.event_id,
        intervention=intervention,
        policy_key=decision.policy_key,
        attempt_number=decision.attempt_number,
        reason=reason,
        guardrail_checks=checks,
        blocked=any(c.blocked for c in checks),
        discount_offered=discount_offered,
    )
