"""AI店长 v1.2 - 反向找货引擎

闲鱼爆款 → PDD找同款/同类低价 → 差价判断

流程:
1. 闲鱼搜索 → 提取热门商品
2. 每个热门商品提取关键词 → PDD搜索
3. 结构化匹配 → ROI计算
4. 按 (热度 × ROI) 综合排序
"""
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def reverse_source(
    keyword: str,
    xy_items: List[Dict[str, Any]],
    pdd_scraper,
    xy_scraper,
    shipping: float = 3.0,
    fee_rate: float = 0.016,
    config: Dict[str, Any] = None,
    db=None,
    min_hotness: float = 0.05,
    max_xy: int = 10,
) -> List[Dict[str, Any]]:
    """反向找货: 闲鱼热门 → PDD找同款低价

    Args:
        keyword: 搜索关键词
        xy_items: 闲鱼商品列表（已含 price/want_count/view_count）
        pdd_scraper: PDD搜索器
        xy_scraper: 闲鱼搜索器
        shipping: 运费
        fee_rate: 平台费率
        config: 全局配置
        db: 数据库（PDD限流时回退用）
        min_hotness: 最低热度阈值
        max_xy: 最多处理几个闲鱼商品

    Returns:
        套利机会列表，按 (热度 × ROI) 综合得分降序
    """
    from modules.hot_collector import rank_by_hotness, filter_hot_items
    from modules.matcher import bidirectional_scan, extract_search_keywords

    # 1. 按热度排序过滤（min_want=0 因为闲鱼页面上想要数经常不展示）
    hot_items = filter_hot_items(xy_items, min_hotness=min_hotness, min_want=0)
    if not hot_items:
        hot_items = xy_items  # 兜底：全部都用

    hot_items = hot_items[:max_xy]

    # 2. 对每个热门商品做 PDD 反向搜索
    all_opps = []

    for xy_item in hot_items:
        xy_title = xy_item.get("title", "")
        hotness = xy_item.get("hotness", 0)

        # 提取搜索关键词
        search_queries = extract_search_keywords(xy_title, max_queries=3)

        for q in search_queries[:2]:  # 限制每个商品最多2个查询
            try:
                opps = bidirectional_scan(
                    q, pdd_scraper, xy_scraper,
                    shipping, fee_rate,
                    min_roi=None, min_similarity=0.10,
                    config=config, db=db,
                )
                for opp in opps:
                    opp["xy_hotness"] = hotness
                    opp["xy_want_count"] = xy_item.get("want_count", 0)
                    opp["xy_view_count"] = xy_item.get("view_count", 0)
                    # 综合得分 = 热度归一化 × 0.4 + ROI归一化 × 0.6
                    roi = opp.get("roi", 0)
                    opp["hot_roi_score"] = round(
                        min(hotness, 1.0) * 0.4 + min(roi / 500, 1.0) * 0.6, 3
                    )
                all_opps.extend(opps)
            except Exception as e:
                logger.debug("reverse_source sub-query failed [%s]: %s", q, e)

    # 3. 去重 + 按综合得分排序
    seen = set()
    unique_opps = []
    for opp in sorted(all_opps, key=lambda x: x.get("hot_roi_score", 0), reverse=True):
        key = opp.get("buy_product_id", "") + opp.get("sell_product_id", "")
        if key not in seen:
            seen.add(key)
            unique_opps.append(opp)

    logger.info("reverse_source '%s': %d hot items → %d opportunities",
                keyword, len(hot_items), len(unique_opps))
    return unique_opps


__all__ = ["reverse_source"]
