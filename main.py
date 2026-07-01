"""AI店长 v1.1 - CLI 入口

命令：
  python main.py scan      立即跑一次自动扫描并按需推送
  python main.py daily     立即生成并推送今日日报
  python main.py schedule  启动定时调度（9:00/21:00 日报 + 实时高 ROI 推送）
  python main.py test      运行 pytest
"""
import argparse
import logging
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from config import load_config
from database import Database


def _setup(cfg):
    log_level = cfg.get("system", {}).get("log_level", "INFO")
    logging.basicConfig(level=log_level,
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    db_path = cfg.get("database", {}).get("path", "data/ai_storekeeper.db")
    abs_db = os.path.join(os.path.dirname(__file__), db_path)
    return Database(abs_db)


def cmd_scan(args):
    cfg = load_config(os.path.join(os.path.dirname(__file__), "config.ini")).as_dict()
    cfg = _normalize_cfg(cfg)
    db = _setup(cfg)

    from modules.scrapers import Scraper1688, ScraperPddApi, ScraperXianyu

    # 关键词来源：命令行指定 > 关键词池 > 种子品类扩展
    if args.keywords:
        keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]
    else:
        keywords = db.get_next_keywords(20)
        if not keywords:
            from modules.discovery import expand_to_flat_list, expand_apple_keywords
            seeds = cfg.get("scanner", {}).get("seed_categories", [])
            logging.info("关键词池为空，正在从 %d 个种子品类扩展...", len(seeds))
            all_kws = expand_to_flat_list(seeds)
            all_kws.extend(expand_apple_keywords())
            db.add_keywords(all_kws, source="suggest")
            keywords = db.get_next_keywords(20)
            logging.info("扩展完成，共 %d 个关键词", len(all_kws))

    min_roi = float(args.min_roi) if args.min_roi else cfg.get("arbitrage", {}).get("min_roi", 20)
    max_items = int(args.max_items) if args.max_items else 20

    run_id = db.start_workflow_run("auto_scan", ["1688", "pdd", "xianyu"])
    total_opps = 0
    pushed = 0

    from modules.pusher import Pusher
    pusher = Pusher(cfg)
    rt_threshold = cfg.get("arbitrage", {}).get("realtime_push_roi_threshold", 30)

    for kw in keywords:
        kw = kw.strip()
        if not kw:
            continue
        logging.info("扫描关键词: %s", kw)
        pdd_items, xy_items = [], []
        if cfg.get("platforms", {}).get("enabled_1688", True):
            s = Scraper1688(cfg)
            items = s.fetch(kw, max_items)
            db.save_products(items, platform="1688")
        if cfg.get("platforms", {}).get("enabled_pdd", True):
            try:
                pdd_s = ScraperPddApi.from_config(cfg)
                pdd_items = pdd_s.fetch(kw, max_items)
            except Exception as e:
                logging.warning("PDD API 失败 (%s)，使用 demo 数据", e)
                pdd_items = [{
                    "platform": "pdd", "product_id": f"demo_pdd_{kw}_{i}",
                    "title": f"{kw} 拼多多{i+1} 特价爆款",
                    "price": round(random.uniform(5, 50), 2),
                    "sales_count": random.randint(100, 10000),
                    "seller_name": f"拼多多旗舰店{i+1}",
                    "product_url": "#", "image_url": "",
                    "region": "", "raw_data": {},
                } for i in range(min(max_items, 12))]
            db.save_products(pdd_items, platform="pdd")
        if cfg.get("platforms", {}).get("enabled_xianyu", True):
            xy_s = ScraperXianyu(cfg)
            xy_items = xy_s.fetch(kw, max_items)
            db.save_products(xy_items, platform="xianyu")

        if pdd_items and xy_items:
            from modules.matcher import bidirectional_scan
            opps = bidirectional_scan(kw, pdd_s, xy_s, min_roi=min_roi,
                                      shipping_cost=float(cfg.get("finance", {}).get("domestic_shipping", 3)),
                                      platform_fee_rate=float(cfg.get("finance", {}).get("platform_fee_rate", 0.016)))
            for d in opps:
                d["status"] = "pending"
                db.save_opportunity(d)
                total_opps += 1
                title = d.get("buy_title", "")
                if db.is_blacklisted(title=title, seller_name=""):
                    continue
                if d.get("roi", 0) >= rt_threshold:
                    if pusher.push_opportunity(d):
                        pushed += 1
                        db.log_push(d.get("id", 0), "realtime",
                                   cfg.get("push", {}).get("method", "email"), "success")

        db.mark_keyword_scanned(kw)

    db.finish_workflow_run(run_id, "success", signals=len(keywords),
                           opportunities=total_opps, pushed=pushed)
    print(f"扫描完成: {len(keywords)} 个关键词, {total_opps} 个机会, 推送 {pushed} 条")


