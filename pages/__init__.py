"""AI店长 v1.2 - 共享组件（Unicode 图标 + 玻璃卡片 + 节标题）"""
import html
import os
import sys

import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from config import load_config
from database import Database


def h(text) -> str:
    """安全 HTML 转义，防止产品标题中的特殊字符破坏页面渲染"""
    if text is None:
        return ""
    return html.escape(str(text), quote=False)


# ── Unicode 图标映射 ───────────────────────────
ICON_MAP = {
    "home": "🏠", "dashboard": "📊", "dashboard_customize": "📋",
    "radar": "📡", "insights": "💡", "today": "📅",
    "trending_up": "📈", "local_fire_department": "🔥",
    "notifications_active": "🔔", "bar_chart": "📊", "leaderboard": "🏆",
    "inventory_2": "📦", "sell": "💰", "rate_review": "📝",
    "check_circle": "✅", "info": "ℹ️", "search": "🔍",
    "pending": "⏳", "timer": "⏱️", "refresh": "🔄",
    "sync": "🔄", "database": "🗄️", "task_alt": "✔️",
    "travel_explore": "🔎", "schedule": "📅", "list_alt": "📋",
    "warning": "⚠️", "send": "📤", "save": "💾", "delete": "🗑️",
    "cleaning_services": "🧹", "local_shipping": "🚚", "construction": "🚧",
    "point_of_sale": "💳", "shopping_cart": "🛒", "swap_horiz": "↔️",
    "rocket_launch": "🚀", "pending_actions": "📋", "cancel": "❌",
    "block": "🚫", "add_circle": "➕", "download": "📥",
    "key": "🔑", "settings": "⚙️", "monitoring": "📡", "tune": "🎚️",
    "build": "🔧", "login": "🔐", "lightbulb": "💡",
    "account_balance": "💰", "calculate": "🧮", "receipt_long": "🧾",
    "savings": "💰", "mail": "📧", "error": "❌",
    "lan": "🌐", "storefront": "🏪", "stethoscope": "🩺",
    "storage": "💾", "description": "📄", "assessment": "📊",
    "calendar_month": "📆", "history": "📜",
    "arrow_forward": "▶", "hub": "🔗", "scan": "📡",
    "article": "📄", "notifications": "🔔", "report": "📑",
    "subdirectory_arrow_right": "▸", "add": "➕",
}


def icon(name: str, size: int = 18, color: str = "") -> str:
    """返回 Unicode emoji 字符（无 HTML 标签，可安全用于所有 Streamlit 组件）"""
    return ICON_MAP.get(name, "●")


def metric_card(label: str, value, delta=None, icon_name: str = "", help_text: str = ""):
    """指标卡片 — 使用 st.metric 原生组件，确保兼容性"""
    icon_char = icon(icon_name) if icon_name else ""
    full_label = f"{icon_char} {label}" if icon_char else label
    help_kw = {"help": help_text} if help_text else {}
    st.metric(label=full_label, value=value, delta=delta, **help_kw)


def glass_card(title: str, content: str, badge: str = "", icon_name: str = "article"):
    """HTML 玻璃卡片 — 用在 opportunity_card 等场景"""
    badge_html = f'<span class="badge">{badge}</span>' if badge else ""
    return f"""
    <div class="glass-card">
        <div class="glass-card-header">
            {icon(icon_name, 16)} <span class="card-title">{title}</span>
            {badge_html}
        </div>
        <div class="glass-card-body">{content}</div>
    </div>
    """


def opportunity_card(opp: dict, rank: int = 0) -> None:
    """套利机会卡片 — 玻璃卡片风格"""
    roi = opp.get("roi", 0)
    if roi >= 60:
        badge_cls = "high"
    elif roi >= 30:
        badge_cls = "mid"
    else:
        badge_cls = "low"

    buy_title = h((opp.get("buy_title") or opp.get("title", ""))[:40])
    buy_price = opp.get("buy_price", 0)
    sell_price = opp.get("sell_price", 0)
    profit = opp.get("profit", 0)
    buy_pf = h(opp.get("buy_platform", ""))
    sell_pf = h(opp.get("sell_platform", ""))
    buy_url = opp.get("buy_url", "") or opp.get("product_url", "")
    roi_cls = "high" if roi >= 60 else "mid" if roi >= 30 else "low"

    rank_html = f'<div class="opp-rank">#{rank}</div>' if rank else ''
    link_html = f'<a href="{buy_url}" target="_blank" style="font-size:0.6rem;color:var(--text-muted);">查看详情</a>' if buy_url else ''

    st.markdown(f"""
<div class="glass-card opp-card">
    {rank_html}
    <div class="opp-title" title="{buy_title}">{buy_title}</div>
    <div class="opp-platform">{buy_pf} → {sell_pf}</div>
    <div class="opp-prices">
        <span style="color:var(--red);">¥{buy_price:.2f}</span>
        <span style="color:var(--text-muted);">→</span>
        <span style="color:var(--green);">¥{sell_price:.2f}</span>
    </div>
    <div class="opp-roi"><b class="roi-{roi_cls}">{roi:.0f}%</b></div>
    {link_html}
</div>
""", unsafe_allow_html=True)


