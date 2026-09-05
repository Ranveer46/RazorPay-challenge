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
    "bg": "#0B1120",
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


PIPELINE_STAGES = [
    ("detect", "🔎", "Detect", "Risk + recoverable ₹"),
    ("diagnose", "🩺", "Diagnose", "Root cause: rules + LLM"),
    ("decide", "🧭", "Decide", "Deterministic policy table"),
    ("guardrail", "🛡️", "Guard", "Non-overridable stop rules"),
    ("act", "⚡", "Act", "Simulated recovery workflow"),
    ("measure", "📊", "Measure", "Recovered ₹ + audit trail"),
]


def pipeline_stepper() -> str:
    """Header visual: the six-stage loop, one node per audit stage."""
    nodes: list[str] = []
    for i, (_key, icon, label, sub) in enumerate(PIPELINE_STAGES):
        nodes.append(
            '<div class="pl-node">'
            f'<div class="pl-icon-wrap">{icon}</div>'
            f'<div class="pl-label">{label}</div>'
            f'<div class="pl-sub">{sub}</div>'
            "</div>"
        )
        if i < len(PIPELINE_STAGES) - 1:
            nodes.append('<div class="pl-arrow">&rarr;</div>')
    return f'<div class="pipeline-row">{"".join(nodes)}</div>'


def inject_css() -> str:
    return f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');

    html, body, [class^="css"], .stApp, .stMarkdown, p, span, div {{
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }}

    .stApp {{
        background:
            radial-gradient(720px 320px at 18% 0%, rgba(99,102,241,0.09), transparent 70%),
            {COLORS['bg']};
    }}

    .block-container {{
        padding-top: 1.6rem;
        padding-bottom: 2.5rem;
        max-width: 1220px;
    }}
    #MainMenu, footer, header {{ visibility: hidden; }}

    .kicker {{
        display: inline-flex;
        align-items: center;
        gap: 0.4rem;
        background: rgba(99,102,241,0.14);
        border: 1px solid rgba(99,102,241,0.35);
        color: #A5B4FC;
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        padding: 0.3rem 0.75rem;
        border-radius: 999px;
        margin-bottom: 0.7rem;
    }}
    .kicker .dot {{
        width: 6px; height: 6px; border-radius: 50%;
        background: {COLORS['recovered']};
        box-shadow: 0 0 0 3px rgba(34,197,94,0.25);
    }}

    .app-title {{
        font-size: 2.4rem;
        font-weight: 900;
        margin-bottom: 0.15rem;
        letter-spacing: -0.03em;
        background: linear-gradient(100deg, #F8FAFC 25%, #A5B4FC 55%, #7DD3FC 85%);
        -webkit-background-clip: text;
        background-clip: text;
        color: transparent;
    }}
    .app-subtitle {{
        color: {COLORS['text_dim']};
        font-size: 1rem;
        margin-bottom: 1.6rem;
        max-width: 780px;
        line-height: 1.5;
    }}
    .section-title {{
        font-size: 1.15rem;
        font-weight: 700;
        margin: 1.6rem 0 0.7rem 0;
        letter-spacing: -0.01em;
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }}
    .section-title::before {{
        content: "";
        width: 3px;
        height: 1.1rem;
        border-radius: 3px;
        background: linear-gradient(180deg, {COLORS['neutral']}, {COLORS['recovered']});
        display: inline-block;
    }}

    /* Pipeline stepper */
    .pipeline-row {{
        display: flex;
        align-items: stretch;
        gap: 0.4rem;
        margin-bottom: 1.8rem;
        flex-wrap: wrap;
    }}
    .pl-node {{
        flex: 1 1 130px;
        background: linear-gradient(180deg, rgba(255,255,255,0.04), rgba(255,255,255,0.01));
        border: 1px solid {COLORS['border']};
        border-radius: 12px;
        padding: 0.8rem 0.7rem;
        text-align: center;
        transition: transform 0.15s ease, border-color 0.15s ease;
    }}
    .pl-node:hover {{
        transform: translateY(-3px);
        border-color: {COLORS['neutral']};
    }}
    .pl-icon-wrap {{
        width: 34px; height: 34px;
        border-radius: 10px;
        display: flex; align-items: center; justify-content: center;
        margin: 0 auto 0.4rem auto;
        background: rgba(99,102,241,0.15);
        font-size: 1.05rem;
    }}
    .pl-label {{
        font-weight: 700;
        font-size: 0.82rem;
        letter-spacing: 0.01em;
        margin-bottom: 0.15rem;
    }}
    .pl-sub {{
        font-size: 0.68rem;
        color: {COLORS['text_dim']};
        line-height: 1.25;
    }}
    .pl-arrow {{
        display: flex;
        align-items: center;
        justify-content: center;
        color: {COLORS['border']};
        font-size: 1.2rem;
        flex: 0 0 auto;
        padding: 0 0.1rem;
    }}
    @media (max-width: 900px) {{ .pl-arrow {{ display: none; }} }}

    /* KPI cards */
    .kpi-card {{
        position: relative;
        background: linear-gradient(180deg, rgba(255,255,255,0.035), rgba(255,255,255,0.005)), {COLORS['card_bg']};
        border: 1px solid {COLORS['border']};
        border-radius: 14px;
        padding: 1.05rem 1.2rem 1.1rem 1.2rem;
        height: 100%;
        box-shadow: 0 8px 24px rgba(0,0,0,0.18);
        transition: transform 0.15s ease, box-shadow 0.15s ease, border-color 0.15s ease;
        overflow: hidden;
    }}
    .kpi-card::before {{
        content: "";
        position: absolute;
        top: 0; left: 0; right: 0;
        height: 3px;
        background: var(--accent, {COLORS['neutral']});
    }}
    .kpi-card:hover {{
        transform: translateY(-3px);
        box-shadow: 0 14px 32px rgba(0,0,0,0.28);
        border-color: var(--accent, {COLORS['neutral']});
    }}
    .kpi-label {{
        font-size: 0.72rem;
        text-transform: uppercase;
        letter-spacing: 0.07em;
        color: {COLORS['text_dim']};
        margin-bottom: 0.5rem;
        font-weight: 700;
    }}
    .kpi-value {{
        font-size: 1.85rem;
        font-weight: 800;
        line-height: 1.1;
        display: flex;
        align-items: center;
        letter-spacing: -0.01em;
    }}
    .kpi-icon {{
        font-size: 1.05rem;
        margin-right: 0.5rem;
        width: 30px; height: 30px;
        border-radius: 9px;
        display: inline-flex; align-items: center; justify-content: center;
        background: color-mix(in srgb, var(--accent, {COLORS['neutral']}) 20%, transparent);
        flex: 0 0 auto;
    }}
    .kpi-sub {{
        font-size: 0.78rem;
        color: {COLORS['text_dim']};
        margin-top: 0.4rem;
    }}

    /* Tabs */
    button[data-baseweb="tab"] {{
        font-weight: 600;
        font-size: 0.95rem;
        padding: 0.6rem 1.1rem !important;
    }}
    div[data-baseweb="tab-highlight"] {{
        background: linear-gradient(90deg, {COLORS['neutral']}, {COLORS['recovered']}) !important;
        height: 3px !important;
    }}
    div[data-baseweb="tab-border"] {{ background: {COLORS['border']} !important; }}

    /* Dataframe / expander polish */
    div[data-testid="stDataFrame"] {{
        border-radius: 10px;
        overflow: hidden;
        border: 1px solid {COLORS['border']};
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
