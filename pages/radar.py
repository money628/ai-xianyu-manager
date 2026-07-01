"""雷达 — 自动品类扫描 + Plotly 雷达图/热力图 + 后台调度器"""
import time
from datetime import datetime

import streamlit as st

from . import (
    get_config, get_db, get_scheduler, icon, metric_card, section_header,
    opportunity_card, inject_glass_css,
)


def render():
    inject_glass_css()
    st.markdown(
        f"<h2 style='display:flex;align-items:center;gap:8px;'>"
        f"{icon('radar',24)} 雷达 {icon('scan',20)}"
        f"<span style='font-size:0.7rem;font-weight:400;color:var(--on-surface-variant);margin-left:auto;'>跨平台价差监测</span>"
        f"</h2>",
        unsafe_allow_html=True,
    )

    cfg = get_config()
    db = get_db()

    # ── 获取调度器 ──
    scheduler = get_scheduler()
    sched_status = scheduler.status

    # 自动启动：config.ini auto_run=true 且调度器未运行
    if cfg.get("system", {}).get("auto_run", True) and not sched_status["running"]:
        scheduler.start()
        sched_status = scheduler.status

    # ── 关键词池初始化 ──
    pool = db.get_keyword_pool_stats()
    if pool["total"] == 0:
        with st.spinner(f"{icon('sync',18)} 首次启动，正在从种子品类扩展关键词池..."):
            from modules.discovery import expand_to_flat_list, expand_apple_keywords
            seeds = cfg.get("scanner", {}).get("seed_categories", [])
            if not seeds:
                from modules.discovery import DEFAULT_SEED_CATEGORIES
                seeds = DEFAULT_SEED_CATEGORIES
            all_kws = expand_to_flat_list(seeds)
            all_kws.extend(expand_apple_keywords())
            db.add_keywords(all_kws, source="suggest")
            pool = db.get_keyword_pool_stats()
        st.success(f"{icon('check_circle',18)} 关键词池初始化完成：{pool['total']} 个关键词")

    # ── 调度器状态面板 ──
    section_header("自动扫描调度器", "monitoring")
    _render_scheduler_panel(scheduler, sched_status)

    # ── 数据源状态 ──
    _render_datasource_status()

    st.markdown("---")

    # ── 状态栏 ──
    c1, c2, c3, c4 = st.columns(4)
    with c1: metric_card("关键词池", pool["total"], icon_name="database")
    with c2: metric_card("已扫描", pool["scanned"], icon_name="task_alt")
    with c3: metric_card("待扫描", pool["pending"], icon_name="pending")
    with c4: metric_card("间隔", f'{int(cfg.get("scanner",{}).get("scan_interval_minutes",60) or 60)}分钟', icon_name="timer")

    if pool["total"] > 0:
        pct = pool["scanned"] / pool["total"]
        st.progress(pct, text=f"扫描进度: {pool['scanned']}/{pool['total']} ({pct:.0%})")

    # ── 自定义关键词扫描 ──
    custom_kw = st.text_input("自定义关键词", placeholder="输入要搜索的关键词...", key="custom_kw_input")
    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        if st.button(f"{icon('travel_explore',18)} 搜索此关键词", type="secondary", disabled=not custom_kw.strip()):
            _scan_custom_kw(custom_kw.strip(), cfg, db)
    with c2:
        if st.button(f"🔥 爆款反向找货", type="primary", disabled=not custom_kw.strip(),
                     help="先搜闲鱼热门商品，再反向去PDD找同款低价货源"):
            _reverse_source_kw(custom_kw.strip(), cfg, db)
    with c3:
        st.caption("普通搜索 | 🔥反向找货：闲鱼爆款 → PDD找低价同款")

    # ── 手动扫描按钮 ──
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        if st.button(f"{icon('refresh',18)} 立即扫描（手动）", type="primary", use_container_width=True):
            _run_auto_scan(cfg, db)
            st.rerun()
    with c2:
        if st.button(f"{icon('refresh',16)} 刷新结果", use_container_width=True):
            st.rerun()
    with c3:
        import time
        st.caption(f"页面加载: {time.strftime('%H:%M:%S')}")

    st.markdown("---")

    # ── 双轨监测 ──
    section_header("双轨监测", "trending_up")
    c1, c2 = st.columns(2)
    with c1:
        _render_radar_chart(db)
    with c2:
        _render_trend_chart(db)

    # ── 最新机会 ──
    section_header("最新机会", "list_alt")
    filter_roi = st.selectbox("ROI 筛选", ["全部", "≥30%", "≥60%"], index=0)
    roi_filter = 0
    if filter_roi == "≥30%":
        roi_filter = 30
    elif filter_roi == "≥60%":
        roi_filter = 60

    opps = db.list_opportunities(limit=50, min_roi=roi_filter)
    if not opps:
        st.info(f"{icon('info',16)} 暂无数据，等待扫描完成...")
        return

    c1, c2, c3 = st.columns(3)
    with c1: metric_card("总机会", len(opps), icon_name="sell")
    avg_roi = sum(o.get("roi", 0) for o in opps) / len(opps) if opps else 0
    with c2: metric_card("平均ROI", f"{avg_roi:.1f}%", icon_name="trending_up")
    with c3: metric_card("高ROI(≥60%)", len([o for o in opps if o.get("roi", 0) >= 60]), icon_name="local_fire_department")

    cols = st.columns(3)
    for i, opp in enumerate(opps[:12]):
        with cols[i % 3]:
            opportunity_card(opp, i + 1)

    if len(opps) > 12:
        with st.expander(f"查看全部 {len(opps)} 条机会"):
            for opp in opps[12:]:
                opportunity_card(opp)


