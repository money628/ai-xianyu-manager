"""发货 SOP — 半自动发货流程"""
import streamlit as st
from . import get_db, icon, section_header, inject_glass_css, h


def render():
    inject_glass_css()
    db = get_db()

    # ====== 诊断：检查 Database 方法 ======
    import sys
    cls = db.__class__
    mod_file = sys.modules.get(cls.__module__)
    mod_path = getattr(mod_file, '__file__', 'unknown') if mod_file else 'unknown'
    
    missing = []
    for m in ['get_shipping_orders', 'create_shipping_order', 'get_dashboard_stats',
              'save_traffic_record', 'get_traffic_items', 'save_image_pack']:
        if not hasattr(db, m):
            missing.append(m)
    
    if missing:
        st.error("### 数据库方法缺失")
        st.code(f"Database 来源: {mod_path}")
        st.write(f"缺失方法: {missing}")
        st.info("请关闭所有窗口后双击 `重启.bat`")
        return
    # ====== 诊断结束 ======

    st.markdown(
        f"<h2 style='display:flex;align-items:center;gap:8px;'>"
        f"{icon('local_shipping',24)} 发货 SOP"
        f"</h2>",
        unsafe_allow_html=True,
    )

    try:
        from modules.shipping import SHIPPING_STATUSES, build_pdd_order_note
    except ImportError as e:
        st.error(f"模块加载失败: {e}")
        return

    tab1, tab2 = st.tabs(["📋 所有订单", "➕ 新建订单"])

    with tab2:
        st.markdown("### 从已通过机会创建发货订单")
        try:
            approved = [o for o in db.list_opportunities(limit=20, status="approved")
                         if o.get("buy_platform") != "1688"]
        except Exception as e:
            st.warning(f"加载机会失败: {e}")
            approved = []

        if not approved:
            st.info("暂无已通过的机会，请先去看板审核")
        else:
            opp_opts = {f"{o.get('buy_title','')[:30]} ROI{o.get('roi',0):.0f}%": o for o in approved if o.get('buy_title')}
            if not opp_opts:
                st.info("暂无有效机会")
                return

            sel_label = st.selectbox("选择机会", list(opp_opts.keys()))
            opp = opp_opts.get(sel_label, {})
            if opp:
                with st.form("create_shipping"):
                    c1, c2 = st.columns(2)
                    with c1:
                        buyer_name = st.text_input("买家姓名")
                        buyer_phone = st.text_input("买家电话")
                    with c2:
                        xianyu_order = st.text_input("闲鱼订单号")
                        pdd_sku = st.text_input("PDD SKU")
                    buyer_addr = st.text_area("买家地址")
                    remark = st.text_area("备注")
                    c1, c2, c3 = st.columns(3)
                    with c1: st.caption(f"进价 ¥{opp.get('buy_price',0):.2f}")
                    with c2: st.caption(f"售价 ¥{opp.get('sell_price',0):.2f}")
                    with c3: st.caption(f"利润 ¥{opp.get('profit',0):.2f}")

                    if st.form_submit_button("创建发货订单", type="primary"):
                        try:
                            order_data = {
                                "draft_id": str(opp.get("id", "")),
                                "product_family_id": opp.get("product_family_id", ""),
                                "xianyu_order_no": xianyu_order,
                                "buyer_name": buyer_name,
                                "buyer_phone": buyer_phone,
                                "buyer_address": buyer_addr,
                                "pdd_goods_url": opp.get("buy_url", ""),
                                "pdd_sku": pdd_sku,
                                "cost_price": float(opp.get("buy_price", 0)),
                                "sale_price": float(opp.get("sell_price", 0)),
                                "profit": float(opp.get("profit", 0)),
                                "remark": remark,
                            }
                            order_id = db.create_shipping_order(order_data)
                            st.success(f"订单已创建 (ID: {order_id})")
                            st.rerun()
                        except Exception as e:
                            st.error(f"创建失败: {e}")
                            import traceback
                            st.code(traceback.format_exc())

    with tab1:
        status_filter = st.selectbox("状态筛选", ["全部"] + SHIPPING_STATUSES)
        sf = status_filter if status_filter != "全部" else None
        search = st.text_input("搜索（买家/商品/单号）", placeholder="输入关键词快速定位...", key="ship_search")

        try:
            orders = db.get_shipping_orders(sf)
        except AttributeError as e:
            st.error(f"数据库方法缺失: {e}")
            return
        except Exception as e:
            st.warning(f"加载订单失败: {e}")
            orders = []

        # 搜索过滤
        if search and orders:
            q = search.lower()
            orders = [o for o in orders if
                      q in (o.get('buyer_name','') or '').lower() or
                      q in (o.get('pdd_goods_url','') or '').lower() or
                      q in (o.get('xianyu_order_no','') or '').lower() or
                      q in (o.get('pdd_sku','') or '').lower()]

        if not orders:
            st.info("暂无发货订单" if not search else f"未找到匹配 \"{search}\" 的订单")
            return

        for order in orders:
            status = order.get("shipping_status", "待填地址") if isinstance(order, dict) else "?"
            label = order.get("buyer_name", "未知买家") if isinstance(order, dict) else "?"
            pdd_url = (order.get("pdd_goods_url", "") or "")[:40] if isinstance(order, dict) else ""
            profit = order.get("profit", 0) if isinstance(order, dict) else 0

            with st.expander(f"{status} · {label} · +¥{profit:.0f} · {pdd_url}"):
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown(f"**买家**: {order.get('buyer_name','')}")
                    st.markdown(f"**电话**: {order.get('buyer_phone','')}")
                    st.markdown(f"**地址**: {order.get('buyer_address','')}")
                    st.markdown(f"**闲鱼单号**: {order.get('xianyu_order_no','')}")
                with c2:
                    pdd_goods = order.get('pdd_goods_url','')
                    st.markdown(f"**进货链接**: [{pdd_goods[:40]}...]({pdd_goods})")
                    if pdd_goods:
                        st.link_button("去PDD下单", pdd_goods)
                    st.markdown(f"**PDD SKU**: {order.get('pdd_sku','')}")
                    st.markdown(f"**PDD单号**: {order.get('pdd_order_no','')}")
                    st.markdown(f"**快递**: {order.get('tracking_company','')} {order.get('tracking_no','')}")

                c1, c2, c3 = st.columns(3)
                with c1: st.metric("进价", f"¥{order.get('cost_price',0):.0f}")
                with c2: st.metric("售价", f"¥{order.get('sale_price',0):.0f}")
                with c3: st.metric("利润", f"¥{order.get('profit',0):.0f}")

                try:
                    note = build_pdd_order_note(order)
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        addr = f"{order.get('buyer_name','')} {order.get('buyer_phone','')} {order.get('buyer_address','')}"
                        st.code(addr, language=None)
                        st.caption("📋 复制买家地址")
                    with col2:
                        st.code(note, language=None)
                        st.caption("📋 复制PDD下单备注")
                    with col3:
                        st.caption(f"当前状态: **{status}**")
                except Exception as e:
                    st.caption(f"备注生成错误: {e}")

                st.markdown("---")
                st.markdown("**更新状态**")

                col1, col2, col3 = st.columns(3)
                cur_idx = SHIPPING_STATUSES.index(status) if status in SHIPPING_STATUSES else 0
                with col1:
                    new_status = st.selectbox(
                        "新状态", SHIPPING_STATUSES, index=cur_idx, key=f"st_{order['id']}"
                    )
                with col2:
                    if status in ("已下单PDD", "待发货"):
                        pdd_no = st.text_input("PDD订单号", value=order.get("pdd_order_no",""), key=f"pdd_{order['id']}")
                    else:
                        pdd_no = ""
                with col3:
                    if status in ("待发货", "已发货"):
                        tracking_no = st.text_input("快递单号", value=order.get("tracking_no",""), key=f"trk_{order['id']}")
                        tracking_co = st.text_input("快递公司", value=order.get("tracking_company",""), key=f"trkc_{order['id']}")
                    else:
                        tracking_no = ""
                        tracking_co = ""

                if st.button("更新", key=f"upd_{order['id']}", type="primary"):
                    try:
                        updates = {"shipping_status": new_status}
                        if pdd_no:
                            updates["pdd_order_no"] = pdd_no
                        if tracking_no:
                            updates["tracking_no"] = tracking_no
                        if tracking_co:
                            updates["tracking_company"] = tracking_co
                        db.update_shipping_order(order["id"], updates)
                        st.success("已更新")
                        st.rerun()
                    except Exception as e:
                        st.error(f"更新失败: {e}")

    # 批量操作
    if orders:
        st.markdown("---")
        section_header("批量操作", "rocket_launch")
        pending_orders = [o for o in orders if o.get('shipping_status','') == '待下单']
        if pending_orders:
            st.caption(f"{len(pending_orders)} 个待下单订单")
            c1, c2 = st.columns(2)
            with c1:
                if st.button(f"一键打开全部PDD链接 ({len(pending_orders)}个)", use_container_width=True):
                    for o in pending_orders:
                        url = o.get('pdd_goods_url','')
                        if url:
                            import webbrowser
                            webbrowser.open(url)
            with c2:
                all_addr = "\n---\n".join(
                    f"{o.get('buyer_name','')}\n{o.get('buyer_phone','')}\n{o.get('buyer_address','')}"
                    for o in pending_orders
                )
                st.code(all_addr, language=None)
                st.caption("全部买家地址")
