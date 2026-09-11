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
    STATUS_LABEL, format_inr, inject_css, pipeline_stepper,
)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

st.set_page_config(
    page_title="Razorpay AI Revenue Recovery Agent",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)
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

# --------------------------------------------------------------- sidebar ---

with st.sidebar:
    st.markdown(
        f'<div style="font-size:1.15rem;font-weight:800;letter-spacing:-0.02em;margin-bottom:0.2rem;display:flex;align-items:center;gap:0.5rem;">'
        f'<span style="color:#3B82F6;">⚡</span> Razorpay Agent</div>'
        f'<div style="font-size:0.75rem;color:{COLORS["text_dim"]};margin-bottom:1.4rem;">Autonomous Revenue Recovery Console</div>',
        unsafe_allow_html=True,
    )

    if scorecard:
        st.markdown(
            f'<div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);border-radius:12px;padding:0.9rem;margin-bottom:1.2rem;">'
            f'<div style="font-size:0.72rem;font-weight:700;color:{COLORS["text_dim"]};text-transform:uppercase;letter-spacing:0.06em;">Active Batch</div>'
            f'<div style="font-size:0.95rem;font-weight:700;color:#F8FAFC;margin:0.25rem 0;" class="mono-font">{scorecard.get("batch_id", "N/A")}</div>'
            f'<div style="font-size:0.76rem;color:{COLORS["text_dim"]};">{scorecard.get("total_events", 0)} events analyzed</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.markdown(
        f'<div style="font-size:0.75rem;font-weight:800;color:#64748B;letter-spacing:0.08em;text-transform:uppercase;margin-bottom:0.7rem;">System Guardians</div>',
        unsafe_allow_html=True,
    )

    guardians = [
        ("Deterministic Policy", "100% Auditable", COLORS["recovered"]),
        ("Safety Guardrails", "Non-Overridable", COLORS["neutral"]),
        ("LLM Generative Layer", "Fault-Tolerant Fallback", COLORS["recovered"]),
        ("Compliance Ledger", "ACID SQLite", COLORS["neutral"]),
    ]

    for title, desc, col in guardians:
        st.markdown(
            f'<div style="display:flex;align-items:center;justify-content:space-between;padding:0.45rem 0;border-bottom:1px solid rgba(255,255,255,0.05);">'
            f'<span style="font-size:0.8rem;color:#E2E8F0;">{title}</span>'
            f'<span style="font-size:0.72rem;font-weight:700;color:{col};">{desc}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height: 1.5rem;'></div>", unsafe_allow_html=True)
    if st.button("🔄 Refresh Data & Metrics", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.markdown(
        f'<div style="font-size:0.72rem;color:#475569;text-align:center;margin-top:2rem;">'
        f'Razorpay Challenge &middot; High-Reliability Agent'
        f'</div>',
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------- header ---

st.markdown(
    '<div class="hero-container">'
    '<div class="kicker"><span class="dot"></span>Live Autonomous Pipeline &middot; Production Ready</div>'
    '<div class="app-title">⚡ Razorpay AI Revenue Recovery Agent</div>'
    '<div class="app-subtitle">A bounded, rule-driven system that identifies at-risk revenue, diagnoses root cause, '
    'and executes guardrailed recovery workflows — across payment failures, cart abandonment, subscription renewals, '
    'and overdue B2B receivables. Deterministic policy controls <i>what</i> to execute; LLMs write the copy.</div>'
    '</div>',
    unsafe_allow_html=True,
)

st.markdown(pipeline_stepper(), unsafe_allow_html=True)

tab_overview, tab_queue, tab_audit = st.tabs(["📊 Executive Overview", "🎯 Prioritized Risk Queue", "🧾 Compliance Audit Drill-Down"])


# -------------------------------------------------------------- helpers ----

def kpi_card(icon: str, label: str, value: str, accent: str, sub: str = "") -> str:
    sub_html = f'<div class="kpi-sub">{sub}</div>' if sub else ""
    return (
        f'<div class="kpi-card" style="--accent:{accent}">'
        f'<div class="kpi-header">'
        f'<div class="kpi-label">{label}</div>'
        f'<div class="kpi-icon-badge">{icon}</div>'
        f'</div>'
        f'<div class="kpi-value">{value}</div>'
        f"{sub_html}</div>"
    )


def reason_panel(title: str, reasons: dict[str, int], accent: str) -> str:
    if not reasons:
        body = '<div class="reason-empty">No events triggered this condition.</div>'
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
        st.warning("⚠️ No scorecard found. Run `python -m batch.run_batch` first, then refresh.")
    else:
        c1, c2, c3, c4 = st.columns(4)
        c1.markdown(
            kpi_card("💰", "Total Revenue At Risk", format_inr(scorecard["total_at_risk"]),
                     COLORS["at_risk"], f"Across {scorecard['total_events']} critical events"),
            unsafe_allow_html=True,
        )
        c2.markdown(
            kpi_card("✅", "Total Recovered", format_inr(scorecard["total_recovered"]),
                     COLORS["recovered"], f"Direct GMV saved into merchant ledger"),
            unsafe_allow_html=True,
        )
        c3.markdown(
            kpi_card("📈", "Recovery Conversion", f"{scorecard['recovery_rate_overall']:.1f}%",
                     COLORS["neutral"], f"Avg {scorecard['avg_steps_to_recovery']:.2f} automated steps / recovery"),
            unsafe_allow_html=True,
        )
        c4.markdown(
            kpi_card("🛡️", "Safety Guardrails & Escalation", str(scorecard["guardrail_blocked_count"] + scorecard["escalation_count"]),
                     COLORS["escalated"], f"{scorecard['guardrail_blocked_count']} blocked &middot; {scorecard['escalation_count']} human escalated"),
            unsafe_allow_html=True,
        )

        # AI insight strip
        st.markdown(
            f'<div class="insight-strip">'
            f'<span class="insight-pill">AGENT INSIGHT</span>'
            f'<span>The policy engine recovered <b>{format_inr(scorecard["total_recovered"])}</b> with zero un-bounded discounts. '
            f'<b>{scorecard["guardrail_blocked_count"]} guardrail halts</b> prevented customer fatigue and maintained compliance.</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

        st.markdown('<div class="section-title">Recovered Capital by Category</div>', unsafe_allow_html=True)
        cat_df = pd.DataFrame(scorecard["by_category"]).T.reset_index(names="category")
        cat_df["label"] = cat_df["category"].map(CATEGORY_LABEL).fillna(cat_df["category"])
        cat_df = cat_df.sort_values("recovered")

        fig_cat = go.Figure()
        fig_cat.add_trace(go.Bar(
            x=cat_df["recovered"],
            y=cat_df["label"],
            orientation="h",
            marker=dict(
                color=[CATEGORY_COLOR.get(c, COLORS["neutral"]) for c in cat_df["category"]],
                line=dict(width=1, color="rgba(255,255,255,0.15)"),
            ),
            text=[format_inr(v) for v in cat_df["recovered"]],
            textposition="outside",
            customdata=cat_df[["at_risk", "recovery_rate_pct", "events_recovered", "events"]].values,
            hovertemplate=(
                "<b>%{y}</b><br>Recovered: %{x:,.0f}<br>At risk: %{customdata[0]:,.0f}<br>"
                "Recovery rate: %{customdata[1]:.1f}%<br>Events recovered: %{customdata[2]:.0f}/"
                "%{customdata[3]:.0f}<extra></extra>"
            ),
        ))
        fig_cat.update_layout(
            height=280,
            margin=dict(l=10, r=80, t=10, b=10),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Plus Jakarta Sans, sans-serif", color="#F8FAFC"),
            xaxis=dict(showgrid=True, gridcolor="#1E293B", title="Amount Recovered (₹)"),
            yaxis=dict(title=""),
            showlegend=False,
        )
        st.plotly_chart(fig_cat, use_container_width=True, config={"displayModeBar": False})

        st.markdown('<div class="section-title">Category Outcome Distribution</div>', unsafe_allow_html=True)
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
                    x=sub["count"],
                    y=sub["label"],
                    orientation="h",
                    name=STATUS_LABEL[status],
                    marker=dict(
                        color=STATUS_COLOR[status],
                        line=dict(width=0.5, color="rgba(255,255,255,0.1)"),
                    ),
                    hovertemplate=f"<b>%{{y}}</b><br>{STATUS_LABEL[status]}: %{{x}} events<extra></extra>",
                ))
            fig_mix.update_layout(
                barmode="stack",
                height=280,
                margin=dict(l=10, r=10, t=10, b=10),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(family="Plus Jakarta Sans, sans-serif", color="#F8FAFC"),
                xaxis=dict(showgrid=True, gridcolor="#1E293B", title="Events"),
                yaxis=dict(title=""),
                legend=dict(orientation="h", y=1.18, x=0, font=dict(size=12)),
            )
            st.plotly_chart(fig_mix, use_container_width=True, config={"displayModeBar": False})

        st.markdown('<div class="section-title">Guardrail Enforcements &amp; Human Escalations</div>', unsafe_allow_html=True)
        gc1, gc2 = st.columns(2)
        with gc1:
            st.markdown(
                reason_panel(f"🛡️ Guardrail Blocks ({scorecard['guardrail_blocked_count']} events safely halted)",
                             scorecard["guardrail_block_reasons"], COLORS["at_risk"]),
                unsafe_allow_html=True,
            )
        with gc2:
            st.markdown(
                reason_panel(f"🚨 Human Agent Escalations ({scorecard['escalation_count']} complex cases)",
                             scorecard["escalation_reasons"], COLORS["escalated"]),
                unsafe_allow_html=True,
            )


# ------------------------------------------------------------ risk queue ---

with tab_queue:
    st.markdown('<div class="section-title">Prioritized Risk Queue</div>', unsafe_allow_html=True)
    if not events:
        st.info("No events loaded. Run `python -m data.generate_dataset` first.")
    else:
        rows = []
        for e in events:
            d = score_event(e)
            rows.append(dict(
                event_id=e.event_id,
                category=CATEGORY_LABEL.get(e.category.value, e.category.value),
                category_raw=e.category.value,
                customer=e.customer_name,
                segment=e.segment.value.upper(),
                amount_at_risk=e.amount_at_risk,
                risk_score=d.risk_score,
                recoverable_amount=d.recoverable_amount,
                priority_score=d.priority_score,
            ))
        queue_df = pd.DataFrame(rows)

        fc1, fc2, fc3 = st.columns([2.5, 2.5, 3])
        cat_options = sorted(queue_df["category"].unique())
        seg_options = sorted(queue_df["segment"].unique())
        picked_cats = fc1.multiselect("Filter by Category", cat_options, default=cat_options)
        picked_segs = fc2.multiselect("Filter by Segment", seg_options, default=seg_options)
        search_query = fc3.text_input("Search Customer / Event ID", placeholder="e.g. Greenleaf or EVT-0020")

        filtered = queue_df[queue_df["category"].isin(picked_cats) & queue_df["segment"].isin(picked_segs)]
        if search_query.strip():
            sq = search_query.strip().lower()
            filtered = filtered[filtered["customer"].str.lower().str.contains(sq) | filtered["event_id"].str.lower().str.contains(sq)]

        filtered = filtered.sort_values("priority_score", ascending=False).drop(columns=["category_raw"])

        st.dataframe(
            filtered,
            use_container_width=True,
            hide_index=True,
            column_config={
                "event_id": st.column_config.TextColumn("Event ID"),
                "category": st.column_config.TextColumn("Channel Category"),
                "customer": st.column_config.TextColumn("Customer / Entity"),
                "segment": st.column_config.TextColumn("Segment"),
                "amount_at_risk": st.column_config.NumberColumn("At Risk (₹)", format="₹%,.0f"),
                "risk_score": st.column_config.ProgressColumn("Risk Probability", min_value=0, max_value=1, format="%.2f"),
                "recoverable_amount": st.column_config.NumberColumn("Expected Recoverable", format="₹%,.0f"),
                "priority_score": st.column_config.NumberColumn("Priority Index", format="%,.0f"),
            },
        )
        st.caption(f"Displaying {len(filtered)} of {len(queue_df)} revenue events. Sorted by Priority Index.")


# ------------------------------------------------------- audit drill-down --

with tab_audit:
    st.markdown('<div class="section-title">Compliance Audit Drill-Down</div>', unsafe_allow_html=True)

    examples: dict[str, str] = {}
    if scorecard is not None:
        examples = load_example_events(scorecard["batch_id"])

    quick_picks = {
        f"[{STATUS_LABEL.get(status, status).upper()}] {eid}": eid
        for status, eid in examples.items()
    }
    default_id = next(iter(examples.values()), events[0].event_id if events else "")

    pc1, pc2 = st.columns([2.5, 3])
    with pc1:
        pick_label = st.selectbox("Select Exemplar Event", ["— Select an Outcome Case —"] + list(quick_picks.keys()))
    with pc2:
        typed_id = st.text_input("Or query Event ID directly", value="", placeholder="e.g. EVT-0020-70885f")

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
            st.info(f"No audit trail discovered for `{event_id}`. Please verify the ID or run the batch engine.")
        else:
            measure = next((r for r in trail if r["stage"] == "measure"), None)
            final_status = measure["output"]["final_status"] if measure else "unresolved"
            src_event = events_by_id.get(event_id)

            header_bits = [f"<b class='mono-font'>{event_id}</b>"]
            if src_event:
                header_bits.append(
                    f"{CATEGORY_LABEL.get(src_event.category.value, src_event.category.value)} &middot; "
                    f"{src_event.customer_name} &middot; {format_inr(src_event.amount_at_risk)} at risk"
                )
            st.markdown(
                f'<div style="display:flex;align-items:center;gap:0.9rem;margin-bottom:1.1rem;background:rgba(15,23,42,0.6);padding:0.75rem 1rem;border-radius:12px;border:1px solid rgba(255,255,255,0.08);">'
                f'<span class="badge badge-{final_status}">{STATUS_LABEL.get(final_status, final_status)}</span>'
                f'<span style="color:{COLORS["text_dim"]};font-size:0.92rem;">{" &middot; ".join(header_bits)}</span>'
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
                    summary = f"Risk Score <b>{output.get('risk_score', 0):.2f}</b> &middot; Recoverable <b>{format_inr(output.get('recoverable_amount', 0))}</b> &middot; Priority {output.get('priority_score', 0):,.0f}"
                elif stage == "diagnose":
                    summary = f"Root Cause: <b>{output.get('root_cause')}</b> (Method: {output.get('method')}, Confidence: {output.get('confidence', 0):.2f})"
                elif stage == "decide":
                    summary = f"Deterministic Policy selected: <b>{output.get('intervention')}</b> &middot; Reason: {output.get('reason')}"
                elif stage == "guardrail":
                    blocked = output.get("blocked", False)
                    dot_color = COLORS["at_risk"] if blocked else COLORS["recovered"]
                    disc = output.get("discount_offered") or 0
                    disc_txt = f" &middot; Discount Bounded at {format_inr(disc)}" if disc else ""
                    summary = f"{'🛑 BLOCKED BY SAFETY BOUNDS' if blocked else '✅ PASSED GUARDRAILS'} &rarr; Final Action: <b>{output.get('final_intervention')}</b>{disc_txt}"
                elif stage == "act":
                    outcome = output.get("outcome")
                    dot_color = {
                        "success": COLORS["recovered"], "escalated": COLORS["escalated"],
                        "failure": COLORS["at_risk"], "skipped": COLORS["at_risk"],
                    }.get(outcome, COLORS["unresolved"])
                    summary = f"Execution Outcome: <b>{outcome.upper()}</b> &middot; Amount Recovered: <b>{format_inr(output.get('amount_recovered', 0))}</b>"
                elif stage == "measure":
                    dot_color = STATUS_COLOR.get(output.get("final_status"), COLORS["unresolved"])
                    summary = (
                        f"Final Lifecycle Status: <b>{output.get('final_status').upper()}</b> &middot; "
                        f"Total Recovered: <b>{format_inr(output.get('amount_recovered', 0))}</b> &middot; "
                        f"{output.get('steps_taken', 0)} step(s) recorded"
                    )

                st.markdown(
                    f'<div class="tl-card" style="--dot-color:{dot_color}">'
                    f'<span class="tl-icon">{icon}</span>'
                    f'<span class="tl-stage">{stage}</span>'
                    f'<span class="tl-summary">{summary}</span>'
                    f"</div>",
                    unsafe_allow_html=True,
                )
                with st.expander(f"Audit Payload & Details: {stage.upper()}", expanded=False):
                    dcol1, dcol2 = st.columns(2)
                    with dcol1:
                        st.caption("Input State")
                        st.json(record["input"])
                    with dcol2:
                        st.caption("Output State")
                        st.json(record["output"])
                    if record.get("notes"):
                        st.caption(f"System Note: {record['notes']}")