def _render_datasource_status():
    """渲染数据源状态（闲鱼 + PDD 登录态）"""
    import json, time as _t
    from pathlib import Path
    data_dir = Path(__file__).resolve().parent.parent / "data" / "login_states"
    
    c1, c2 = st.columns(2)
    
    # 闲鱼
    with c1:
        xy_state = data_dir / "xianyu_state.json"
        xy_ok = False
        xy_detail = ""
        if xy_state.exists():
            try:
                d = json.loads(xy_state.read_text(encoding="utf-8"))
                cookies = d.get("cookies", []) if isinstance(d, dict) else []
                key_names = {"t", "cookie2", "unb"}
                found = set()
                min_h = float('inf')
                now = _t.time()
                for c in cookies:
                    if c.get("name", "") in key_names:
                        found.add(c.get("name"))
                        exp = c.get("expires", -1)
                        if isinstance(exp, (int, float)) and exp > 0:
                            h = (exp - now) / 3600
                            if h < min_h: min_h = h
                xy_ok = bool(found & {"t", "cookie2", "unb"})
                if min_h != float('inf'):
                    xy_detail = f" ({min_h:.0f}h 后过期)" if min_h < 48 else ""
                    if min_h < 24: xy_detail = f" ({min_h:.0f}h 后过期!)"
                    if min_h <= 0: xy_ok = False
            except Exception:
                xy_ok = False
        
        if xy_ok:
            st.success(f"闲鱼 已登录{xy_detail}")
        else:
            st.warning("闲鱼 未登录 — 去工具页扫码登录")
    
    # PDD
    with c2:
        pdd_state = data_dir / "pdd_state.json"
        if pdd_state.exists():
            st.success("PDD API 正常")
        else:
            st.info("PDD API 模式 (无需浏览器登录)")

def _render_scheduler_panel(scheduler, sched_status: dict):
    """渲染调度器控制面板"""
    running = sched_status["running"]
    degraded = sched_status["degraded"]
    failures = sched_status["consecutive_failures"]
    last_scan = sched_status["last_scan_time"]
    next_scan = sched_status["next_scan_time"]
    total_scans = sched_status["total_scans"]
    total_opps = sched_status["total_opportunities"]
    total_pushes = sched_status["total_pushes"]

    # 状态指示器
    if degraded:
        status_color = "#ff6b6b"
        status_text = "⚠️ 已降级（仅日报）"
        status_detail = f"连续失败 {failures} 次，自动降级中"
    elif running:
        status_color = "#00f59b"
        status_text = "🟢 运行中"
        status_detail = f"每 {sched_status['interval_minutes']} 分钟自动扫描"
    else:
        status_color = "#64748b"
        status_text = "⏸️ 已停止"
        status_detail = "点击启动按钮开始自动扫描"

    st.markdown(
        f"""<div style="background:var(--surface-container);border:1px solid {status_color}33;
        border-radius:12px;padding:1rem 1.25rem;margin-bottom:0.75rem;">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
            <span style="font-size:1.1rem;font-weight:700;color:{status_color};">{status_text}</span>
        </div>
        <div style="font-size:0.8rem;color:var(--on-surface-variant);">{status_detail}</div>
        </div>""",
        unsafe_allow_html=True,
    )

    # 控制按钮
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        if running:
            if st.button(f"{icon('stop',16)} 停止调度器", key="stop_sched"):
                scheduler.stop()
                st.rerun()
        else:
            if st.button(f"{icon('play_arrow',16)} 启动调度器", type="primary", key="start_sched"):
                scheduler.start()
                st.rerun()
    with c2:
        if degraded:
            if st.button(f"{icon('refresh',16)} 重置降级", key="reset_degrade"):
                scheduler.reset_degrade()
                st.rerun()
    with c3:
        if last_scan:
            ago = int((datetime.now() - datetime.fromisoformat(last_scan)).total_seconds() / 60)
            metric_card("上次扫描", f"{ago}分钟前", icon_name="schedule")
        else:
            metric_card("上次扫描", "从未", icon_name="schedule")
    with c4:
        if next_scan and running:
            ndt = datetime.fromisoformat(next_scan)
            mins = int((ndt - datetime.now()).total_seconds() / 60)
            metric_card("下次扫描", f"{mins}分钟后", icon_name="timer")
        else:
            metric_card("下次扫描", "未计划", icon_name="timer")
    with c5:
        metric_card("累计推送", total_pushes, icon_name="send")

    # 详细统计
    if total_scans > 0:
        with st.expander("调度器统计详情"):
            mc1, mc2, mc3, mc4 = st.columns(4)
            with mc1: metric_card("累计扫描", f"{total_scans} 轮", icon_name="radar")
            with mc2: metric_card("发现机会", total_opps, icon_name="sell")
            with mc3: metric_card("推送次数", total_pushes, icon_name="send")
            with mc4: metric_card("失败次数", failures, icon_name="warning")


