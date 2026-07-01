"""AI店长 v1.2 - 跨平台价差计算器

核心业务逻辑：计算从采购平台到出售平台的净利润和 ROI。

价格公式（国内）：
  净利润 = 售价 × (1 - 平台费率) - 进价 - 国内运费
  ROI = 净利润 / (进价 + 国内运费) × 100%

v1.2 新增：config.ini [arbitrage] 权重和阈值驱动评分
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ArbitrageItem:
    """单条套利机会"""
    buy_platform: str = ""
    sell_platform: str = ""
    buy_title: str = ""
    sell_title: str = ""
    buy_product_id: str = ""
    sell_product_id: str = ""
    buy_price: float = 0.0
    sell_price: float = 0.0
    shipping_cost: float = 3.0
    platform_fee_rate: float = 0.016
    ad_cost: float = 0.0
    return_reserve_rate: float = 0.0
    profit: float = 0.0
    roi: float = 0.0
    confidence: float = 0.0
    score: float = 0.0  # v1.2: 加权综合评分
    buy_url: str = ""
    sell_url: str = ""
    buy_sales: int = 0
    sell_sales: int = 0

    @property
    def total_cost(self) -> float:
        return self.buy_price + self.shipping_cost

    @property
    def seller_revenue(self) -> float:
        return self.sell_price * (1 - self.platform_fee_rate)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "buy_platform": self.buy_platform,
            "sell_platform": self.sell_platform,
            "buy_title": self.buy_title,
            "sell_title": self.sell_title,
            "buy_product_id": self.buy_product_id,
            "sell_product_id": self.sell_product_id,
            "buy_price": self.buy_price,
            "sell_price": self.sell_price,
            "shipping_cost": self.shipping_cost,
            "platform_fee_rate": self.platform_fee_rate,
            "ad_cost": self.ad_cost,
            "profit": round(self.profit, 2),
            "roi": round(self.roi, 2),
            "confidence": round(self.confidence, 3),
            "score": round(self.score, 3),
            "buy_url": self.buy_url,
            "sell_url": self.sell_url,
            "buy_sales": self.buy_sales,
            "sell_sales": self.sell_sales,
            "total_cost": round(self.total_cost, 2),
            "seller_revenue": round(self.seller_revenue, 2),
        }


def _get_arbitrage_config(config: Dict[str, Any] = None) -> Dict[str, Any]:
    """从配置中提取套利参数，缺失时使用默认值"""
    if config is None:
        return {
            "weight_roi": 0.5,
            "weight_sales": 0.3,
            "weight_confidence": 0.2,
            "min_roi": 15.0,  # 不传 config 时用宽松默认（向后兼容）
            "min_confidence": 0.0,  # 不传 config 时不校验置信度
        }
    arb = config.get("arbitrage", {})
    return {
        "weight_roi": float(arb.get("weight_roi", 0.5) or 0.5),
        "weight_sales": float(arb.get("weight_sales", 0.3) or 0.3),
        "weight_confidence": float(arb.get("weight_confidence", 0.2) or 0.2),
        "min_roi": float(arb.get("min_roi_threshold", 0.15) or 0.15) * 100,
        "min_confidence": float(arb.get("min_confidence", 0.6) or 0.6),
    }


def _compute_score(roi: float, sales: int, confidence: float, weights: dict) -> float:
    """计算加权综合评分 (0-1)"""
    roi_norm = min(roi / 200, 1.0)  # 200% ROI 为满分
    sales_norm = min(sales / 10000, 1.0)  # 1万销量为满分
    return (
        weights["weight_roi"] * roi_norm +
        weights["weight_sales"] * sales_norm +
        weights["weight_confidence"] * confidence
    )


def calculate_arbitrage(
    buy_item: Dict[str, Any],
    sell_item: Dict[str, Any],
    match_confidence: float = 0.0,
    shipping_cost: float = 3.0,
    platform_fee_rate: float = 0.016,
    min_roi: float = None,
    config: Dict[str, Any] = None,
) -> Optional[ArbitrageItem]:
    """计算单对商品的套利空间

    Args:
        buy_item: 采购平台商品字典
        sell_item: 出售平台商品字典
        match_confidence: 标题匹配置信度
        shipping_cost: 国内运费
        platform_fee_rate: 出售平台手续费率
        min_roi: 最低 ROI 阈值（覆盖 config 中的值）
        config: 全局配置字典（优先使用其中的权重/阈值）

    Returns:
        ArbitrageItem 或 None（不满足条件）
    """
    buy_price = buy_item.get("price", 0)
    sell_price = sell_item.get("price", 0)

    if buy_price <= 0 or sell_price <= 0:
        return None

    total_cost = buy_price + shipping_cost
    seller_revenue = sell_price * (1 - platform_fee_rate)
    profit = seller_revenue - total_cost
    roi = (profit / total_cost * 100) if total_cost > 0 else 0

    # 从 config 获取阈值和权重
    ac = _get_arbitrage_config(config)
    effective_min_roi = min_roi if min_roi is not None else ac["min_roi"]

    if roi < effective_min_roi:
        return None

    # 置信度不做硬过滤（跨平台相似度天然低，0.15-0.5是正常的）

    # 综合评分
    buy_sales = buy_item.get("sales_count", 0)
    score = _compute_score(roi, buy_sales, match_confidence, {
        "weight_roi": ac["weight_roi"],
        "weight_sales": ac["weight_sales"],
        "weight_confidence": ac["weight_confidence"],
    })

    item = ArbitrageItem(
        buy_platform=buy_item.get("platform", ""),
        sell_platform=sell_item.get("platform", ""),
        buy_title=buy_item.get("title", ""),
        sell_title=sell_item.get("title", ""),
        buy_product_id=buy_item.get("product_id", ""),
        sell_product_id=sell_item.get("product_id", ""),
        buy_price=buy_price,
        sell_price=sell_price,
        shipping_cost=shipping_cost,
        platform_fee_rate=platform_fee_rate,
        profit=profit,
        roi=roi,
        confidence=match_confidence,
        score=score,
        buy_url=buy_item.get("product_url", ""),
        sell_url=sell_item.get("product_url", ""),
        buy_sales=buy_sales,
        sell_sales=sell_item.get("sales_count", 0),
    )
    return item


def scan_cross_platform(
    buy_products: List[Dict[str, Any]],
    sell_products: List[Dict[str, Any]],
    buy_platform: str = "1688",
    sell_platform: str = "xianyu",
    min_roi: float = 20.0,
    shipping_cost: float = 3.0,
    platform_fee_rate: float = 0.016,
) -> List[ArbitrageItem]:
    """扫描两个平台商品列表，找出所有套利机会

    Args:
        buy_products: 采购平台商品列表
        sell_products: 出售平台商品列表
        buy_platform: 采购平台名
        sell_platform: 出售平台名
        min_roi: 最低 ROI 阈值

    Returns:
        按 ROI 降序的套利机会列表
    """
    from .matcher import match_cross_platform

    # 跨平台标题风格差异大，默认用 0.30 阈值
    matches = match_cross_platform(buy_products, sell_products, threshold=0.15)

    results = []
    for item_a, item_b, confidence in matches:
        # 通常 1688 价格低于闲鱼，item_a 是 1688
        arb = calculate_arbitrage(
            buy_item=item_a,
            sell_item=item_b,
            match_confidence=confidence,
            shipping_cost=shipping_cost,
            platform_fee_rate=platform_fee_rate,
            min_roi=min_roi,
        )
        if arb is not None:
            results.append(arb)

    # 按 ROI 降序
    results.sort(key=lambda x: x.roi, reverse=True)
    logger.info("scan %s→%s: %d opportunities (ROI>%.0f%%)",
                buy_platform, sell_platform, len(results), min_roi)
    return results


def format_profit_report(items: List[ArbitrageItem], top_n: int = 10) -> str:
    """格式化利润报告文本"""
    if not items:
        return "未发现符合条件的套利机会。"

    lines = ["📊 跨平台套利机会", "=" * 40, ""]
    for i, item in enumerate(items[:top_n], 1):
        lines.append(f"#{i} ROI: {item.roi:.1f}%")
        lines.append(f"  采购: {item.buy_platform} ¥{item.buy_price:.2f}")
        lines.append(f"  出售: {item.sell_platform} ¥{item.sell_price:.2f}")
        lines.append(f"  净利润: ¥{item.profit:.2f}")
        lines.append(f"  匹配置信度: {item.confidence:.0%}")
        lines.append(f"  采购: {item.buy_title[:30]}...")
        lines.append(f"  出售: {item.sell_title[:30]}...")
        lines.append("")

    lines.append(f"共发现 {len(items)} 个机会，展示 Top{top_n}")
    return "\n".join(lines)


__all__ = [
    "ArbitrageItem",
    "calculate_arbitrage",
    "scan_cross_platform",
    "format_profit_report",
    "_get_arbitrage_config",
    "_compute_score",
]
