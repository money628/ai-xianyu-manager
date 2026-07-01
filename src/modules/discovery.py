"""AI店长 v1.1 - 品类发现模块

从种子品类大类词出发，调淘宝建议 API 扩展为热门子关键词。
免费方案，无需 AK。

数据流：
  种子品类（30 个大类）→ 淘宝建议 API → 每个种子扩展 10-20 个子关键词 → 去重后存入关键词池
"""
import logging
from typing import Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

# 内置 30 个种子品类（大类词）
DEFAULT_SEED_CATEGORIES = [
    "玩具", "手机壳", "收纳盒", "毛绒玩具", "宠物用品",
    "女装", "男装", "童装", "鞋靴", "箱包",
    "数码配件", "家居用品", "厨房用品", "美妆", "护肤",
    "饰品", "文具", "运动户外", "母婴用品", "汽车用品",
    "五金工具", "灯具", "家纺", "内衣", "食品",
    "茶叶", "宠物食品", "办公用品", "乐器", "健身器材",
]

# 淘宝建议 API（公开，无需登录/AK）
SUGGEST_API_URL = "https://suggest.taobao.com/sug"


def _call_suggest_api(keyword: str, timeout: int = 10) -> List[str]:
    """调淘宝建议 API，返回相关关键词列表

    Args:
        keyword: 种子关键词
        timeout: 请求超时（秒）

    Returns:
        关键词列表（不含原始关键词）
    """
    params = {"code": "utf-8", "q": keyword, "area": "c2c"}
    try:
        resp = requests.get(
            SUGGEST_API_URL,
            params=params,
            timeout=timeout,
            proxies={"http": "", "https": ""},  # 不走代理
        )
        resp.raise_for_status()
        data = resp.json()

        results = data.get("result", [])
        keywords = []
        for item in results:
            if isinstance(item, (list, tuple)) and len(item) >= 1:
                kw = str(item[0]).strip()
                if kw and kw != keyword:
                    keywords.append(kw)
            elif isinstance(item, str):
                kw = item.strip()
                if kw and kw != keyword:
                    keywords.append(kw)

        logger.debug("suggest API '%s' → %d keywords", keyword, len(keywords))
        return keywords

    except requests.RequestException as e:
        logger.warning("suggest API failed for '%s': %s", keyword, e)
        return []
    except (ValueError, KeyError, TypeError) as e:
        logger.warning("suggest API parse error for '%s': %s", keyword, e)
        return []


def expand_categories(
    seeds: Optional[List[str]] = None,
    max_per_seed: int = 15,
    timeout: int = 10,
) -> Dict[str, List[str]]:
    """扩展种子品类为子关键词

    Args:
        seeds: 种子品类列表，None 则使用默认 30 个
        max_per_seed: 每个种子最多取几个子关键词
        timeout: API 超时（秒）

    Returns:
        {seed_keyword: [sub_keyword1, sub_keyword2, ...], ...}
    """
    if seeds is None:
        seeds = DEFAULT_SEED_CATEGORIES

    result = {}
    total = 0

    for seed in seeds:
        sub_kws = _call_suggest_api(seed, timeout=timeout)
        # 去重 + 限制数量
        seen = set()
        unique = []
        for kw in sub_kws:
            if kw not in seen and kw != seed:
                seen.add(kw)
                unique.append(kw)
                if len(unique) >= max_per_seed:
                    break

        result[seed] = unique
        total += len(unique)

    logger.info("expanded %d seeds → %d total keywords", len(seeds), total)
    return result


def expand_to_flat_list(
    seeds: Optional[List[str]] = None,
    max_per_seed: int = 15,
    timeout: int = 10,
) -> List[str]:
    """扩展并返回去重后的扁平关键词列表（含种子词本身）"""
    expanded = expand_categories(seeds, max_per_seed, timeout)

    all_kws = set()
    # 先加种子词
    for seed in expanded:
        all_kws.add(seed)
    # 再加扩展词
    for sub_kws in expanded.values():
        for kw in sub_kws:
            all_kws.add(kw)

    return sorted(all_kws)


# ── 苹果生态型号扩展（v1.2 新增）──
# 苹果产品型号多、配件利润高，自动生成型号×配件组合关键词

