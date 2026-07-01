"""AI店长 v1.2 - 价格预警模块

追踪商品价格变化，发现降价机会并推送。

逻辑：
1. 从 price_history 查询有至少 2 条快照的商品
2. 对比最新价格和上一次价格
3. 降价超过阈值则生成预警
"""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def scan_price_drops(db, days: int = 7, drop_threshold: float = 0.10, min_price: float = 1.0) -> List[Dict[str, Any]]:
    """扫描最近 N 天内降价超过阈值的商品

    Args:
        db: Database 实例
        days: 回溯天数
        drop_threshold: 降价比例阈值（如 0.10 = 10%）
        min_price: 最低价格，低于此价不预警

    Returns:
        [{product_id, platform, title, old_price, new_price, drop_pct, drop_amount}]
    """
    import sqlite3
    from pathlib import Path

    alerts = []
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    try:
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row

        # 查询有 ≥2 条快照的商品
        rows = conn.execute("""
            SELECT platform, product_id, title,
                   MAX(price) as max_price,
                   MIN(price) as min_price,
                   FIRST_VALUE(price) OVER w AS first_price,
                   LAST_VALUE(price) OVER w AS last_price
            FROM price_history
            WHERE snapshot_date >= ?
            GROUP BY platform, product_id
            HAVING COUNT(*) >= 2 AND MIN(price) > ?
            WINDOW w AS (PARTITION BY platform, product_id ORDER BY snapshot_date
                         ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING)
        """, (cutoff, min_price))
    except Exception:
        # 降级：不用窗口函数
        rows = conn.execute("""
            SELECT platform, product_id, title,
                   MAX(price) as max_price, MIN(price) as min_price
            FROM price_history
            WHERE snapshot_date >= ?
            GROUP BY platform, product_id
            HAVING COUNT(*) >= 2 AND MIN(price) > ?
        """, (cutoff, min_price))

    for row in rows:
        # 获取该商品的最新和上一次价格
        curve = db.get_price_curve(row["platform"], row["product_id"], days=days)
        if len(curve) < 2:
            continue

        latest = curve[0]["price"]
        prev = curve[1]["price"]

        if prev <= 0 or latest <= 0 or latest >= prev:
            continue

        drop_pct = (prev - latest) / prev
        if drop_pct < drop_threshold:
            continue

        alerts.append({
            "product_id": row["product_id"],
            "platform": row["platform"],
            "title": row["title"],
            "old_price": round(prev, 2),
            "new_price": round(latest, 2),
            "drop_amount": round(prev - latest, 2),
            "drop_pct": round(drop_pct * 100, 1),
        })

    conn.close()
    alerts.sort(key=lambda x: x["drop_pct"], reverse=True)
    logger.info("price_alert: %d products dropped > %.0f%% in %d days",
                len(alerts), drop_threshold * 100, days)
    return alerts


def format_alert_text(alerts: List[Dict[str, Any]], top: int = 10) -> str:
    """格式化预警为推送文本"""
    if not alerts:
        return "最近无价格预警。商品价格稳定。"

    lines = [f"📉 价格预警 ({len(alerts)} 商品降价)", "=" * 40, ""]
    for i, a in enumerate(alerts[:top], 1):
        lines.append(
            f"#{i} {a['title'][:30]}"
        )
        lines.append(
            f"   {a['platform']} | ¥{a['old_price']:.2f} → ¥{a['new_price']:.2f} "
            f"| 降 {a['drop_pct']:.1f}% (¥{a['drop_amount']:.2f})"
        )
        lines.append("")

    lines.append(f"共 {len(alerts)} 商品降价，展示 Top {min(top, len(alerts))}")
    return "\n".join(lines)


__all__ = ["scan_price_drops", "format_alert_text"]
