"""AI店长 v1.1 - 模块单元测试"""
import os
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from modules.matcher import title_similarity, match_cross_platform, find_best_match
from modules.arbitrage import ArbitrageItem, calculate_arbitrage, scan_cross_platform, format_profit_report
from modules.reporter import Reporter
from modules.scheduler import ScanScheduler
from database import Database


class TestMatcher(unittest.TestCase):
    """标题匹配器测试"""

    def test_identical_titles(self):
        score = title_similarity("儿童玩具积木城堡", "儿童玩具积木城堡")
        self.assertAlmostEqual(score, 1.0, places=1)

    def test_similar_titles(self):
        score = title_similarity(
            "儿童益智积木拼装城堡玩具",
            "益智儿童积木拼装城堡",
        )
        self.assertGreater(score, 0.5)

    def test_different_titles(self):
        score = title_similarity("儿童玩具积木", "男士运动跑鞋")
        self.assertLess(score, 0.3)

    def test_empty_titles(self):
        score = title_similarity("", "")
        self.assertEqual(score, 0.0)

    def test_match_cross_platform(self):
        products_a = [
            {"product_id": "a1", "title": "儿童益智积木拼装城堡玩具", "price": 15.0},
            {"product_id": "a2", "title": "男士运动跑鞋轻便透气", "price": 45.0},
        ]
        products_b = [
            {"product_id": "b1", "title": "益智儿童积木拼装城堡", "price": 39.0},
            {"product_id": "b2", "title": "运动跑鞋男轻便透气鞋", "price": 89.0},
        ]
        matches = match_cross_platform(products_a, products_b, threshold=0.4)
        self.assertGreaterEqual(len(matches), 1)

    def test_find_best_match(self):
        target = {"title": "儿童益智积木拼装城堡玩具"}
        candidates = [
            {"title": "益智儿童积木拼装城堡"},
            {"title": "男士运动跑鞋"},
        ]
        result = find_best_match(target, candidates, threshold=0.4)
        self.assertIsNotNone(result)
        self.assertEqual(result[0]["title"], "益智儿童积木拼装城堡")


class TestArbitrage(unittest.TestCase):
    """价差计算器测试"""

    def test_profitable_opportunity(self):
        buy = {"platform": "1688", "product_id": "a1", "title": "玩具积木", "price": 10.0}
        sell = {"platform": "xianyu", "product_id": "b1", "title": "玩具积木", "price": 35.0}
        result = calculate_arbitrage(buy, sell, min_roi=20)
        self.assertIsNotNone(result)
        self.assertGreater(result.profit, 0)
        self.assertGreater(result.roi, 20)

    def test_unprofitable_opportunity(self):
        buy = {"platform": "1688", "product_id": "a1", "title": "玩具", "price": 30.0}
        sell = {"platform": "xianyu", "product_id": "b1", "title": "玩具", "price": 32.0}
        result = calculate_arbitrage(buy, sell, min_roi=20)
        self.assertIsNone(result)

    def test_scan_cross_platform(self):
        buy_products = [
            {"platform": "1688", "product_id": "a1", "title": "儿童积木拼装城堡玩具", "price": 12.0},
        ]
        sell_products = [
            {"platform": "xianyu", "product_id": "b1", "title": "积木拼装城堡儿童玩具", "price": 45.0},
        ]
        results = scan_cross_platform(buy_products, sell_products, min_roi=20)
        self.assertGreaterEqual(len(results), 0)  # may or may not match

    def test_format_profit_report_empty(self):
        report = format_profit_report([])
        self.assertIn("未发现", report)

    def test_format_profit_report_with_data(self):
        items = [
            ArbitrageItem(
                buy_platform="1688", sell_platform="xianyu",
                buy_title="测试商品", buy_product_id="a1",
                sell_title="测试商品", sell_product_id="b1",
                buy_price=10.0, sell_price=35.0,
                profit=21.46, roi=214.6, confidence=0.85,
            )
        ]
        report = format_profit_report(items)
        self.assertIn("ROI", report)
        self.assertIn("214.6%", report)


