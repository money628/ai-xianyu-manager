"""AI店长 v1.1 - Streamlit 主入口

5 页导航：首页 / 雷达 / 看板 / 工具 / 历史
暗色主题，Material Design 3 风格。
支持后台定时自动扫描 + ROI 实时推送。
"""
import os
import sys

import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

st.set_page_config(
    page_title="AI店长 v1.1",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------- Material Design 3 暗色主题 ----------
st.markdown("""
<style>
/* ── 使用系统内置字体，不依赖 Google Fonts ── */

:root {
    --bg: #0a0e17;
    --surface: #0f131c;
    --surface-container: #1c1f29;
    --surface-low: #181b25;
    --surface-high: #262a34;
    --surface-highest: #31353f;
    --primary: #cdffdc;
    --primary-container: #00f59b;
    --on-primary: #003920;
    --secondary: #a6e6ff;
    --secondary-container: #14d1ff;
    --tertiary-container: #fbd400;
    --on-surface: #dfe2ef;
    --on-surface-variant: #b9cbbd;
    --outline: #849588;
    --outline-variant: #3b4a3f;
    --error: #ffb4ab;
    --error-container: #93000a;
}

/* 全局 */
.stApp {
    background: var(--bg);
    color: var(--on-surface);
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei', 'PingFang SC', sans-serif;
}
.stApp > header { display: none; }
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
div[data-testid="stToolbar"] { display: none; }
div[data-testid="stDecoration"] { display: none; }
.stDeployButton { display: none; }

/* 侧边栏 */
section[data-testid="stSidebar"] { background: var(--surface); border-right: 1px solid var(--outline-variant); }
section[data-testid="stSidebar"] .stRadio label span { color: var(--on-surface) !important; font-size: 0.95rem; }

/* 指标卡片 */
[data-testid="stMetric"], .kpi-metric {
    background: var(--surface-container);
    border: 1px solid rgba(255,255,255,0.05);
    border-radius: 12px;
    padding: 1rem 1.25rem;
    transition: all 0.2s;
}
[data-testid="stMetric"]:hover, .kpi-metric:hover { border-color: var(--outline-variant); }
[data-testid="stMetricValue"] { color: var(--on-surface) !important; }
[data-testid="stMetricLabel"] { color: var(--on-surface-variant) !important; font-size: 0.75rem !important; text-transform: uppercase; letter-spacing: 0.05em; }
[data-testid="stMetricDelta"] { color: var(--primary-container) !important; }

/* Tabs */
[data-baseweb="tab-list"] { gap: 0.5rem; }
[data-baseweb="tab"] {
    background: var(--surface-container);
    color: var(--on-surface-variant);
    border-radius: 8px;
    padding: 0.5rem 1rem;
    border: 1px solid var(--outline-variant);
    transition: all 0.2s;
}
[aria-selected="true"] { color: var(--primary-container) !important; border-color: var(--primary-container) !important; box-shadow: inset 0 0 8px rgba(0,245,155,0.1); }
[data-baseweb="tab-highlight"], [data-baseweb="tab-border"] { display: none; }
.stTabs { margin-bottom: 1rem; }

/* 按钮 */
.stButton > button {
    background: var(--surface-container);
    color: var(--on-surface);
    border: 1px solid var(--outline-variant);
    border-radius: 8px;
    transition: all 0.2s;
}
.stButton > button:hover { border-color: var(--secondary); color: var(--secondary); }
.stButton > button[kind="primary"], .stButton > button[data-testid="baseButton-primary"] {
    background: var(--primary-container) !important;
    color: var(--on-primary) !important;
    border: none !important;
    font-weight: 700;
    box-shadow: 0 0 15px rgba(0,245,155,0.2);
}
.stButton > button[kind="primary"]:hover { opacity: 0.85; }

/* 进度条 */
[data-testid="stProgress"] > div > div > div { background: linear-gradient(90deg, var(--primary-container), var(--secondary-container)) !important; }

/* 数据框 */
[data-testid="stDataFrame"] {
    background: var(--surface-container);
    border: 1px solid rgba(255,255,255,0.05);
    border-radius: 12px;
}
[data-testid="stDataFrame"] th { color: var(--on-surface-variant); text-transform: uppercase; font-size: 0.75rem; letter-spacing: 0.05em; border-bottom: 1px solid var(--outline-variant); }
[data-testid="stDataFrame"] td { border-bottom: 1px solid rgba(255,255,255,0.03); }

/* 代码块/数据 */
code, .data-mono { font-family: 'Geist', 'SF Mono', 'Fira Code', monospace; letter-spacing: 0.01em; }

/* 容器边框边框 */
[data-testid="stVerticalBlockBorderWrapper"] > div {
    border-radius: 12px;
    border-color: var(--outline-variant);
}

/* 警告/信息/错误框 */
[data-testid="stAlertContainer"] { border-radius: 8px; }

/* 展开器 */
.streamlit-expanderHeader {
    background: var(--surface-container);
    border: 1px solid var(--outline-variant);
    border-radius: 8px;
}

/* 响应式侧边栏宽度 */
@media (max-width: 768px) {
    section[data-testid="stSidebar"] { min-width: 60px !important; width: 60px !important; }
}

/* 隐藏 Streamlit 自动生成的多页面导航 */
[data-testid="stSidebarNav"] { display: none !important; }
section[data-testid="stSidebar"] nav { display: none !important; }
</style>
""", unsafe_allow_html=True)

# ---------- 页面定义 ----------
PAGES = {
    "home": "🏠 驾驶舱",
    "radar": "📡 雷达",
    "kanban": "📋 商品族",
    "shipping": "📦 订单履约",
    "dashboard": "📊 仪表盘",
    "traffic": "📈 流量复盘",
    "tools": "🛠️ 工具",
    "history": "📜 历史",
}

# ---------- 侧边栏 ----------
st.sidebar.markdown(
    '<div style="text-align:center;padding:1rem 0 0.5rem;">'
    '<span style="font-size:2rem;">🤖</span><br>'
    '<span style="font-weight:700;color:var(--primary-container);font-size:1.1rem;">AI 店长</span><br>'
    '<span style="color:var(--on-surface-variant);font-size:0.65rem;font-family:monospace;">v1.1 · 套利扫描</span>'
    '</div>',
    unsafe_allow_html=True,
)
st.sidebar.markdown("---")

page = st.sidebar.radio(
    "导航",
    list(PAGES.keys()),
    format_func=lambda x: PAGES[x],
    label_visibility="collapsed",
    key="main_nav",
)

st.sidebar.markdown("---")
st.sidebar.caption("仅供学习研究")

# ---------- 页面路由 ----------
if page == "home":
    from pages import home
    home.render()
elif page == "radar":
    from pages import radar
    radar.render()
elif page == "kanban":
    from pages import kanban
    kanban.render()
elif page == "shipping":
    from pages import shipping
    shipping.render()
elif page == "dashboard":
    from pages import dashboard
    dashboard.render()
elif page == "traffic":
    from pages import traffic
    traffic.render()
elif page == "tools":
    from pages import tools
    tools.render()
elif page == "history":
    from pages import history
    history.render()