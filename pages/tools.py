"""工具 — 登录管理 · 参数设置 · 数据监控 · 黑名单 · 调度器"""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import streamlit as st

from . import (
    get_config, get_db, get_scheduler, icon, metric_card, section_header,
    inject_glass_css,
)


def _check_login(platform_key: str):
    """检查登录态是否有效，返回 (is_valid, hours_remaining, detail)"""
    state_path = Path(__file__).resolve().parent.parent / "data" / "login_states" / f"{platform_key}_state.json"
    if not state_path.exists():
        return False, 0, "未登录"
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
        cookies = data.get("cookies", []) if isinstance(data, dict) else []
        if not cookies:
            return False, 0, "无 cookie"
        key_names = {"t", "cookie2", "unb"} if platform_key == "xianyu" else {"PDDAccessToken", "pdd_user_id"}
        found = set()
        min_hours = float('inf')
        now = time.time()
        for c in cookies:
            n = c.get("name", "")
            if n in key_names:
                found.add(n)
                exp = c.get("expires", -1)
                if isinstance(exp, (int, float)) and exp > 0:
                    h = (exp - now) / 3600
                    if h < min_hours:
                        min_hours = h
        if platform_key == "xianyu":
            if not bool(found & {"t", "cookie2", "unb"}):
                return False, 0, "关键 cookie 缺失"
        if min_hours == float('inf'):
            return True, 24, "cookie 无限期"
        if min_hours <= 0:
            return False, 0, "cookie 已过期"
        if min_hours < 24:
            return True, min_hours, f"即将过期 ({min_hours:.0f}h)"
        return True, min_hours, f"有效 ({min_hours:.0f}h)"
    except Exception as e:
        return False, 0, f"解析错误: {e}"


def _launch_login(platform_key: str):
    script = os.path.join(os.path.dirname(__file__), "..", "src", "modules", "login_helper.py")
    subprocess.Popen(
        [sys.executable, script, platform_key],
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )


