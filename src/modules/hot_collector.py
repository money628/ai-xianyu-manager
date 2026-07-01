"""AI店长 v1.2 - 闲鱼热度采集器

从闲鱼搜索结果中提取热度指标（想要数/浏览数），
排序优先匹配高热度商品。
"""
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def score_hotness(item: Dict[str, Any]) -> float:
    """计算商品热度评分 (0-1)

    权重: 想要数 0.6 + 浏览数 0.3 + 已售数 0.1
    """
    want = int(item.get("want_count", 0) or 0)
    view = int(item.get("view_count", 0) or 0)
    sold = int(item.get("sales_count", 0) or 0)

    # 归一化 (log scale 避免极端值)
    import math
    w_score = min(math.log(want + 1) / math.log(1000), 1.0) if want > 0 else 0
    v_score = min(math.log(view + 1) / math.log(10000), 1.0) if view > 0 else 0
    s_score = min(math.log(sold + 1) / math.log(5000), 1.0) if sold > 0 else 0

    return round(w_score * 0.6 + v_score * 0.3 + s_score * 0.1, 3)


def rank_by_hotness(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """按热度降序排列"""
    for item in items:
        item["hotness"] = score_hotness(item)
    return sorted(items, key=lambda x: x.get("hotness", 0), reverse=True)


def filter_hot_items(items: List[Dict[str, Any]], min_hotness: float = 0.0,
                     min_want: int = 0) -> List[Dict[str, Any]]:
    """过滤出热门商品"""
    result = []
    for item in items:
        want = int(item.get("want_count", 0) or 0)
        hot = item.get("hotness", score_hotness(item))
        if hot >= min_hotness and want >= min_want:
            item["hotness"] = hot
            result.append(item)
    return sorted(result, key=lambda x: x["hotness"], reverse=True)


__all__ = ["score_hotness", "rank_by_hotness", "filter_hot_items"]
