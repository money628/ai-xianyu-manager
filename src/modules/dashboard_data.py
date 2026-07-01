"""运营仪表盘 — 统计数据聚合"""
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def build_dashboard_data(db, days: int = 30) -> dict:
    """构建仪表盘数据"""
    raw = db.get_dashboard_stats(days)
    data = {
        "today": raw.get("today", {}),
        "week": raw.get("week", {}),
        "month": raw.get("month", {}),
        "avg_roi": round(raw.get("avg_roi", 0), 1),
        "listed_count": raw.get("listed_count", 0),
        "sold_out": raw.get("sold_out", 0),
        "pending_shipping": raw.get("pending_shipping", 0),
        "category_profit": raw.get("category_profit", []),
        "daily_trend": raw.get("daily_trend", []),
    }
    return data
