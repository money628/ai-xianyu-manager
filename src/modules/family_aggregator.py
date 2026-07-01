"""AI店长 v1.2 - 商品族聚合器

将同一商品的多型号机会聚合为一个 ProductFamily，减少刷屏。

规则:
1. 同 source_item_id / source_url → 同一 family
2. 型号去重 + 聚合统计
3. 分级展示 (A/B/C/D)
"""
import re
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class VariantOpportunity:
    """单个型号的机会"""
    model: str = ""
    cost_price: float = 0.0
    sale_price: float = 0.0
    profit: float = 0.0
    roi: float = 0.0
    match_confidence: float = 0.0
    price_confidence: float = 0.0
    sku_price_confirmed: bool = False
    risk_flags: set = field(default_factory=set)
    status: str = "pending"
    raw_opportunity: dict = field(default_factory=dict)


@dataclass
class ProductFamilyOpportunity:
    """商品族机会"""
    family_id: str = ""
    family_title: str = ""
    normalized_title: str = ""       # 去型号标题
    brand: str = ""
    category: str = ""
    features: set = field(default_factory=set)
    material: str = ""
    source_platform: str = ""
    source_shop: str = ""
    source_item_id: str = ""
    source_url: str = ""
    variants: List[VariantOpportunity] = field(default_factory=list)
    model_count: int = 0
    min_cost_price: float = 0.0
    max_cost_price: float = 0.0
    median_cost_price: float = 0.0
    min_sale_price: float = 0.0
    max_sale_price: float = 0.0
    best_profit: float = 0.0
    median_profit: float = 0.0
    best_roi: float = 0.0
    family_match_confidence: float = 0.0
    family_price_confidence: float = 0.0
    family_grade: str = "D"
    family_risk_flags: set = field(default_factory=set)
    review_status: str = "pending"
    created_at: str = ""
    updated_at: str = ""


_MODEL_PATTERNS = [
    r'iphone\s*\d+\s*(pro|max|plus|mini|air)?\s*(pro|max|plus|mini|air)?',
    r'ipad\s*\d*\s*(pro|air|mini)?\s*(pro|air|mini)?',
    r'\b[a-z]{1,5}\d+[a-z]*(pro|max|plus|ultra|mini|t|s)?',
    r'\d+\s*(pro|max|plus|ultra|mini)',
    r'[xrxs]{2}\s*\d*',
]


def _normalize_title(title: str) -> str:
    """去掉型号词生成归一化标题"""
    result = title.lower()
    for pattern in _MODEL_PATTERNS:
        result = re.sub(pattern, '', result)
    result = re.sub(r'\s+', ' ', result).strip()
    # 清理多余符号
    result = re.sub(r'[，,。.\-—/\\|、]\s*$', '', result)
    return result if result else title


def group_variants_into_families(
    opportunities: List[Dict[str, Any]],
    config: Dict[str, Any] = None
) -> List[ProductFamilyOpportunity]:
    """将机会列表聚合成商品族"""
    families: Dict[str, ProductFamilyOpportunity] = {}

    for opp in opportunities:
        # 聚合键
        item_id = str(opp.get("buy_product_id", opp.get("product_id", "")))
        source_url = opp.get("buy_url", "") or opp.get("product_url", "")
        shop = opp.get("seller_name", opp.get("buy_seller", "")) or opp.get("buy_platform", "")

        if item_id:
            key = f"{opp.get('buy_platform','')}:{item_id}"
        elif source_url:
            key = source_url[:80]
        else:
            title = _normalize_title(opp.get("buy_title", opp.get("title", "")))
            key = f"{shop}:{opp.get('buy_platform','')}:{title[:60]}"

        # 创建或获取 family
        if key not in families:
            from modules.matcher import parse_product_title
            attrs = parse_product_title(opp.get("buy_title", opp.get("title", "")))
            family = ProductFamilyOpportunity(
                family_id=key,
                family_title=opp.get("buy_title", opp.get("title", ""))[:80],
                normalized_title=_normalize_title(opp.get("buy_title", opp.get("title", ""))),
                brand=attrs.product_brand,
                category=attrs.category,
                features=attrs.features,
                material=attrs.material,
                source_platform=opp.get("buy_platform", ""),
                source_shop=shop,
                source_item_id=item_id,
                source_url=source_url,
                created_at=datetime.now().isoformat(),
            )
            families[key] = family

        family = families[key]

        # 添加 variant
        models_found = parse_product_title(
            opp.get("buy_title", opp.get("title", ""))
        ).models

        for model in models_found or ["通用"]:
            # 去重同型号
            if any(v.model == model for v in family.variants):
                continue
            variant = VariantOpportunity(
                model=model,
                cost_price=opp.get("buy_price", 0),
                sale_price=opp.get("sell_price", 0),
                profit=opp.get("profit", 0),
                roi=opp.get("roi", 0),
                match_confidence=opp.get("match_confidence", opp.get("confidence", 0)),
                price_confidence=opp.get("price_confidence", 0.8),
                raw_opportunity=opp,
            )
            family.variants.append(variant)

    # 计算统计 + 分级
    for family in families.values():
        _compute_family_stats(family)
        _assign_family_grade(family)

    return sorted(families.values(),
                  key=lambda x: (_grade_order(x.family_grade), -x.best_roi))