def _render_radar_chart(db):
    """套利评分雷达图 — Plotly polar"""
    import plotly.graph_objects as go
    stats = db.get_stats()
    categories = ["利润", "需求", "增速", "供应", "饱和度", "成本"]
    values = [
        min(stats.get("avg_roi", 0) * 2, 100),
        min(stats.get("total_opportunities", 0), 100),
        min(stats.get("max_roi", 0), 100),
        min(stats.get("total_products", 0), 100),
        50, 70,
    ]
    fig = go.Figure(data=go.Scatterpolar(
        r=values + [values[0]],
        theta=categories + [categories[0]],
        fill="toself",
        fillcolor="rgba(0,245,155,0.15)",
        line=dict(color="#00f59b", width=2),
    ))
    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 100], gridcolor="#31353f"),
            angularaxis=dict(gridcolor="#31353f"),
            bgcolor="rgba(0,0,0,0)",
        ),
        showlegend=False,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=40, r=40, t=50, b=40),
        height=300,
        title=dict(text="套利评分指数", font=dict(size=14, color="#b9cbbd")),
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_trend_chart(db):
    """趋势动能力图 — Plotly bar"""
    import plotly.graph_objects as go
    from collections import Counter
    opps = db.list_opportunities(limit=100, min_roi=0)
    daily = Counter()
    for o in opps:
        d = (o.get("discovered_at") or "")[:10]
        if d:
            daily[d] += 1
    dates = sorted(daily.keys())[-7:]
    values = [daily.get(d, 0) for d in dates]
    max_val = max(values) if values else 1
    colors = [
        "#fbd400" if v / max_val > 0.8
        else "#14d1ff" if v / max_val > 0.5
        else "rgba(20,209,255,0.4)"
        for v in values
    ]

    labels = [f"T-{len(values)-1-i}" for i in range(len(values))]
    if labels:
        labels[-1] = "当前"

    fig = go.Figure(data=go.Bar(
        x=labels, y=values,
        marker=dict(color=colors),
        text=[str(v) for v in values],
        textposition="auto",
    ))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=20, r=20, t=50, b=20),
        height=300,
        title=dict(text="趋势动能热力图", font=dict(size=14, color="#b9cbbd")),
        xaxis=dict(color="#64748b"),
        yaxis=dict(color="#64748b", gridcolor="#31353f", zeroline=False),
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)


