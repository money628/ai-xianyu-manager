"""AI店长 v1.1 - 数据库层测试

覆盖：
- 表创建
- 商品保存/查询
- 价格历史快照
- 拉黑清单
- 跑批日志
- 推送日志（去重）
- 统计
- 数据清理
"""
import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.database import (
    init_db,
    save_products,
    get_recent_products,
    save_price_snapshot,
    get_price_curve,
    save_opportunity,
    list_opportunities,
    update_opportunity_status,
    add_to_blacklist,
    is_blacklisted,
    list_blacklist,
    remove_from_blacklist,
    start_workflow_run,
    finish_workflow_run,
    was_pushed_recently,
    log_push,
    cleanup_old_data,
    get_stats,
    add_keywords,
    get_next_keywords,
    mark_keyword_scanned,
    get_keyword_pool_stats,
)


class TestDatabase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = self.tmp.name
        init_db(self.db_path)

    def tearDown(self):
        try:
            os.unlink(self.db_path)
        except OSError:
            pass

    # ---------- 表创建 ----------
    def test_init_db_creates_all_tables(self):
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
            table_names = {r[0] for r in rows}
        expected = {
            "products", "price_history", "opportunities",
            "user_blacklist", "system_config", "workflow_runs", "push_log",
            "keyword_pool",
        }
        self.assertTrue(expected.issubset(table_names),
                        f"Missing tables: {expected - table_names}")

    # ---------- 商品保存/查询 ----------
    def test_save_and_query_products(self):
        products = [
            {
                "platform": "1688",
                "product_id": "A001",
                "title": "极简风桌面收纳盒",
                "price": 12.5,
                "sales_count": 100,
                "seller_name": "义乌工厂",
                "product_url": "https://1688.com/offer/A001",
                "image_url": "https://img.com/1.jpg",
                "region": "浙江",
            },
            {
                "platform": "pdd",
                "product_id": "P001",
                "title": "户外露营灯",
                "price": 45.0,
                "sales_count": 200,
                "seller_name": "拼多多店铺",
                "product_url": "https://pdd.com/P001",
            },
        ]
        n = save_products(self.db_path, products)
        self.assertEqual(n, 2)

        recent = get_recent_products(self.db_path)
        self.assertEqual(len(recent), 2)
        self.assertEqual(recent[0]["platform"], "pdd")  # 按时间倒序

        # 平台过滤
        p1688 = get_recent_products(self.db_path, platform="1688")
        self.assertEqual(len(p1688), 1)
        self.assertEqual(p1688[0]["title"], "极简风桌面收纳盒")

    # ---------- 价格历史快照 ----------
    def test_price_history_snapshot_and_curve(self):
        products = [
            {"platform": "1688", "product_id": "A001", "title": "X", "price": 10.0},
        ]
        save_price_snapshot(self.db_path, products)
        curve = get_price_curve(self.db_path, "1688", "A001", days=10)
        self.assertEqual(len(curve), 1)
        self.assertEqual(curve[0]["price"], 10.0)

    def test_price_snapshot_dedup(self):
        products = [
            {"platform": "1688", "product_id": "A001", "title": "X", "price": 10.0},
            {"platform": "1688", "product_id": "A001", "title": "X", "price": 11.0},  # 同日同商品
        ]
        n = save_price_snapshot(self.db_path, products)
        # 第二次覆盖第一次
        curve = get_price_curve(self.db_path, "1688", "A001")
        self.assertEqual(len(curve), 1)
        # 第二次插入（REPLACE）应覆盖
        self.assertEqual(curve[0]["price"], 11.0)

    # ---------- 价差机会 ----------
    def test_opportunity_crud(self):
        opp = {
            "source_platform": "1688",
            "source_title": "收纳盒",
            "source_price": 12.5,
            "target_platform": "xianyu",
            "target_title": "极简风桌面收纳盒",
            "target_price": 39.9,
            "gross_profit": 27.4,
            "net_profit": 24.4,
            "roi": 0.95,
            "confidence": 0.85,
            "sales_signal": 500,
        }
        opp_id = save_opportunity(self.db_path, opp)
        self.assertGreater(opp_id, 0)

        pending = list_opportunities(self.db_path, status="PENDING")
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["roi"], 0.95)

        # 状态更新
        update_opportunity_status(self.db_path, opp_id, "APPROVED", "看起来不错", "user")
        approved = list_opportunities(self.db_path, status="APPROVED")
        self.assertEqual(len(approved), 1)
        self.assertEqual(approved[0]["notes"], "看起来不错")

    def test_list_opportunities_filter_by_roi(self):
        for roi in [0.1, 0.3, 0.5]:
            save_opportunity(self.db_path, {
                "source_platform": "1688", "source_title": "X", "source_price": 10,
                "target_platform": "xianyu", "target_title": "X", "target_price": 10 + roi * 10,
                "gross_profit": roi * 10, "net_profit": roi * 10,
                "roi": roi, "confidence": 0.8,
            })
        high_roi = list_opportunities(self.db_path, min_roi=0.3)
        self.assertEqual(len(high_roi), 2)

    # ---------- 拉黑 ----------
    def test_blacklist_by_seller(self):
        add_to_blacklist(self.db_path, {"seller_name": "BadSeller", "reason": "骗子"})
        self.assertTrue(is_blacklisted(self.db_path, seller_name="BadSeller"))
        self.assertFalse(is_blacklisted(self.db_path, seller_name="GoodSeller"))

    def test_blacklist_by_brand(self):
        add_to_blacklist(self.db_path, {"brand": "BadBrand", "reason": "劣质"})
        self.assertTrue(is_blacklisted(self.db_path, brand="BadBrand"))

    def test_blacklist_by_keyword(self):
        add_to_blacklist(self.db_path, {"product_keyword": "假货", "reason": "假货多"})
        self.assertTrue(is_blacklisted(self.db_path, title="这是个假货商品"))
        self.assertFalse(is_blacklisted(self.db_path, title="这是正品"))

    def test_blacklist_remove(self):
        item_id = add_to_blacklist(self.db_path, {"brand": "TmpBrand"})
        self.assertEqual(len(list_blacklist(self.db_path)), 1)
        remove_from_blacklist(self.db_path, item_id)
        self.assertEqual(len(list_blacklist(self.db_path)), 0)

    # ---------- 跑批日志 ----------
    def test_workflow_run_lifecycle(self):
        run_id = start_workflow_run(self.db_path, "auto_scan", ["1688", "pdd"])
        self.assertGreater(run_id, 0)
        finish_workflow_run(
            self.db_path, run_id, "success",
            signals=100, opportunities=5, pushed=2,
        )
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM workflow_runs WHERE id=?", (run_id,)
            ).fetchone()
        self.assertEqual(row["run_type"], "auto_scan")
        self.assertEqual(row["status"], "success")
        self.assertEqual(row["platforms"], "1688,pdd")
        self.assertEqual(row["signals_found"], 100)
        self.assertEqual(row["opportunities_found"], 5)
        self.assertEqual(row["opportunities_pushed"], 2)

    # ---------- 推送日志 ----------
    def test_push_log_dedup(self):
        opp_id = save_opportunity(self.db_path, {
            "source_platform": "1688", "source_title": "X", "source_price": 10,
            "target_platform": "xianyu", "target_title": "X", "target_price": 20,
            "gross_profit": 10, "net_profit": 10, "roi": 1.0, "confidence": 0.9,
        })
        log_push(self.db_path, opp_id, "realtime", "serverchan", "success")
        self.assertTrue(was_pushed_recently(self.db_path, opp_id, hours=24))

        # 不同 opportunity
        opp_id2 = save_opportunity(self.db_path, {
            "source_platform": "1688", "source_title": "Y", "source_price": 10,
            "target_platform": "xianyu", "target_title": "Y", "target_price": 20,
            "gross_profit": 10, "net_profit": 10, "roi": 1.0, "confidence": 0.9,
        })
        self.assertFalse(was_pushed_recently(self.db_path, opp_id2, hours=24))

    # ---------- 数据清理 ----------
    def test_cleanup_old_data(self):
        # 插入旧数据
        old_date = (datetime.now() - timedelta(days=40)).strftime("%Y-%m-%d")
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO price_history
                   (platform, product_id, title, price, snapshot_date)
                   VALUES ('1688', 'OLD', 'X', 10, ?)""",
                (old_date,),
            )
        cleanup_old_data(self.db_path, retention_days=30)
        curve = get_price_curve(self.db_path, "1688", "OLD")
        self.assertEqual(len(curve), 0)

    # ---------- 统计 ----------
    def test_get_stats(self):
        save_products(self.db_path, [
            {"platform": "1688", "product_id": "A1", "title": "X", "price": 10},
        ])
        save_opportunity(self.db_path, {
            "source_platform": "1688", "source_title": "X", "source_price": 10,
            "target_platform": "xianyu", "target_title": "X", "target_price": 20,
            "gross_profit": 10, "net_profit": 10, "roi": 1.0, "confidence": 0.9,
        })
        add_to_blacklist(self.db_path, {"brand": "X"})

        stats = get_stats(self.db_path)
        self.assertEqual(stats["total_products"], 1)
        self.assertEqual(stats["total_opportunities"], 1)
        self.assertEqual(stats["pending_opportunities"], 1)
        self.assertEqual(stats["blacklist_count"], 1)

    # ---------- 关键词池 ----------
    def test_keyword_pool_add_and_get(self):
        added = add_keywords(self.db_path, ["玩具", "手机壳", "收纳盒"], source="seed")
        self.assertEqual(added, 3)
        # 重复添加应被忽略
        added2 = add_keywords(self.db_path, ["玩具", "新品"], source="seed")
        self.assertEqual(added2, 1)

    def test_keyword_pool_next_keywords(self):
        add_keywords(self.db_path, ["a", "b", "c", "d", "e"], source="seed")
        # 全部未扫描，按插入顺序
        kws = get_next_keywords(self.db_path, limit=3)
        self.assertEqual(len(kws), 3)

    def test_keyword_pool_mark_scanned(self):
        add_keywords(self.db_path, ["a", "b"], source="seed")
        mark_keyword_scanned(self.db_path, "a")
        stats = get_keyword_pool_stats(self.db_path)
        self.assertEqual(stats["scanned"], 1)
        self.assertEqual(stats["pending"], 1)
        # 下一批应优先返回未扫描的
        kws = get_next_keywords(self.db_path, limit=10)
        self.assertEqual(kws[0], "b")  # b 未扫描，排前面

    def test_keyword_pool_stats(self):
        add_keywords(self.db_path, ["x", "y", "z"], source="seed")
        stats = get_keyword_pool_stats(self.db_path)
        self.assertEqual(stats["total"], 3)
        self.assertEqual(stats["scanned"], 0)
        self.assertEqual(stats["pending"], 3)


if __name__ == "__main__":
    unittest.main()
