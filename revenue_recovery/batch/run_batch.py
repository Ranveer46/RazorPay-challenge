"""Runs the full recovery loop over the synthetic dataset and prints/saves a
scorecard. This is the "one command" demo path.

Run: python -m batch.run_batch [--events data/events.json] [--out data/scorecard.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.audit import AuditLog  # noqa: E402
from core.guardrails import DiscountBudget, GuardrailContext  # noqa: E402
from core.models import BatchScorecard, RevenueEvent  # noqa: E402
from core.orchestrator import run_batch  # noqa: E402


def print_scorecard(sc: BatchScorecard) -> None:
    print("=" * 72)
    print(f"BATCH SCORECARD  ({sc.batch_id})")
    print("=" * 72)
    print(f"Total events processed:     {sc.total_events}")
    print(f"Total revenue at risk:      Rs {sc.total_at_risk:,.2f}")
    print(f"Total revenue recovered:    Rs {sc.total_recovered:,.2f}")
    print(f"Overall recovery rate:      {sc.recovery_rate_overall:.2f}%")
    print()
    print("Recovery rate by category:")
    print(f"  {'category':24s} {'events':>7s} {'at_risk':>16s} {'recovered':>16s} {'rate%':>8s} {'ev.recov.':>10s}")
    for cat, stats in sc.by_category.items():
        print(f"  {cat:24s} {stats['events']:7d} {stats['at_risk']:16,.2f} {stats['recovered']:16,.2f} "
              f"{stats['recovery_rate_pct']:8.2f} {stats['events_recovered']:10d}")
    print()
    print(f"Guardrail-blocked events:   {sc.guardrail_blocked_count}")
    for reason, count in sorted(sc.guardrail_block_reasons.items(), key=lambda x: -x[1]):
        print(f"    - {reason:28s} {count}")
    print()
    print(f"Escalations:                {sc.escalation_count}")
    for cat, count in sorted(sc.escalation_reasons.items(), key=lambda x: -x[1]):
        print(f"    - {cat:28s} {count}")
    print()
    print(f"Avg steps to recovery:      {sc.avg_steps_to_recovery:.2f}")
    print()
    print("Sample audit trails (top recovered per category):")
    for sample in sc.sample_audit_trails:
        print(f"  - {sample['event_id']} [{sample['category']}] {sample['customer']}: "
              f"Rs {sample['amount_at_risk']:,.2f} at risk -> Rs {sample['amount_recovered']:,.2f} recovered "
              f"({sample['final_status']}, path={sample['intervention_path']})")
    print("=" * 72)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", type=str, default=str(Path(__file__).parent.parent / "data" / "events.json"))
    parser.add_argument("--audit-db", type=str, default=str(Path(__file__).parent.parent / "data" / "audit.db"))
    parser.add_argument("--out", type=str, default=str(Path(__file__).parent.parent / "data" / "scorecard.json"))
    parser.add_argument("--discount-budget", type=float, default=50000.0)
    parser.add_argument("--reset-audit", action="store_true", default=True)
    args = parser.parse_args()

    events_path = Path(args.events)
    if not events_path.exists():
        print(f"No dataset found at {events_path}, generating one first...")
        from data.generate_dataset import generate, summarize
        events = generate(count=240, seed=7)
        events_path.parent.mkdir(parents=True, exist_ok=True)
        events_path.write_text(
            json.dumps([json.loads(e.model_dump_json()) for e in events], indent=2, default=str),
            encoding="utf-8",
        )
        print(summarize(events))
    else:
        raw = json.loads(events_path.read_text(encoding="utf-8"))
        events = [RevenueEvent(**r) for r in raw]

    audit = AuditLog(db_path=args.audit_db, reset=args.reset_audit)
    ctx = GuardrailContext(batch_discount_budget=DiscountBudget(total=args.discount_budget))

    scorecard = run_batch(events, audit, ctx=ctx)
    print_scorecard(scorecard)

    Path(args.out).write_text(scorecard.model_dump_json(indent=2), encoding="utf-8")
    print(f"\nScorecard saved to {args.out}")
    print(f"Full audit trail (SQLite) at {args.audit_db}")
    audit.close()


if __name__ == "__main__":
    main()