def render():
    inject_glass_css()
    st.markdown(
        f"<h2 style='display:flex;align-items:center;gap:8px;'>"
        f"{icon('build',24)} 工具 {icon('tune',20)}"
        f"<span style='font-size:0.7rem;font-weight:400;color:var(--on-surface-variant);margin-left:auto;'>参数设置 · 系统监控 · 财务计算</span>"
        f"</h2>",
        unsafe_allow_html=True,
    )

    cfg = get_config()
    db = get_db()

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        f"{icon('key',16)} 登录管理",
        f"{icon('settings',16)} 参数设置",
        f"{icon('monitoring',16)} 数据监控",
        f"{icon('block',16)} 黑名单",
        f"{icon('star',16)} 关注列表",
    ])

    # ────────── 登录管理 ──────────
    with tab1:
        section_header("平台登录状态", "key")
        st.caption("首次使用需手动登录各平台一次，登录态自动保存")

        platforms = [
            ("pdd", "拼多多", "拼多多 · yangkeduo.com", "shopping_cart"),
            ("xianyu", "闲鱼", "闲鱼 · goofish.com", "sell"),
        ]

        cols = st.columns(2)
        for i, (key, name, desc, ic) in enumerate(platforms):
            logged_in, hours, detail = _check_login(key)
            if hours < 24 and logged_in:
                status_icon = icon('warning', 16)
                status_color = 'warning'
            else:
                status_icon = icon('check_circle', 16) if logged_in else icon('cancel', 16)
                status_color = 'primary-container' if logged_in else 'error'
            with cols[i]:
                st.markdown(
                    f"""
                <div class="glass-card" style="text-align:center;padding:1rem;">
                    <div style="font-size:2rem;margin-bottom:4px;">{icon(ic, 32)}</div>
                    <div style="font-weight:600;font-size:1.1rem;">{name}</div>
                    <div style="font-size:0.75rem;color:var(--on-surface-variant);">{desc}</div>
                    <div style="margin:0.5rem 0;">
                        {status_icon}
                        <span style="color:var(--{'primary-container' if logged_in else 'error'})">
                            {'已登录' if logged_in else '未登录'}
                        </span>
                    </div>
                    <div style="font-size:0.7rem;color:var(--on-surface-variant);">{detail}</div>
                </div>
                """,
                    unsafe_allow_html=True,
                )
                btn_label = "重新登录" if logged_in else "登录"
                if st.button(f"{icon('login',16)} {btn_label}", key=f"login_{key}", use_container_width=True):
                    chrome_flag = ["--chrome"] if key == "pdd" else []
                    subprocess.Popen(
                        [sys.executable, 
                         os.path.join(os.path.dirname(__file__), "..", "src", "modules", "login_helper.py"),
                         key, "--force"] + chrome_flag,
                        creationflags=subprocess.CREATE_NEW_CONSOLE,
                    )
                    if key == "pdd":
                        st.info(f"{icon('chrome',16)} 已打开 Chrome 浏览器，请在 {name} 页面完成登录后关闭窗口")
                    else:
                        st.info(f"已打开 {name} 登录窗口，请完成登录后关闭浏览器")

        st.markdown("---")
        st.caption(f"{icon('lightbulb',14)} 登录窗口打开后，手动完成登录，然后关闭浏览器窗口即可")
        st.caption(f"{icon('lightbulb',14)} 登录态保存在 data/login_states/ 目录，长期有效无需重复登录")

        # AI Token 用量
        st.markdown("---")
        try:
            from modules.ai_service import get_usage
            calls, tokens, cost = get_usage()
            if calls > 0:
                st.caption(f"AI 用量: {calls} 次调用, ~{tokens} tokens, 约 ¥{cost}")
        except Exception:
            pass

    # ────────── 参数设置 ──────────
    with tab2:
        section_header("扫描参数", "search")
        scan_cfg = cfg.get("scanner", {})
        c1, c2 = st.columns(2)
        with c1:
            seeds_list = cfg.get("scanner", {}).get("seed_categories", [])
            seeds_text = ",".join(seeds_list) if isinstance(seeds_list, list) else str(seeds_list)
            new_seeds = st.text_area("种子品类（逗号分隔）", value=seeds_text, height=100)
        with c2:
            per_round = st.number_input("每轮扫描关键词数", 5, 50, int(scan_cfg.get("keywords_per_round", 20) or 20))
            history_days = st.number_input("数据保留天数", 7, 90, int(cfg.get("database", {}).get("retention_days", 30) or 30))

        section_header("财务参数", "account_balance")
        fin_cfg = cfg.get("finance", {})
        c1, c2, c3 = st.columns(3)
        with c1:
            shipping = st.number_input("国内运费 (¥)", 0.0, 20.0, float(fin_cfg.get("domestic_shipping", 3.0) or 3.0), step=0.5)
        with c2:
            fee_rate = st.number_input("平台手续费率", 0.0, 0.1, float(fin_cfg.get("platform_fee_rate", 0.016) or 0.016), step=0.005, format="%.3f")
        with c3:
            rt_thresh = cfg.get("arbitrage", {}).get("realtime_push_roi_threshold", 30)
            realtime_threshold = st.number_input("实时推送 ROI 阈值 (%)", 10, 100, int(rt_thresh or 30))

        # ROI 计算器
        section_header("ROI 计算器", "calculate")
        cc1, cc2, cc3 = st.columns(3)
        with cc1:
            buy_p = st.number_input("进价 (¥)", 0.0, 10000.0, 10.0, step=1.0, key="calc_buy")
        with cc2:
            sell_p = st.number_input("售价 (¥)", 0.0, 50000.0, 50.0, step=1.0, key="calc_sell")
        with cc3:
            ship = st.number_input("运费 (¥)", 0.0, 50.0, float(fin_cfg.get("domestic_shipping", 3.0) or 3.0),
                                    step=0.5, key="calc_ship")
        fee_r = st.slider("平台手续费率", 0.0, 0.1, float(fin_cfg.get("platform_fee_rate", 0.016) or 0.016),
                          0.001, format="%.2f%%", key="calc_fee")

        cst = buy_p + ship
        rev = sell_p * (1 - fee_r)
        calc_p = rev - cst
        calc_r = (calc_p / cst * 100) if cst > 0 else 0
        breakeven = cst / (1 - fee_r) if (1 - fee_r) > 0 else 0

        r1, r2, r3, r4 = st.columns(4)
        with r1: st.metric("总成本", f"¥{cst:.2f}")
        with r2: st.metric("到手收入", f"¥{rev:.2f}")
        with r3: st.metric("净利润", f"¥{calc_p:.2f}",
                           delta="盈利" if calc_p > 0 else "亏损")
        with r4: st.metric("ROI", f"{calc_r:.1f}%",
                           delta=f"回本价 ¥{breakeven:.0f}", delta_color="off")
        st.caption(f"利润率: {calc_p/sell_p*100:.1f}%" if sell_p > 0 else "")

        section_header("推送设置", "notifications")
        push_cfg = cfg.get("push", {})
        method_opts = ["邮件", "Server酱", "钉钉", "两者"]
        method_map = {"邮件": "email", "Server酱": "serverchan", "钉钉": "dingtalk", "两者": "both"}
        rev_map = {"email": "邮件", "serverchan": "Server酱", "dingtalk": "钉钉", "both": "两者"}
        curr_method = push_cfg.get("method", "email")
        method_idx = method_opts.index(rev_map.get(curr_method, "邮件"))
        method_cn = st.selectbox("推送方式", method_opts, index=method_idx)
        method = method_map.get(method_cn, "email")
        c1, c2, c3 = st.columns(3)
        with c1:
            sckey = st.text_input("Server酱 SendKey", value=str(push_cfg.get("serverchan_send_key", "")), type="password")
        with c2:
            email_to = st.text_input("接收邮箱", value=str(push_cfg.get("email_to", "")))
        with c3:
            ding_webhook = st.text_input("钉钉 Webhook", value=str(push_cfg.get("dingtalk_webhook", "")), type="password")

        with st.expander(f"{icon('mail',14)} 邮件 SMTP 配置"):
            c1, c2 = st.columns(2)
            with c1:
                smtp_host = st.text_input("SMTP 主机", value=str(push_cfg.get("smtp_host", "smtp.qq.com")))
                smtp_user = st.text_input("SMTP 用户名", value=str(push_cfg.get("smtp_user", "")))
            with c2:
                smtp_port = st.number_input("SMTP 端口", 25, 465, int(push_cfg.get("smtp_port", 465) or 465))
                smtp_pass = st.text_input("SMTP 密码", value=str(push_cfg.get("smtp_password", "")), type="password")

        if st.button(f"{icon('save',16)} 保存参数", type="primary"):
            new_cfg = {
                **cfg,
                "scanner": {
                    **scan_cfg,
                    "seed_categories": [k.strip() for k in new_seeds.split(",") if k.strip()],
                    "keywords_per_round": per_round,
                },
                "finance": {
                    **fin_cfg,
                    "domestic_shipping": shipping,
                    "platform_fee_rate": fee_rate,
                },
                "arbitrage": {
                    **cfg.get("arbitrage", {}),
                    "realtime_push_roi_threshold": realtime_threshold,
                },
                "push": {
                    **push_cfg,
                    "method": method,
                    "serverchan_send_key": sckey,
                    "dingtalk_webhook": ding_webhook,
                    "email_to": email_to,
                    "smtp_host": smtp_host,
                    "smtp_port": smtp_port,
                    "smtp_user": smtp_user,
                    "smtp_password": smtp_pass,
                },
                "database": {**cfg.get("database", {}), "retention_days": history_days},
            }
            from config import save_config
            config_path = os.path.join(os.path.dirname(__file__), "..", "config.ini")
            save_config(new_cfg, config_path)
            st.success(f"{icon('check_circle',16)} 参数已保存，重启应用生效。")

        # 配置导入导出
        section_header("配置备份", "save")
        c1, c2, c3 = st.columns(3)
        with c1:
            config_path = os.path.join(os.path.dirname(__file__), "..", "config.ini")
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    st.download_button(
                        f"{icon('download',16)} 导出配置",
                        f.read(), "config_backup.ini", "text/plain",
                    )
        with c2:
            uploaded = st.file_uploader("导入配置", type=["ini"], label_visibility="collapsed")
            if uploaded:
                content = uploaded.read().decode("utf-8")
                # 验证格式
                if "[system]" in content and "[pdd_api]" in content:
                    with open(config_path, "w", encoding="utf-8") as f:
                        f.write(content)
                    st.success("配置已导入，重启生效")
                    st.rerun()
                else:
                    st.error("无效的配置文件")
        with c3:
            st.caption("导出备份配置，或导入已有配置")

        if st.button(f"{icon('send',16)} 发送测试推送"):
            from modules.pusher import Pusher
            if Pusher(cfg).push("AI店长测试", f"{icon('check_circle',16)} 这是一条测试推送"):
                st.success(f"{icon('check_circle',16)} 推送成功")
            else:
                st.error(f"{icon('error',16)} 推送失败，请检查配置")

        # ── 调度器设置 ──
        st.markdown("---")
        section_header("自动扫描调度器", "monitoring")
        from modules.reporter import Reporter
        from modules.pusher import Pusher
        from datetime import datetime
        scheduler = get_scheduler()
        sched_status = scheduler.status

        # 调度器状态概览
        if sched_status["running"]:
            st.success(f"{icon('check_circle',14)} 调度器运行中")
        else:
            st.warning(f"{icon('warning',14)} 调度器已停止")
        if sched_status["degraded"]:
            st.error(f"{icon('error',14)} 已降级为仅日报模式（连续失败 {sched_status['consecutive_failures']} 次）")

        c1, c2 = st.columns(2)
        with c1:
            scan_interval = st.number_input("扫描间隔（分钟）", 10, 1440, int(scan_cfg.get("scan_interval_minutes", 60) or 60))
        with c2:
            report_times_str = st.text_input("日报推送时间（逗号分隔）", value=",".join(cfg.get("scanner", {}).get("daily_report_times", ["09:00", "21:00"])))

        if st.button(f"{icon('save',16)} 保存调度器设置", key="save_sched"):
            report_times = [t.strip() for t in report_times_str.split(",") if t.strip()]
            # 更新内存中的配置
            scn = cfg.get("scanner", {})
            scn["scan_interval_minutes"] = scan_interval
            scn["daily_report_times"] = report_times
            scheduler.update_config(cfg)
            st.success(f"{icon('check_circle',16)} 调度器设置已更新")

        # 控制按钮
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            if sched_status["running"]:
                if st.button(f"{icon('stop',16)} 停止调度器", key="stop_sched_tools"):
                    scheduler.stop()
                    st.rerun()
            else:
                if st.button(f"{icon('play_arrow',16)} 启动调度器", type="primary", key="start_sched_tools"):
                    scheduler.start()
                    st.rerun()
        with c2:
            if sched_status["degraded"]:
                if st.button(f"{icon('refresh',16)} 重置降级", key="reset_degrade_tools"):
                    scheduler.reset_degrade()
                    st.rerun()
        with c3:
            if st.button(f"{icon('send',16)} 立即发送日报", key="send_daily_now"):
                from modules.reporter import Reporter
                from modules.pusher import Pusher
                from datetime import datetime
                now = datetime.now()
                today = now.strftime("%Y-%m-%d")
                opps = db.list_opportunities(limit=200, min_roi=0)
                today_opps = [o for o in opps if (o.get("discovered_at") or "")[:10] == today]
                reporter = Reporter(cfg)
                report = reporter.generate_daily_report(today_opps)
                report_text = reporter.format_daily_text(report)
                pusher = Pusher(cfg)
                ok = pusher.push(f"AI店长日报 (手动) - {len(today_opps)}个机会", report_text)
                if ok:
                    st.success(f"{icon('check_circle',16)} 日报已发送")
                else:
                    st.error(f"{icon('error',16)} 发送失败")
        with c4:
            if st.button(f"{icon('calendar_month',16)} 发送周报", key="send_weekly_now"):
                from modules.reporter import Reporter
                from modules.pusher import Pusher
                from datetime import datetime, timedelta
                now = datetime.now()
                week_start = now - timedelta(days=now.weekday())
                opps = db.list_opportunities(limit=500, min_roi=0)
                week_opps = [o for o in opps if (o.get("discovered_at") or "")[:10] >= week_start.strftime("%Y-%m-%d")]
                reporter = Reporter(cfg)
                report = reporter.generate_weekly_report(week_opps)
                report_text = reporter.format_weekly_text(report)
                pusher = Pusher(cfg)
                ok = pusher.push(f"AI店长周报 ({week_start.strftime('%Y-%m-%d')} ~ {now.strftime('%Y-%m-%d')})", report_text)
                if ok:
                    st.success(f"{icon('check_circle',16)} 周报已发送")
                else:
                    st.error(f"{icon('error',16)} 发送失败")

        # 检查价格预警按钮
        st.markdown("---")
        section_header("系统设置", "settings")

        # 开机自启动
        import os as _os
        startup_dir = _os.path.join(_os.getenv("APPDATA", ""),
                                     "Microsoft", "Windows", "Start Menu", "Programs", "Startup")
        startup_lnk = _os.path.join(startup_dir, "AI店长.lnk")
        is_autostart = _os.path.exists(startup_lnk)
        if st.checkbox("开机自动启动（网页+钉钉机器人）", value=is_autostart,
                       help="Windows启动时自动运行AI店长网页端和钉钉机器人"):
            if not is_autostart:
                import shutil
                desktop_lnk = _os.path.join(_os.path.expanduser("~"), "Desktop", "AI店长.lnk")
                if _os.path.exists(desktop_lnk):
                    shutil.copy2(desktop_lnk, startup_lnk)
                    st.success("已设置开机自启（下次开机自动运行）")
                    st.rerun()
                else:
                    st.warning("桌面上未找到 AI店长 快捷方式")
        else:
            if is_autostart:
                _os.remove(startup_lnk)
                st.success("已取消开机自启")
                st.rerun()

        if st.button(f"{icon('trending_up',16)} 检查价格预警（降价>10%）", key="check_price_alert"):
            from modules.price_alert import scan_price_drops, format_alert_text
            from modules.pusher import Pusher
            with st.spinner("扫描价格变化..."):
                alerts = scan_price_drops(db, days=7, drop_threshold=0.10)
            if alerts:
                st.success(f"发现 {len(alerts)} 个降价商品")
                text = format_alert_text(alerts, top=10)
                st.text(text)
                if st.button(f"{icon('send',16)} 推送预警", key="push_price_alert"):
                    Pusher(cfg).push(f"📉 价格预警 - {len(alerts)} 商品降价", text)
                    st.success("预警已推送")
            else:
                st.info("近期无显著降价")

    # ────────── 数据监控 ──────────
    with tab3:
        section_header("平台连接状态", "lan")
        c1, c2 = st.columns(2)
        with c1:
            metric_card("拼多多", "已连接" if cfg.get("platforms", {}).get("enabled_pdd", True) else "未启用", icon_name="shopping_cart")
        with c2:
            metric_card("闲鱼", "已连接" if cfg.get("platforms", {}).get("enabled_xianyu", True) else "未启用", icon_name="sell")

        if st.button(f"{icon('stethoscope',16)} 运行健康检查"):
            from modules.scrapers import ScraperPddApi, ScraperXianyu
            for cls in [ScraperPddApi, ScraperXianyu]:
                try:
                    if cls is ScraperPddApi:
                        scraper = ScraperPddApi.from_config(cfg)
                    else:
                        scraper = cls(cfg)
                    has_state = scraper._has_login_state()
                    if not has_state:
                        state = f"{icon('warning',14)} 未登录"
                    else:
                        ok = scraper.health_check()
                        state = f"{icon('check_circle',14)} 正常" if ok else f"{icon('error',14)} 异常"
                    st.markdown(f"- {icon(cls.__name__.replace('Scraper','').replace('Api','').lower(), 14)} **{scraper.PLATFORM_NAME}**: {state}")
                except Exception as e:
                    st.markdown(f"- {icon('error',14)} **{cls.__name__}**: 检查失败: {e}")

        section_header("数据库状态", "storage")
        stats = db.get_stats()
        c1, c2, c3, c4 = st.columns(4)
        with c1: metric_card("商品总数", stats.get("total_products", 0), icon_name="inventory_2")
        with c2: metric_card("机会总数", stats.get("total_opportunities", 0), icon_name="sell")
        with c3: metric_card("待审核", stats.get("pending_count", 0), icon_name="rate_review")
        with c4: metric_card("黑名单数", stats.get("blacklist_count", 0), icon_name="block")

        db_path = db.db_path
        if os.path.exists(db_path):
            st.caption(f"{icon('database',14)} 数据库大小: {os.path.getsize(db_path) / 1024:.1f} KB")

        section_header("关键词池", "key")
        pool = db.get_keyword_pool_stats()
        c1, c2, c3 = st.columns(3)
        with c1: metric_card("总关键词", pool["total"], icon_name="database")
        with c2: metric_card("已扫描", pool["scanned"], icon_name="task_alt")
        with c3: metric_card("待扫描", pool["pending"], icon_name="pending")
        if st.button(f"{icon('refresh',16)} 重新扩展关键词池"):
            with st.spinner(f"{icon('sync',16)} 正在从种子品类扩展..."):
                from modules.discovery import expand_to_flat_list, expand_apple_keywords
                seeds = cfg.get("scanner", {}).get("seed_categories", [])
                all_kws = expand_to_flat_list(seeds)
                all_kws.extend(expand_apple_keywords())
                db.add_keywords(all_kws, source="suggest")
            st.success(f"{icon('check_circle',16)} 扩展完成，共 {len(all_kws)} 个关键词")
            st.rerun()

        section_header("数据清理", "delete")
        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button(f"{icon('cleaning_services',16)} 清理过期数据"):
                st.success(f"已清理 {db.cleanup_old_data()} 条")
        with c2:
            if st.button(f"{icon('delete',16)} 清理1688假数据"):
                n = db.delete_opportunities_by_platform("1688")
                st.success(f"已清理 {n} 条1688数据")
                st.rerun()
        with c3:
            confirm = st.checkbox("确认清空（不可恢复）", key="clear_confirm")
            if st.button(f"{icon('warning',16)} 清空全部数据", disabled=not confirm):
                db.clear_all()
                st.success("已清空")
                st.rerun()

    # ────────── 黑名单 ──────────
    with tab4:
        section_header("拦截清单管理", "block")
        with st.form("add_bl_form", clear_on_submit=True):
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
        if not bl:
            st.info(f"{icon('info',16)} 暂无黑名单")
        else:
            type_cn = {"seller": "卖家", "brand": "品牌", "keyword": "关键词", "category": "品类"}
            for item in bl:
                c1, c2 = st.columns([5, 1])
                with c1:
                    t = type_cn.get(item.get("type", ""), item.get("type", ""))
                    st.markdown(
                        f'<span style="background:rgba(255,255,255,0.04);padding:2px 6px;border-radius:4px;'
                        f'font-size:0.75rem;font-family:monospace;">{t}</span> '
                        f'<b>{item["value"]}</b> '
                        f'<span style="color:var(--on-surface-variant);font-size:0.85rem;">· {item.get("reason","")}</span>',
                        unsafe_allow_html=True,
                    )
                with c2:
                    if st.button(f"{icon('delete',16)} 移除", key=f"rm_bl_{item['id']}"):
                        db.remove_blacklist(item["id"])
                        st.rerun()

    # ────────── 关注列表 ──────────
    with tab5:
        section_header("关注商品", "star")
        watched = db.get_watched_products(limit=50)
        if not watched:
            st.info("暂无关注商品。在看板中点击⭐关注即可添加。")
        else:
            st.caption(f"共 {len(watched)} 个关注商品")
            for p in watched:
                c1, c2, c3 = st.columns([3, 1, 1])
                with c1:
                    st.markdown(f"**{p.get('title','')[:50]}**")
                    st.caption(f"{p.get('platform','')} | ¥{p.get('price',0):.2f} | 销量 {p.get('sales_count',0)}")
                with c2:
                    if p.get('product_url'):
                        st.markdown(f"[查看]({p.get('product_url')})")
                with c3:
                    if st.button("取消关注", key=f"unwatch_{p.get('product_id','')}_{p.get('platform','')}"):
                        db.toggle_watch_product(p.get('product_id', ''), p.get('platform', ''), False)
                        st.rerun()
