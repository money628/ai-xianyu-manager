"""AI店长 v1.2 - 钉钉 Stream 模式（修复版）"""
import logging
import os
import re
import sys
import threading
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_DIR / "src"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("dingtalk_stream")

_config = None
_db = None
_pusher = None


def _init():
    global _config, _db, _pusher
    from config import load_config
    from database import Database
    from modules.pusher import Pusher
    cfg_path = APP_DIR / "config.ini"
    _config = load_config(str(cfg_path)).as_dict()
    _db = Database(str(APP_DIR / _config.get("database", {}).get("path", "data/ai_storekeeper.db")))
    _pusher = Pusher(_config)


def _reply_via_webhook(content: str):
    _pusher.push_dingtalk("AI店长", content)


def _handle_scan(keyword: str) -> str:
    from modules.scrapers import ScraperPddApi, ScraperXianyu
    from modules.matcher import bidirectional_scan
    shipping = float(_config.get("finance", {}).get("domestic_shipping", 3))
    fee_rate = float(_config.get("finance", {}).get("platform_fee_rate", 0.016))
    pdd_items, xy_items = [], []
    pdd_s = None
    try:
        pdd_s = ScraperPddApi.from_config(_config)
        pdd_items = pdd_s.fetch(keyword, 15)
        _db.save_products(pdd_items, "pdd")
    except Exception as e:
        log.warning("PDD失败: %s", e)
    try:
        xy_s = ScraperXianyu(_config)
        xy_items = xy_s.fetch(keyword, 10)
        _db.save_products(xy_items, "xianyu")
    except Exception as e:
        log.warning("闲鱼失败: %s", e)
    if not pdd_items and not xy_items:
        return f"\"{keyword}\" 未搜到商品"
    if pdd_items and xy_items and pdd_s:
        opps = bidirectional_scan(keyword, pdd_s, xy_s, shipping, fee_rate,
                                  min_roi=None, min_similarity=0.10, config=_config, db=_db)
        for d in opps:
            d["status"] = "pending"
            _db.save_opportunity(d)
        lines = [f"🔍 {keyword}: PDD {len(pdd_items)} | 闲鱼 {len(xy_items)}"]
        if opps:
            lines.append(f"🔥 {len(opps)} 个机会:")
            for o in opps[:3]:
                lines.append(f"  ROI {o.get('roi',0):.0f}% | Y{o.get('buy_price',0):.0f} -> Y{o.get('sell_price',0):.0f} | +Y{o.get('profit',0):.0f}")
        else:
            lines.append("未发现套利机会")
        return "\n".join(lines)
    return f"\"{keyword}\": PDD {len(pdd_items)}, 闲鱼 {len(xy_items)}"


def _handle_report() -> str:
    from modules.reporter import Reporter
    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")
    opps = _db.list_opportunities(limit=100, min_roi=0)
    today_opps = [o for o in opps if (o.get("discovered_at") or "")[:10] == today]
    if not today_opps:
        return "今日暂无新机会"
    reporter = Reporter(_config)
    report = reporter.generate_daily_report(today_opps)
    return reporter.format_daily_text(report)


def _handle_profit() -> str:
    sold = _db.get_sold_stats()
    return f"💰 本月卖出 {sold.get('month_sold',0)}件 Y{sold.get('month_real_profit',0):.2f} | 累计 {sold.get('total_sold',0)}件 Y{sold.get('total_real_profit',0):.2f}"


def _handle_status() -> str:
    try:
        stats = _db.get_stats()
        return f"📊 今日 {stats.get('today_opportunities',0)} 机会 | 待审 {stats.get('pending_count',0)} | 高ROI {stats.get('high_roi_count',0)}"
    except Exception:
        return "状态查询失败"


def parse_command(text: str) -> str:
    text = text.strip()
    for cmd, handler in {
        "扫描": lambda a: _handle_scan(a),
        "报告": lambda a: _handle_report(),
        "利润": lambda a: _handle_profit(),
        "状态": lambda a: _handle_status(),
        "帮助": lambda a: "🤖 命令: 扫描 <词> | 报告 | 利润 | 状态 | 帮助",
    }.items():
        if text.startswith(cmd):
            return handler(text[len(cmd):].strip())
    return "未识别。试试: 帮助"


def main():
    from dingtalk_stream import ChatbotHandler, DingTalkStreamClient, Credential

    _init()
    dingtalk_cfg = _config.get("dingtalk", {})
    app_key = dingtalk_cfg.get("app_key", "")
    app_secret = dingtalk_cfg.get("app_secret", "")

    if not app_key or not app_secret:
        log.error("未配置钉钉凭证")
        return

    class BotHandler(ChatbotHandler):
        async def process(self, incoming):
            try:
                # Debug: 打印消息结构
                log.info("收到消息: %s", str(incoming)[:200])

                text = ""
                try:
                    # 尝试多种方式提取文本
                    if hasattr(incoming, 'text') and incoming.text:
                        text = incoming.text.content if hasattr(incoming.text, 'content') else str(incoming.text)
                except Exception:
                    try:
                        text = incoming.get_text_content() if hasattr(incoming, 'get_text_content') else ""
                    except Exception:
                        pass

                text = re.sub(r"@\S+\s*", "", text).strip()
                log.info("解析内容: %s", text)

                if not text:
                    return

                result = parse_command(text)

                # 回复
                try:
                    incoming.reply_markdown_card(
                        result + "\n\n> ai店长自动推送",
                        incoming, title="AI店长",
                    )
                    log.info("回复成功")
                except Exception as e:
                    log.error("回复失败: %s", e)
                    _reply_via_webhook(result)

            except Exception as e:
                log.error("处理异常: %s", e, exc_info=True)

    credential = Credential(app_key, app_secret)
    client = DingTalkStreamClient(credential)

    # 注册所有可能的机器人消息 topic
    handler = BotHandler()
    for topic in [
        "/v1.0/im/bot/messages/get",
        "/v1.0/robot/messages/receive",
        "/v1.0/robot/groupMessages/query",
        "/v1.0/im/groupChats/messages/receive",
        "/v1.0/ai/bot/messages/query",
    ]:
        client.register_callback_handler(topic, handler)
        log.info("注册 topic: %s", topic)

    log.info("钉钉 Stream 已连接，等待消息...")
    log.info("在群里 @小钉4 发指令即可")
    client.start_forever()


if __name__ == "__main__":
    main()
