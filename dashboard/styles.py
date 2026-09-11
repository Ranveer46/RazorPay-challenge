"""Shared color palette + injected CSS for the Razorpay AI Revenue Recovery Agent dashboard.
Visual-only module — no pipeline logic lives here.
"""
from __future__ import annotations

COLORS = {
    "recovered": "#10B981",    # Emerald green — successfully recovered
    "at_risk": "#F59E0B",      # Warm amber — at risk / guardrail blocked
    "escalated": "#EF4444",    # Crimson red — routed to human collections
    "neutral": "#3B82F6",      # Razorpay Royal Blue — primary brand accent
    "accent_indigo": "#6366F1",# Deep Indigo
    "accent_cyan": "#06B6D4",  # Cyan highlight
    "unresolved": "#64748B",   # Cool slate — no clean outcome yet
    "card_bg": "#0F172A",      # Deep slate card background
    "card_border": "#1E293B",  # Crisp border
    "border_glow": "rgba(59, 130, 246, 0.25)",
    "text_main": "#F8FAFC",    # Crisp white text
    "text_dim": "#94A3B8",     # Muted secondary text
    "bg": "#050814",           # Ultra-dark executive canvas
}

STATUS_COLOR = {
    "recovered": COLORS["recovered"],
    "blocked": COLORS["at_risk"],
    "escalated": COLORS["escalated"],
    "unresolved": COLORS["unresolved"],
}

STATUS_LABEL = {
    "recovered": "Recovered",
    "blocked": "Guardrail-Blocked",
    "escalated": "Human Escalated",
    "unresolved": "Unresolved",
}

CATEGORY_COLOR = {
    "payment_failure": "#3B82F6",      # Razorpay Blue
    "checkout_abandonment": "#06B6D4",  # Cyan
    "subscription_renewal": "#8B5CF6",  # Violet
    "receivable_overdue": "#F97316",    # Warm Orange
}

CATEGORY_LABEL = {
    "payment_failure": "Payment Failure",
    "checkout_abandonment": "Checkout Abandonment",
    "subscription_renewal": "Subscription Renewal",
    "receivable_overdue": "Receivable Overdue",
}

STAGE_ICON = {
    "detect": "🔍",
    "diagnose": "🩺",
    "decide": "🧭",
    "guardrail": "🛡️",
    "act": "⚡",
    "measure": "📊",
}


def format_inr(amount: float) -> str:
    """Formats a number with standard Indian digit grouping (Lakhs & Crores).
    E.g. 1234567 -> '₹12,34,567' or negative values with proper sign.
    """
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
    ("1", "detect", "🔍", "1. Detect", "Risk & Recoverable ₹"),
    ("2", "diagnose", "🩺", "2. Diagnose", "Rules + LLM Parser"),
    ("3", "decide", "🧭", "3. Decide", "Deterministic Policy"),
    ("4", "guardrail", "🛡️", "4. Guardrail", "Non-Overridable Bounds"),
    ("5", "act", "⚡", "5. Act", "Orchestration & Copy"),
    ("6", "measure", "📊", "6. Measure", "Audit Ledger & Scorecard"),
]


def pipeline_stepper() -> str:
    """Visual pipeline stepper with numbered node badges and glowing arrows."""
    nodes: list[str] = []
    for i, (num, _key, icon, label, sub) in enumerate(PIPELINE_STAGES):
        nodes.append(
            '<div class="pl-node">'
            f'<div class="pl-step-num">{num}</div>'
            f'<div class="pl-icon-wrap">{icon}</div>'
            f'<div class="pl-label">{label}</div>'
            f'<div class="pl-sub">{sub}</div>'
            "</div>"
        )
        if i < len(PIPELINE_STAGES) - 1:
            nodes.append('<div class="pl-arrow"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"></polyline></svg></div>')
    return f'<div class="pipeline-wrapper"><div class="pipeline-title">AUTONOMOUS 6-STAGE RECOVERY LIFECYCLE</div><div class="pipeline-row">{"".join(nodes)}</div></div>'


