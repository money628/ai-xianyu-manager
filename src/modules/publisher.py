"""AI店长 v1.2 - 合规半自动铺货助手

将"一键铺货"降级为草稿生成 + 人工确认 + 手动发布流程。
Playwright 自动填表默认关闭，仅在用户确认后作为实验性辅助使用。

原则：
1. 永远不自动点击发布按钮
2. 默认生成草稿，用户手动去闲鱼发布
3. 合规检查不通过的不允许进入发布状态
4. 频率保护防止过度操作
"""
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_APP_DIR = Path(__file__).resolve().parent.parent.parent
_PUBLISH_LOG = _APP_DIR / "data" / "publish_log.jsonl"

# 频率限制
MAX_DRAFTS_PER_DAY = 10
MAX_PUBLISHED_PER_DAY = 3
MIN_INTERVAL_MINUTES = 30


@dataclass
class PublishDraft:
    """铺货草稿"""
    source_item_id: str = ""
    title: str = ""
    price: float = 0.0
    description: str = ""
    images: list = field(default_factory=list)
    category: str = ""
    condition: str = "全新未使用"
    shipping_note: str = "包邮 48h内发货"

    # 来源
    buy_platform: str = ""
    buy_price: float = 0.0
    buy_url: str = ""
    sell_platform: str = "xianyu"

    # 置信度
    match_confidence: float = 0.0
    price_confidence: float = 0.0
    roi: float = 0.0
    profit: float = 0.0

    # 风险与合规
    risk_flags: set = field(default_factory=set)
    compliance_flags: set = field(default_factory=set)

    # 状态
    publish_status: str = "FOUND"
    created_at: str = ""
    updated_at: str = ""


# ── 频率保护 ──