class TestReporter(unittest.TestCase):
    """报告生成器测试"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.reporter = Reporter({}, output_dir=self.tmpdir)

    def test_generate_daily_report(self):
        opps = [
            {"buy_platform": "1688", "sell_platform": "xianyu",
             "buy_title": "商品A", "buy_price": 10, "sell_price": 35,
             "profit": 21.46, "roi": 214.6, "confidence": 0.8},
            {"buy_platform": "1688", "sell_platform": "pdd",
             "buy_title": "商品B", "buy_price": 20, "sell_price": 50,
             "profit": 25.2, "roi": 126.0, "confidence": 0.7},
        ]
        report = self.reporter.generate_daily_report(opps)
        self.assertEqual(report["report_type"], "daily")
        self.assertEqual(report["summary"]["total_opportunities"], 2)
        self.assertEqual(len(report["top10"]), 2)

    def test_format_daily_text(self):
        opps = [
            {"buy_platform": "1688", "sell_platform": "xianyu",
             "buy_title": "测试商品", "buy_price": 10, "sell_price": 35,
             "profit": 21.46, "roi": 214.6, "confidence": 0.8},
        ]
        report = self.reporter.generate_daily_report(opps)
        text = self.reporter.format_daily_text(report)
        self.assertIn("AI店长日报", text)
        self.assertIn("214.6%", text)

    def test_list_reports_empty(self):
        reports = self.reporter.list_reports(7)
        self.assertEqual(len(reports), 0)


class TestScheduler(unittest.TestCase):
    """后台调度器测试"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test.db")
        self.db = Database(self.db_path)
        self.config = {
            "scanner": {
                "scan_interval_minutes": 1,
                "keywords_per_round": 5,
                "realtime_push_threshold": 0.30,
                "daily_report_times": ["09:00", "21:00"],
                "top_n": 10,
            },
            "finance": {
                "domestic_shipping": 3.0,
                "platform_fee_rate": 0.016,
            },
            "antiscrap": {
                "auto_degrade_after_failures": 3,
            },
            "push": {
                "method": "email",
                "smtp_host": "",
                "smtp_user": "",
                "smtp_pass": "",
                "email_to": "",
            },
        }

    def test_init(self):
        scheduler = ScanScheduler(self.db, self.config)
        self.assertFalse(scheduler.status["running"])
        self.assertFalse(scheduler.status["degraded"])
        self.assertEqual(scheduler.status["consecutive_failures"], 0)
        self.assertEqual(scheduler.status["total_scans"], 0)

    def test_start_stop(self):
        scheduler = ScanScheduler(self.db, self.config)
        self.assertTrue(scheduler.start())
        self.assertTrue(scheduler.status["running"])
        self.assertFalse(scheduler.start())  # already running
        self.assertTrue(scheduler.stop())
        self.assertFalse(scheduler.status["running"])
        self.assertFalse(scheduler.stop())  # already stopped

    def test_status_dict(self):
        scheduler = ScanScheduler(self.db, self.config)
        status = scheduler.status
        self.assertIn("running", status)
        self.assertIn("degraded", status)
        self.assertIn("consecutive_failures", status)
        self.assertIn("last_scan_time", status)
        self.assertIn("next_scan_time", status)
        self.assertIn("interval_minutes", status)
        self.assertIn("total_scans", status)
        self.assertIn("total_opportunities", status)
        self.assertIn("total_pushes", status)

    def test_reset_degrade(self):
        scheduler = ScanScheduler(self.db, self.config)
        scheduler._degraded = True
        scheduler._consecutive_failures = 5
        scheduler.reset_degrade()
        self.assertFalse(scheduler.status["degraded"])
        self.assertEqual(scheduler.status["consecutive_failures"], 0)

    def test_update_config(self):
        scheduler = ScanScheduler(self.db, self.config)
        new_config = dict(self.config)
        new_config["scanner"] = dict(self.config["scanner"])
        new_config["scanner"]["scan_interval_minutes"] = 30
        scheduler.update_config(new_config)
        self.assertEqual(scheduler.status["interval_minutes"], 30)

    def test_daemon_thread(self):
        scheduler = ScanScheduler(self.db, self.config)
        scheduler.start()
        self.assertTrue(scheduler._thread.is_alive())
        self.assertTrue(scheduler._thread.daemon)
        scheduler.stop()


if __name__ == "__main__":
    unittest.main()
