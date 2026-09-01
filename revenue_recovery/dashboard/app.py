"""Streamlit dashboard: scorecard headline, risk queue, audit drill-down.

Visual layer only — reads the same scorecard.json / events.json / audit.db
that the batch run and API already produce. No pipeline logic here.

Run: streamlit run dashboard/app.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core.audit import AuditLog
from core.detector import score_event
from core.models import RevenueEvent
from dashboard.styles import (
    CATEGORY_COLOR, CATEGORY_LABEL, COLORS, STAGE_ICON, STATUS_COLOR,
    STATUS_LABEL, format_inr, inject_css,
)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

st.set_page_config(page_title="AI Revenue Recovery Agent", page_icon="💸", layout="wide")
st.markdown(inject_css(), unsafe_allow_html=True)


# ---------------------------------------------------------------- data -----

@st.cache_data
def load_events() -> list[RevenueEvent]:
    path = DATA_DIR / "events.json"
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [RevenueEvent(**r) for r in raw]


@st.cache_data
def load_scorecard() -> dict | None:
    path = DATA_DIR / "scorecard.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


@st.cache_data
def load_outcome_mix(batch_id: str) -> pd.DataFrame:
    """Per-category outcome mix (recovered/blocked/escalated/unresolved),
    read straight from the existing 'measure' stage audit records for this
    batch — no schema changes, just a different read of the same rows."""
    audit = AuditLog(db_path=DATA_DIR / "audit.db")
    trail = audit.get_batch_trail(batch_id)
    audit.close()
    rows = [r["output"] for r in trail if r["stage"] == "measure"]
    if not rows:
        return pd.DataFrame(columns=["category", "final_status", "count"])
    df = pd.DataFrame(rows)[["category", "final_status"]]
    grouped = df.groupby(["category", "final_status"]).size().reset_index(name="count")
    return grouped


@st.cache_data
def load_example_events(batch_id: str) -> dict[str, str]:
    """One example event id per outcome status, for the drill-down quick-pick."""
    audit = AuditLog(db_path=DATA_DIR / "audit.db")
    trail = audit.get_batch_trail(batch_id)
    audit.close()
    examples: dict[str, str] = {}
    for r in trail:
        if r["stage"] != "measure":
            continue
        status = r["output"].get("final_status", "unresolved")
        if status not in examples:
            examples[status] = r["event_id"]
    return examples


events = load_events()
events_by_id = {e.event_id: e for e in events}
scorecard = load_scorecard()

# ---------------------------------------------------------------- header ---

st.markdown('<div class="app-title">💸 AI Revenue Recovery Agent</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="app-subtitle">Detect &rarr; Diagnose &rarr; Decide &rarr; Act &rarr; Log &rarr; '
    'Measure — live batch results on synthetic revenue-at-risk events</div>',
    unsafe_allow_html=True,
)

tab_overview, tab_queue, tab_audit = st.tabs(["📊 Overview", "🎯 Risk Queue", "🧾 Audit Drill-Down"])


# -------------------------------------------------------------- helpers ----

def kpi_card(icon: str, label: str, value: str, accent: str, sub: str = "") -> str:
    sub_html = f'<div class="kpi-sub">{sub}</div>' if sub else ""
    return (
        f'<div class="kpi-card" style="--accent:{accent}">'
        f'<div class="kpi-label">{label}</div>'
        f'<div class="kpi-value"><span class="kpi-icon">{icon}</span>{value}</div>'
        f"{sub_html}</div>"
    )


def reason_panel(title: str, reasons: dict[str, int], accent: str) -> str:
    if not reasons:
        body = '<div class="reason-empty">None recorded in this batch.</div>'
    else:
        max_v = max(reasons.values()) or 1
        rows = []
        for name, count in sorted(reasons.items(), key=lambda x: -x[1]):
            pct = round(100 * count / max_v)
            label = name.replace("_", " ").strip().title()
            rows.append(
                '<div class="reason-row">'
                f'<div class="reason-label">{label}</div>'
                f'<div class="reason-bar-track"><div class="reason-bar-fill" '
                f'style="width:{pct}%;background:{accent}"></div></div>'
                f'<div class="reason-count">{count}</div>'
                "</div>"
            )
        body = "".join(rows)
    return f'<div class="reason-panel"><div class="reason-panel-title">{title}</div>{body}</div>'


# ------------------------------------------------------------- overview ----

with tab_overview:
    if scorecard is None:
        st.warning("No scorecard found. Run `python -m batch.run_batch` first, then refresh.")
    else:
        c1, c2, c3, c4 = st.columns(4)
        c1.markdown(kpi_card("💰", "Total at risk", format_inr(scorecard["total_at_risk"]),
                              COLORS["at_risk"], f"{scorecard['total_events']} events"), unsafe_allow_html=True)
        c2.markdown(kpi_card("✅", "Total recovered", format_inr(scorecard["total_recovered"]),
                              COLORS["recovered"]), unsafe_allow_html=True)
        c3.markdown(kpi_card("📈", "Recovery rate", f"{scorecard['recovery_rate_overall']:.1f}%",
                              COLORS["neutral"], f"avg {scorecard['avg_steps_to_recovery']:.2f} steps/recovery"),
                    unsafe_allow_html=True)
        c4.markdown(kpi_card("🚨", "Escalations", str(scorecard["escalation_count"]),
                              COLORS["escalated"], f"{scorecard['guardrail_blocked_count']} guardrail-blocked"),
                    unsafe_allow_html=True)

        st.markdown('<div class="section-title">Recovery by category</div>', unsafe_allow_html=True)
        cat_df = pd.DataFrame(scorecard["by_category"]).T.reset_index(names="category")
        cat_df["label"] = cat_df["category"].map(CATEGORY_LABEL).fillna(cat_df["category"])
        cat_df = cat_df.sort_values("recovered")

        fig_cat = go.Figure()
        fig_cat.add_trace(go.Bar(
            x=cat_df["recovered"], y=cat_df["label"], orientation="h",
            marker_color=[CATEGORY_COLOR.get(c, COLORS["neutral"]) for c in cat_df["category"]],
            text=[format_inr(v) for v in cat_df["recovered"]], textposition="outside",
            customdata=cat_df[["at_risk", "recovery_rate_pct", "events_recovered", "events"]].values,
            hovertemplate=(
                "<b>%{y}</b><br>Recovered: %{x:,.0f}<br>At risk: %{customdata[0]:,.0f}<br>"
                "Recovery rate: %{customdata[1]:.1f}%<br>Events recovered: %{customdata[2]:.0f}/"
                "%{customdata[3]:.0f}<extra></extra>"
            ),
        ))
        fig_cat.update_layout(
            height=280, margin=dict(l=10, r=60, t=10, b=10),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#E5E9F5"), xaxis=dict(showgrid=True, gridcolor="#28324A", title="Amount recovered (Rs)"),
            yaxis=dict(title=""), showlegend=False,
        )
        st.plotly_chart(fig_cat, width="stretch", config={"displayModeBar": False})

        st.markdown('<div class="section-title">Outcome mix per category</div>', unsafe_allow_html=True)
        mix_df = load_outcome_mix(scorecard["batch_id"])
        if mix_df.empty:
            st.info("No per-event outcome records found for this batch yet.")
        else:
            mix_df["label"] = mix_df["category"].map(CATEGORY_LABEL).fillna(mix_df["category"])
            mix_df["status_label"] = mix_df["final_status"].map(STATUS_LABEL).fillna(mix_df["final_status"])
            fig_mix = go.Figure()
            for status in ["recovered", "escalated", "blocked", "unresolved"]:
                sub = mix_df[mix_df["final_status"] == status]
                if sub.empty:
                    continue
                fig_mix.add_trace(go.Bar(
                    x=sub["count"], y=sub["label"], orientation="h", name=STATUS_LABEL[status],
                    marker_color=STATUS_COLOR[status],
                    hovertemplate=f"<b>%{{y}}</b><br>{STATUS_LABEL[status]}: %{{x}}<extra></extra>",
                ))
            fig_mix.update_layout(
                barmode="stack", height=280, margin=dict(l=10, r=10, t=10, b=10),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#E5E9F5"), xaxis=dict(showgrid=True, gridcolor="#28324A", title="Events"),
                yaxis=dict(title=""), legend=dict(orientation="h", y=1.15, x=0),
            )
            st.plotly_chart(fig_mix, width="stretch", config={"displayModeBar": False})

        st.markdown('<div class="section-title">Guardrails &amp; escalations</div>', unsafe_allow_html=True)
        gc1, gc2 = st.columns(2)
        with gc1:
            st.markdown(
                reason_panel(f"🛡️ Guardrail blocks ({scorecard['guardrail_blocked_count']} events)",
                             scorecard["guardrail_block_reasons"], COLORS["at_risk"]),
                unsafe_allow_html=True,
            )
        with gc2:
            st.markdown(
                reason_panel(f"🚨 Escalations by category ({scorecard['escalation_count']} events)",
                             scorecard["escalation_reasons"], COLORS["escalated"]),
                unsafe_allow_html=True,
            )


# ------------------------------------------------------------ risk queue ---

with tab_queue:
    st.markdown('<div class="section-title">Risk Queue</div>', unsafe_allow_html=True)
    if not events:
        st.info("No events loaded. Run `python -m data.generate_dataset` first.")
    else:
        rows = []
        for e in events:
            d = score_event(e)
            rows.append(dict(
                event_id=e.event_id, category=CATEGORY_LABEL.get(e.category.value, e.category.value),
                category_raw=e.category.value, customer=e.customer_name, segment=e.segment.value,
                amount_at_risk=e.amount_at_risk, risk_score=d.risk_score,
                recoverable_amount=d.recoverable_amount, priority_score=d.priority_score,
            ))
        queue_df = pd.DataFrame(rows)

        fc1, fc2, fc3 = st.columns([2, 2, 3])
        cat_options = sorted(queue_df["category"].unique())
        seg_options = sorted(queue_df["segment"].unique())
        picked_cats = fc1.multiselect("Category", cat_options, default=cat_options)
        picked_segs = fc2.multiselect("Segment", seg_options, default=seg_options)
        fc3.markdown(
            f'<div style="padding-top:1.9rem;color:{COLORS["text_dim"]};font-size:0.85rem;">'
            f"Showing top-priority events first — click column headers to re-sort.</div>",
            unsafe_allow_html=True,
        )

        filtered = queue_df[queue_df["category"].isin(picked_cats) & queue_df["segment"].isin(picked_segs)]
        filtered = filtered.sort_values("priority_score", ascending=False).drop(columns=["category_raw"])

        st.dataframe(
            filtered,
            width="stretch",
            hide_index=True,
            column_config={
                "event_id": st.column_config.TextColumn("Event ID"),
                "category": st.column_config.TextColumn("Category"),
                "customer": st.column_config.TextColumn("Customer"),
                "segment": st.column_config.TextColumn("Segment"),
                "amount_at_risk": st.column_config.NumberColumn("At risk (Rs)", format="₹%,.0f"),
                "risk_score": st.column_config.ProgressColumn("Risk score", min_value=0, max_value=1, format="%.2f"),
                "recoverable_amount": st.column_config.NumberColumn("Recoverable (Rs)", format="₹%,.0f"),
                "priority_score": st.column_config.NumberColumn("Priority", format="%,.0f"),
            },
        )
        st.caption(f"{len(filtered)} of {len(queue_df)} events shown.")


# ------------------------------------------------------- audit drill-down --

with tab_audit:
    st.markdown('<div class="section-title">Audit Trail Drill-Down</div>', unsafe_allow_html=True)

    examples: dict[str, str] = {}
    if scorecard is not None:
        examples = load_example_events(scorecard["batch_id"])

    quick_picks = {
        f"{STATUS_LABEL.get(status, status)} example — {eid}": eid
        for status, eid in examples.items()
    }
    default_id = next(iter(examples.values()), events[0].event_id if events else "")

    pc1, pc2 = st.columns([2, 3])
    with pc1:
        pick_label = st.selectbox("Quick pick", ["— choose an example —"] + list(quick_picks.keys()))
    with pc2:
        typed_id = st.text_input("Or enter an Event ID directly", value="")

    if typed_id.strip():
        event_id = typed_id.strip()
    elif pick_label in quick_picks:
        event_id = quick_picks[pick_label]
    else:
        event_id = default_id

    if event_id:
        audit = AuditLog(db_path=DATA_DIR / "audit.db")
        trail = audit.get_trail(event_id)
        audit.close()

        if not trail:
            st.info("No audit trail for this event yet — run the batch first.")
        else:
            measure = next((r for r in trail if r["stage"] == "measure"), None)
            final_status = measure["output"]["final_status"] if measure else "unresolved"
            src_event = events_by_id.get(event_id)

            header_bits = [f"<b>{event_id}</b>"]
            if src_event:
                header_bits.append(
                    f"{CATEGORY_LABEL.get(src_event.category.value, src_event.category.value)} · "
                    f"{src_event.customer_name} · {format_inr(src_event.amount_at_risk)} at risk"
                )
            st.markdown(
                f'<div style="display:flex;align-items:center;gap:0.8rem;margin-bottom:0.9rem;">'
                f'<span class="badge badge-{final_status}">{STATUS_LABEL.get(final_status, final_status)}</span>'
                f'<span style="color:{COLORS["text_dim"]};font-size:0.92rem;">{" · ".join(header_bits)}</span>'
                f"</div>",
                unsafe_allow_html=True,
            )

            for record in trail:
                stage = record["stage"]
                output = record["output"]
                icon = STAGE_ICON.get(stage, "•")
                dot_color = COLORS["neutral"]
                summary = ""

                if stage == "detect":
                    summary = f"risk score {output.get('risk_score', 0):.2f} · recoverable {format_inr(output.get('recoverable_amount', 0))}"
                elif stage == "diagnose":
                    summary = f"root cause: {output.get('root_cause')} ({output.get('method')}, confidence {output.get('confidence', 0):.2f})"
                elif stage == "decide":
                    summary = f"chose <b>{output.get('intervention')}</b>"
                elif stage == "guardrail":
                    blocked = output.get("blocked", False)
                    dot_color = COLORS["at_risk"] if blocked else COLORS["recovered"]
                    disc = output.get("discount_offered") or 0
                    disc_txt = f" · discount capped at {format_inr(disc)}" if disc else ""
                    summary = f"{'BLOCKED' if blocked else 'passed'} → final: <b>{output.get('final_intervention')}</b>{disc_txt}"
                elif stage == "act":
                    outcome = output.get("outcome")
                    dot_color = {
                        "success": COLORS["recovered"], "escalated": COLORS["escalated"],
                        "failure": COLORS["at_risk"], "skipped": COLORS["at_risk"],
                    }.get(outcome, COLORS["unresolved"])
                    summary = f"{outcome} · recovered {format_inr(output.get('amount_recovered', 0))}"
                elif stage == "measure":
                    dot_color = STATUS_COLOR.get(output.get("final_status"), COLORS["unresolved"])
                    summary = (
                        f"final status <b>{output.get('final_status')}</b> · "
                        f"recovered {format_inr(output.get('amount_recovered', 0))} · "
                        f"{output.get('steps_taken', 0)} step(s)"
                    )

                st.markdown(
                    f'<div class="tl-card" style="--dot-color:{dot_color}">'
                    f'<span class="tl-icon">{icon}</span>'
                    f'<span class="tl-stage">{stage}</span>'
                    f'<span class="tl-summary">{summary}</span>'
                    f"</div>",
                    unsafe_allow_html=True,
                )
                with st.expander("Details", expanded=False):
                    dcol1, dcol2 = st.columns(2)
                    with dcol1:
                        st.caption("Input")
                        st.json(record["input"])
                    with dcol2:
                        st.caption("Output")
                        st.json(record["output"])
                    if record.get("notes"):
                        st.caption(f"Note: {record['notes']}")