def section_header(title: str, icon_name: str = "bar_chart") -> None:
    """节标题 — 带 Material Symbol 图标"""
    st.markdown(f"<h3 class='section-title'>{icon(icon_name, 22)} {title}</h3>", unsafe_allow_html=True)


# ── 全局注入 CSS（一次）───────────────────────
_GLASS_CSS_INJECTED = False


def inject_glass_css():
    global _GLASS_CSS_INJECTED
    if _GLASS_CSS_INJECTED:
        return
    _GLASS_CSS_INJECTED = True
    st.markdown("""
<style>
/* ── 全局变量 ── */
:root {
  --bg: #0b0e14;
  --card-bg: rgba(18, 22, 33, 0.92);
  --card-border: rgba(255,255,255,0.06);
  --text: #e2e4ec;
  --text-muted: #8b8fa3;
  --green: #00f59b;
  --yellow: #fbd400;
  --red: #ff6b6b;
  --blue: #5b9bd5;
  --radius: 10px;
}

/* ── 玻璃卡片 ── */
.glass-card {
    background: var(--card-bg);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    border: 1px solid var(--card-border);
    border-radius: var(--radius);
    padding: 0.75rem 1rem;
    margin-bottom: 0.5rem;
    transition: border-color 0.2s, box-shadow 0.2s;
}
.glass-card:hover {
    border-color: rgba(0,245,155,0.18);
    box-shadow: 0 4px 24px rgba(0,245,155,0.06);
}

/* ── 产品卡片（看板用）── */
.product-card {
    padding: 0.85rem 1rem;
}
.product-card .pc-title {
    font-size: 0.82rem;
    font-weight: 600;
    color: var(--text);
    line-height: 1.35;
    margin-bottom: 8px;
}
.product-card .pc-meta {
    display: flex;
    gap: 16px;
    flex-wrap: wrap;
    font-size: 0.73rem;
    color: var(--text-muted);
    margin-bottom: 8px;
}
.product-card .pc-meta b { color: var(--text); }
.product-card .pc-prices {
    display: flex;
    gap: 10px;
    align-items: center;
    font-size: 0.8rem;
    margin-bottom: 8px;
}
.product-card .pc-price-item {
    background: rgba(255,255,255,0.03);
    border-radius: 6px;
    padding: 4px 10px;
    text-align: center;
    min-width: 80px;
}
.product-card .pc-price-item .label {
    font-size: 0.6rem;
    color: var(--text-muted);
    text-transform: uppercase;
}
.product-card .pc-price-item .value {
    font-weight: 700;
    font-size: 0.95rem;
}
.product-card .pc-price-item.buy .value { color: var(--red); }
.product-card .pc-price-item.sell .value { color: var(--green); }
.product-card .pc-price-item.profit .value { color: var(--green); }
.product-card .pc-arrow {
    color: var(--text-muted);
    font-size: 1rem;
}

/* ── 链接行 ── */
.product-card .pc-links {
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
    margin-bottom: 6px;
}
.product-card .pc-links a {
    font-size: 0.7rem;
    padding: 3px 10px;
    border-radius: 5px;
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.06);
    text-decoration: none;
    transition: all 0.15s;
}
.product-card .pc-links a:hover {
    background: rgba(0,245,155,0.08);
    border-color: rgba(0,245,155,0.2);
}

/* ── 机会卡片（首页用）── */
.opp-card {
    padding: 0.7rem 0.9rem;
    text-align: center;
}
.opp-card .opp-rank {
    font-size: 0.6rem;
    color: var(--text-muted);
    letter-spacing: 0.08em;
    margin-bottom: 4px;
}
.opp-card .opp-title {
    font-size: 0.75rem;
    font-weight: 600;
    color: var(--text);
    margin-bottom: 6px;
    line-height: 1.3;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
.opp-card .opp-platform {
    font-size: 0.65rem;
    color: var(--text-muted);
    margin-bottom: 6px;
}
.opp-card .opp-prices {
    display: flex;
    justify-content: center;
    gap: 8px;
    font-size: 0.72rem;
    margin-bottom: 4px;
}
.opp-card .opp-roi {
    font-size: 1.1rem;
    font-weight: 800;
    margin-top: 2px;
}

/* ── Badges ── */
.badge { display: inline-block; font-size: 0.6rem; font-weight: 700; letter-spacing: 0.06em; padding: 2px 8px; border-radius: 4px; margin-left: 6px; vertical-align: middle; }
.badge-high { background: rgba(0,245,155,0.12); color: #00f59b; }
.badge-mid { background: rgba(251,212,0,0.12); color: #fbd400; }
.badge-low { background: rgba(255,107,107,0.12); color: #ff6b6b; }

/* ── ROI colors ── */
.roi-high { color: #00f59b; }
.roi-mid { color: #fbd400; }
.roi-low { color: #ff6b6b; }

/* ── Section Title ── */
.section-title {
    font-size: 1rem; font-weight: 600; color: var(--text);
    margin: 1rem 0 0.5rem 0; padding-bottom: 0.25rem;
    border-bottom: 1px solid rgba(255,255,255,0.04);
}

/* ── Stepper ── */
.stepper { display: flex; align-items: center; gap: 0.5rem; font-size: 0.82rem; color: var(--text-muted); padding: 0.5rem 0; }
.stepper .step { display: flex; align-items: center; gap: 0.25rem; }
.stepper .step.active { color: var(--green); font-weight: 600; }
.stepper .arrow { color: var(--text-muted); }

/* ── KPI card ── */
.kpi-item {
    flex: 1; min-width: 110px; background: rgba(18,22,33,0.7);
    border: 1px solid rgba(255,255,255,0.04); border-radius: 10px;
    padding: 0.5rem 0.75rem;
}

/* ── 移动端响应式 ── */
@media (max-width: 768px) {
    .product-card .pc-prices { flex-direction: column; gap: 6px; }
    .product-card .pc-price-item { width: 100%; }
    .product-card .pc-links { flex-direction: column; }
    .opp-card { padding: 0.5rem; }
    .opp-card .opp-title { font-size: 0.7rem; }
    .glass-card { padding: 0.5rem 0.7rem; }
}
</style>
""", unsafe_allow_html=True)


