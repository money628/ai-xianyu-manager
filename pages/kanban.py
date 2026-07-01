"""看板 — 决策审核（玻璃卡片 + 多型号聚合）"""
import streamlit as st
from . import get_db, icon, section_header, inject_glass_css, h


def render():
    inject_glass_css()
    db = get_db()

    st.markdown(
        f"<h2 style='display:flex;align-items:center;gap:8px;'>"
        f"{icon('dashboard_customize',24)} 决策看板"
        f"<span style='font-size:0.7rem;font-weight:400;color:var(--on-surface-variant);margin-left:auto;'>人工审核 · 半自动铺货</span>"
        f"</h2>",
        unsafe_allow_html=True,
    )

    # ── 顶部分页 ──
    tab = st.radio("模式", ["审核", "铺货"], horizontal=True, key="kanban_tab")

    if tab == "铺货":
        try:
            _render_publish_workbench(db)
        except Exception as e:
            st.error(f"铺货页面加载失败")
            import traceback
            st.code(traceback.format_exc())
        return

    # ── Stepper ──
    st.markdown(
        f'<div class="stepper">'
        f'<span class="step active">{icon("travel_explore",16)} 系统分析</span>'
        f'<span class="arrow">{icon("arrow_forward",14)}</span>'
        f'<span class="step">{icon("rate_review",16)} 人工审核</span>'
        f'<span class="arrow">{icon("arrow_forward",14)}</span>'
        f'<span class="step">{icon("rocket_launch",16)} 决策执行</span>'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.progress(1 / 3)

    pending = [o for o in db.list_opportunities(limit=50, status="pending")
               if o.get("buy_platform") != "1688"]
    approved = [o for o in db.list_opportunities(limit=20, status="approved")
                if o.get("buy_platform") != "1688"]
    rejected = db.list_opportunities(limit=10, status="rejected")

    view_mode = st.radio("展示方式", ["列表", "多型号聚合"], horizontal=True, key="kanban_view")

    if view_mode == "多型号聚合" and pending:
        _render_family_view(pending, db)
        return

    c1, c2, c3 = st.columns(3)

    # ── 待审核 ──
    with c1:
        # 批量操作
        if pending:
            bc1, bc2, bc3 = st.columns(3)
            with bc1:
                if st.button("✅ 全部通过", key="approve_all", type="primary", use_container_width=True):
                    for opp in pending:
                        db.update_opportunity_status(opp["id"], "approved")
                    st.rerun()
            with bc2:
                if st.button("❌ 全部拒绝", key="reject_all", use_container_width=True):
                    for opp in pending:
                        db.update_opportunity_status(opp["id"], "rejected")
                    st.rerun()
            with bc3:
                if st.button("🤖 AI 审核", key="ai_review", use_container_width=True,
                             help="AI 逐个分析商品，给出通过/拒绝建议"):
                    _ai_review_pending(pending, db)
        st.markdown(
            f"<h4 style='display:flex;align-items:center;gap:6px;border-bottom:1px solid rgba(255,255,255,0.04);padding-bottom:8px;'>"
            f"{icon('pending_actions',18)} 待审核 <span style='color:var(--on-surface-variant);font-weight:400;'>({len(pending)})</span>"
            f"</h4>",
            unsafe_allow_html=True,
        )
        if not pending:
            st.info(f"{icon('info',16)} 暂无待审核机会")
        for opp in pending:
            _render_pending_card(opp, db)

    # ── 已通过 ──
    with c2:
        st.markdown(
            f"<h4 style='display:flex;align-items:center;gap:6px;border-bottom:1px solid rgba(255,255,255,0.04);padding-bottom:8px;'>"
            f"{icon('check_circle',18)} 已通过 <span style='color:var(--on-surface-variant);font-weight:400;'>({len(approved)})</span>"
            f"</h4>",
            unsafe_allow_html=True,
        )
        if not approved:
            st.info(f"{icon('info',16)} 暂无已通过机会")
        for opp in approved:
            _render_approved_card(opp)

    # ── 已拒绝 ──
    with c3:
        st.markdown(
            f"<h4 style='display:flex;align-items:center;gap:6px;border-bottom:1px solid rgba(255,255,255,0.04);padding-bottom:8px;'>"
            f"{icon('cancel',18)} 已拒绝 <span style='color:var(--on-surface-variant);font-weight:400;'>({len(rejected)})</span>"
            f"</h4>",
            unsafe_allow_html=True,
        )
        if not rejected:
            st.info(f"{icon('info',16)} 暂无已拒绝机会")
        for opp in rejected:
            _render_rejected_card(opp)

    # ── 黑名单 ──
    st.markdown("---")
    section_header("拦截清单管理", "block")
    with st.form("add_blacklist", clear_on_submit=True):
        c1, c2, c3 = st.columns([1, 2, 1])
        with c1:
            bl_type = st.selectbox("类型", ["卖家", "品牌", "关键词"])
            type_map = {"卖家": "seller", "品牌": "brand", "关键词": "keyword"}
        with c2:
            bl_value = st.text_input("值", placeholder="店铺名/品牌名/关键词")
        with c3:
            bl_reason = st.text_input("原因")
        if st.form_submit_button(f"{icon('add_circle',16)} 添加规则", type="primary") and bl_value.strip():
            db.add_blacklist(type_map[bl_type], bl_value.strip(), bl_reason)
            st.rerun()

    bl = db.list_blacklist()
    if bl:
        type_cn = {"seller": "卖家", "brand": "品牌", "keyword": "关键词", "category": "品类"}
        for item in bl:
            c1, c2 = st.columns([5, 1])
            with c1:
                t = h(type_cn.get(item.get("type", ""), item.get("type", "")))
                st.markdown(
                    f'<span style="background:rgba(255,255,255,0.04);padding:2px 6px;border-radius:4px;font-size:0.75rem;'
                    f'font-family:monospace;">{t}</span> '
                    f'<b>{h(item["value"])}</b> '
                    f'<span style="color:var(--on-surface-variant);font-size:0.85rem;">· {h(item.get("reason",""))}</span>',
                    unsafe_allow_html=True,
                )
            with c2:
                if st.button(f"{icon('delete',16)} 移除", key=f"rm_{item['id']}"):
                    db.remove_blacklist(item["id"])
                    st.rerun()


def _render_pending_card(opp, db):
    buy_title = (opp.get("buy_title") or opp.get("title", ""))[:70]
    buy_price = opp.get("buy_price", 0)
    sell_price = opp.get("sell_price", 0)
    profit = opp.get("profit", 0)
    roi = opp.get("roi", 0)
    confidence = opp.get("confidence", 0)
    buy_url = opp.get("buy_url", "").strip() or opp.get("product_url", "").strip()
    sell_url = opp.get("sell_url", "").strip() or opp.get("source_product_url", "").strip()

    roi_badge = 'high' if roi >= 60 else 'mid' if roi >= 30 else 'low'
    roi_label = '高' if roi >= 60 else '中' if roi >= 30 else '低'

    link_html = ""
    if buy_url:
        link_html += f'<a href="{buy_url}" target="_blank" rel="noopener">🔗 进货</a>'
    if sell_url:
        link_html += f'<a href="{sell_url}" target="_blank" rel="noopener">📱 卖出</a>'

    st.markdown(f"""
<div class="glass-card product-card">
    <div class="pc-title">{h(buy_title)}<span class="badge badge-{roi_badge}">{roi_label} ROI {roi:.0f}%</span></div>
    <div class="pc-meta">
        置信度 <b>{confidence:.0%}</b>
    </div>
    <div class="pc-prices">
        <div class="pc-price-item buy"><div class="label">进价</div><div class="value">¥{buy_price:.2f}</div></div>
        <div class="pc-arrow">→</div>
        <div class="pc-price-item sell"><div class="label">售价</div><div class="value">¥{sell_price:.2f}</div></div>
        <div class="pc-arrow">=</div>
        <div class="pc-price-item profit"><div class="label">净利</div><div class="value">¥{profit:.2f}</div></div>
    </div>
    <div class="pc-links">{link_html}</div>
</div>
""", unsafe_allow_html=True)

    with st.expander("查看详情"):
        st.caption(f"进价平台: {h(opp.get('buy_platform',''))} → 出售平台: {h(opp.get('sell_platform',''))}")
        st.caption(f"置信度: {confidence:.0%} | 评分: {opp.get('score', 0):.2f}")
        st.caption(f"采购商品ID: {opp.get('buy_product_id', opp.get('product_id', ''))}")
        st.caption(f"出售商品ID: {opp.get('sell_product_id', '')}")
        if opp.get('description') or opp.get('goods_rating'):
            st.caption(f"描述: {opp.get('description', '')[:100]}")
            st.caption(f"评分: {opp.get('goods_rating', 'N/A')}")
        # 关注按钮
        buy_pid = opp.get('buy_product_id', '')
        if buy_pid and st.button("⭐ 关注此商品", key=f"watch_{opp['id']}"):
            db.toggle_watch_product(buy_pid, opp.get('buy_platform', ''), True)
            st.success("已加入关注列表")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("✅ 通过", key=f"pass_{opp['id']}", type="primary", use_container_width=True):
            db.update_opportunity_status(opp["id"], "approved")
            st.rerun()
    with c2:
        if st.button("❌ 拒绝", key=f"rej_{opp['id']}", use_container_width=True):
            db.update_opportunity_status(opp["id"], "rejected")
            st.rerun()


def _render_approved_card(opp):
    roi = opp.get("roi", 0)
    title = h((opp.get("buy_title") or opp.get("title", "无"))[:50])
    roi_c = 'high' if roi >= 60 else 'mid'
    buy_url = opp.get("buy_url", "") or opp.get("product_url", "")
    sell_img = opp.get("sell_image") or opp.get("buy_image", "")

    # 图片 + 标题
    img_html = f'<img src="{sell_img}" style="max-width:60px;max-height:60px;border-radius:4px;float:left;margin-right:8px;">' if sell_img else ""
    link_html = f'<a href="{buy_url}" target="_blank" style="font-size:0.65rem;color:var(--primary-container);">进货链接</a>' if buy_url else ""

    st.markdown(f"""
<div class="glass-card" style="padding:0.5rem 0.75rem;overflow:hidden;">
{img_html}
<span class="badge badge-high" style="margin-right:4px;">✅</span>
<b>{title}</b>
{link_html}
<span style="font-size:0.78rem;color:var(--text-muted);margin-left:6px;">
ROI <b class="roi-{roi_c}">{roi:.0f}%</b> · +¥{opp.get('profit',0):.2f}
</span>
</div>
""", unsafe_allow_html=True)

    with st.expander("铺货工作台", expanded=True):
        from modules.publisher import (
            generate_publish_draft, mark_published, check_rate_limit,
        )

        if f"draft_{opp['id']}" not in st.session_state:
            st.session_state[f"draft_{opp['id']}"] = generate_publish_draft(opp)
        draft = st.session_state[f"draft_{opp['id']}"]

        if draft.publish_status == "MANUALLY_PUBLISHED":
            st.success("✅ 已发布")
            return

        # ── 铺货 ──
        st.markdown("**标题**")
        st.code(draft.title, language=None)

        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("下载图片", key=f"img_{opp['id']}", use_container_width=True):
                from modules.image_pack import generate_image_pack
                pack = generate_image_pack(opp, str(opp.get("id", "")))
                if pack["downloaded"] > 0:
                    st.success(f"已下载 {pack['downloaded']} 张 ({pack['zip_size']/1024:.0f}KB)")
                    st.caption(f"路径: {pack['zip_path']}")
                elif pack["failed"] > 0:
                    st.warning(f"下载失败 {pack['failed']} 张")
                else:
                    st.info("未找到图片URL")
        with c2:
            if st.button("自动上架填表", key=f"autofill_{opp['id']}", use_container_width=True):
                from modules.auto_listing import auto_fill_listing
                result = auto_fill_listing(draft, opp)
                if result["ok"]:
                    st.success(f"已填写 {sum(1 for s in result['steps'] if s.get('ok'))} 个字段，浏览器保持打开")
                    st.caption("请手动上传图片并点发布")
                else:
                    st.warning(result.get('message', '自动填写不完整'))
        with c3:
            if st.button("AI 智能定价", key=f"aiprice_{opp['id']}", use_container_width=True):
                from modules.ai_service import _call
                info = f"商品：{(opp.get('buy_title','') or '')[:40]} 进价{opp.get('buy_price',0)} 建议售价{opp.get('sell_price',0)}"
                advice = _call(f"给这个闲鱼商品建议一个售价和理由（30字以内）：{info}", "你是闲鱼定价专家。", 0.3)
                if advice:
                    st.info(advice)
        with st.container():
            st.caption(f"售价 Y{draft.price:.0f} | 利润 Y{draft.profit:.0f}")
        st.markdown("**描述**")
        st.code(draft.description[:200], language=None)

        st.caption(f"售价 ¥{draft.price:.0f} | 利润 ¥{draft.profit:.0f} | ROI {draft.roi:.0f}%")

        c1, c2 = st.columns(2)
        with c1:
            allowed, reason, _, _ = check_rate_limit()
            btn = st.button("已发布到闲鱼", key=f"done_{opp['id']}", type="primary",
                            disabled=not allowed, use_container_width=True)
            if btn:
                mark_published(draft)
                st.success("记录成功")
                st.rerun()
        with c2:
            if st.button("放弃", key=f"ab_{opp['id']}", use_container_width=True):
                from modules.publisher import mark_abandoned
                mark_abandoned(draft, "user_abandoned")
                if f"draft_{opp['id']}" in st.session_state:
                    del st.session_state[f"draft_{opp['id']}"]
                st.rerun()


def _render_rejected_card(opp):
    title = h((opp.get("buy_title") or opp.get("title", ""))[:45])
    st.markdown(f"""
<div class="glass-card" style="opacity:0.5;padding:0.35rem 0.75rem;">
<span style="text-decoration:line-through;font-size:0.78rem;">{title}</span>
<span style="font-size:0.7rem;color:var(--text-muted);">· ROI {opp.get('roi',0):.0f}%</span>
</div>
""", unsafe_allow_html=True)

def _render_publish_workbench(db):
    """集中铺货工作台"""
    try:
        from modules.publisher import get_publish_stats, generate_publish_draft, mark_published, check_rate_limit, mark_abandoned
    except ImportError as e:
        st.error(f"模块加载失败: {e}")
        return

    approved = [o for o in db.list_opportunities(limit=50, status="approved")
                if o.get("buy_platform") != "1688"]
    
    try:
        stats = get_publish_stats()
    except Exception:
        stats = {"published_today": 0, "max_published": 3, "drafts_today": 0, "max_drafts": 10}

    c1, c2, c3 = st.columns(3)
    with c1: st.metric("待铺货", len(approved))
    with c2: st.metric("今日已发", stats["published_today"], delta=f"/{stats['max_published']}")
    with c3: st.metric("今日草稿", stats["drafts_today"], delta=f"/{stats['max_drafts']}")

    if not approved:
        st.info('暂无待铺货商品，先去审核页面批准一些机会吧')
        return

    search = st.text_input("筛选商品", placeholder="输入商品名称...", key="pub_search")
    filtered = [o for o in approved if not search or search.lower() in (o.get("buy_title") or "").lower()
                or search.lower() in (o.get("sell_title") or "").lower()]

    st.markdown("---")
    cols = st.columns(2)
    for idx, opp in enumerate(filtered):
        with cols[idx % 2]:
            _render_publish_item(opp)


def _render_publish_item(opp):
    """单个铺货卡片"""
    from modules.publisher import generate_publish_draft, mark_published, check_rate_limit

    roi = opp.get("roi", 0)
    title = h((opp.get("buy_title") or opp.get("title", "无"))[:40])
    roi_c = 'high' if roi >= 60 else 'mid'
    buy_url = opp.get("buy_url", "") or opp.get("product_url", "")
    sell_img = opp.get("sell_image") or opp.get("buy_image", "")
    draft_key = f"pub_{opp['id']}"

    if draft_key not in st.session_state:
        st.session_state[draft_key] = generate_publish_draft(opp)
    draft = st.session_state[draft_key]

    if draft.publish_status == "MANUALLY_PUBLISHED":
        st.success(f"已发布: {title}")
        return

    img_html = f'<img src="{sell_img}" style="max-width:60px;max-height:60px;border-radius:4px;float:left;margin-right:8px;">' if sell_img else ""
    link_html = f'<a href="{buy_url}" target="_blank" style="font-size:0.65rem;color:var(--primary-container);">进货</a>' if buy_url else ""

    st.markdown(f"""
<div class="glass-card" style="padding:0.4rem 0.7rem;overflow:hidden;">
{img_html}
<span class="badge badge-{roi_c}" style="margin-right:4px;">ROI {roi:.0f}%</span>
<b style="font-size:0.8rem;">{title}</b>
{link_html}
<span style="font-size:0.7rem;color:var(--text-muted);"> +Y{opp.get('profit',0):.0f}</span>
</div>
""", unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        st.caption("标题")
        st.code(draft.title, language=None)
    with c2:
        st.caption("描述")
        st.code(draft.description[:200], language=None)

    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        st.caption(f"售价 Y{draft.price:.0f} | 利润 Y{draft.profit:.0f}")
    with c2:
        allowed, reason, _, _ = check_rate_limit()
        if st.button("已发布", key=f"pd_{opp['id']}", type="primary",
                     disabled=not allowed, use_container_width=True):
            mark_published(draft)
            st.rerun()
    with c3:
        if st.button("放弃", key=f"pa_{opp['id']}", use_container_width=True):
            from modules.publisher import mark_abandoned
            mark_abandoned(draft, "user_abandoned")
            if draft_key in st.session_state:
                del st.session_state[draft_key]
            st.rerun()
    st.markdown("---")


def _render_family_view(pending, db):
    """多型号聚合视图"""
    from modules.family_aggregator import group_variants_into_families, generate_family_publish_draft

    families = group_variants_into_families(pending)
    total_opps = sum(f.model_count for f in families)

    st.markdown(f"聚合: {len(pending)} 条机会 → {len(families)} 个商品族 ({total_opps} 个型号)")

    if not families:
        st.info("无待审核机会")
        return

    cols = st.columns(3)
    col_idx = 0

    for family in families:
        with cols[col_idx % 3]:
            grade_color = {"A": "#00f59b", "B": "#fbd400", "C": "#ff9800", "D": "#ff6b6b"}.get(family.family_grade, "#888")

            # 型号摘要
            models_text = " / ".join(v.model for v in family.variants[:5])
            if family.model_count > 5:
                models_text += f" 等{family.model_count}款"

            # 价格区间
            price_text = f"Y{family.min_cost_price:.0f}-{family.max_cost_price:.0f}" if family.max_cost_price > family.min_cost_price else f"Y{family.min_cost_price:.0f}"

            # 卡片
            st.markdown(f"""
<div class="glass-card product-card" style="border-left:3px solid {grade_color};margin-bottom:0.5rem;">
    <div class="pc-title" style="margin-bottom:4px;">
        <span style="color:{grade_color};font-weight:800;margin-right:4px;">{family.family_grade}</span>
        {h(family.normalized_title or family.family_title)[:50]}
    </div>
    <div style="font-size:0.7rem;color:var(--text-muted);margin-bottom:4px;">
        {models_text}
    </div>
    <div style="font-size:0.75rem;margin-bottom:4px;">
        进价 {price_text} | 售价 Y{family.min_sale_price:.0f}-{family.max_sale_price:.0f} | 净利 Y{family.best_profit:.0f}
    </div>
    <div style="font-size:0.7rem;color:var(--text-muted);margin-bottom:4px;">
        ROI {family.best_roi:.0f}% | 置信: 匹配{family.family_match_confidence:.0%} 价格{family.family_price_confidence:.0%}
    </div>
</div>
""", unsafe_allow_html=True)

            # 展开型号
            with st.expander(f"型号明细 ({family.model_count}款)"):
                for v in family.variants:
                    st.caption(
                        f"**{v.model}** | "
                        f"进Y{v.cost_price:.0f} → 售Y{v.sale_price:.0f} | "
                        f"+Y{v.profit:.0f} (ROI {v.roi:.0f}%) | "
                        f"匹{v.match_confidence:.0%}"
                    )

            # 操作
            bc1, bc2, bc3 = st.columns(3)
            with bc1:
                source_url = family.source_url or family.variants[0].raw_opportunity.get("buy_url", "#") if family.variants else "#"
                st.markdown(f'<a href="{source_url}" target="_blank" style="font-size:0.7rem;color:#00f59b;">进货链接</a>', unsafe_allow_html=True)
            with bc2:
                if st.button("通过", key=f"pass_fam_{abs(hash(family.family_id))}", use_container_width=True):
                    for v in family.variants:
                        opp = v.raw_opportunity
                        if opp.get("id"):
                            db.update_opportunity_status(opp["id"], "approved")
                    st.rerun()
            with bc3:
                draft = generate_family_publish_draft(family)
                status = draft.get("status", "?")
                if st.button(f"草稿({status})", key=f"draft_fam_{abs(hash(family.family_id))}", use_container_width=True,
                             disabled=status != "DRAFT_GENERATED"):
                    st.success("草稿已生成")

        col_idx += 1

    st.markdown("---")
    if st.button("返回列表视图"):
        st.rerun()


def _ai_review_pending(pending, db):
    """AI 批量审核待审核商品"""
    if not pending:
        return
    items_text = "\n".join(
        f"{i+1}. {o.get('buy_title','')[:40]} P{o.get('buy_price',0)}->Y{o.get('sell_price',0)} ROI{o.get('roi',0):.0f}%"
        for i, o in enumerate(pending[:10])
    )
    from modules.ai_service import _call
    result = _call(
        f"审核以下{len(pending[:10])}个套利商品。对每个给出：通过/拒绝/需人工，以及一句话理由（品类是否好卖、ROI是否合理、是否有风险）。每行格式：序号.决定 理由\n{items_text}",
        "你是闲鱼选品专家。只分析电商品类、利润合理性、供应链风险。不说废话。", 0.2
    )
    if result:
        st.markdown("### AI 审核建议")
        for i, line in enumerate(result.strip().split("\n")):
            if i >= len(pending):
                break
            line = line.strip()
            if not line or len(line) < 3:
                continue
            opp = pending[i] if i < len(pending) else None
            if not opp:
                continue
            title = (opp.get('buy_title','') or '')[:30]
            roi = opp.get('roi', 0)
            decision = "通过" if "通过" in line else ("拒绝" if "拒绝" in line else "需人工")
            color = "#00f59b" if decision == "通过" else ("#ff6b6b" if decision == "拒绝" else "#fbd400")
            with st.container():
                c1, c2, c3 = st.columns([4, 2, 2])
                with c1:
                    st.markdown(f"<span style='color:{color};font-weight:700;'>{decision}</span> {title}")
                    st.caption(line[line.find(" ")+1:].strip() if " " in line else line)
                with c2:
                    if st.button(f"通过 {i}", key=f"ai_p_{opp['id']}", type="primary" if decision == "通过" else "secondary"):
                        db.update_opportunity_status(opp["id"], "approved")
                        st.rerun()
                with c3:
                    if st.button(f"拒绝 {i}", key=f"ai_r_{opp['id']}"):
                        db.update_opportunity_status(opp["id"], "rejected")
                        st.rerun()
                st.markdown("---")
