"""AI店长 v1.1 - 后台定时扫描调度器

功能：
- 定时自动扫描（默认 60 分钟一轮）
- ROI > 30% 实时推送
- 每日 09:00 / 21:00 日报推送
- 连续失败 ≥3 次自动降级为仅日报模式
- 线程安全，支持启停控制
"""
import atexit
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class ScanScheduler:
    """后台扫描调度器（单例，线程安全）"""

    def __init__(
        self,
        db,
        config: Dict[str, Any],
        on_scan_complete: Optional[Callable] = None,
    ):
        self.db = db
        self.config = config
        self.on_scan_complete = on_scan_complete

        # 扫描参数
        scn = config.get("scanner", {})
        self.interval_minutes = int(scn.get("scan_interval_minutes", 60) or 60)
        self.keywords_per_round = int(scn.get("keywords_per_round", 20) or 20)
        self.realtime_push_threshold = float(scn.get("realtime_push_threshold", 0.30) or 0.30)
        self.daily_report_times = scn.get("daily_report_times", ["09:00", "21:00"])
        self.top_n = int(scn.get("top_n", 10) or 10)

        # 降级参数
        antiscrap = config.get("antiscrap", {})
        self.max_failures = int(antiscrap.get("auto_degrade_after_failures", 3) or 3)

        # 状态
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._consecutive_failures = 0
        self._degraded = False
        self._last_scan_time: Optional[datetime] = None
        self._last_reverse_scan_time: Optional[datetime] = None
        self._last_seller_sync: Optional[datetime] = None
        self._last_report_time: Optional[datetime] = None
        self._total_scans = 0
        self._total_opportunities = 0
        self._total_pushes = 0
        self._lock = threading.Lock()

        # 从 DB 恢复上次状态（重启不丢失进度）
        saved = self.db.load_scheduler_state()
        if saved:
            self._total_scans = saved.get("total_scans", 0)
            self._total_opportunities = saved.get("total_opportunities", 0)
            self._total_pushes = saved.get("total_pushes", 0)
            self._consecutive_failures = saved.get("consecutive_failures", 0)
            self._degraded = saved.get("degraded", False)
            if saved.get("last_scan_time"):
                self._last_scan_time = datetime.fromisoformat(saved["last_scan_time"])
            logger.info("scheduler state restored: %d scans", self._total_scans)

        # 注册退出清理
        atexit.register(self.stop)

    @property
    def status(self) -> Dict[str, Any]:
        """返回调度器当前状态"""
        with self._lock:
            now = datetime.now()
            next_scan = None
            if self._running and self._last_scan_time:
                next_scan = self._last_scan_time + timedelta(minutes=self.interval_minutes)

            return {
                "running": self._running,
                "degraded": self._degraded,
                "consecutive_failures": self._consecutive_failures,
                "last_scan_time": self._last_scan_time.isoformat() if self._last_scan_time else None,
                "last_report_time": self._last_report_time.isoformat() if self._last_report_time else None,
                "next_scan_time": next_scan.isoformat() if next_scan else None,
                "interval_minutes": self.interval_minutes,
                "total_scans": self._total_scans,
                "total_opportunities": self._total_opportunities,
                "total_pushes": self._total_pushes,
            }

    def start(self) -> bool:
        """启动后台调度线程"""
        if self._running:
            logger.warning("调度器已在运行")
            return False

        self._stop_event.clear()
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="scan-scheduler")
        self._thread.start()
        logger.info("调度器已启动，间隔 %d 分钟", self.interval_minutes)
        return True

    def stop(self) -> bool:
        """停止调度器"""
        if not self._running:
            return False

        self._stop_event.set()
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        logger.info("调度器已停止")
        return True

    def reset_degrade(self) -> None:
        """手动重置降级状态"""
        with self._lock:
            self._degraded = False
            self._consecutive_failures = 0
            logger.info("降级状态已重置")

    def update_config(self, config: Dict[str, Any]) -> None:
        """热更新配置"""
        self.config = config
        scn = config.get("scanner", {})
        self.interval_minutes = int(scn.get("scan_interval_minutes", 60) or 60)
        self.keywords_per_round = int(scn.get("keywords_per_round", 20) or 20)
        self.realtime_push_threshold = float(scn.get("realtime_push_threshold", 0.30) or 0.30)
        self.daily_report_times = scn.get("daily_report_times", ["09:00", "21:00"])

    def _run_loop(self) -> None:
        """后台主循环"""
        while not self._stop_event.is_set():
            try:
                now = datetime.now()

                # 检查是否该执行日报
                self._check_daily_report(now)

                # 检查是否该执行扫描（降级模式下跳过）
                if not self._degraded:
                    should_scan = False
                    if self._last_scan_time is None:
                        should_scan = True
                    elif (now - self._last_scan_time).total_seconds() / 60 >= self.interval_minutes:
                        should_scan = True

                    if should_scan:
                        self._run_scan()

                    # 反向找货（每3小时）
                    should_reverse = False
                    if self._last_reverse_scan_time is None:
                        should_reverse = True
                    elif (now - self._last_reverse_scan_time).total_seconds() / 3600 >= 3:
                        should_reverse = True

                    if should_reverse:
                        self._run_reverse_scan()

                    # 闲鱼卖家数据同步（每小时）
                    should_sync_seller = False
                    if self._last_seller_sync is None:
                        should_sync_seller = True
                    elif (now - self._last_seller_sync).total_seconds() / 3600 >= 1:
                        should_sync_seller = True
                    if should_sync_seller:
                        self._sync_seller_data()

                # 每 30 秒检查一次
                self._stop_event.wait(timeout=30)

            except Exception as e:
                logger.error("调度器循环异常: %s", e)
                self._stop_event.wait(timeout=60)

    def _run_scan(self) -> None:
        """执行一轮扫描"""
        with self._lock:
            scan_start = datetime.now()

        try:
            from modules.scrapers import Scraper1688, ScraperPddApi, ScraperXianyu
            from modules.arbitrage import scan_cross_platform

            # 获取待扫描关键词
            keywords = self.db.get_next_keywords(self.keywords_per_round)
            if not keywords:
                self.db.reset_keyword_pool()
                # 每重置一次计数 +1，每 10 轮扩展一次新词
                self._cycle_count = getattr(self, '_cycle_count', 0) + 1
                logger.info("Pool cycled %d times, resetting", self._cycle_count)
                if self._cycle_count % 10 == 0:
                    try:
                        from modules.discovery import expand_to_flat_list, expand_apple_keywords
                        seeds = self.config.get("scanner", {}).get("seed_categories", [])
                        new_kws = expand_to_flat_list(seeds) if seeds else []
                        new_kws.extend(expand_apple_keywords())
                        if new_kws:
                            added = self.db.add_keywords(new_kws, source="cycle_expand")
                            logger.info("Cycle expand: +%d keywords, pool now at %d", added,
                                       self.db.get_keyword_pool_stats()["total"])
                    except Exception as e:
                        logger.warning("Cycle expand failed: %s", e)
                keywords = self.db.get_next_keywords(self.keywords_per_round)
                if not keywords:
                    logger.info("关键词池为空")
                    return

            run_id = self.db.start_workflow_run("auto_scan", ["1688", "pdd", "xianyu"])
            total_opps = 0
            total_pushes = 0
            shipping = float(self.config.get("finance", {}).get("domestic_shipping", 3) or 3)
            fee_rate = float(self.config.get("finance", {}).get("platform_fee_rate", 0.016) or 0.016)

            for kw in keywords:
                if self._stop_event.is_set():
                    break

                platforms_enabled = self.config.get("platforms", {})

                # 1. 保存各平台原始商品数据
                try:
                    pdd_scraper = ScraperPddApi.from_config(self.config)
                    pdd_items = pdd_scraper.fetch(kw, 20)
                    self.db.save_products(pdd_items, "pdd")
                except Exception as e:
                    logger.warning("PDD 抓取失败 [%s]: %s", kw, e)
                    pdd_items = []

                try:
                    xy_scraper = ScraperXianyu(self.config)
                    xy_items = xy_scraper.fetch(kw, 20)
                    self.db.save_products(xy_items, "xianyu")
                except Exception as e:
                    logger.warning("闲鱼 抓取失败 [%s]: %s", kw, e)
                    xy_items = []

                # 1688: 仅当已攻克并启用时才抓取
                if platforms_enabled.get("enabled_1688", False):
                    try:
                        s1688 = Scraper1688(self.config)
                        items_1688 = s1688.fetch(kw, 20)
                        self.db.save_products(items_1688, "1688")
                    except Exception as e:
                        logger.warning("1688 抓取失败 [%s]: %s", kw, e)

                # 2. 双向交叉扫描匹配
                if pdd_items and xy_items:
                    from modules.matcher import bidirectional_scan
                    opps = bidirectional_scan(
                        kw, pdd_scraper, xy_scraper,
                        shipping, fee_rate,
                        min_roi=None, min_similarity=0.08,
                        config=self.config, db=self.db,
                    )
                    for d in opps:
                        d["status"] = "pending"
                        # 黑名单拦截
                        if self.db.is_blacklisted(
                            title=d.get("buy_title", ""),
                            seller_name=d.get("buy_seller", ""),
                        ):
                            continue
                        # 类目过滤：拦截服装等低质量品类
                        from modules.category_filter import filter_opportunity
                        passed, reason = filter_opportunity(d)
                        if not passed:
                            self._filtered_count = getattr(self, '_filtered_count', 0) + 1
                            continue
                        opp_id = self.db.save_opportunity(d)
                        d["id"] = opp_id
                        total_opps += 1
                        if d.get("roi", 0) >= self.realtime_push_threshold * 100:
                            if total_pushes < self.top_n:
                                if self._push_opportunity(d, opp_id):
                                    total_pushes += 1

                self.db.mark_keyword_scanned(kw)

            # 3. 保存价格快照（供价格曲线使用）
            all_products = self.db.get_recent_products(limit=500)
            if all_products:
                self.db.save_price_snapshot(all_products)
                logger.info("saved price snapshots for %d products", len(all_products))

            # 4. 标记成功
            self.db.finish_workflow_run(run_id, "success", len(keywords), total_opps, total_pushes)
            filtered = getattr(self, '_filtered_count', 0)
            if filtered > 0:
                logger.info("Filtered %d clothing/low-quality opportunities", filtered)
                self._filtered_count = 0

            # 5. 自动补充关键词池（防止空池）
            pool = self.db.get_keyword_pool_stats()
            if pool.get("unscanned", 0) < 10:
                logger.info("关键词池快空了，自动补充...")
                from modules.discovery import expand_to_flat_list, expand_apple_keywords, get_trending_keywords
                seeds = self.config.get("scanner", {}).get("seed_categories", [])
                if seeds:
                    new_kws = expand_to_flat_list(seeds)
                    new_kws.extend(expand_apple_keywords())
                    new_kws.extend(get_trending_keywords(20))
                    self.db.add_keywords(new_kws, source="auto_refill")
                    logger.info("自动补充 %d 个关键词 (含热门趋势)", len(new_kws))

            # 6. 价格预警检查（降价>10%则推送）
            try:
                from modules.price_alert import scan_price_drops, format_alert_text
                from modules.pusher import Pusher
                drop_alerts = scan_price_drops(self.db, days=7, drop_threshold=0.10)
                if drop_alerts:
                    text = format_alert_text(drop_alerts, top=5)
                    Pusher(self.config).push(
                        f"📉 价格预警 - {len(drop_alerts)} 商品降价", text
                    )
                    logger.info("价格预警已推送: %d 商品降价", len(drop_alerts))
            except Exception as e:
                logger.debug("价格预警检查跳过: %s", e)

            with self._lock:
                self._last_scan_time = scan_start
                self._total_scans += 1
                self._total_opportunities += total_opps
                self._total_pushes += total_pushes
                self._consecutive_failures = 0

            # 持久化状态（重启不丢失）
            self.db.save_scheduler_state({
                "total_scans": self._total_scans,
                "total_opportunities": self._total_opportunities,
                "total_pushes": self._total_pushes,
                "consecutive_failures": 0,
                "degraded": self._degraded,
                "last_scan_time": scan_start.isoformat() if scan_start else None,
                "last_report_time": self._last_report_time.isoformat() if self._last_report_time else None,
            })

            logger.info(
                "扫描完成: %d 关键词, %d 机会, %d 推送",
                len(keywords), total_opps, total_pushes,
            )

            if self.on_scan_complete:
                self.on_scan_complete(total_opps, total_pushes)

        except Exception as e:
            logger.error("扫描执行失败: %s", e)
            with self._lock:
                self._consecutive_failures += 1
                if self._consecutive_failures >= self.max_failures:
                    self._degraded = True
                    logger.warning(
                        "连续失败 %d 次，已降级为仅日报模式",
                        self._consecutive_failures,
                    )
            # 持久化失败和降级状态
            self.db.save_scheduler_state({
                "total_scans": self._total_scans,
                "total_opportunities": self._total_opportunities,
                "total_pushes": self._total_pushes,
                "consecutive_failures": self._consecutive_failures,
                "degraded": self._degraded,
                "last_scan_time": self._last_scan_time.isoformat() if self._last_scan_time else None,
            })

    def _run_reverse_scan(self) -> None:
        """执行反向找货：闲鱼爆款 -> PDD找同款低价"""
        try:
            from modules.scrapers import ScraperPddApi, ScraperXianyu
            from modules.hot_collector import filter_hot_items
            from modules.reverse_sourcing import reverse_source
            from modules.pusher import Pusher

            keywords = self.db.get_next_keywords(3)
            if not keywords:
                logger.info("反向找货: 无关键词")
                return

            pdd_s = ScraperPddApi.from_config(self.config)
            xy_s = ScraperXianyu(self.config)
            shipping = float(self.config.get("finance", {}).get("domestic_shipping", 3) or 3)
            fee_rate = float(self.config.get("finance", {}).get("platform_fee_rate", 0.016) or 0.016)
            total_opps = 0

            for kw in keywords[:3]:
                if self._stop_event.is_set():
                    break
                kw = kw.strip()
                if not kw:
                    continue

                xy_items = xy_s.fetch(kw, 15)
                if not xy_items:
                    continue
                self.db.save_products(xy_items, "xianyu")

                hot = filter_hot_items(xy_items, min_want=1) or xy_items[:8]
                opps = reverse_source(kw, hot, pdd_s, xy_s, shipping, fee_rate,
                                      config=self.config, db=self.db)
                for d in opps:
                    d["status"] = "pending"
                    self.db.save_opportunity(d)
                    total_opps += 1
                self.db.mark_keyword_scanned(kw)

            with self._lock:
                self._last_reverse_scan_time = datetime.now()

            if total_opps > 0:
                Pusher(self.config).push("AI店长 反向找货完成",
                            f"{len(keywords)} 词, 发现 {total_opps} 机会")

            logger.info("反向找货完成: %d 关键词, %d 机会", len(keywords), total_opps)

        except Exception as e:
            logger.error("反向找货失败: %s", e)

    def _check_daily_report(self, now: datetime) -> None:
        """检查是否该发送日报，周一同时发送周报"""
        current_time = now.strftime("%H:%M")
        for report_time in self.daily_report_times:
            if current_time == report_time:
                if self._last_report_time and self._last_report_time.date() == now.date():
                    if self._last_report_time.hour == now.hour:
                        continue

                self._send_daily_report(now)

                # 周一早上发送周报
                if now.weekday() == 0 and report_time == self.daily_report_times[0]:
                    self._send_weekly_report(now)
                break

    def _send_daily_report(self, now: datetime) -> None:
        """发送日报"""
        try:
            from modules.reporter import Reporter
            from modules.pusher import Pusher

            today = now.strftime("%Y-%m-%d")
            opps = self.db.list_opportunities(limit=200, min_roi=0)
            today_opps = [
                o for o in opps
                if (o.get("discovered_at") or "")[:10] == today
            ]

            reporter = Reporter(self.config)
            report = reporter.generate_daily_report(today_opps)
            report_text = reporter.format_daily_text(report)

            pusher = Pusher(self.config)
            time_slot = now.strftime("%H:%M")
            title = f"AI店长日报 ({time_slot}) - {len(today_opps)}个机会"
            pusher.push(title, report_text)

            with self._lock:
                self._last_report_time = now

            logger.info("日报已发送: %s, %d 个机会", time_slot, len(today_opps))

        except Exception as e:
            logger.error("日报发送失败: %s", e)

    def _send_weekly_report(self, now: datetime) -> None:
        """发送周报"""
        try:
            from modules.reporter import Reporter
            from modules.pusher import Pusher
            from datetime import timedelta

            reporter = Reporter(self.config)
            week_start = now - timedelta(days=now.weekday())
            week_start_str = week_start.strftime("%Y-%m-%d")

            opps = self.db.list_opportunities(limit=500, min_roi=0)
            week_opps = [
                o for o in opps
                if (o.get("discovered_at") or "")[:10] >= week_start_str
            ]

            if not week_opps:
                logger.info("周报跳过：本周无数据")
                return

            report = reporter.generate_weekly_report(week_opps)
            report_text = reporter.format_weekly_text(report)

            pusher = Pusher(self.config)
            title = f"AI店长周报 ({week_start_str} ~ {now.strftime('%Y-%m-%d')})"
            pusher.push(title, report_text)

            logger.info("周报已发送: %d 个机会", len(week_opps))

        except Exception as e:
            logger.error("周报发送失败: %s", e)

    def _push_opportunity(self, opp: Dict[str, Any], opp_id: int = 0) -> bool:
        """推送单条机会（带去重）"""
        try:
            from modules.pusher import Pusher

            pusher = Pusher(self.config)
            product_id = opp.get("sell_product_id", opp.get("product_id", ""))
            platform = opp.get("sell_platform", "")

            # DB 级去重（使用 max_push_per_item 控制时间窗口）
            dedup_hours = max(int(self.config.get("scanner", {}).get("max_push_per_item", 24) or 24), 1)
            if opp_id > 0 and self.db.was_pushed_recently(opp_id, hours=dedup_hours):
                return False

            ok = pusher.push_opportunity(opp)
            if ok:
                self.db.log_push(opp_id, "realtime", "email", "success")
            return ok

        except Exception as e:
            logger.error("推送失败: %s", e)
            return False

    def _sync_seller_data(self):
        """同步闲鱼卖家数据总览"""
        import re, json, time as _t
        from pathlib import Path as _Path
        state_path = _Path(__file__).resolve().parent.parent.parent / "data" / "login_states" / "xianyu_state.json"
        if not state_path.exists():
            return
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=False, channel="msedge",
                    args=["--disable-blink-features=AutomationControlled", "--no-proxy-server"],
                )
                ctx = browser.new_context(storage_state=str(state_path))
                page = ctx.new_page()
                page.goto("https://seller.goofish.com/", timeout=30000, wait_until="load")
                _t.sleep(4)
                body = page.inner_text("body")
                ctx.close()
                browser.close()
            def get_after(kw):
                idx = body.find(kw)
                if idx < 0: return 0
                nums = re.findall(r'(\d+(?:\.\d+)?)', body[idx+len(kw):].strip()[:30])
                return float(nums[0]) if nums else 0
            data = {
                "online_items": int(get_after("在线商品数")),
                "exposure": int(get_after("商品曝光次数")),
                "visitors": int(get_after("商品访问人数")),
                "orders": int(get_after("支付笔数")),
                "revenue": get_after("支付金额"),
                "synced_at": datetime.now().isoformat(),
            }
            self.db.set_config("xianyu_seller_data", json.dumps(data, ensure_ascii=False))
            self.db.set_config("xianyu_last_sync", data["synced_at"])
            self._last_seller_sync = datetime.now()
            logger.info("Xianyu seller synced: %d items, %d exp, %d visitors",
                        data["online_items"], data["exposure"], data["visitors"])
        except Exception as e:
            logger.warning("Xianyu seller sync failed: %s", e)
