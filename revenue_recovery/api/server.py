"""FastAPI surface over the revenue recovery pipeline.

Run: uvicorn api.server:app --reload --port 8000
"""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from typing import Union

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from core.audit import AuditLog  # noqa: E402
from core.detector import score_event  # noqa: E402
from core.diagnoser import diagnose  # noqa: E402
from core.guardrails import DiscountBudget, GuardrailContext  # noqa: E402
from core.models import BatchScorecard, Decision, Detection, RevenueEvent  # noqa: E402
from core.orchestrator import process_event, run_batch  # noqa: E402
from core.policy import decide_intervention  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

app = FastAPI(title="AI Revenue Recovery Agent", version="0.1.0")

_store: dict[str, RevenueEvent] = {}
_audit = AuditLog(db_path=DATA_DIR / "audit_api.db")
_scorecards: dict[str, BatchScorecard] = {}
_guardrail_ctx = GuardrailContext(batch_discount_budget=DiscountBudget(total=50000.0))


@app.on_event("startup")
def _load_default_dataset():
    events_path = DATA_DIR / "events.json"
    if events_path.exists():
        raw = json.loads(events_path.read_text(encoding="utf-8"))
        for r in raw:
            event = RevenueEvent(**r)
            _store[event.event_id] = event


class IngestRequest(BaseModel):
    events: Union[RevenueEvent, list[RevenueEvent]]


@app.post("/events/ingest")
def ingest_events(payload: IngestRequest):
    events = payload.events if isinstance(payload.events, list) else [payload.events]
    for e in events:
        _store[e.event_id] = e
    return {"ingested": len(events), "total_in_store": len(_store)}


@app.get("/risk/queue")
def risk_queue(limit: int = 50):
    scored: list[tuple[Detection, RevenueEvent]] = [
        (score_event(e), e) for e in _store.values()
    ]
    scored.sort(key=lambda pair: pair[0].priority_score, reverse=True)
    return [
        {
            "event_id": e.event_id,
            "category": e.category.value,
            "customer_name": e.customer_name,
            "segment": e.segment.value,
            "amount_at_risk": e.amount_at_risk,
            "risk_score": d.risk_score,
            "recoverable_amount": d.recoverable_amount,
            "priority_score": d.priority_score,
        }
        for d, e in scored[:limit]
    ]


@app.post("/recover/{event_id}/execute")
def recover_execute(event_id: str):
    event = _store.get(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail=f"event {event_id} not found")
    outcome = process_event(event, _audit, _guardrail_ctx)
    diagnosis = diagnose(event)
    decision = decide_intervention(event, diagnosis)
    return {
        "event_id": event_id,
        "diagnosis": diagnosis.model_dump(),
        "decision": decision.model_dump(),
        "outcome": outcome.model_dump(),
    }


@app.get("/audit/{event_id}")
def audit_trail(event_id: str):
    trail = _audit.get_trail(event_id)
    if not trail:
        raise HTTPException(status_code=404, detail=f"no audit trail for event {event_id}")
    return trail


class BatchRunRequest(BaseModel):
    discount_budget: float = 50000.0


@app.post("/batch/run")
def batch_run(payload: BatchRunRequest | None = None):
    if not _store:
        raise HTTPException(status_code=400, detail="no events loaded; POST /events/ingest first")
    budget = payload.discount_budget if payload else 50000.0
    ctx = GuardrailContext(batch_discount_budget=DiscountBudget(total=budget))
    batch_id = f"BATCH-{uuid.uuid4().hex[:8]}"
    scorecard = run_batch(list(_store.values()), _audit, ctx=ctx, batch_id=batch_id)
    _scorecards[batch_id] = scorecard
    return scorecard.model_dump()


@app.get("/metrics/batch/{batch_id}")
def batch_metrics(batch_id: str):
    scorecard = _scorecards.get(batch_id)
    if scorecard is None:
        raise HTTPException(status_code=404, detail=f"no scorecard for batch {batch_id}")
    total_events = scorecard.total_events
    return {
        "batch_id": batch_id,
        "total_at_risk": scorecard.total_at_risk,
        "total_recovered": scorecard.total_recovered,
        "recovery_rate_overall": scorecard.recovery_rate_overall,
        "recovery_rate_by_category": {
            cat: stats["recovery_rate_pct"] for cat, stats in scorecard.by_category.items()
        },
        "escalation_rate_pct": round(100 * scorecard.escalation_count / total_events, 2) if total_events else 0.0,
        "guardrail_block_rate_pct": round(100 * scorecard.guardrail_blocked_count / total_events, 2) if total_events else 0.0,
        "avg_steps_to_recovery": scorecard.avg_steps_to_recovery,
    }


@app.get("/")
def root():
    return {
        "service": "AI Revenue Recovery Agent",
        "events_loaded": len(_store),
        "endpoints": [
            "POST /events/ingest", "GET /risk/queue", "POST /recover/{event_id}/execute",
            "GET /audit/{event_id}", "POST /batch/run", "GET /metrics/batch/{batch_id}",
        ],
    }