def _run_auto_scan(cfg, db):
    """执行一轮手动扫描"""
    from modules.scrapers import ScraperPddApi, ScraperXianyu

    per_round = int(cfg.get("scanner", {}).get("keywords_per_round", 20) or 20)
    keywords = db.get_next_keywords(per_round)
    if not keywords:
        st.warning("关键词池为空或已扫描完毕")
        return

    platforms_enabled = cfg.get("platforms", {})
    run_id = db.start_workflow_run("manual", ["pdd", "xianyu"])
    total_opps = 0
    shipping = float(cfg.get("finance", {}).get("domestic_shipping", 3) or 3)
    fee_rate = float(cfg.get("finance", {}).get("platform_fee_rate", 0.016) or 0.016)

    progress = st.progress(0, text="扫描中...")
    status = st.empty()

    for i, kw in enumerate(keywords):
        progress.progress((i / len(keywords)), text=f"扫描 [{i+1}/{len(keywords)}]: {kw}")
        status.info(f"{icon('travel_explore',16)} 抓取: **{kw}**")

        # 1. 搜索并保存原始数据
        try:
            pdd_scraper = ScraperPddApi.from_config(cfg)
            pdd_items = pdd_scraper.fetch(kw, 20)
            db.save_products(pdd_items, "pdd")
        except Exception as e:
            st.warning(f"PDD 失败: {e}")
            pdd_items = []

        try:
            xy_scraper = ScraperXianyu(cfg)
            xy_items = xy_scraper.fetch(kw, 20)
            db.save_products(xy_items, "xianyu")
        except Exception as e:
            st.warning(f"闲鱼 失败: {e}")
            xy_items = []

        # 2. 双向交叉扫描
        if pdd_items and xy_items:
            from modules.matcher import bidirectional_scan
            opps = bidirectional_scan(kw, pdd_scraper, xy_scraper,
                                       shipping, fee_rate,
                                       min_roi=None, min_similarity=0.12,
                                       config=cfg, db=db)
            for d in opps:
                d["status"] = "pending"
                db.save_opportunity(d)
                total_opps += 1

        db.mark_keyword_scanned(kw)

    progress.progress(1.0, text="扫描完成")
    status.success(f"{icon('check_circle',18)} 扫描完成: {len(keywords)} 关键词, {total_opps} 机会")
    db.finish_workflow_run(run_id, "success", len(keywords), total_opps, 0)


def _scan_custom_kw(kw: str, cfg: dict, db):
    """扫描用户自定义关键词"""
    from modules.scrapers import ScraperPddApi, ScraperXianyu
    from modules.matcher import bidirectional_scan

    shipping = float(cfg.get("finance", {}).get("domestic_shipping", 3) or 3)
    fee_rate = float(cfg.get("finance", {}).get("platform_fee_rate", 0.016) or 0.016)

    with st.spinner(f'正在搜索 "{kw}" ...'):
        pdd_items, xy_items = [], []
        pdd_s = None
        try:
            pdd_s = ScraperPddApi.from_config(cfg)
            pdd_items = pdd_s.fetch(kw, 20)
            db.save_products(pdd_items, "pdd")
        except Exception as e:
            st.warning(f"PDD 失败: {e}")

        try:
            xy_s = ScraperXianyu(cfg)
            xy_items = xy_s.fetch(kw, 10)
            db.save_products(xy_items, "xianyu")
        except Exception as e:
            st.warning(f"闲鱼 失败: {e}")

        if pdd_items and xy_items and pdd_s:
            opps = bidirectional_scan(kw, pdd_s, xy_s, shipping, fee_rate,
                                      min_roi=None, min_similarity=0.12, config=cfg, db=db)
            for d in opps:
                d["status"] = "pending"
                db.save_opportunity(d)
            st.success(f'"{kw}" 扫描完成: PDD {len(pdd_items)} + 闲鱼 {len(xy_items)}, {len(opps)} 机会')
        else:
            st.info(f'"{kw}" 扫描完成: PDD {len(pdd_items)}, 闲鱼 {len(xy_items)}')
        st.rerun()

def _reverse_source_kw(kw: str, cfg: dict, db):
    """闲鱼爆款 -> PDD反向找货"""
    from modules.scrapers import ScraperPddApi, ScraperXianyu
    from modules.hot_collector import filter_hot_items
    from modules.reverse_sourcing import reverse_source
    shipping = float(cfg.get("finance", {}).get("domestic_shipping", 3) or 3)
    fee_rate = float(cfg.get("finance", {}).get("platform_fee_rate", 0.016) or 0.016)
    with st.spinner(f"搜索闲鱼爆款 {kw} -> PDD找货..."):
        pdd_s = ScraperPddApi.from_config(cfg)
        xy_s = ScraperXianyu(cfg)
        xy_items = xy_s.fetch(kw, 20)
        db.save_products(xy_items, "xianyu")
        hot = filter_hot_items(xy_items, min_want=1) or xy_items[:10]
        opps = reverse_source(kw, hot, pdd_s, xy_s, shipping, fee_rate, config=cfg, db=db)
        for d in opps:
            d["status"] = "pending"
            db.save_opportunity(d)
        st.success(f"{kw} 反向找货: XY{len(xy_items)} 热门{len(hot)} 机会{len(opps)}")
        st.rerun()