def cmd_daily(args):
    cfg = _normalize_cfg(load_config(os.path.join(os.path.dirname(__file__), "config.ini")).as_dict())
    db = _setup(cfg)
    from modules.reporter import Reporter
    from modules.pusher import Pusher

    opps = db.list_opportunities(limit=200, min_roi=10)
    reporter = Reporter(cfg, output_dir=os.path.join(os.path.dirname(__file__), "outputs", "reports"))
    report = reporter.generate_daily_report(opps)
    text = reporter.format_daily_text(report)

    pusher = Pusher(cfg)
    slot = args.slot or "09:00"
    ok = pusher.push(f"📋 AI店长日报 ({slot})", text)
    print(("日报推送成功" if ok else "日报推送失败（检查配置）"))


def cmd_schedule(args):
    import schedule as sched_mod
    import time as _time
    cfg = _normalize_cfg(load_config(os.path.join(os.path.dirname(__file__), "config.ini")).as_dict())

    report_times = cfg.get("scanner", {}).get("daily_report_times", ["09:00", "21:00"])
    for t in report_times:
        sched_mod.every().day.at(t).do(cmd_daily, argparse.Namespace(slot=t))
    logging.info("调度已启动: 日报 %s", report_times)
    print(f"调度已启动（日报 {report_times}）。Ctrl+C 退出。")
    while True:
        sched_mod.run_pending()
        _time.sleep(30)


def cmd_test(args):
    import subprocess
    subprocess.run([sys.executable, "-m", "pytest", "tests/", "-v"],
                   cwd=os.path.dirname(__file__))


def _normalize_cfg(cfg):
    """与 pages/__init__.py get_config() 一致的键归一化"""
    push = dict(cfg.get("push", {}))
    push.setdefault("serverchan_send_key", push.get("serverchan_sendkey", ""))
    push.setdefault("serverchan_sendkey", push.get("serverchan_send_key", ""))
    push.setdefault("smtp_password", push.get("smtp_pass", ""))
    push.setdefault("smtp_pass", push.get("smtp_password", ""))
    push.setdefault("method", push.get("method", "serverchan"))
    cfg["push"] = push

    fin = dict(cfg.get("finance", {}))
    fin.setdefault("platform_fee_rate", fin.get("xianyu_fee", 0.016))
    cfg["finance"] = fin

    arb = dict(cfg.get("arbitrage", {}))
    arb.setdefault("min_roi", float(arb.get("min_roi_threshold", 0.15)) * 100)
    arb.setdefault("realtime_push_roi_threshold",
                   int(float(cfg.get("scanner", {}).get("realtime_push_threshold", 0.30)) * 100))
    cfg["arbitrage"] = arb
    return cfg


def main():
    parser = argparse.ArgumentParser(prog="AI店长", description="AI店长 v1.1 CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_scan = sub.add_parser("scan", help="立即自动扫描")
    p_scan.add_argument("--keywords", help="逗号分隔关键词")
    p_scan.add_argument("--min-roi", type=float, help="最低 ROI 百分比，如 20 表示 20%%")
    p_scan.add_argument("--max-items", type=int, help="每关键词抓取数量")
    p_scan.set_defaults(func=cmd_scan)

    p_daily = sub.add_parser("daily", help="生成并推送日报")
    p_daily.add_argument("--slot", default="09:00", help="时段标签")
    p_daily.set_defaults(func=cmd_daily)

    p_sched = sub.add_parser("schedule", help="启动定时调度")
    p_sched.set_defaults(func=cmd_schedule)

    p_test = sub.add_parser("test", help="运行 pytest")
    p_test.set_defaults(func=cmd_test)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()