APPLE_DEVICES = [
    # (设备前缀, 型号列表, 配件类型列表)
    ("iPhone", [
        "11", "11Pro", "11ProMax",
        "12", "12Pro", "12ProMax", "12mini",
        "13", "13Pro", "13ProMax", "13mini",
        "14", "14Pro", "14ProMax", "14Plus",
        "15", "15Pro", "15ProMax", "15Plus",
        "16", "16Pro", "16ProMax", "16Plus",
        "17", "17Pro", "17ProMax", "17Air",
    ], ["手机壳", "钢化膜", "磁吸壳", "透明壳", "硅胶壳", "镜头膜"]),
    ("iPad", [
        "Pro", "Air", "mini6", "mini7",
        "ProM4", "ProM2", "10代", "9代",
    ], ["保护套", "壳", "钢化膜", "键盘"]),
    ("AirPods", [
        "Pro2", "Pro", "3代", "4代", "Max",
    ], ["保护套", "壳", "耳塞", "清洁套装"]),
    ("Apple Watch", [
        "Ultra2", "Ultra", "Series10", "Series9",
        "Series8", "SE2", "SE",
    ], ["表带", "保护壳", "充电底座"]),
    ("MacBook", [
        "Pro16", "Pro14", "Air15", "Air13",
        "ProM4", "ProM3", "AirM3", "AirM2",
    ], ["保护壳", "屏幕膜", "键盘膜", "支架"]),
]

# 苹果品牌通用词
APPLE_BRAND_KEYWORDS = [
    "MagSafe充电器", "MagSafe磁吸", "MagSafe支架",
    "苹果原装数据线", "MFi数据线", "CtoL数据线",
    "苹果20W快充", "苹果充电头", "苹果无线充",
    "AirTag保护套", "AirTag钥匙扣",
    "苹果抛光布", "苹果擦拭布",
    "Casetify手机壳", "Casetify联名",
]


def expand_apple_keywords() -> list:
    """生成苹果生态的型号×配件组合关键词
    
    苹果配件利润空间大（PDD 进价 ¥5-30，闲鱼售价 ¥50-350），
    型号多（每个型号都有人搜），是最理想的套利品类。
    
    Returns:
        去重后的关键词列表（约 300+ 个）
    """
    keywords = []

    for device, models, accessories in APPLE_DEVICES:
        for model in models:
            for acc in accessories:
                keywords.append(f"{device}{model} {acc}")
                # 别名：中文数字
                if device == "iPhone":
                    keywords.append(f"苹果{model} {acc}")

    # 苹果通用词
    keywords.extend(APPLE_BRAND_KEYWORDS)

    # 去重排序
    seen = set()
    result = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            result.append(kw)
    result.sort()
    return result


__all__ = [
    "DEFAULT_SEED_CATEGORIES",
    "expand_categories",
    "expand_to_flat_list",
    "expand_apple_keywords",
    "get_trending_keywords",
    "APPLE_DEVICES",
    "APPLE_BRAND_KEYWORDS",
]

# ── 热门趋势关键词（季节+节日+热点）──

_TRENDING_SEASONAL = {
    "summer": ["防晒衣", "墨镜", "小风扇", "泳衣", "驱蚊器", "凉席", "冰袖", "遮阳帽", "水杯"],
    "winter": ["暖宝宝", "保暖内衣", "围巾", "手套", "电热毯", "加湿器", "保温杯"],
    "spring": ["防晒霜", "春季外套", "运动鞋", "瑜伽垫", "跳绳"],
    "autumn": ["卫衣", "风衣", "马丁靴", "围巾", "秋季护肤"],
    "back_to_school": ["文具", "书包", "台灯", "保温饭盒", "宿舍用品", "床上用品"],
    "holiday": ["礼品盒", "装饰品", "红包", "对联", "年货", "月饼", "粽子"],
}

_TRENDING_HOT = [
    "蓝牙耳机", "智能手表", "无线充电器", "车载支架", "电动牙刷",
    "咖啡杯", "瑜伽裤", "露营装备", "便携风扇", "手机支架",
    "化妆品收纳", "桌面收纳", "洞洞板", "挂脖风扇", "迷你打印机",
    "投影仪", "筋膜枪", "按摩仪", "助眠产品", "宠物玩具",
    "汽车用品", "防晒袖套", "渔夫帽", "托特包", "帆布袋",
]


def get_trending_keywords(count: int = 30) -> List[str]:
    """获取热门趋势关键词（季节+节日+热点）

    用于自动补充关键词池，跟上市场热度。
    """
    from datetime import datetime
    month = datetime.now().month
    keywords = set(_TRENDING_HOT)

    # 季节词
    if month in (6, 7, 8):
        keywords.update(_TRENDING_SEASONAL["summer"])
    elif month in (12, 1, 2):
        keywords.update(_TRENDING_SEASONAL["winter"])
    elif month in (3, 4, 5):
        keywords.update(_TRENDING_SEASONAL["spring"])
    else:
        keywords.update(_TRENDING_SEASONAL["autumn"])

    # 开学季
    if month in (2, 8, 9):
        keywords.update(_TRENDING_SEASONAL["back_to_school"])

    # 节假日
    if month in (1, 2, 9, 10, 12):
        keywords.update(_TRENDING_SEASONAL["holiday"])

    return list(keywords)[:count]