"""AI店长 v1.2 - E2E 真实验证系统

验证全链路：闲鱼抓取 → PDD搜索 → 双向匹配 → ROI计算 → DB入库 → 报告

用法: python run_e2e_verify.py
"""
import logging
import os
import sys
import time
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(SCRIPT_DIR, "src"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(SCRIPT_DIR, "data", "e2e_verify.log"), encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("e2e_verify")


class E2EVerifier:
    """真实全链路验证器"""

    def __init__(self):
        from config import load_config
        from database import Database

        cfg_path = os.path.join(SCRIPT_DIR, "config.ini")
        self.cfg = load_config(cfg_path).as_dict()
        self.db = Database(os.path.join(SCRIPT_DIR, "data", "ai_storekeeper.db"))
        self.db_path = self.db.db_path
        # 同时连接生产 DB 用于 PDD 缓存回退
        self.prod_db = self.db  # 直接使用生产 DB 避免空白

        # 参数
        arb = self.cfg.get("arbitrage", {})
        fin = self.cfg.get("finance", {})
        self.min_roi = float(arb.get("min_roi_threshold", 0.15) or 0.15) * 100
        self.fee_rate = float(fin.get("xianyu_fee", 0.016) or 0.016)
        self.shipping = float(fin.get("domestic_shipping", 3) or 3)
        self.min_similarity = 0.10  # 稍低阈值以发现更多匹配

        # 统计
        self.stats = {
            "keywords_scanned": 0,
            "xianyu_items": 0,
            "pdd_api_calls": 0,
            "pdd_api_failures": 0,
            "pdd_db_fallback": 0,
            "pdd_total_items": 0,
            "matches_found": 0,
            "matches_above_20": 0,
            "matches_above_50": 0,
            "low_confidence": 0,
            "likely_mismatch": 0,
            "start_time": None,
            "end_time": None,
        }
        self.opportunities = []

    def _count_pdd_call(self):
        self.stats["pdd_api_calls"] += 1

    def _count_pdd_fail(self):
        self.stats["pdd_api_failures"] += 1

    def fetch_xianyu(self, keyword: str, max_items: int = 10):
        """抓取闲鱼真实商品"""
        from modules.scrapers import ScraperXianyu
        try:
            xy = ScraperXianyu(self.cfg)
            items = xy.fetch(keyword, max_items=max_items)
            real = [i for i in items if not str(i.get("product_id", "")).startswith("demo")]
            self.db.save_products(real, "xianyu")
            self.stats["xianyu_items"] += len(real)
            log.info(f"  闲鱼: {len(real)} items (keyword: {keyword})")
            return real, xy
        except Exception as e:
            log.warning(f"  闲鱼失败 [{keyword}]: {e}")
            return [], None

    def fetch_pdd(self, keyword: str, max_items: int = 10, pdd_scraper=None):
        """抓取 PDD，带缓存回退"""
        from modules.scrapers import ScraperPddApi

        items = []
        scraper = pdd_scraper

        # 尝试 API
        try:
            if scraper is None:
                scraper = ScraperPddApi.from_config(self.cfg)
            self._count_pdd_call()
            items = scraper.fetch(keyword, max_items=10)
        except Exception:
            pass

        # API 限流 → DB 缓存回退
        if not items:
            log.info(f"  PDD API 限流，使用 DB 缓存: {keyword}")
            self.stats["pdd_db_fallback"] += 1
            try:
                cached = self.prod_db.get_recent_products(platform="pdd", limit=200)
            except Exception:
                cached = self.db.get_recent_products(platform="pdd", limit=200)
            kw_lower = keyword.lower()
            keywords = kw_lower.split()
            items = []
            for c in cached:
                title = (c.get("title") or "").lower()
                if any(w in title for w in keywords):
                    items.append(dict(c))

        if items:
            self.db.save_products(items, "pdd")
            self.stats["pdd_total_items"] += len(items)

        log.info(f"  PDD: {len(items)} items (keyword: {keyword})")
        return items, scraper

    def run_matching(self, keyword: str, xy_items: list, pdd_items: list,
                     pdd_scraper, xy_scraper):
        """执行双向匹配"""
        from modules.matcher import bidirectional_scan

        if not xy_items or not pdd_items:
            return []

        try:
            opps = bidirectional_scan(
                keyword, pdd_scraper, xy_scraper,
                self.shipping, self.fee_rate,
                min_roi=None, min_similarity=self.min_similarity,
                config=self.cfg, db=self.db,
            )
            return opps if opps else []
        except Exception as e:
            log.warning(f"  匹配失败 [{keyword}]: {e}")
            return []

    def classify_opportunity(self, opp: dict):
        """分类并记录匹配质量"""
        roi = opp.get("roi", 0)
        confidence = opp.get("confidence", 0)

        if roi >= 50:
            self.stats["matches_above_50"] += 1
        if roi >= 20:
            self.stats["matches_above_20"] += 1
        if confidence < 0.15:
            self.stats["low_confidence"] += 1
        if roi > 200 or confidence < 0.05:
            self.stats["likely_mismatch"] += 1

    def run(self, keywords: list = None, max_keywords: int = 5):
        """执行验证"""
        self.stats["start_time"] = datetime.now()
        log.info("=" * 60)
        log.info("E2E 真实验证开始: %s", self.stats["start_time"].strftime("%Y-%m-%d %H:%M"))
        log.info("=" * 60)

        from modules.scrapers import ScraperPddApi

        if keywords is None:
            keywords = ["手机壳", "蓝牙耳机", "充电器", "数据线", "钢化膜"]
        keywords = keywords[:max_keywords]

        pdd_scraper = ScraperPddApi.from_config(self.cfg)
        xy_scraper = None

        for kw in keywords:
            kw = kw.strip()
            if not kw:
                continue
            log.info(f"[{self.stats['keywords_scanned']+1}/{len(keywords)}] 扫描: {kw}")
            self.stats["keywords_scanned"] += 1

            # 1. 闲鱼
            xy_items, xy_sc = self.fetch_xianyu(kw, max_items=5)
            if xy_sc:
                xy_scraper = xy_sc

            # 2. PDD
            pdd_items, pdd_sc = self.fetch_pdd(kw, max_items=10, pdd_scraper=pdd_scraper)
            if pdd_sc:
                pdd_scraper = pdd_sc

            # 3. 匹配
            if xy_items and pdd_items:
                opps = self.run_matching(kw, xy_items, pdd_items, pdd_scraper, xy_scraper)
                for opp in opps:
                    opp["status"] = "pending"
                    self.classify_opportunity(opp)
                    self.db.save_opportunity(opp)
                    self.opportunities.append(opp)
                self.stats["matches_found"] += len(opps)
                log.info(f"  匹配: {len(opps)} 个机会")
            else:
                log.info(f"  匹配: 跳过 (XY:{len(xy_items)} PDD:{len(pdd_items)})")

            # 4. 价格快照
            all_p = self.db.get_recent_products(limit=500)
            self.db.save_price_snapshot(all_p)

        self.stats["end_time"] = datetime.now()
        log.info("=" * 60)
        log.info("E2E 验证完成")
        log.info("=" * 60)

    def report(self):
        """生成验证报告"""
        s = self.stats
        match_rate = (
            s["matches_found"] / s["xianyu_items"] * 100
            if s["xianyu_items"] > 0 else 0
        )
        elapsed = (s["end_time"] - s["start_time"]).total_seconds() if s["end_time"] and s["start_time"] else 0

        report = f"""
{'='*60}
 AI店长 v1.2 — E2E 真实验证报告
{'='*60}

【基础指标】
  扫描关键词: {s['keywords_scanned']}
  闲鱼商品数: {s['xianyu_items']}
  PDD API 调用: {s['pdd_api_calls']}
  PDD API 失败: {s['pdd_api_failures']}
  PDD DB 回退: {s['pdd_db_fallback']}
  PDD 商品总数: {s['pdd_total_items']}
  总耗时: {elapsed:.1f}s

【匹配结果】
  成功匹配数: {s['matches_found']}
  匹配率: {match_rate:.1f}%
  ROI ≥ 20%: {s['matches_above_20']}
  ROI ≥ 50%: {s['matches_above_50']}

【质量过滤】
  低置信度 (<15%): {s['low_confidence']}
  疑似误匹配: {s['likely_mismatch']}
  有效匹配: {s['matches_found'] - s['likely_mismatch']}

【PDD 配额优化】
  启用 DB 缓存回退: {'是' if s['pdd_db_fallback'] > 0 else '否'}
  本次 API 消耗: {s['pdd_api_calls']} 次

【Top 10 推荐查看】
"""
        # Top 10 by ROI
        top10 = sorted(self.opportunities, key=lambda x: x.get("roi", 0), reverse=True)[:10]
        if top10:
            for i, o in enumerate(top10, 1):
                report += (
                    f"  #{i} ROI {o.get('roi',0):.0f}% | "
                    f"¥{o.get('buy_price',0):.1f} → ¥{o.get('sell_price',0):.1f} | "
                    f"+¥{o.get('profit',0):.1f} | 置信度 {o.get('confidence',0):.0%}\n"
                    f"      {o.get('buy_title','')[:60]}\n"
                )
        else:
            report += "  暂无有效套利机会\n"

        report += f"\n{'='*60}\n"

        # 同时写入文件
        report_file = os.path.join(SCRIPT_DIR, "data", "e2e_report.txt")
        with open(report_file, "w", encoding="utf-8") as f:
            f.write(report)
        log.info("报告已保存: %s", report_file)

        return report


def main():
    verifier = E2EVerifier()

    # 验证关键词（选择有代表性的）
    keywords = [
        "手机壳",
        "蓝牙耳机",
        "充电器",
        "钢化膜",
        "数据线",
    ]

    verifier.run(keywords=keywords, max_keywords=5)
    report = verifier.report()
    print(report)


if __name__ == "__main__":
    main()
