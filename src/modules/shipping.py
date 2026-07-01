"""发货 SOP — 半自动流程"""
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

SHIPPING_STATUSES = [
    "待填地址",
    "待下单",
    "已下单PDD",
    "待发货",
    "已发货",
    "已完成",
    "售后中",
    "已取消",
]


def build_pdd_order_note(order: dict) -> str:
    """生成 PDD 下单备注"""
    return (
        f"收件人：{order.get('buyer_name','')}\n"
        f"电话：{order.get('buyer_phone','')}\n"
        f"地址：{order.get('buyer_address','')}\n"
        f"商品：{order.get('pdd_goods_url','')}\n"
        f"SKU：{order.get('pdd_sku','')}\n"
        f"闲鱼订单号：{order.get('xianyu_order_no','')}\n"
        f"备注：{order.get('remark','')}"
    )


def create_from_draft(draft, opportunity: dict, buyer_name: str = "",
                       buyer_phone: str = "", buyer_address: str = "") -> dict:
    """从铺货草稿创建发货订单"""
    order = {
        "draft_id": getattr(draft, "source_item_id", "") or str(opportunity.get("id", "")),
        "product_family_id": opportunity.get("product_family_id", ""),
        "xianyu_order_no": "",
        "buyer_name": buyer_name,
        "buyer_phone": buyer_phone,
        "buyer_address": buyer_address,
        "pdd_goods_url": opportunity.get("buy_url", "") or opportunity.get("product_url", ""),
        "pdd_sku": opportunity.get("pdd_sku", ""),
        "pdd_order_no": "",
        "cost_price": float(opportunity.get("buy_price", 0)),
        "sale_price": float(opportunity.get("sell_price", 0)),
        "profit": float(opportunity.get("profit", 0)),
        "shipping_status": "待填地址",
        "tracking_no": "",
        "tracking_company": "",
        "remark": "",
    }
    return order


def update_status(order_id: int, new_status: str, db) -> bool:
    """更新订单状态（带校验）"""
    if new_status not in SHIPPING_STATUSES:
        logger.warning("Invalid shipping status: %s", new_status)
        return False
    db.update_shipping_order(order_id, {"shipping_status": new_status})
    logger.info("Shipping order %s -> %s", order_id, new_status)
    return True