# ── 缓存资源 ─────────────────────────────────
@st.cache_resource
def get_config() -> dict:
    config_path = os.path.join(os.path.dirname(__file__), "..", "config.ini")
    app_cfg = load_config(config_path)
    cfg = app_cfg.as_dict()

    push = dict(cfg.get("push", {}))
    push.setdefault("serverchan_send_key", push.get("serverchan_sendkey", ""))
    push.setdefault("serverchan_sendkey", push.get("serverchan_send_key", ""))
    push.setdefault("smtp_password", push.get("smtp_pass", ""))
    push.setdefault("smtp_pass", push.get("smtp_password", ""))
    push.setdefault("method", push.get("method", "serverchan"))
    cfg["push"] = push

    fin = dict(cfg.get("finance", {}))
    fin.setdefault("platform_fee_rate", fin.get("xianyu_fee", 0.016))
    fin.setdefault("domestic_shipping", fin.get("domestic_shipping", 3.0))
    cfg["finance"] = fin

    scn = dict(cfg.get("scanner", {}))
    scn.setdefault("seed_categories", scn.get("seed_categories", []))
    scn.setdefault("keywords_per_round", scn.get("keywords_per_round", 20))
    scn.setdefault("realtime_push_roi_threshold",
                   int(float(scn.get("realtime_push_threshold", 0.30)) * 100))
    cfg["scanner"] = scn

    arb = dict(cfg.get("arbitrage", {}))
    arb.setdefault("min_roi", float(arb.get("min_roi_threshold", 0.15)) * 100)
    arb.setdefault("realtime_push_roi_threshold", cfg["scanner"]["realtime_push_roi_threshold"])
    cfg["arbitrage"] = arb

    return cfg


@st.cache_resource
def get_db() -> Database:
    cfg = get_config()
    db_path = cfg.get("database", {}).get("path", "data/ai_storekeeper.db")
    abs_path = os.path.join(os.path.dirname(__file__), "..", db_path)
    db = Database(abs_path)
    # 诊断：检查新增方法是否存在
    required = ['get_shipping_orders', 'create_shipping_order', 'get_dashboard_stats',
                'save_traffic_record', 'get_traffic_items', 'save_image_pack']
    missing = [m for m in required if not hasattr(db, m)]
    if missing:
        st.error(f"### Database 方法缺失 ({len(missing)} 个)")
        st.code(f"类来源: {getattr(sys.modules.get(db.__class__.__module__), '__file__', '?')}")
        st.write(f"缺失: {missing}")
        st.info("请关闭所有 Python 进程后运行 `重启.bat`")
    return db


@st.cache_resource
def get_scheduler():
    """获取后台扫描调度器单例"""
    from modules.scheduler import ScanScheduler
    cfg = get_config()
    db = get_db()
    return ScanScheduler(db, cfg)


__all__ = [
    "icon", "metric_card", "glass_card", "opportunity_card", "section_header",
    "inject_glass_css", "get_config", "get_db", "get_scheduler",
]
