"""店长驾驶舱 — 今日任务中心"""
import streamlit as st
from . import get_db, get_config, icon, section_header, inject_glass_css, h


def render():
    inject_glass_css()
    db = get_db()
    cfg = get_config()

    st.markdown(
        f"<h2 style='display:flex;align-items:center;gap:8px;'>"
        f"{icon('dashboard',24)} 店长驾驶舱"
        f"<span style='font-size:0.7rem;color:var(--on-surface-variant);margin-left:auto;'>今日任务概览</span>"
        f"</h2>",
        unsafe_allow_html=True,
    )

    # ── 今日任务卡片 ──
    pending = db.list_opportunities(limit=200, status="pending")
    approved = db.list_opportunities(limit=200, status="approved")
    
    import json, time as _t
    seller_raw = db.get_config("xianyu_seller_data", "{}")
    seller_data = json.loads(seller_raw) if seller_raw else {}
    last_sync = db.get_config("xianyu_last_sync", "never")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        count = len(pending)
        st.metric("待审核", count)
        if count > 0:
            st.caption("去审核高分商品族")
    with c2:
        count = len(approved)
        st.metric("待铺货", count)
        if count > 0:
            st.caption("生成铺货草稿上架")
    with c3:
        from modules.shipping import SHIPPING_STATUSES
        orders = db.get_shipping_orders()
        active = [o for o in orders if o.get('shipping_status','') not in ('已完成','已取消')]
        st.metric("待处理订单", len(active))
    with c4:
        st.metric("在线商品", seller_data.get("online_items", "?"))

    # ── 关键指标 ──
    st.markdown("---")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("今日曝光", seller_data.get("exposure", "?"))
    with c2:
        st.metric("今日访问", seller_data.get("visitors", "?"))
    with c3:
        st.metric("今日订单", seller_data.get("orders", 0))
    with c4:
        rev = seller_data.get("revenue", 0)
        st.metric("今日成交", f"Y{rev:.0f}" if rev else "Y0")
    st.caption(f"上次同步: {last_sync}")

    # ── 建议操作列表 ──
    st.markdown("---")
    section_header("建议操作", "lightbulb")

    tasks = []
    
    if len(pending) > 0:
        high_roi = [o for o in pending if o.get('roi', 0) >= 50]
        tasks.append(("审核商品族", f"{len(pending)} 个待审核 ({len(high_roi)} 个高ROI)", "kanban"))
    
    if len(approved) > 0:
        tasks.append(("生成铺货草稿", f"{len(approved)} 个已通过待铺货", "kanban"))
    
    active_orders = [o for o in orders if o.get('shipping_status', '') == '待下单']
    if active_orders:
        tasks.append(("待下单发货", f"{len(active_orders)} 个订单待去PDD下单", "shipping"))

    stats = db.get_stats()
    if stats.get('total_opportunities', 0) < 10:
        tasks.append(("启动雷达扫描", "暂无套利机会，需要扫描", "radar"))

    if not tasks:
        tasks.append(("系统正常", "暂无待办任务", "home"))

    for action, detail, target in tasks:
        st.markdown(f"""
        <div class="glass-card" style="padding:0.5rem 1rem;margin-bottom:0.3rem;">
        <b>{action}</b>
        <span style="color:var(--text-muted);margin-left:8px;">{detail}</span>
        </div>
        """, unsafe_allow_html=True)

    # ── 待处理订单速览 ──
    if active:
        st.markdown("---")
        section_header("待处理订单", "local_shipping")
        for o in active[:5]:
            status = o.get("shipping_status", "?")
            buyer = o.get("buyer_name", "?")
            profit = o.get("profit", 0)
            st.caption(f"{status} · {buyer} · Y{profit:.0f}")

    # ── 类目过滤统计 ──
    st.markdown("---")
    st.caption("服装类/低质量商品已自动过滤，不再进入待审核列表。")
    st.caption("类目黑名单包括: 女装、男装、童装、裤子、鞋袜等30+品类。")

    # AI 日报
    if st.button("AI 生成今日日报", use_container_width=True):
        from modules.ai_service import _call
        summary = _call(
            f"今日运营数据：待审核{len(pending)}个 已通过{len(approved)}个 在线商品{seller_data.get('online_items','?')} 今日曝光{seller_data.get('exposure','?')} 访问{seller_data.get('visitors','?')} 订单{seller_data.get('orders',0)}。请生成一个30字日报总结和明天建议。",
            "你是电商运营助手，简短务实。",
            0.3
        )
        if summary:
            st.success(summary) if summary and len(summary) < 10 else st.info(summary)
