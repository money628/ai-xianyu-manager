"""AI店长 v1.2 - 单次扫描脚本（供 Windows 任务计划调用）

用法：
    python run_scan.py

每次运行：读取关键词池 → 并发扫描 PDD + 闲鱼 → 双向匹配 → 推送高ROI → DB备份 → 退出
"""
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(SCRIPT_DIR, "src"))

LOG_FILE = os.path.join(SCRIPT_DIR, "data", "scan_log.txt")
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8"), logging.StreamHandler()],
)
logger = logging.getLogger("run_scan")


def _scan_keyword(kw: str, cfg: dict, db) -> dict:
    """扫描单个关键词，返回统计"""
    from modules.scrapers import ScraperPddApi, ScraperXianyu
        from modules.matcher import bidirectional_scan, reset_pdd_cache, get_cache_stats

    reset_pdd_cache()  # 每次扫描开始时重置缓存统计
    from modules.pusher import Pusher

    shipping = float(cfg.get("finance", {}).get("domestic_shipping", 3))
    fee_rate = float(cfg.get("finance", {}).get("platform_fee_rate", 0.016))
    pusher = Pusher(cfg)
    result = {"kw": kw, "pdd": 0, "xy": 0, "opps": 0, "pushed": 0}

    pdd_items, xy_items = [], []
    pdd_s = None

    try:
        pdd_s = ScraperPddApi.from_config(cfg)
        pdd_items = pdd_s.fetch(kw, 15)
        db.save_products(pdd_items, "pdd")
        result["pdd"] = len(pdd_items)
    except Exception as e:
        logger.warning("  [%s] PDD 失败: %s", kw, e)

    try:
        xy_s = ScraperXianyu(cfg)
        xy_items = xy_s.fetch(kw, 5)
        db.save_products(xy_items, "xianyu")
        result["xy"] = len(xy_items)
    except Exception as e:
        logger.warning("  [%s] 闲鱼 失败: %s", kw, e)

    if pdd_items and xy_items and pdd_s:
        opps = bidirectional_scan(kw, pdd_s, xy_s, shipping, fee_rate,
                                  min_roi=None, min_similarity=0.12, config=cfg, db=db)
        for d in opps:
            d["status"] = "pending"
            if db.is_blacklisted(title=d.get("buy_title", ""),
                                 seller_name=d.get("buy_seller", "")):
                continue
            db.save_opportunity(d)
            result["opps"] += 1
            logger.info("  [%s] ROI=%.0f%% %.2f->%.2f %s",
                        kw, d.get("roi", 0), d.get("buy_price", 0),
                        d.get("sell_price", 0), d.get("buy_title", "")[:30])
            if d.get("roi", 0) >= 30:
                if pusher.push_opportunity(d):
                    result["pushed"] += 1

    return result


def main():
    start = datetime.now()
    try:
        from config import load_config
        from database import Database
        from modules.discovery import expand_apple_keywords, expand_to_flat_list, get_trending_keywords
        from modules.pusher import Pusher

        logger.info("=" * 50)
        logger.info("AI店长 单次扫描启动 %s", start.strftime("%Y-%m-%d %H:%M"))

        cfg_path = os.path.join(SCRIPT_DIR, "config.ini")
        cfg = load_config(cfg_path).as_dict()
        cfg["push"] = {"smtp_password": cfg.get("push", {}).get("smtp_pass", "")}

        db_path = cfg.get("database", {}).get("path", "data/ai_storekeeper.db")
        db = Database(os.path.join(SCRIPT_DIR, db_path))
        logger.info("数据库已连接: %s", db_path)

        # 关键词
        keywords = db.get_next_keywords(10)
        if not keywords:
            seeds = cfg.get("scanner", {}).get("seed_categories", [])
            logger.info("关键词池空，扩展中...")
            all_kws = expand_to_flat_list(seeds)
            all_kws.extend(expand_apple_keywords())
            all_kws.extend(get_trending_keywords(15))
            db.add_keywords(all_kws, source="auto")
            keywords = db.get_next_keywords(10)

        if not keywords:
            logger.warning("无关键词可扫描")
            return

        # 并发扫描（3 线程，避免 API 限流）
        total_pdd = 0
        total_xy = 0
        total_opps = 0
        total_pushed = 0

        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(_scan_keyword, kw, cfg, db): kw
                       for kw in keywords if kw.strip()}
            for future in as_completed(futures):
                r = future.result()
                total_pdd += r["pdd"]
                total_xy += r["xy"]
                total_opps += r["opps"]
                total_pushed += r["pushed"]
                db.mark_keyword_scanned(r["kw"])

        # 价格快照 + 清理 + 备份
        all_products = db.get_recent_products(limit=500)
        db.save_price_snapshot(all_products)
        db.cleanup_old_data()
        db.backup()

        elapsed = (datetime.now() - start).total_seconds()
        summary = (f"扫描完成: {len(keywords)} 关键词, "
                   f"PDD({total_pdd}) + 闲鱼({total_xy}), "
                   f"{total_opps} 机会, {total_pushed} 推送, "
                   f"耗时 {elapsed:.0f}s")
        logger.info(summary)
        logger.info("=" * 50)

        # 扫描完成推送
        if total_opps > 0 or total_pushed > 0:
            pusher = Pusher(cfg)
            pusher.push("AI店长扫描完成", summary)

    except Exception as e:
        logger.error("扫描异常: %s", e, exc_info=True)
        # 失败通知
        try:
            from config import load_config
            from modules.pusher import Pusher
            cfg_path = os.path.join(SCRIPT_DIR, "config.ini")
            cfg = load_config(cfg_path).as_dict()
            Pusher(cfg).push("AI店长扫描失败", f"错误: {str(e)[:200]}\n\n查看日志: data/scan_log.txt")
        except Exception:
            pass


if __name__ == "__main__":
    main()
