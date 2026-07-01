"""运营仪表盘 — 销售额/利润/订单趋势"""
import streamlit as st
import traceback
from . import get_db, icon, section_header, inject_glass_css, h


def render():
    inject_glass_css()
    db = get_db()

    # ====== 诊断 ======
    import sys
    missing = [m for m in ['get_dashboard_stats'] if not hasattr(db, m)]
    if missing:
        st.error("### 数据库方法缺失")
        st.code(f"来源: {getattr(sys.modules.get(db.__class__.__module__), '__file__', '?')}")
        st.write(f"缺失: {missing}")
        st.info("请关闭所有窗口后双击 `重启.bat`")
        return

    st.markdown(
        f"<h2 style='display:flex;align-items:center;gap:8px;'>"
        f"{icon('bar_chart',24)} 运营仪表盘"
        f"</h2>",
        unsafe_allow_html=True,
    )

    try:
        from modules.dashboard_data import build_dashboard_data
        import plotly.graph_objects as go
        import plotly.express as px
    except ImportError as e:
        st.error(f"模块加载失败: {e}")
        return

    days = st.selectbox("时间范围", [7, 30, 90], index=1, key="dash_days")

    try:
        data = build_dashboard_data(db, days)
    except Exception as e:
        st.error(f"数据加载失败: {e}")
        st.code(traceback.format_exc())
        return

    # ── KPI 卡片 ──
    c1, c2, c3, c4 = st.columns(4)
    td = data.get("today", {}) or {}
    with c1: st.metric("今日销售额", f"¥{td.get('revenue', 0):.0f}")
    with c2: st.metric("今日利润", f"¥{td.get('profit', 0):.0f}")
    with c3: st.metric("今日订单", td.get('orders', 0))
    with c4: st.metric("平均 ROI", f"{data.get('avg_roi', 0):.1f}%")

    c1, c2, c3, c4 = st.columns(4)
    wk = data.get("week", {}) or {}
    with c1: st.metric("近7天销售额", f"¥{wk.get('revenue', 0):.0f}")
    with c2: st.metric("近7天利润", f"¥{wk.get('profit', 0):.0f}")
    with c3: st.metric("已铺货", data.get('listed_count', 0))
    with c4: st.metric("待发货", data.get('pending_shipping', 0))

    # ── 趋势图 ──
    trend = data.get("daily_trend", [])
    if trend and isinstance(trend, list):
        try:
            dates = [r.get("date", str(r)) for r in trend]
            tab1, tab2, tab3 = st.tabs(["销售额趋势", "利润趋势", "订单趋势"])

            with tab1:
                try:
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(x=dates, y=[r.get("revenue", 0) for r in trend],
                                             mode="lines+markers", name="销售额", line=dict(color="#00f59b")))
                    fig.update_layout(template="plotly_dark", height=300, margin=dict(l=20, r=20, t=20, b=20))
                    st.plotly_chart(fig, use_container_width=True)
                except Exception as e:
                    st.caption(f"图表渲染失败: {e}")

            with tab2:
                try:
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(x=dates, y=[r.get("profit", 0) for r in trend],
                                             mode="lines+markers", name="利润", line=dict(color="#fbd400")))
                    fig.update_layout(template="plotly_dark", height=300, margin=dict(l=20, r=20, t=20, b=20))
                    st.plotly_chart(fig, use_container_width=True)
                except Exception as e:
                    st.caption(f"图表渲染失败: {e}")

            with tab3:
                try:
                    fig = go.Figure()
                    fig.add_trace(go.Bar(x=dates, y=[r.get("orders", 0) for r in trend], name="订单",
                                         marker_color="#14d1ff"))
                    fig.update_layout(template="plotly_dark", height=300, margin=dict(l=20, r=20, t=20, b=20))
                    st.plotly_chart(fig, use_container_width=True)
                except Exception as e:
                    st.caption(f"图表渲染失败: {e}")
        except Exception as e:
            st.caption(f"数据格式异常: {e}")
    else:
        st.info("暂无订单数据。创建发货订单后趋势图将自动显示。")

    # ── 类目排行 ──
    st.markdown("---")
    section_header("类目利润排行", "leaderboard")
    cat_data = data.get("category_profit", [])
    if cat_data and isinstance(cat_data, list) and len(cat_data) > 0:
        try:
            fig = px.bar(x=[r["category"] for r in cat_data],
                         y=[r["profit"] for r in cat_data],
                         labels={"x": "类目", "y": "利润"},
                         template="plotly_dark", height=300)
            fig.update_traces(marker_color="#00f59b")
            st.plotly_chart(fig, use_container_width=True)
        except Exception as e:
            st.caption(f"类目图表渲染失败: {e}")
    else:
        st.caption("暂无类目数据")
