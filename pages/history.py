"""历史 — 机会记录 · 报告归档 · 30日汇总 · v1.2 增强"""
import json
import os
import math

import pandas as pd
import streamlit as st

from . import (
    get_db, icon, metric_card, section_header,
    inject_glass_css,
)

PAGE_SIZE = 20


def render():
    inject_glass_css()
    db = get_db()

    st.markdown(
        f"<h2 style='display:flex;align-items:center;gap:8px;'>"
        f"{icon('history',24)} 历史 {icon('description',20)}"
        f"<span style='font-size:0.7rem;font-weight:400;color:var(--on-surface-variant);margin-left:auto;'>过去 30 天的定价情报</span>"
        f"</h2>",
        unsafe_allow_html=True,
    )

    tab1, tab2 = st.tabs([
        f"{icon('list_alt',16)} 机会记录",
        f"{icon('assessment',16)} 扫描报告",
    ])

    # ────────── 机会记录 ──────────
    with tab1:
        c1, c2, c3 = st.columns([1, 1, 2])
        with c1:
            platform_filter = st.selectbox("平台", ["全部", "拼多多", "闲鱼"])
        with c2:
            status_filter = st.selectbox("状态", ["全部", "待审核", "已通过", "已拒绝"])
        with c3:
            search_text = st.text_input("搜索标题", placeholder="输入关键词过滤...")

        # 获取全量数据
        opps = db.list_opportunities(limit=500, min_roi=0)

        # 过滤平台
        if platform_filter != "全部":
            pf_map = {"拼多多": "pdd", "闲鱼": "xianyu"}
            pf = pf_map.get(platform_filter, platform_filter)
            opps = [o for o in opps if o.get("buy_platform") == pf or o.get("sell_platform") == pf]

        # 过滤状态
        if status_filter != "全部":
            st_map = {"待审核": "pending", "已通过": "approved", "已拒绝": "rejected"}
            st_val = st_map.get(status_filter, status_filter)
            opps = [o for o in opps if o.get("status") == st_val]

        # 搜索过滤
        if search_text.strip():
            qt = search_text.strip().lower()
            opps = [o for o in opps
                    if qt in (o.get("buy_title") or o.get("title", "")).lower()]

        total = len(opps)
        st.text(f"共 {total} 条记录")

        if not opps:
            st.info("暂无记录")
        else:
            # 分页
            total_pages = max(1, math.ceil(total / PAGE_SIZE))
            if "history_page" not in st.session_state:
                st.session_state.history_page = 1
            page = st.session_state.history_page

            c1, c2, c3 = st.columns([1, 2, 1])
            with c1:
                if st.button("← 上一页", disabled=(page <= 1)):
                    st.session_state.history_page -= 1
                    st.rerun()
            with c2:
                st.text(f"第 {page} / {total_pages} 页")
            with c3:
                if st.button("下一页 →", disabled=(page >= total_pages)):
                    st.session_state.history_page += 1
                    st.rerun()

            start = (page - 1) * PAGE_SIZE
            page_opps = opps[start:start + PAGE_SIZE]

            # 构建带 ROI 颜色高亮的表格
            status_cn = {"pending": "待审核", "approved": "已通过", "rejected": "已拒绝"}
            rows = []
            for o in page_opps:
                roi = o.get("roi", 0)
                roi_color = "#00f59b" if roi >= 60 else "#fbd400" if roi >= 30 else "#ff6b6b"
                rows.append({
                    "#": o.get("id"),
                    "标题": (o.get("buy_title") or o.get("title", ""))[:35],
                    "进价": f"¥{o.get('buy_price', 0):.2f}",
                    "售价": f"¥{o.get('sell_price', 0):.2f}",
                    "利润": f"¥{o.get('profit', 0):.2f}",
                    "ROI": f"{roi:.1f}%",
                    "状态": status_cn.get(o.get("status"), ""),
                })

            df = pd.DataFrame(rows)

            # ROI 列自定义样式
            def color_roi(val):
                try:
                    v = float(val.replace("%", ""))
                    if v >= 60:
                        return "color: #00f59b; font-weight: 700"
                    elif v >= 30:
                        return "color: #fbd400; font-weight: 700"
                    else:
                        return "color: #ff6b6b"
                except Exception:
                    return ""

            styled = df.style.map(color_roi, subset=["ROI"])
            st.dataframe(styled, use_container_width=True, hide_index=True, height=400)

            # CSV/JSON/Excel 导出
            c1, c2, c3 = st.columns(3)
            with c1:
                export_df = pd.DataFrame([{
                    **{k: v for k, v in o.items()
                       if k not in ("raw_data", "extra_stats")},
                } for o in opps])
                csv = export_df.to_csv(index=False).encode("utf-8-sig")
                st.download_button(f"{icon('download',16)} 导出 CSV ({total}条)",
                                   csv, "opportunities.csv", "text/csv")
            with c2:
                try:
                    import io
                    buf = io.BytesIO()
                    with pd.ExcelWriter(buf, engine="openpyxl") as w:
                        export_df.to_excel(w, index=False, sheet_name="机会")
                    st.download_button(f"{icon('download',16)} 导出 Excel ({total}条)",
                                       buf.getvalue(), "opportunities.xlsx",
                                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                except ImportError:
                    st.caption("需 pip install openpyxl 才能导出 Excel")
            with c3:
                json_data = json.dumps(opps, ensure_ascii=False, indent=2).encode("utf-8")
                st.download_button(f"{icon('download',16)} 导出 JSON ({total}条)",
                                   json_data, "opportunities.json", "application/json")

    # ────────── 扫描报告 ──────────
    with tab2:
        from modules.reporter import Reporter
        reports_dir = os.path.join(os.path.dirname(__file__), "..", "outputs", "reports")
        reporter = Reporter({}, output_dir=reports_dir)
        reports = reporter.list_reports(30)

        if not reports:
            st.info(f"{icon('info',16)} 暂无历史报告")
        else:
            selected = st.selectbox(
                "选择报告",
                reports,
                format_func=lambda x: os.path.basename(x),
            )
            report = reporter.load_report(selected)
            if report:
                st.markdown(
                    f"<h4 style='display:flex;align-items:center;gap:6px;'>"
                    f"{icon('calendar_month',18)} {report.get('date','')} 日报"
                    f"</h4>",
                    unsafe_allow_html=True,
                )
                summary = report.get("summary", {})
                c1, c2, c3 = st.columns(3)
                with c1:
                    metric_card("机会数", summary.get("total_opportunities", 0), icon_name="sell")
                with c2:
                    metric_card("平均ROI", f"{summary.get('avg_roi', 0):.1f}%", icon_name="trending_up")
                with c3:
                    metric_card("最高ROI", f"{summary.get('max_roi', 0):.1f}%", icon_name="local_fire_department")

                section_header("前十名", "leaderboard")
                for item in report.get("top10", []):
                    st.markdown(
                        f'<div class="glass-card" style="margin-bottom:4px;padding:0.5rem 0.75rem;">'
                        f'<span style="color:var(--on-surface-variant);font-size:0.75rem;">#{item["rank"]}</span> '
                        f'{icon("swap_horiz",14)} '
                        f'<b>{item.get("buy_platform","")}→{item.get("sell_platform","")}</b> '
                        f'· ROI <b class="roi-{"high" if item.get("roi",0)>=60 else "mid"}">{item.get("roi",0):.0f}%</b> '
                        f'· ¥{item.get("buy_price",0):.0f}→¥{item.get("sell_price",0):.0f} '
                        f'· {icon("trending_up",14)} +¥{item.get("profit",0):.0f} '
                        f'· {item.get("title","")[:35]}'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

    # ────────── 30日汇总 ──────────
    st.markdown("---")
    section_header("30日汇总", "bar_chart")
    stats = db.get_stats()
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        metric_card("机会总数", stats.get("total_opportunities", 0), icon_name="sell")
    with c2:
        metric_card("商品总数", stats.get("total_products", 0), icon_name="inventory_2")
    with c3:
        metric_card("待审核", stats.get("pending_count", 0), icon_name="rate_review")
    with c4:
        metric_card("已推送", stats.get("pushed_count", 0), icon_name="notifications_active")
