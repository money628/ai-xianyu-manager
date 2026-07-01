"""闲鱼流量分析 — 曝光/浏览/想要/转化"""
import csv
import io
import traceback
from datetime import datetime, timedelta
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from . import get_db, icon, section_header, inject_glass_css, h


def render():
    inject_glass_css()
    db = get_db()

    # ====== 诊断 ======
    import sys
    missing = [m for m in ['save_traffic_record','get_traffic_items','get_traffic_records'] if not hasattr(db, m)]
    if missing:
        st.error("### 数据库方法缺失")
        st.code(f"来源: {getattr(sys.modules.get(db.__class__.__module__), '__file__', '?')}")
        st.write(f"缺失: {missing}")
        st.info("请关闭所有窗口后双击 `重启.bat`")
        return

    st.markdown(
        f"<h2 style='display:flex;align-items:center;gap:8px;'>"
        f"{icon('monitoring',24)} 流量分析"
        f"</h2>",
        unsafe_allow_html=True,
    )

    tab1, tab2 = st.tabs(["📊 数据分析", "📥 录入/导入"])

    with tab2:
        st.markdown("### 手动录入")
        with st.form("traffic_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                item_id = st.text_input("闲鱼商品ID", placeholder="如: 123456789")
                tdate = st.date_input("日期", value=datetime.now())
            with c2:
                title = st.text_input("商品标题", placeholder="可选")

            c1, c2, c3, c4, c5 = st.columns(5)
            with c1: exp = st.number_input("曝光", min_value=0, value=0)
            with c2: views = st.number_input("浏览", min_value=0, value=0)
            with c3: wants = st.number_input("想要", min_value=0, value=0)
            with c4: chats = st.number_input("咨询", min_value=0, value=0)
            with c5: orders = st.number_input("订单", min_value=0, value=0)

            if st.form_submit_button("保存", type="primary") and item_id:
                try:
                    conv = orders / max(views, 1)
                    db.save_traffic_record({
                        "xianyu_item_id": item_id, "date": tdate.isoformat(),
                        "title": title, "exposure_count": exp, "view_count": views,
                        "want_count": wants, "chat_count": chats, "order_count": orders,
                        "conversion_rate": round(conv, 4),
                    })
                    st.success("已保存")
                    st.rerun()
                except AttributeError:
                    st.error("数据库方法未就绪，请重启 Streamlit 后重试")
                except Exception as e:
                    st.error(f"保存失败: {e}")

        st.markdown("---")
        st.markdown("### CSV导入")
        st.caption("CSV格式: date,xianyu_item_id,title,exposure_count,view_count,want_count,chat_count,order_count")
        uploaded = st.file_uploader("选择CSV文件", type=["csv"])
        if uploaded:
            try:
                text = uploaded.read().decode("utf-8-sig")
                reader = csv.DictReader(io.StringIO(text))
                imported = 0
                errors = []
                for i, row in enumerate(reader, 2):
                    try:
                        if "xianyu_item_id" not in row or "date" not in row:
                            raise ValueError("缺少 xianyu_item_id 或 date 字段")
                        conv = int(row.get("order_count", 0)) / max(int(row.get("view_count", 0)), 1)
                        db.save_traffic_record({
                            "xianyu_item_id": row["xianyu_item_id"],
                            "date": row["date"], "title": row.get("title", ""),
                            "exposure_count": int(row.get("exposure_count", 0)),
                            "view_count": int(row.get("view_count", 0)),
                            "want_count": int(row.get("want_count", 0)),
                            "chat_count": int(row.get("chat_count", 0)),
                            "order_count": int(row.get("order_count", 0)),
                            "conversion_rate": round(conv, 4),
                        })
                        imported += 1
                    except ValueError as ve:
                        errors.append(f"第{i}行: {ve}")
                    except Exception as e:
                        errors.append(f"第{i}行: {e}")
                if errors:
                    st.warning(f"部分行导入失败:" + "\n".join(errors[:5]))
                if imported > 0:
                    st.success(f"成功导入 {imported} 条记录")
                    st.rerun()
                else:
                    st.error("没有成功导入任何数据")
            except Exception as e:
                st.error(f"CSV解析失败: {e}")
                st.code(traceback.format_exc())

    with tab1:
        # 商品选择
        try:
            items = db.get_traffic_items()
        except AttributeError:
            st.error("数据库方法未就绪，请重启 Streamlit。")
            return
        except Exception as e:
            st.warning(f"加载商品列表失败: {e}")
            items = []

        if not items:
            st.info("暂无流量数据，请先在「录入/导入」标签页添加数据。")
            return

        item_options = {}
        for i in items:
            name = h((i.get("title", "") or "")[:30])
            iid = i.get("xianyu_item_id", "")
            if iid:
                item_options[f"{name} ({iid})"] = iid
            
        if not item_options:
            st.info("暂无有效商品记录")
            return

        selected = st.selectbox("选择商品", ["全部"] + list(item_options.keys()))

        c1, c2 = st.columns(2)
        with c1: date_from = st.date_input("开始日期", value=datetime.now() - timedelta(days=30))
        with c2: date_to = st.date_input("结束日期", value=datetime.now())

        sel_id = item_options.get(selected, "") if selected != "全部" else ""

        try:
            records = db.get_traffic_records(
                sel_id or None, date_from.isoformat(), date_to.isoformat()
            )
        except AttributeError:
            st.error("数据库方法未就绪，请重启 Streamlit。")
            return
        except Exception as e:
            st.warning(f"加载记录失败: {e}")
            records = []

        if not records:
            st.info("选定的时间范围内暂无流量数据。")
            return

        try:
            df = pd.DataFrame(records).sort_values("date")
        except Exception as e:
            st.error(f"数据格式错误: {e}")
            return

        st.markdown("### 趋势图")
        tab_a, tab_b, tab_c, tab_d, tab_e = st.tabs(["曝光", "浏览", "想要", "咨询", "订单"])

        def _line_chart(col, y_col, color, label):
            with col:
                try:
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(x=df["date"], y=df[y_col], mode="lines+markers",
                                             name=label, line=dict(color=color)))
                    fig.update_layout(template="plotly_dark", height=250, margin=dict(l=20, r=20, t=20, b=20))
                    st.plotly_chart(fig, use_container_width=True)
                except Exception as e:
                    st.caption(f"图表失败: {e}")

        _line_chart(tab_a, "exposure_count", "#00f59b", "曝光")
        _line_chart(tab_b, "view_count", "#14d1ff", "浏览")
        _line_chart(tab_c, "want_count", "#fbd400", "想要")
        _line_chart(tab_d, "chat_count", "#ff6b6b", "咨询")
        _line_chart(tab_e, "order_count", "#cdffdc", "订单")

        # 对比分析
        st.markdown("### 铺货后对比")
        if len(df) >= 2:
            days_offset = [1, 3, 7]
            cols = st.columns(len(days_offset))
            for i, d in enumerate(days_offset):
                with cols[i]:
                    st.subheader(f"第{d}天")
                    try:
                        threshold = df["date"].min() + pd.Timedelta(days=d - 1)
                        row = df[df["date"] >= threshold]
                        if not row.empty:
                            r = row.iloc[0]
                            st.metric("曝光", int(r.get("exposure_count", 0)))
                            st.metric("浏览", int(r.get("view_count", 0)))
                            st.metric("想要", int(r.get("want_count", 0)))
                            cr = float(r.get("conversion_rate", 0))
                            st.metric("转化率", f"{cr:.2%}")
                        else:
                            st.caption("暂无数据")
                    except Exception as e:
                        st.caption(f"错误: {e}")
        else:
            st.caption("数据不足，无法对比分析")