def _get_today_logs() -> List[dict]:
    """读取今天的操作日志"""
    if not _PUBLISH_LOG.exists():
        return []
    today = date.today().isoformat()
    logs = []
    with open(_PUBLISH_LOG, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if entry.get("timestamp", "")[:10] == today:
                    logs.append(entry)
            except json.JSONDecodeError:
                continue
    return logs


def _append_log(entry: dict):
    """追加日志"""
    os.makedirs(_PUBLISH_LOG.parent, exist_ok=True)
    with open(_PUBLISH_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def check_rate_limit() -> tuple:
    """检查频率限制。返回 (allowed: bool, reason: str, today_drafts: int, today_published: int)"""
    logs = _get_today_logs()
    drafts = [l for l in logs if l.get("action") == "draft_generated"]
    published = [l for l in logs if l.get("action") == "marked_published"]

    if len(drafts) >= MAX_DRAFTS_PER_DAY:
        return False, f"今日草稿已达上限({MAX_DRAFTS_PER_DAY})", len(drafts), len(published)

    if len(published) >= MAX_PUBLISHED_PER_DAY:
        return False, f"今日发布已达上限({MAX_PUBLISHED_PER_DAY})", len(drafts), len(published)

    # 最近一次发布时间
    if published:
        last = published[-1]
        last_time = datetime.fromisoformat(last["timestamp"])
        elapsed = (datetime.now() - last_time).total_seconds() / 60
        if elapsed < MIN_INTERVAL_MINUTES:
            remaining = int(MIN_INTERVAL_MINUTES - elapsed)
            return False, f"距离上次发布仅{int(elapsed)}分钟，需等待{remaining}分钟", len(drafts), len(published)

    return True, "", len(drafts), len(published)


# ── 草稿生成 ──

def generate_publish_draft(opportunity: dict) -> PublishDraft:
    """根据套利机会生成铺货草稿"""
    draft = PublishDraft()
    draft.source_item_id = str(opportunity.get("id", opportunity.get("buy_product_id", "")))
    draft.created_at = datetime.now().isoformat()
    draft.updated_at = draft.created_at

    # 标题
    sell_title = opportunity.get("sell_title") or opportunity.get("buy_title") or ""
    draft.title = _build_listing_title(sell_title)

    # 价格
    draft.price = opportunity.get("sell_price", 0)
    draft.buy_price = opportunity.get("buy_price", 0)
    draft.profit = opportunity.get("profit", 0)
    draft.roi = opportunity.get("roi", 0)

    # 描述
    draft.description = _build_listing_description(opportunity)

    # AI 增强：一次调用同时生成标题+描述（节省 50% token）
    try:
        from modules.ai_service import _call
        buy_title = opportunity.get('buy_title', '') or ''
        info = f"{buy_title} 进价{opportunity.get('buy_price',0)} 售价{draft.price}"
        result = _call(
            f"为闲鱼商品生成标题和描述。第一行标题(20-30字)，空一行后写描述(100-200字含规格/发货/售后)。不用emoji。\n商品：{info}",
            "你是闲鱼卖家，口语化。", 0.5
        )
        if result and "\n\n" in result:
            parts = result.split("\n\n", 1)
            if len(parts[0]) > 5: draft.title = parts[0].strip()[:60]
            if len(parts[1]) > 20: draft.description = parts[1].strip()
        elif result and len(result) > 10:
            draft.title = result.strip()[:60]
    except Exception:
        pass
    draft.price = opportunity.get("sell_price", 0)
    draft.buy_price = opportunity.get("buy_price", 0)
    draft.profit = opportunity.get("profit", 0)
    draft.roi = opportunity.get("roi", 0)

    # 描述
    draft.description = _build_listing_description(opportunity)

    # 图片
    sell_img = opportunity.get("sell_image", "")
    buy_img = opportunity.get("buy_image", "")
    if sell_img:
        draft.images.append(sell_img)
    if buy_img:
        draft.images.append(buy_img)

    # 平台
    draft.buy_platform = opportunity.get("buy_platform", "")
    draft.buy_url = opportunity.get("buy_url", "") or opportunity.get("product_url", "")

    # 品类
    if "膜" in draft.title:
        draft.category = "screen_protector"
    elif "壳" in draft.title or "套" in draft.title:
        draft.category = "phone_case"
    elif "线" in draft.title:
        draft.category = "cable"
    elif "充电" in draft.title or "电器" in draft.title:
        draft.category = "charger"
    elif "耳机" in draft.title:
        draft.category = "earphone"

    # 置信度
    draft.match_confidence = opportunity.get("match_confidence", opportunity.get("confidence", 0))
    draft.price_confidence = opportunity.get("price_confidence", 0.8)

    # 风险标记
    _assess_risks(draft, opportunity)

    # 合规标记
    _check_compliance(draft)

    # 决定初始状态
    _decide_status(draft)

    # 日志
    _append_log({
        "draft_id": draft.source_item_id,
        "source_item_id": draft.source_item_id,
        "action": "draft_generated",
        "timestamp": draft.created_at,
        "status": draft.publish_status,
        "risk_flags": list(draft.risk_flags),
    })

    return draft


def _build_listing_title(sell_title: str) -> str:
    """生成闲鱼标题"""
    if not sell_title:
        return ""
    # 删除明显不合适的词
    for word in ["全新未拆封", "包邮", "正品保证"]:
        sell_title = sell_title.replace(word, "")
    sell_title = sell_title.strip()[:60]
    return sell_title


def _build_listing_description(opp: dict) -> str:
    """生成闲鱼描述"""
    title = opp.get("sell_title") or opp.get("buy_title", "") or ""
    price = opp.get("sell_price", 0)
    profit = opp.get("profit", 0)
    buy_price = opp.get("buy_price", 0)
    platform = opp.get("buy_platform", "")

    desc = f"📦 {title[:50]}\n\n"
    desc += f"全新，包装完好\n"
    if buy_price > 0:
        desc += f"官方正品，品质保障\n"
    desc += f"包邮速发\n"
    desc += f"-\n"
    desc += f"#好物推荐 #数码好物"
    return desc


def _assess_risks(draft: PublishDraft, opp: dict):
    """评估风险标记"""
    # 图片风险
    if not draft.images:
        draft.risk_flags.add("image_source_uncertain")

    # 价格风险
    pdd_price = opp.get("buy_price", 0)
    if pdd_price < 1.0:
        draft.risk_flags.add("low_price_teaser")
    if opp.get("sku_price_uncertain"):
        draft.risk_flags.add("sku_price_uncertain")

    # 数量/规格不确定
    if "多规格" in (opp.get("buy_title", "") or ""):
        draft.risk_flags.add("spec_uncertain")

    # 价格不确定
    if draft.price_confidence < 0.5:
        draft.risk_flags.add("price_uncertain")

    # 匹配不确定
    if draft.match_confidence < 0.4:
        draft.risk_flags.add("match_uncertain")


def _check_compliance(draft: PublishDraft):
    """合规检查"""
    flags = draft.compliance_flags

    # 缺少型号
    from modules.matcher import parse_product_title
    attrs = parse_product_title(draft.title)
    if not attrs.models:
        flags.add("missing_model")

    # 缺少规格
    if draft.category and not attrs.features:
        flags.add("missing_spec")

    # 价格问题
    if draft.price_confidence < 0.4:
        flags.add("low_price_confidence")

    # 匹配问题
    if draft.match_confidence < 0.3:
        flags.add("low_match_confidence")

    # 图片问题
    if "image_source_uncertain" in draft.risk_flags:
        flags.add("missing_image")

    # 发货时效
    if not draft.shipping_note:
        flags.add("missing_shipping_info")

    # 疑似违禁品类
    _RESTRICTED_KEYWORDS = ["药品", "食品", "化妆品", "医疗器械", "虚拟", "服务"]
    for kw in _RESTRICTED_KEYWORDS:
        if kw in draft.title:
            flags.add("restricted_category")
            break


def _decide_status(draft: PublishDraft):
    """根据风险和合规决定初始状态"""
    flags = draft.compliance_flags

    # 严重问题 → NEEDS_REVIEW
    severe = {"low_match_confidence", "low_price_confidence", "restricted_category"}
    if severe & flags:
        draft.publish_status = "NEEDS_REVIEW"
        return

    # 中等风险 → 可生成草稿
    if flags:
        draft.publish_status = "DRAFT_GENERATED"
        return

    draft.publish_status = "DRAFT_GENERATED"


# ── 状态管理 ──

def mark_published(draft: PublishDraft) -> bool:
    """标记为已手动发布（带频率保护）"""
    allowed, reason, _, _ = check_rate_limit()
    if not allowed:
        logger.warning("rate limit: %s", reason)
        return False

    draft.publish_status = "MANUALLY_PUBLISHED"
    draft.updated_at = datetime.now().isoformat()

    _append_log({
        "draft_id": draft.source_item_id,
        "source_item_id": draft.source_item_id,
        "action": "marked_published",
        "timestamp": draft.updated_at,
        "user_confirmed": True,
        "status": draft.publish_status,
        "risk_flags": list(draft.risk_flags),
    })
    return True


def mark_abandoned(draft: PublishDraft, reason: str = ""):
    """标记放弃"""
    draft.publish_status = "ARCHIVED"
    draft.updated_at = datetime.now().isoformat()
    _append_log({
        "draft_id": draft.source_item_id,
        "source_item_id": draft.source_item_id,
        "action": "marked_abandoned",
        "timestamp": draft.updated_at,
        "reason": reason,
        "status": draft.publish_status,
    })


def reject_draft(draft: PublishDraft, reason: str):
    """拒绝草稿"""
    if "price" in reason.lower():
        draft.publish_status = "REJECTED_PRICE_UNCERTAIN"
    elif "compliance" in reason.lower():
        draft.publish_status = "REJECTED_COMPLIANCE_RISK"
    elif "image" in reason.lower():
        draft.publish_status = "REJECTED_IMAGE_RISK"
    elif "confidence" in reason.lower() or "match" in reason.lower():
        draft.publish_status = "REJECTED_LOW_CONFIDENCE"
    else:
        draft.publish_status = "ARCHIVED"

    draft.updated_at = datetime.now().isoformat()
    _append_log({
        "draft_id": draft.source_item_id,
        "source_item_id": draft.source_item_id,
        "action": "rejected",
        "timestamp": draft.updated_at,
        "reason": reason,
        "status": draft.publish_status,
    })


# ── 统计 ──

def get_publish_stats() -> dict:
    """获取今日铺货统计"""
    logs = _get_today_logs()
    return {
        "drafts_today": len([l for l in logs if l.get("action") == "draft_generated"]),
        "published_today": len([l for l in logs if l.get("action") == "marked_published"]),
        "max_drafts": MAX_DRAFTS_PER_DAY,
        "max_published": MAX_PUBLISHED_PER_DAY,
        "min_interval": MIN_INTERVAL_MINUTES,
    }


# ── 复制辅助 ──

def get_copy_text(draft: PublishDraft) -> dict:
    """获取各字段的复制文本"""
    return {
        "title": draft.title,
        "price": f"¥{draft.price:.2f}",
        "description": draft.description,
        "all": f"{draft.title}\n\n{draft.description}\n\n售价: ¥{draft.price:.2f}\n成色: {draft.condition}\n{draft.shipping_note}",
    }


__all__ = [
    "PublishDraft",
    "generate_publish_draft",
    "mark_published",
    "mark_abandoned",
    "reject_draft",
    "check_rate_limit",
    "get_publish_stats",
    "get_copy_text",
    "_check_compliance",
]
