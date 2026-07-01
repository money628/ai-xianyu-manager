"""AI店长 v1.1 - 端到端流程测试

模拟雷达页面的完整流程：
合成商品 → 保存DB → 跨平台匹配 → 价差计算 → 保存机会 → 统计 → 黑名单过滤
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from database import Database
from modules.matcher import match_cross_platform, find_best_match
from modules.arbitrage import calculate_arbitrage, scan_cross_platform


# ---------- 合成 1688 / 闲鱼 商品数据 ----------
def _fake_1688_items():
    return [
        {"platform": "1688", "product_id": "f1", "title": "儿童益智积木拼装城堡玩具",
         "price": 12.0, "sales_count": 500, "seller_name": "积木工厂A",
         "product_url": "https://1688/x", "image_url": "", "region": "浙江"},
        {"platform": "1688", "product_id": "f2", "title": "男士运动跑鞋轻便透气学生鞋",
         "price": 45.0, "sales_count": 200, "seller_name": "鞋厂B",
         "product_url": "https://1688/y", "image_url": "", "region": "福建"},
        {"platform": "1688", "product_id": "f3", "title": "毛绒玩具熊大号可爱公仔",
         "price": 18.0, "sales_count": 800, "seller_name": "玩具C",
         "product_url": "https://1688/z", "image_url": "", "region": "广东"},
    ]


def _fake_xianyu_items():
    return [
        {"platform": "xianyu", "product_id": "x1", "title": "益智儿童积木拼装城堡大号",
         "price": 48.0, "sales_count": 12, "seller_name": "宝妈D",
         "product_url": "https://xianyu/x1", "image_url": "", "region": ""},
        {"platform": "xianyu", "product_id": "x2", "title": "运动跑鞋男轻便透气学生鞋",
         "price": 89.0, "sales_count": 5, "seller_name": "鞋友E",
         "product_url": "https://xianyu/x2", "image_url": "", "region": ""},
        {"platform": "xianyu", "product_id": "x3", "title": "无关品 拖把布",  # 不应被匹配
         "price": 30.0, "sales_count": 2, "seller_name": "杂货F",
         "product_url": "https://xianyu/x3", "image_url": "", "region": ""},
    ]


class TestEndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "e2e.db")
        self.db = Database(self.db_path)

    def test_full_pipeline(self):
        buy = _fake_1688_items()
        sell = _fake_xianyu_items()

        # 1. 保存商品
        n_buy = self.db.save_products(buy, platform="1688")
        n_sell = self.db.save_products(sell, platform="xianyu")
        self.assertGreater(n_buy, 0)
        self.assertGreater(n_sell, 0)

        # 2. 跨平台匹配 + 价差计算
        opps = scan_cross_platform(buy, sell, buy_platform="1688",
                                   sell_platform="xianyu",
                                   min_roi=10, shipping_cost=3.0,
                                   platform_fee_rate=0.016)
        self.assertGreaterEqual(len(opps), 1, "应至少匹配到一个套利机会")

        # 3. 保存机会到 DB
        for opp in opps:
            opp_dict = opp.to_dict()
            opp_dict["status"] = "pending"
            self.db.save_opportunity(opp_dict)

        # 4. 验证统计
        stats = self.db.get_stats()
        self.assertGreaterEqual(stats["total_opportunities"], 1)
        self.assertGreaterEqual(stats["today_opportunities"], 1)
        self.assertGreater(stats["avg_roi"], 0)

        # 5. 列出待审核
        pend = self.db.list_opportunities(status="pending", limit=50)
        self.assertGreaterEqual(len(pend), 1)
        # 验证 buy_*/sell_* 别名存在（UI 用）
        first = pend[0]
        self.assertIn("buy_platform", first)
        self.assertIn("buy_title", first)
        self.assertEqual(first["status"], "pending")

        # 6. 审批：通过一条
        self.db.update_opportunity_status(first["id"], "approved")
        approved = self.db.list_opportunities(status="approved", limit=50)
        self.assertEqual(len(approved), 1)

        # 7. 黑名单过滤：拉黑卖家"杂货F" 验证 is_blacklisted
        self.db.add_blacklist("seller", "杂货F", "测试")
        self.assertTrue(self.db.is_blacklisted(seller_name="杂货F"))
        self.assertFalse(self.db.is_blacklisted(seller_name="不存在"))

        # 8. 关键词黑名单
        self.db.add_blacklist("keyword", "拖把", "不感兴趣")
        self.assertTrue(self.db.is_blacklisted(title="精品拖把布"))
        self.assertFalse(self.db.is_blacklisted(title="积木城堡"))

        # 9. 机会 ROI 排序：确认有 ROI>=20 的项
        high = [o for o in pend if o["roi"] >= 20]
        self.assertGreaterEqual(len(high), 1)

    def test_price_curve_flow(self):
        """价格快照 + 10 天曲线"""
        items = _fake_1688_items()
        self.db.save_price_snapshot(items)
        curve = self.db.get_price_curve("1688", "f1", days=10)
        self.assertGreaterEqual(len(curve), 1)
        self.assertEqual(curve[0]["platform"] if "platform" in curve[0] else True, True)

    def test_workflow_run_lifecycle_e2e(self):
        run_id = self.db.start_workflow_run("auto_scan", ["1688", "xianyu"])
        self.db.finish_workflow_run(run_id, "success", signals=3, opportunities=2, pushed=1)
        stats = self.db.get_stats()
        self.assertGreaterEqual(stats["runs_count"], 1)


if __name__ == "__main__":
    unittest.main()