def inject_css() -> str:
    return f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');

    html, body, [class^="css"], .stApp, .stMarkdown, p, span, div, input, button, select {{
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif !important;
    }}

    code, pre, .mono-font {{
        font-family: 'JetBrains Mono', monospace !important;
    }}

    /* Futuristic FinTech Mesh Background */
    .stApp {{
        background-color: {COLORS['bg']};
        background-image: 
            radial-gradient(circle at 10% 0%, rgba(59, 130, 246, 0.12) 0%, transparent 45%),
            radial-gradient(circle at 90% 15%, rgba(99, 102, 241, 0.08) 0%, transparent 40%),
            radial-gradient(circle at 50% 100%, rgba(16, 185, 129, 0.05) 0%, transparent 50%);
        background-attachment: fixed;
        color: {COLORS['text_main']};
    }}

    .block-container {{
        padding-top: 1.8rem;
        padding-bottom: 3.5rem;
        max-width: 1280px;
    }}

    #MainMenu, footer, header {{ visibility: hidden; }}

    /* Header & Branding Hero */
    .hero-container {{
        padding: 1.2rem 1.6rem;
        background: linear-gradient(135deg, rgba(15, 23, 42, 0.75), rgba(30, 41, 59, 0.4));
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 18px;
        backdrop-filter: blur(16px);
        margin-bottom: 1.8rem;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.25);
    }}

    .kicker {{
        display: inline-flex;
        align-items: center;
        gap: 0.5rem;
        background: rgba(59, 130, 246, 0.12);
        border: 1px solid rgba(59, 130, 246, 0.3);
        color: #93C5FD;
        font-size: 0.75rem;
        font-weight: 700;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        padding: 0.35rem 0.85rem;
        border-radius: 999px;
        margin-bottom: 0.8rem;
    }}

    .kicker .dot {{
        width: 7px; height: 7px; border-radius: 50%;
        background: {COLORS['recovered']};
        box-shadow: 0 0 10px {COLORS['recovered']};
        animation: pulse 2s infinite ease-in-out;
    }}

    @keyframes pulse {{
        0%, 100% {{ transform: scale(1); opacity: 1; }}
        50% {{ transform: scale(1.35); opacity: 0.6; }}
    }}

    .app-title {{
        font-size: 2.3rem;
        font-weight: 800;
        letter-spacing: -0.03em;
        margin-bottom: 0.4rem;
        background: linear-gradient(135deg, #FFFFFF 30%, #93C5FD 70%, #60A5FA 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        display: flex;
        align-items: center;
        gap: 0.7rem;
    }}

    .app-subtitle {{
        color: {COLORS['text_dim']};
        font-size: 0.98rem;
        line-height: 1.6;
        max-width: 900px;
    }}

    /* Section Titles */
    .section-title {{
        font-size: 1.25rem;
        font-weight: 700;
        margin: 1.8rem 0 0.9rem 0;
        letter-spacing: -0.015em;
        display: flex;
        align-items: center;
        gap: 0.65rem;
        color: #F1F5F9;
    }}

    .section-title::before {{
        content: "";
        width: 4px;
        height: 1.25rem;
        border-radius: 4px;
        background: linear-gradient(180deg, {COLORS['neutral']}, {COLORS['recovered']});
        display: inline-block;
    }}

    /* Pipeline Stepper Component */
    .pipeline-wrapper {{
        background: rgba(15, 23, 42, 0.65);
        border: 1px solid rgba(255, 255, 255, 0.07);
        border-radius: 16px;
        padding: 1.1rem 1.4rem;
        margin-bottom: 2rem;
        backdrop-filter: blur(12px);
    }}

    .pipeline-title {{
        font-size: 0.72rem;
        font-weight: 800;
        letter-spacing: 0.1em;
        color: #94A3B8;
        margin-bottom: 0.85rem;
    }}

    .pipeline-row {{
        display: flex;
        align-items: center;
        gap: 0.45rem;
        flex-wrap: wrap;
    }}

    .pl-node {{
        flex: 1 1 140px;
        background: linear-gradient(180deg, rgba(30, 41, 59, 0.6), rgba(15, 23, 42, 0.7));
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 12px;
        padding: 0.85rem 0.75rem;
        text-align: center;
        position: relative;
        transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
    }}

    .pl-node:hover {{
        transform: translateY(-3px);
        border-color: {COLORS['neutral']};
        box-shadow: 0 8px 20px rgba(59, 130, 246, 0.2);
    }}

    .pl-step-num {{
        position: absolute;
        top: 6px;
        right: 8px;
        font-size: 0.62rem;
        font-weight: 800;
        color: #475569;
    }}

    .pl-icon-wrap {{
        width: 36px; height: 36px;
        border-radius: 10px;
        display: flex; align-items: center; justify-content: center;
        margin: 0 auto 0.45rem auto;
        background: rgba(59, 130, 246, 0.15);
        border: 1px solid rgba(59, 130, 246, 0.3);
        font-size: 1.1rem;
    }}

    .pl-label {{
        font-weight: 700;
        font-size: 0.84rem;
        color: #F8FAFC;
        margin-bottom: 0.2rem;
    }}

    .pl-sub {{
        font-size: 0.7rem;
        color: {COLORS['text_dim']};
        line-height: 1.3;
    }}

    .pl-arrow {{
        display: flex;
        align-items: center;
        justify-content: center;
        color: #475569;
        flex: 0 0 auto;
    }}

    @media (max-width: 950px) {{ .pl-arrow {{ display: none; }} }}

    /* KPI Glassmorphism Cards */
    .kpi-card {{
        position: relative;
        background: linear-gradient(145deg, rgba(15, 23, 42, 0.85), rgba(30, 41, 59, 0.5));
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 16px;
        padding: 1.25rem 1.4rem;
        height: 100%;
        backdrop-filter: blur(14px);
        box-shadow: 0 8px 25px rgba(0, 0, 0, 0.25);
        transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
        overflow: hidden;
    }}

    .kpi-card::before {{
        content: "";
        position: absolute;
        top: 0; left: 0; right: 0;
        height: 3px;
        background: var(--accent, {COLORS['neutral']});
        box-shadow: 0 0 12px var(--accent, {COLORS['neutral']});
    }}

    .kpi-card:hover {{
        transform: translateY(-4px);
        box-shadow: 0 14px 35px rgba(0, 0, 0, 0.35);
        border-color: var(--accent, {COLORS['neutral']});
    }}

    .kpi-header {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 0.65rem;
    }}

    .kpi-label {{
        font-size: 0.74rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: {COLORS['text_dim']};
        font-weight: 700;
    }}

    .kpi-icon-badge {{
        width: 34px; height: 34px;
        border-radius: 10px;
        display: inline-flex; align-items: center; justify-content: center;
        background: color-mix(in srgb, var(--accent, {COLORS['neutral']}) 18%, transparent);
        border: 1px solid color-mix(in srgb, var(--accent, {COLORS['neutral']}) 35%, transparent);
        font-size: 1.15rem;
    }}

    .kpi-value {{
        font-size: 1.95rem;
        font-weight: 800;
        line-height: 1.15;
        letter-spacing: -0.02em;
        color: #F8FAFC;
    }}

    .kpi-sub {{
        font-size: 0.8rem;
        color: {COLORS['text_dim']};
        margin-top: 0.55rem;
        display: flex;
        align-items: center;
        gap: 0.4rem;
    }}

    /* Insight Banner */
    .insight-strip {{
        background: linear-gradient(90deg, rgba(59, 130, 246, 0.15), rgba(16, 185, 129, 0.08));
        border: 1px solid rgba(59, 130, 246, 0.3);
        border-radius: 12px;
        padding: 0.75rem 1.1rem;
        margin-top: 1.2rem;
        margin-bottom: 1.2rem;
        display: flex;
        align-items: center;
        gap: 0.75rem;
        font-size: 0.88rem;
        color: #E2E8F0;
    }}

    .insight-pill {{
        background: {COLORS['neutral']};
        color: white;
        font-size: 0.7rem;
        font-weight: 800;
        padding: 0.2rem 0.55rem;
        border-radius: 6px;
        text-transform: uppercase;
        letter-spacing: 0.06em;
    }}

    /* Tabs Styling */
    button[data-baseweb="tab"] {{
        font-weight: 700;
        font-size: 0.98rem;
        color: #94A3B8 !important;
        padding: 0.75rem 1.4rem !important;
        border-radius: 8px 8px 0 0 !important;
        transition: all 0.2s ease;
    }}

    button[data-baseweb="tab"][aria-selected="true"] {{
        color: #FFFFFF !important;
    }}

    div[data-baseweb="tab-highlight"] {{
        background: linear-gradient(90deg, {COLORS['neutral']}, {COLORS['recovered']}) !important;
        height: 3px !important;
        border-radius: 3px 3px 0 0;
        box-shadow: 0 0 10px rgba(59, 130, 246, 0.5);
    }}

    div[data-baseweb="tab-border"] {{ 
        background: rgba(255, 255, 255, 0.08) !important; 
    }}

    /* Badges */
    .badge {{
        display: inline-flex;
        align-items: center;
        gap: 0.35rem;
        padding: 0.22rem 0.7rem;
        border-radius: 999px;
        font-size: 0.76rem;
        font-weight: 700;
        letter-spacing: 0.02em;
    }}

    .badge-recovered {{ 
        background: rgba(16, 185, 129, 0.16); 
        color: {COLORS['recovered']}; 
        border: 1px solid rgba(16, 185, 129, 0.35);
    }}
    .badge-blocked {{ 
        background: rgba(245, 158, 11, 0.16); 
        color: {COLORS['at_risk']}; 
        border: 1px solid rgba(245, 158, 11, 0.35);
    }}
    .badge-escalated {{ 
        background: rgba(239, 68, 68, 0.16); 
        color: {COLORS['escalated']}; 
        border: 1px solid rgba(239, 68, 68, 0.35);
    }}
    .badge-unresolved {{ 
        background: rgba(100, 116, 139, 0.18); 
        color: {COLORS['unresolved']}; 
        border: 1px solid rgba(100, 116, 139, 0.35);
    }}

    /* Reason Panels */
    .reason-panel {{
        background: linear-gradient(180deg, rgba(15, 23, 42, 0.8), rgba(15, 23, 42, 0.95));
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 14px;
        padding: 1.1rem 1.25rem;
        height: 100%;
        backdrop-filter: blur(10px);
    }}

    .reason-panel-title {{
        font-weight: 700;
        font-size: 0.96rem;
        margin-bottom: 0.9rem;
        color: #F8FAFC;
        display: flex;
        align-items: center;
        gap: 0.4rem;
    }}

    .reason-row {{
        display: flex;
        align-items: center;
        gap: 0.75rem;
        margin-bottom: 0.65rem;
    }}

    .reason-label {{
        flex: 0 0 auto;
        min-width: 170px;
        font-size: 0.83rem;
        color: #CBD5E1;
    }}

    .reason-bar-track {{
        flex: 1 1 auto;
        background: rgba(255, 255, 255, 0.06);
        border-radius: 8px;
        height: 9px;
        overflow: hidden;
    }}

    .reason-bar-fill {{
        height: 100%;
        border-radius: 8px;
        transition: width 0.4s ease-out;
    }}

    .reason-count {{
        flex: 0 0 auto;
        font-weight: 700;
        font-size: 0.86rem;
        min-width: 2rem;
        text-align: right;
        color: #F8FAFC;
    }}

    .reason-empty {{ color: {COLORS['text_dim']}; font-size: 0.86rem; font-style: italic; }}

    /* Audit Drill-Down Cards */
    .tl-card {{
        display: flex;
        align-items: center;
        gap: 0.85rem;
        background: linear-gradient(90deg, rgba(15, 23, 42, 0.9), rgba(30, 41, 59, 0.5));
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-left: 4px solid var(--dot-color, {COLORS['neutral']});
        border-radius: 10px;
        padding: 0.7rem 1.05rem;
        margin-bottom: 0.45rem;
        transition: transform 0.15s ease, border-color 0.15s ease;
    }}

    .tl-card:hover {{
        transform: translateX(4px);
        border-color: rgba(255, 255, 255, 0.2);
    }}

    .tl-icon {{ font-size: 1.15rem; flex: 0 0 auto; }}

    .tl-stage {{
        font-weight: 800;
        font-size: 0.78rem;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: var(--dot-color, {COLORS['neutral']});
        min-width: 90px;
        flex: 0 0 auto;
    }}

    .tl-summary {{ 
        font-size: 0.91rem; 
        color: #F1F5F9; 
        flex: 1 1 auto;
    }}

    /* Polish Streamlit Dataframes & Expanders */
    div[data-testid="stDataFrame"] {{
        border-radius: 12px;
        overflow: hidden;
        border: 1px solid rgba(255, 255, 255, 0.08);
        background: rgba(15, 23, 42, 0.7);
    }}

    div[data-testid="stExpander"] {{
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 10px;
        background: rgba(15, 23, 42, 0.4);
        margin-bottom: 0.75rem;
    }}

    /* Subtle custom scrollbar */
    ::-webkit-scrollbar {{
        width: 8px;
        height: 8px;
    }}
    ::-webkit-scrollbar-track {{
        background: {COLORS['bg']};
    }}
    ::-webkit-scrollbar-thumb {{
        background: #1E293B;
        border-radius: 4px;
    }}
    ::-webkit-scrollbar-thumb:hover {{
        background: #334155;
    }}
</style>
"""
