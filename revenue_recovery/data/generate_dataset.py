"""Generates a synthetic dataset of revenue-at-risk events across the four
leak categories. Ground-truth recoverability/root-cause fields are attached
for later scoring only — nothing downstream in detect/diagnose/decide should
read them.

Run: python -m data.generate_dataset [--count 250] [--seed 7] [--out data/events.json]
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import uuid
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.models import Category, Language, RevenueEvent, Segment  # noqa: E402

FIRST_NAMES = [
    "Aarav", "Vivaan", "Aditya", "Ishaan", "Reyansh", "Diya", "Ananya", "Saanvi",
    "Priya", "Rahul", "Neha", "Karan", "Pooja", "Vikram", "Sneha", "Arjun",
    "Meera", "Rohan", "Kavya", "Aman", "Divya", "Sanjay", "Ritu", "Manish",
]
LAST_NAMES = [
    "Sharma", "Verma", "Gupta", "Reddy", "Iyer", "Nair", "Singh", "Patel",
    "Mehta", "Joshi", "Kapoor", "Rao", "Bose", "Chatterjee", "Malhotra",
]
COMPANIES = [
    "Bluewave Textiles", "Nimbus Logistics", "Pixel Forge Studios", "Greenleaf Foods",
    "Orbit Retail", "Sundial Analytics", "Kestrel Manufacturing", "Amber Traders",
    "Northwind Exports", "Vertex Components",
]
DECLINE_CODES = [
    ("insufficient_funds", 0.35),
    ("card_expired", 0.15),
    ("do_not_honor", 0.15),
    ("gateway_timeout", 0.12),
    ("fraud_suspected", 0.08),
    ("issuer_unavailable", 0.10),
    ("incorrect_cvv", 0.05),
]
ABANDON_NOTES = [
    "price seemed too high compared to other site, wanted to compare",
    "got distracted by a phone call mid checkout, forgot to come back",
    "shipping cost added at last step, felt surprised and left",
    "coupon code did not apply, gave up",
    "was just browsing, added to cart to save for later",
    "payment page kept spinning and did not load, gave up",
    "wanted to check with spouse before buying something this expensive",
    "found item cheaper on another app mid-checkout",
]
PLAN_NAMES = ["Starter Monthly", "Pro Monthly", "Pro Annual", "Team Monthly", "Business Annual"]
INVOICE_TERMS = ["Net 15", "Net 30", "Net 45", "Net 60"]

random.seed(0)


def weighted_choice(pairs):
    items, weights = zip(*pairs)
    return random.choices(items, weights=weights, k=1)[0]


def rand_name():
    return f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"


def make_base(category: Category, now: datetime, idx: int) -> dict:
    segment = weighted_choice([
        (Segment.CONSUMER, 0.55), (Segment.SMB, 0.30), (Segment.ENTERPRISE, 0.15)
    ])
    reliability = round(random.betavariate(2.5, 1.5) if segment != Segment.ENTERPRISE
                         else random.betavariate(4, 1.2), 2)
    language = weighted_choice([(Language.ENGLISH, 0.5), (Language.HINGLISH, 0.5)]) \
        if segment == Segment.CONSUMER else Language.ENGLISH

    dnd = random.random() < 0.06
    opt_out = random.random() < 0.05
    fraud_hold = False
    disputed = False
    legal_flagged = random.random() < 0.02
    quiet_hours_only_region = random.random() < 0.10
    local_hour = random.randint(0, 23)

    customer_name = rand_name() if segment == Segment.CONSUMER else random.choice(COMPANIES)

    return dict(
        event_id=f"EVT-{idx:04d}-{uuid.uuid4().hex[:6]}",
        category=category,
        account_id=f"ACC-{idx:05d}",
        customer_name=customer_name,
        segment=segment,
        language_pref=language,
        payment_reliability_score=reliability,
        currency="INR",
        created_at=now - timedelta(hours=random.randint(0, 96)),
        dnd=dnd,
        opt_out=opt_out,
        fraud_hold=fraud_hold,
        disputed=disputed,
        legal_flagged=legal_flagged,
        quiet_hours_only_region=quiet_hours_only_region,
        local_hour=local_hour,
        attempt_count=0,
        last_contacted_hours_ago=round(random.uniform(0.5, 72), 1) if random.random() < 0.3 else None,
    )


def gen_payment_failure(now: datetime, idx: int) -> dict:
    base = make_base(Category.PAYMENT_FAILURE, now, idx)
    code = weighted_choice(DECLINE_CODES)
    base["decline_code"] = code
    base["gateway"] = random.choice(["Razorpay", "Stripe", "PayU", "CCAvenue"])
    base["card_last4"] = f"{random.randint(1000, 9999)}"
    base["card_expiry"] = f"{random.randint(1, 12):02d}/{random.choice(['24', '25', '26'])}"
    base["amount_at_risk"] = round(random.uniform(299, 45000), 2)
    base["attempt_count"] = random.choices([0, 1, 2, 3], weights=[0.4, 0.3, 0.2, 0.1])[0]

    if code == "fraud_suspected":
        base["fraud_hold"] = True

    root_cause_map = {
        "insufficient_funds": "insufficient_funds",
        "card_expired": "expired_card",
        "do_not_honor": "issuer_declined",
        "gateway_timeout": "gateway_timeout",
        "fraud_suspected": "fraud_hold",
        "issuer_unavailable": "gateway_timeout",
        "incorrect_cvv": "user_input_error",
    }
    base["ground_truth_root_cause"] = root_cause_map[code]

    recoverable = not base["fraud_hold"] and not base["dnd"] and not base["opt_out"]
    prob = {
        "insufficient_funds": 0.35, "expired_card": 0.55, "issuer_declined": 0.30,
        "gateway_timeout": 0.75, "fraud_hold": 0.05, "user_input_error": 0.70,
    }[base["ground_truth_root_cause"]]
    prob *= (0.6 + 0.4 * base["payment_reliability_score"])
    base["ground_truth_recoverable"] = recoverable
    base["ground_truth_recovery_probability"] = round(min(prob, 0.95), 2) if recoverable else 0.0
    return base


def gen_checkout_abandonment(now: datetime, idx: int) -> dict:
    base = make_base(Category.CHECKOUT_ABANDONMENT, now, idx)
    base["cart_value"] = round(random.uniform(199, 25000), 2)
    base["cart_items"] = random.randint(1, 8)
    base["amount_at_risk"] = base["cart_value"]
    base["abandonment_reason_note"] = random.choice(ABANDON_NOTES)
    base["attempt_count"] = random.choices([0, 1], weights=[0.7, 0.3])[0]

    note = base["abandonment_reason_note"]
    if "price" in note or "cheaper" in note:
        root_cause = "price_sensitivity"
        prob = 0.40
    elif "spinning" in note or "did not load" in note:
        root_cause = "technical_friction"
        prob = 0.65
    elif "shipping" in note:
        root_cause = "hidden_cost_surprise"
        prob = 0.45
    elif "coupon" in note:
        root_cause = "promo_failure"
        prob = 0.55
    elif "distracted" in note or "browsing" in note or "spouse" in note:
        root_cause = "low_intent_or_distraction"
        prob = 0.30
    else:
        root_cause = "unknown"
        prob = 0.25

    base["ground_truth_root_cause"] = root_cause
    recoverable = not base["dnd"] and not base["opt_out"]
    base["ground_truth_recoverable"] = recoverable
    base["ground_truth_recovery_probability"] = round(prob * (0.7 + 0.3 * base["payment_reliability_score"]), 2) if recoverable else 0.0
    return base


def gen_subscription_renewal(now: datetime, idx: int) -> dict:
    base = make_base(Category.SUBSCRIPTION_RENEWAL, now, idx)
    base["plan_name"] = random.choice(PLAN_NAMES)
    base["amount_at_risk"] = round(random.uniform(199, 9999), 2)
    base["renewal_date"] = (now - timedelta(days=random.randint(0, 20))).strftime("%Y-%m-%d")
    dunning_attempt = random.choices([0, 1, 2, 3, 4], weights=[0.35, 0.25, 0.2, 0.12, 0.08])[0]
    base["dunning_attempt_count"] = dunning_attempt
    base["attempt_count"] = dunning_attempt

    code = weighted_choice(DECLINE_CODES)
    base["decline_code"] = code
    root_cause_map = {
        "insufficient_funds": "insufficient_funds", "card_expired": "expired_card",
        "do_not_honor": "issuer_declined", "gateway_timeout": "gateway_timeout",
        "fraud_suspected": "fraud_hold", "issuer_unavailable": "gateway_timeout",
        "incorrect_cvv": "user_input_error",
    }
    base["ground_truth_root_cause"] = root_cause_map[code]
    if code == "fraud_suspected":
        base["fraud_hold"] = True

    recoverable = not base["fraud_hold"] and not base["dnd"] and not base["opt_out"]
    base_prob = {
        "insufficient_funds": 0.30, "expired_card": 0.60, "issuer_declined": 0.25,
        "gateway_timeout": 0.70, "fraud_hold": 0.05, "user_input_error": 0.65,
    }[base["ground_truth_root_cause"]]
    decay = max(0.3, 1 - 0.15 * dunning_attempt)
    prob = base_prob * decay * (0.6 + 0.4 * base["payment_reliability_score"])
    base["ground_truth_recoverable"] = recoverable
    base["ground_truth_recovery_probability"] = round(min(prob, 0.9), 2) if recoverable else 0.0
    return base


def gen_receivable_overdue(now: datetime, idx: int) -> dict:
    base = make_base(Category.RECEIVABLE_OVERDUE, now, idx)
    base["segment"] = weighted_choice([(Segment.SMB, 0.6), (Segment.ENTERPRISE, 0.4)])
    base["customer_name"] = random.choice(COMPANIES)
    base["invoice_id"] = f"INV-{10000 + idx}"
    base["invoice_terms"] = random.choice(INVOICE_TERMS)
    base["days_overdue"] = random.choices(
        [5, 15, 30, 45, 60, 90], weights=[0.25, 0.25, 0.2, 0.15, 0.1, 0.05]
    )[0]
    base["amount_at_risk"] = round(random.uniform(15000, 900000), 2)
    base["attempt_count"] = min(base["days_overdue"] // 15, 4)
    base["disputed"] = random.random() < 0.08
    base["promise_to_pay_date"] = None
    if random.random() < 0.15:
        base["promise_to_pay_date"] = (now + timedelta(days=random.randint(1, 14))).strftime("%Y-%m-%d")

    if base["disputed"]:
        root_cause = "invoice_disputed"
        prob = 0.0
    elif base["promise_to_pay_date"]:
        root_cause = "promise_to_pay_pending"
        prob = 0.75
    elif base["days_overdue"] >= 60:
        root_cause = "chronic_late_payer" if base["payment_reliability_score"] < 0.5 else "cashflow_delay"
        prob = 0.35
    else:
        root_cause = "cashflow_delay"
        prob = 0.60

    base["ground_truth_root_cause"] = root_cause
    recoverable = not base["disputed"] and not base["dnd"] and not base["legal_flagged"]
    base["ground_truth_recoverable"] = recoverable
    base["ground_truth_recovery_probability"] = round(prob * (0.5 + 0.5 * base["payment_reliability_score"]), 2) if recoverable else 0.0
    return base


GENERATORS = {
    Category.PAYMENT_FAILURE: gen_payment_failure,
    Category.CHECKOUT_ABANDONMENT: gen_checkout_abandonment,
    Category.SUBSCRIPTION_RENEWAL: gen_subscription_renewal,
    Category.RECEIVABLE_OVERDUE: gen_receivable_overdue,
}


def generate(count: int, seed: int) -> list[RevenueEvent]:
    random.seed(seed)
    now = datetime(2026, 8, 28, 10, 0, 0)
    categories = list(Category)
    events = []
    for i in range(1, count + 1):
        category = categories[(i - 1) % len(categories)]
        # shuffle order a bit within category cycling for realism
        raw = GENERATORS[category](now, i)
        events.append(RevenueEvent(**raw))
    random.shuffle(events)
    return events


def summarize(events: list[RevenueEvent]) -> str:
    by_cat = Counter(e.category.value for e in events)
    total_at_risk = sum(e.amount_at_risk for e in events)
    dnd_count = sum(1 for e in events if e.dnd or e.opt_out)
    disputed_count = sum(1 for e in events if e.disputed)
    fraud_count = sum(1 for e in events if e.fraud_hold)
    legal_count = sum(1 for e in events if e.legal_flagged)
    unrecoverable = sum(1 for e in events if not e.ground_truth_recoverable)

    lines = [
        f"Generated {len(events)} synthetic events",
        f"Total revenue at risk: Rs {total_at_risk:,.2f}",
        "By category:",
    ]
    for cat, n in by_cat.items():
        cat_total = sum(e.amount_at_risk for e in events if e.category.value == cat)
        lines.append(f"  - {cat:24s} {n:4d} events  Rs {cat_total:,.2f}")
    lines.append(f"Compliance-blocked pool: DND/opt-out={dnd_count} disputed={disputed_count} "
                 f"fraud_hold={fraud_count} legal_flagged={legal_count}")
    lines.append(f"Ground-truth unrecoverable events: {unrecoverable} ({unrecoverable/len(events)*100:.1f}%)")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=240)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--out", type=str, default=str(Path(__file__).parent / "events.json"))
    args = parser.parse_args()

    events = generate(args.count, args.seed)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump([json.loads(e.model_dump_json()) for e in events], f, indent=2, default=str)

    print(summarize(events))
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()
