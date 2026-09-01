"""Shared color palette + injected CSS for the dashboard. Visual-only module —
no pipeline logic lives here."""
from __future__ import annotations

COLORS = {
    "recovered": "#22C55E",   # green — money back
    "at_risk": "#F59E0B",     # amber — at risk / blocked
    "escalated": "#EF4444",   # red — routed to a human
    "neutral": "#6366F1",     # indigo — headers / highlights / info
    "unresolved": "#64748B",  # slate — no clean outcome yet
    "card_bg": "#151E32",
    "border": "#28324A",
    "text_dim": "#93A0B8",
}

STATUS_COLOR = {
    "recovered": COLORS["recovered"],
    "blocked": COLORS["at_risk"],
    "escalated": COLORS["escalated"],
    "unresolved": COLORS["unresolved"],
}

STATUS_LABEL = {
    "recovered": "Recovered",
    "blocked": "Guardrail-blocked",
    "escalated": "Escalated",
    "unresolved": "Unresolved",
}

CATEGORY_COLOR = {
    "payment_failure": "#6366F1",
    "checkout_abandonment": "#0EA5E9",
    "subscription_renewal": "#A855F7",
    "receivable_overdue": "#F97316",
}

CATEGORY_LABEL = {
    "payment_failure": "Payment failure",
    "checkout_abandonment": "Checkout abandonment",
    "subscription_renewal": "Subscription renewal",
    "receivable_overdue": "Receivable overdue",
}

STAGE_ICON = {
    "detect": "🔎",
    "diagnose": "🩺",
    "decide": "🧭",
    "guardrail": "🛡️",
    "act": "⚡",
    "measure": "📊",
}


def format_inr(amount: float) -> str:
    """Formats a number with Indian digit grouping, e.g. 1234567 -> '₹12,34,567'."""
    try:
        n = float(amount)
    except (TypeError, ValueError):
        return "₹0"
    sign = "-" if n < 0 else ""
    n = abs(n)
    whole = int(round(n))
    s = str(whole)
    if len(s) <= 3:
        grouped = s
    else:
        last3 = s[-3:]
        rest = s[:-3]
        parts = []
        while len(rest) > 2:
            parts.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            parts.insert(0, rest)
        grouped = ",".join(parts) + "," + last3
    return f"{sign}₹{grouped}"


def inject_css() -> str:
    return f"""
<style>
    .block-container {{
        padding-top: 1.6rem;
        padding-bottom: 2rem;
        max-width: 1200px;
    }}
    #MainMenu, footer, header {{ visibility: hidden; }}

    .app-title {{
        font-size: 1.9rem;
        font-weight: 800;
        margin-bottom: 0.1rem;
        letter-spacing: -0.02em;
    }}
    .app-subtitle {{
        color: {COLORS['text_dim']};
        font-size: 0.95rem;
        margin-bottom: 1.4rem;
    }}
    .section-title {{
        font-size: 1.15rem;
        font-weight: 700;
        margin: 1.4rem 0 0.6rem 0;
        letter-spacing: -0.01em;
    }}

    /* KPI cards */
    .kpi-card {{
        background: {COLORS['card_bg']};
        border: 1px solid {COLORS['border']};
        border-left: 4px solid var(--accent, {COLORS['neutral']});
        border-radius: 10px;
        padding: 0.95rem 1.1rem;
        height: 100%;
    }}
    .kpi-label {{
        font-size: 0.72rem;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: {COLORS['text_dim']};
        margin-bottom: 0.35rem;
        font-weight: 600;
    }}
    .kpi-value {{
        font-size: 1.7rem;
        font-weight: 800;
        line-height: 1.1;
    }}
    .kpi-icon {{ font-size: 1.1rem; margin-right: 0.35rem; }}
    .kpi-sub {{
        font-size: 0.78rem;
        color: {COLORS['text_dim']};
        margin-top: 0.25rem;
    }}

    /* Badges */
    .badge {{
        display: inline-block;
        padding: 0.15rem 0.6rem;
        border-radius: 999px;
        font-size: 0.75rem;
        font-weight: 700;
        letter-spacing: 0.01em;
    }}
    .badge-recovered {{ background: rgba(34,197,94,0.16); color: {COLORS['recovered']}; }}
    .badge-blocked   {{ background: rgba(245,158,11,0.16); color: {COLORS['at_risk']}; }}
    .badge-escalated {{ background: rgba(239,68,68,0.16); color: {COLORS['escalated']}; }}
    .badge-unresolved{{ background: rgba(100,116,139,0.18); color: {COLORS['unresolved']}; }}

    /* Reason panels (guardrails / escalations) */
    .reason-panel {{
        background: {COLORS['card_bg']};
        border: 1px solid {COLORS['border']};
        border-radius: 10px;
        padding: 0.9rem 1.05rem;
        height: 100%;
    }}
    .reason-panel-title {{
        font-weight: 700;
        font-size: 0.95rem;
        margin-bottom: 0.7rem;
    }}
    .reason-row {{
        display: flex;
        align-items: center;
        gap: 0.6rem;
        margin-bottom: 0.55rem;
    }}
    .reason-label {{
        flex: 0 0 auto;
        min-width: 150px;
        font-size: 0.82rem;
        color: #D6DCEA;
    }}
    .reason-bar-track {{
        flex: 1 1 auto;
        background: rgba(255,255,255,0.06);
        border-radius: 6px;
        height: 8px;
        overflow: hidden;
    }}
    .reason-bar-fill {{
        height: 100%;
        border-radius: 6px;
    }}
    .reason-count {{
        flex: 0 0 auto;
        font-weight: 700;
        font-size: 0.85rem;
        min-width: 1.6rem;
        text-align: right;
    }}
    .reason-empty {{ color: {COLORS['text_dim']}; font-size: 0.85rem; }}

    /* Audit timeline — a vertical stack of stage cards (Streamlit renders each
       st.markdown/st.expander call as an independent sibling block, so a single
       CSS line spanning multiple calls isn't reliable — a colored left border
       per card reads just as clearly as a stepper). */
    .tl-card {{
        display: flex;
        align-items: center;
        gap: 0.65rem;
        background: {COLORS['card_bg']};
        border: 1px solid {COLORS['border']};
        border-left: 4px solid var(--dot-color, {COLORS['neutral']});
        border-radius: 8px;
        padding: 0.55rem 0.9rem;
        margin-bottom: 0.35rem;
    }}
    .tl-icon {{ font-size: 1.05rem; flex: 0 0 auto; }}
    .tl-stage {{
        font-weight: 700;
        font-size: 0.76rem;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        color: var(--dot-color, {COLORS['neutral']});
        min-width: 78px;
        flex: 0 0 auto;
    }}
    .tl-summary {{ font-size: 0.9rem; color: #E5E9F5; }}

    div[data-testid="stExpander"] {{
        border: 1px solid {COLORS['border']};
        border-radius: 8px;
        margin-bottom: 0.6rem;
    }}
</style>
"""