def _compute_family_stats(family: ProductFamilyOpportunity):
    """计算族统计"""
    if not family.variants:
        return
    family.model_count = len(family.variants)

    costs = [v.cost_price for v in family.variants if v.cost_price > 0]
    sales = [v.sale_price for v in family.variants if v.sale_price > 0]
    profits = [v.profit for v in family.variants]
    rois = [v.roi for v in family.variants]
    confs = [v.match_confidence for v in family.variants]
    pconfs = [v.price_confidence for v in family.variants]

    if costs:
        family.min_cost_price = min(costs)
        family.max_cost_price = max(costs)
        family.median_cost_price = sorted(costs)[len(costs)//2]
    if sales:
        family.min_sale_price = min(sales)
        family.max_sale_price = max(sales)
    if profits:
        family.best_profit = max(profits)
        family.median_profit = sorted(profits)[len(profits)//2]
    if rois:
        family.best_roi = max(rois)
    if confs:
        family.family_match_confidence = sum(confs) / len(confs)
    if pconfs:
        family.family_price_confidence = sum(pconfs) / len(pconfs)

    # 风险聚合
    all_risks = set()
    for v in family.variants:
        all_risks.update(v.risk_flags)
    family.family_risk_flags = all_risks

    family.updated_at = datetime.now().isoformat()


_BLOCKING_FLAGS = {"low_price_teaser", "sku_price_uncertain", "price_uncertain"}


def _assign_family_grade(family: ProductFamilyOpportunity):
    """分配家族等级"""
    vcount = family.model_count
    mc = family.family_match_confidence
    pc = family.family_price_confidence
    mp = family.median_profit
    risks = family.family_risk_flags

    if (
        vcount >= 2
        and mc >= 0.55
        and pc >= 0.6
        and mp >= 20
        and not (risks & _BLOCKING_FLAGS)
    ):
        family.family_grade = "A"
    elif vcount >= 1 and mp > 0 and mc >= 0.3:
        family.family_grade = "B"
    elif vcount >= 1:
        family.family_grade = "C"
    else:
        family.family_grade = "D"


def _grade_order(grade: str) -> int:
    return {"A": 0, "B": 1, "C": 2, "D": 3}.get(grade, 4)


def generate_family_publish_draft(family: ProductFamilyOpportunity) -> dict:
    """生成统一标题 + 规格列表的铺货草稿"""
    if family.family_grade not in ("A", "B"):
        return {"status": "REJECTED_LOW_CONFIDENCE", "reason": f"Grade: {family.family_grade}"}
    # 统一标题
    title = family.normalized_title or family.family_title
    title = re.sub(r'适用.+$', '', title).strip()
    # 去掉多余型号后缀
    for pat in [r'\s*[（(][\d\s\w\-\+]+[)）]\s*$', r'\s+[\d]+.*$']:
        title = re.sub(pat, '', title).strip()[:50]

    # 规格列表
    models = [v.model for v in family.variants if v.model]
    if not models:
        models = [v.raw_opportunity.get("buy_title", "")[:20] for v in family.variants]

    spec_lines = "\n".join(f"  {i}. {m}" for i, m in enumerate(models[:15], 1))
    if len(models) > 15:
        spec_lines += f"\n  ...等{len(models)}款"

    desc = (
        f"规格选项（请拍下时备注所需型号）：\n"
        f"{spec_lines}\n\n"
        f"价格范围：¥{family.min_cost_price:.0f}-¥{family.max_cost_price:.0f}"
    )

    draft = {
        "status": "DRAFT_GENERATED",
        "title": title,
        "description": desc,
        "price_range": f"¥{family.min_sale_price:.0f}-¥{family.max_sale_price:.0f}" if family.max_sale_price > family.min_sale_price else f"¥{family.min_sale_price:.0f}",
        "model_count": family.model_count,
        "family_grade": family.family_grade,
    }
    return draft


__all__ = [
    "ProductFamilyOpportunity", "VariantOpportunity",
    "group_variants_into_families",
    "generate_family_publish_draft",
    "_normalize_title",
]
