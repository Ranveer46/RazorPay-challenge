"""Composer: turns a chosen intervention into an actual outbound message via
the Anthropic API, in English or Hinglish. This is the one place language
generation is allowed to be creative — WHETHER and HOW MUCH to act was
already locked in by policy.py + guardrails.py before this module runs.

Falls back to a deterministic templated message when no API key is set, so
the batch demo still runs end-to-end offline.
"""
from __future__ import annotations

from core.llm_client import LLMUnavailable, call as llm_call
from core.models import Channel, Decision, Intervention, Language, RevenueEvent

INTERVENTION_CHANNEL = {
    Intervention.RETRY_PAYMENT_NOW: Channel.PAYMENT_RETRY,
    Intervention.RETRY_PAYMENT_DELAYED: Channel.PAYMENT_RETRY,
    Intervention.MANDATE_RETRY_SEQUENCE: Channel.PAYMENT_RETRY,
    Intervention.SEND_UPDATE_PAYMENT_METHOD_LINK: Channel.SMS,
    Intervention.SEND_CART_RECOVERY_NUDGE: Channel.WHATSAPP,
    Intervention.OFFER_BOUNDED_DISCOUNT: Channel.WHATSAPP,
    Intervention.SEND_DUNNING_REMINDER: Channel.EMAIL,
    Intervention.SEND_INVOICE_REMINDER: Channel.EMAIL,
    Intervention.SEND_PROMISE_TO_PAY_REQUEST: Channel.EMAIL,
    Intervention.ESCALATE_TO_HUMAN_AGENT: Channel.NONE,
    Intervention.NO_ACTION: Channel.NONE,
}

_INTERVENTION_INTENT = {
    Intervention.SEND_UPDATE_PAYMENT_METHOD_LINK:
        "Ask the customer to update their expired/failing payment method, with a sense of ease not alarm.",
    Intervention.SEND_CART_RECOVERY_NUDGE:
        "Gently remind the customer they left items in their cart and invite them back, no pressure.",
    Intervention.OFFER_BOUNDED_DISCOUNT:
        "Remind the customer about their cart and offer them a small discount of Rs {discount:.0f} to complete checkout.",
    Intervention.SEND_DUNNING_REMINDER:
        "Let the customer know their subscription payment failed and ask them to retry or update payment details.",
    Intervention.SEND_INVOICE_REMINDER:
        "Politely remind a business customer that invoice {invoice_id} for Rs {amount:.0f} is overdue.",
    Intervention.SEND_PROMISE_TO_PAY_REQUEST:
        "Ask a business customer to confirm or share a specific date by which they will pay invoice {invoice_id}.",
}

SYSTEM_PROMPT = (
    "You write short outbound recovery messages for a fintech revenue-recovery "
    "system. Constraints: under 60 words, one clear call to action, no false "
    "urgency, no threats, respectful tone. If asked for Hinglish, write natural "
    "colloquial Hindi-English code-mixed text in Latin script, the way a young "
    "Indian professional would actually text — not a literal translation. "
    "Output ONLY the message text, nothing else."
)

_TEMPLATES = {
    (Intervention.SEND_UPDATE_PAYMENT_METHOD_LINK, Language.ENGLISH):
        "Hi {name}, your payment for Rs {amount:.0f} didn't go through. Please update your "
        "payment method to complete it: [update-link]",
    (Intervention.SEND_UPDATE_PAYMENT_METHOD_LINK, Language.HINGLISH):
        "Hi {name}, aapka payment of Rs {amount:.0f} fail ho gaya. Please payment method "
        "update kar dijiye yahan: [update-link]",
    (Intervention.SEND_CART_RECOVERY_NUDGE, Language.ENGLISH):
        "Hi {name}, you left some items in your cart worth Rs {amount:.0f}. Come back "
        "and finish checkout whenever you're ready: [cart-link]",
    (Intervention.SEND_CART_RECOVERY_NUDGE, Language.HINGLISH):
        "Hi {name}, aapka cart abhi bhi ready hai, Rs {amount:.0f} ka. Jab time mile "
        "checkout complete kar lijiye: [cart-link]",
    (Intervention.OFFER_BOUNDED_DISCOUNT, Language.ENGLISH):
        "Hi {name}, your cart worth Rs {amount:.0f} is waiting. Here's Rs {discount:.0f} off "
        "if you check out in the next 24 hours: [cart-link]",
    (Intervention.OFFER_BOUNDED_DISCOUNT, Language.HINGLISH):
        "Hi {name}, aapka cart Rs {amount:.0f} ka wait kar raha hai. Agle 24 hours mein "
        "checkout kijiye aur Rs {discount:.0f} off paayiye: [cart-link]",
    (Intervention.SEND_DUNNING_REMINDER, Language.ENGLISH):
        "Hi {name}, your subscription renewal payment of Rs {amount:.0f} failed. Retry "
        "now to avoid losing access: [retry-link]",
    (Intervention.SEND_DUNNING_REMINDER, Language.HINGLISH):
        "Hi {name}, aapka subscription renewal payment (Rs {amount:.0f}) fail ho gaya. "
        "Access na jaaye isliye retry kar lijiye: [retry-link]",
    (Intervention.SEND_INVOICE_REMINDER, Language.ENGLISH):
        "Hi {name}, invoice {invoice_id} for Rs {amount:.0f} is now overdue. Please "
        "arrange payment at your earliest convenience.",
    (Intervention.SEND_PROMISE_TO_PAY_REQUEST, Language.ENGLISH):
        "Hi {name}, could you confirm a date by which invoice {invoice_id} (Rs {amount:.0f}) "
        "will be settled? Happy to work around your cycle.",
}


def _fallback_message(event: RevenueEvent, decision: Decision) -> str:
    key = (decision.intervention, event.language_pref)
    template = _TEMPLATES.get(key) or _TEMPLATES.get((decision.intervention, Language.ENGLISH))
    if not template:
        return ""
    return template.format(
        name=event.customer_name,
        amount=event.amount_at_risk,
        discount=decision.discount_offered,
        invoice_id=event.invoice_id or "",
    )


def compose_message(event: RevenueEvent, decision: Decision) -> tuple[str, str | None, str | None]:
    """Returns (message_text, llm_prompt_or_none, llm_response_or_none)."""
    intent_template = _INTERVENTION_INTENT.get(decision.intervention)
    if intent_template is None:
        return "", None, None  # no customer-facing message for this intervention

    intent = intent_template.format(
        discount=decision.discount_offered, invoice_id=event.invoice_id or "",
        amount=event.amount_at_risk,
    )
    register = "Hinglish" if event.language_pref == Language.HINGLISH else "plain English"
    user_prompt = (
        f"Write the message in {register}.\n"
        f"Customer: {event.customer_name} ({event.segment.value})\n"
        f"Amount: Rs {event.amount_at_risk:.0f}\n"
        f"Intent: {intent}"
    )

    try:
        response = llm_call(SYSTEM_PROMPT, user_prompt, max_tokens=150)
        if response:
            return response, f"SYSTEM: {SYSTEM_PROMPT}\nUSER: {user_prompt}", response
    except LLMUnavailable:
        pass

    return _fallback_message(event, decision), None, None


def channel_for(intervention: Intervention) -> Channel:
    return INTERVENTION_CHANNEL.get(intervention, Channel.NONE)
