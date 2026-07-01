"""AI店长 v1.1 - 跨平台商品匹配器

通过标题模糊匹配，将不同平台的同一商品关联起来。
核心算法：TF-IDF + 余弦相似度（无外部依赖，纯 Python 实现）。

已知局限：
- 标题长度差异大时匹配率下降
- 品牌名被平台替换时可能漏配
- 纯文本匹配，不理解语义
"""
import logging
import re
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 中文停用词（高频无意义词）
_STOP_WORDS = {
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一",
    "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着",
    "没有", "看", "好", "自己", "这", "他", "她", "它", "们", "被", "从",
    "那", "这个", "那个", "什么", "怎么", "多少", "几", "哪", "为什么",
    "但", "因为", "所以", "如果", "虽然", "但是", "而且", "或者", "还是",
    "包邮", "现货", "新款", "热卖", "爆款", "推荐", "正品", "厂家", "直销",
    "批发", "代发", "一件代发", "厂家直销", "源头", "工厂", "源头工厂",
    "厂家", "直供", "一手货源", "跨境", "外贸", "跨境爆款",
}


def _tokenize(text: str) -> List[str]:
    """中英文分离分词：英文按空格+边界切分，中文用2-gram

    跨平台标题格式差异大，需要同时捕获英文品牌/型号词（如 iPhone16）
    和中文品类词（如 手机壳），否则匹配率几乎为零。
    """
    text = text.lower().strip()
    tokens: List[str] = []

    # 1. 提取英文单词（连续字母数字）
    for m in re.finditer(r"[a-z0-9]+", text):
        word = m.group()
        # 过滤太短的
        if len(word) >= 2:
            tokens.append(word)

    # 2. 中文 2-gram
    chinese = re.sub(r"[^\u4e00-\u9fff]", "", text)
    for i in range(len(chinese) - 1):
        bigram = chinese[i : i + 2]
        if bigram not in _STOP_WORDS:
            tokens.append(bigram)

    # 3. 空格分隔的词（中英混合词如 "iPhone16promax"）
    for t in text.split():
        # 过滤纯标点/太短/停用词
        t = re.sub(r"[^\w\u4e00-\u9fff]", "", t)
        if len(t) >= 3 and t not in _STOP_WORDS:
            tokens.append(t)

    return tokens


def _compute_tf(tokens: List[str]) -> Dict[str, float]:
    """计算词频 (TF)"""
    counts = Counter(tokens)
    total = len(tokens) or 1
    return {word: count / total for word, count in counts.items()}


def _cosine_sim(tf1: Dict[str, float], tf2: Dict[str, float]) -> float:
    """计算两个 TF 向量的余弦相似度"""
    all_words = set(tf1.keys()) | set(tf2.keys())
    if not all_words:
        return 0.0
    dot = sum(tf1.get(w, 0) * tf2.get(w, 0) for w in all_words)
    norm1 = sum(v * v for v in tf1.values()) ** 0.5
    norm2 = sum(v * v for v in tf2.values()) ** 0.5
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


def title_similarity(title_a: str, title_b: str) -> float:
    """计算两个标题的相似度 [0, 1]

    混合评分: 60% TF-IDF 余弦 + 40% token 重叠 Jaccard
    跨平台标题格式差异大，token 重叠能捕获共有的品牌/型号/品类词。
    """
    tokens_a = _tokenize(title_a)
    tokens_b = _tokenize(title_b)

    # 1. TF-IDF 余弦相似度
    tf_a = _compute_tf(tokens_a)
    tf_b = _compute_tf(tokens_b)
    cosine = _cosine_sim(tf_a, tf_b)

    # 2. Token 集合 Jaccard 相似度
    set_a = set(tokens_a)
    set_b = set(tokens_b)
    union = len(set_a | set_b)
    jaccard = len(set_a & set_b) / union if union > 0 else 0.0

    # 3. 混合 (TF-IDF 权重更高，捕获语义相似；Jaccard 捕获词汇重叠)
    return 0.6 * cosine + 0.4 * jaccard


def match_cross_platform(
    products_a: List[Dict],
    products_b: List[Dict],
    threshold: float = 0.35,
) -> List[Tuple[Dict, Dict, float]]:
    """将两个平台的商品列表进行交叉匹配

    Args:
        products_a: 平台 A 商品列表
        products_b: 平台 B 商品列表
        threshold: 相似度阈值

    Returns:
        匹配对列表 [(item_a, item_b, similarity), ...]
    """
    if not products_a or not products_b:
        return []

    matches = []
    used_b = set()

    for item_a in products_a:
        best_score = 0.0
        best_idx = -1
        title_a = item_a.get("title", "")

        for idx, item_b in enumerate(products_b):
            if idx in used_b:
                continue
            title_b = item_b.get("title", "")
            score = title_similarity(title_a, title_b)
            if score > best_score:
                best_score = score
                best_idx = idx

        if best_idx >= 0 and best_score >= threshold:
            matches.append((item_a, products_b[best_idx], best_score))
            used_b.add(best_idx)

    # 按相似度降序
    matches.sort(key=lambda x: x[2], reverse=True)
    logger.info("matched %d pairs (threshold=%.2f)", len(matches), threshold)
    return matches


def find_best_match(
    target: Dict,
    candidates: List[Dict],
    threshold: float = 0.55,
) -> Optional[Tuple[Dict, float]]:
    """在候选列表中找最匹配的单品

    Returns:
        (匹配商品, 相似度) 或 None
    """
    title_target = target.get("title", "")
    best_score = 0.0
    best_item = None

    for item in candidates:
        title_cand = item.get("title", "")
        score = title_similarity(title_target, title_cand)
        if score > best_score:
            best_score = score
            best_item = item

    if best_score >= threshold and best_item is not None:
        return (best_item, best_score)
    return None


__all__ = [
    "title_similarity",
    "match_cross_platform",
    "find_best_match",
    "extract_search_keywords",
    "bidirectional_scan",
    "normalize_keyword",
    "reset_pdd_cache",
    "get_cache_stats",
]


def bidirectional_scan(
    keyword: str,
    pdd_scraper,
    xianyu_scraper,
    shipping_cost: float = 3.0,
    fee_rate: float = 0.016,
    min_roi: float = None,
    min_similarity: float = 0.12,
    pdd_limit: int = 10,
    xy_limit: int = 5,
    config: Dict[str, Any] = None,
    db = None,
) -> List[Dict]:
    """双向交叉扫描 + DB 缓存回退

    v1.2: 当 PDD API 限流时，用 DB 中历史 PDD 数据代替
    """
    from .arbitrage import calculate_arbitrage

    xy_items = xianyu_scraper.fetch(keyword, max_items=xy_limit)
    if not xy_items:
        logger.info("bidirectional: no Xianyu items for '%s'", keyword)
        return []

    all_pdd: Dict[str, Dict] = {}
    pdd_broad = _fetch_pdd_cached(normalize_keyword(keyword), pdd_scraper,
                                  max_items=pdd_limit, db=db)
    for it in pdd_broad:
        pid = it.get("product_id", "")
        if pid:
            all_pdd[pid] = it

    # PDD API 限流回退：用 DB 缓存的历史数据
    if not all_pdd and db:
        logger.info("bidirectional: PDD limited, using DB cache for '%s'", keyword)
        cached = db.get_recent_products(platform="pdd", limit=50)
        for it in cached:
            pid = it.get("product_id", "")
            if pid and pid not in all_pdd:
                # 简单标题关键词过滤
                if any(w in (it.get("title", "") or "").lower() for w in keyword.lower().split()):
                    all_pdd[pid] = it
        logger.info("bidirectional: DB cache returned %d PDD items", len(all_pdd))

    sub_queries = set()
    for xy_item in xy_items[:5]:
        title = xy_item.get("title", "")
        for q in extract_search_keywords(title, max_queries=1):
            sub_queries.add(q)

    for q in list(sub_queries)[:5]:
        nq = normalize_keyword(q)
        if not nq:
            continue
        try:
            items = _fetch_pdd_cached(nq, pdd_scraper, max_items=10, db=db)
            for it in items:
                pid = it.get("product_id", "")
                if pid and pid not in all_pdd:
                    all_pdd[pid] = it
        except Exception:
            continue

    pdd_list = list(all_pdd.values())
    stats = get_cache_stats()
    logger.info("bidirectional: %d XY + %d PDD for '%s' | PDD cache: %d hits saved %d calls",
                len(xy_items), len(pdd_list), keyword,
                stats["hits"], stats["saved"])

    # 3. 双向匹配 + 质量校验
    opportunities = []
    best_sims = []  # debug
    for xy_item in xy_items:
        xy_title = xy_item.get("title", "")
        for pdd_item in pdd_list:
            sim = title_similarity(pdd_item.get("title", ""), xy_title)
            best_sims.append(sim)
            if sim >= 0.15:  # 放宽到0.15便于调试
                logger.info("bidirectional debug: sim=%.3f XY=%s PDD=%s",
                            sim, xy_title[:30], pdd_item.get("title","")[:30])
            if sim < min_similarity:
                continue
            valid, reason = validate_match(pdd_item, xy_item, sim)
            if not valid and sim >= 0.25:
                logger.info("bidirectional reject: sim=%.3f reason=%s XYprice=%.1f PDDprice=%.1f XY=%s PDD=%s",
                            sim, reason,
                            xy_item.get("price", 0), pdd_item.get("price", 0),
                            xy_title[:30], pdd_item.get("title", "")[:30])
            if not valid:
                logger.debug("match rejected: %s", reason)
                continue
            arb = calculate_arbitrage(pdd_item, xy_item, sim,
                                      shipping_cost, fee_rate,
                                      min_roi=min_roi, config=config)
            if arb:
                d = arb.to_dict()
                d["buy_image"] = pdd_item.get("image_url", "")
                d["sell_image"] = xy_item.get("image_url", "")
                d["buy_url"] = pdd_item.get("product_url", "")
                d["sell_url"] = xy_item.get("product_url", "")
                opportunities.append(d)

    opportunities.sort(key=lambda x: x.get("roi", 0), reverse=True)
    if best_sims and not opportunities:
        top = sorted(best_sims, reverse=True)[:5]
        logger.info("bidirectional: no matches. Best sims: %s, XY prices: %s, PDD prices: %s",
                    [f"{s:.3f}" for s in top],
                    [f"{i.get('price',0):.0f}" for i in xy_items[:3]],
                    [f"{i.get('price',0):.0f}" for i in pdd_list[:3]])
    return opportunities


def extract_search_keywords(title: str, max_queries: int = 3) -> List[str]:
    """从商品标题提取搜索关键词 v1.2 增强版

    关键改进：
    - 提取完整型号词 (如 iphone16promax 而不是只 iphone)
    - 提取品牌词 (如 casetify)
    - 品类+型号组合查询，提高 PDD 匹配精度
    """
    text = title.lower().strip()

    # 1. 提取英文品牌/型号词（保留完整词，如 iphone16promax）
    en_words = []
    for m in re.finditer(r"[a-z0-9]{3,}", text):
        w = m.group()
        if w.isdigit() or len(w) < 3:
            continue
        en_words.append(w)

    # 合并连续的版本号词
    merged = []
    i = 0
    while i < len(en_words):
        word = en_words[i]
        j = i + 1
        while j < len(en_words) and en_words[j].isdigit():
            word += en_words[j]
            j += 1
        if j < len(en_words) and en_words[j].lower() in ("pro", "max", "plus", "mini", "ultra"):
            word += en_words[j]
            j += 1
        if j < len(en_words) and en_words[j].lower() in ("max", "mini", "ultra"):
            word += en_words[j]
            j += 1
        merged.append(word)
        i = j

    en_words = merged

    # 2. 提取中文品类词
    chinese = re.sub(r"[^\u4e00-\u9fff]", "", text)
    type_words = []
    for i in range(len(chinese) - 1):
        bg = chinese[i:i+2]
        if any(ending in bg for ending in ["壳", "套", "膜", "线", "器", "机",
                                             "盒", "架", "垫", "灯", "包", "袋",
                                             "表", "带", "贴", "扣", "环", "卡"]):
            if bg not in _STOP_WORDS:
                type_words.append(bg)

    type_words = list(dict.fromkeys(type_words))
    top_type = type_words[0] if type_words else ""

    # 3. 生成查询（型号+品类 优先，然后是品牌词）
    queries = []
    for en in en_words[:3]:
        if top_type:
            queries.append(f"{en} {top_type}")
        elif len(en) >= 5:  # 够长的英文词直接搜
            queries.append(en)

    # 如果型号词不够，加上品类词
    if top_type and not queries:
        queries.append(top_type)

    # 兜底：原标题前30字
    if not queries and len(title) > 4:
        queries.append(title[:30])

    return queries[:max_queries]


def normalize_keyword(kw: str) -> str:
    """标准化关键词用于缓存去重"""
    import re
    kw = kw.strip().lower()
    kw = re.sub(r"\s+", " ", kw)       # 多余空格合并
    kw = re.sub(r"[，,。.、/\\\-—|]", " ", kw)  # 符号替换为空格
    kw = re.sub(r"\s+", " ", kw).strip()
    return kw if kw else ""


# ── PDD 搜索缓存（扫描内 + DB 持久化）──

_pdd_search_cache: Dict[str, List[Dict[str, Any]]] = {}
_cache_hits = 0
_cache_misses = 0


def _fetch_pdd_cached(normalized_kw: str, pdd_scraper, max_items: int = 10,
                      db=None) -> List[Dict[str, Any]]:
    """从缓存或 API 获取 PDD 搜索结果"""
    global _cache_hits, _cache_misses

    # 1. 内存缓存
    if normalized_kw in _pdd_search_cache:
        _cache_hits += 1
        logger.debug("PDD cache HIT: '%s'", normalized_kw)
        return _pdd_search_cache[normalized_kw]

    # 2. DB 缓存
    if db:
        try:
            cached = db.get_search_cache("pdd", normalized_kw)
            if cached:
                _cache_hits += 1
                _pdd_search_cache[normalized_kw] = cached
                logger.debug("PDD DB cache HIT: '%s' (%d items)", normalized_kw, len(cached))
                return cached
        except Exception:
            pass

    # 3. API 调用
    _cache_misses += 1
    items = pdd_scraper.fetch(normalized_kw, max_items=max_items)
    _pdd_search_cache[normalized_kw] = items

    # 4. 保存到 DB
    if db and items:
        try:
            db.save_search_cache("pdd", normalized_kw, items)
        except Exception:
            pass

    return items


def reset_pdd_cache():
    """重置缓存统计（每个扫描任务开始时调用）"""
    global _cache_hits, _cache_misses, _pdd_search_cache
    _cache_hits = 0
    _cache_misses = 0
    _pdd_search_cache.clear()
    logger.info("PDD cache reset")


def get_cache_stats() -> dict:
    """返回缓存统计"""
    return {"hits": _cache_hits, "misses": _cache_misses,
            "saved": _cache_hits, "cached_keys": len(_pdd_search_cache)}


# ── 匹配质量校验（v1.2 新增）──
# 纯代码校验，不调 AI agent，零 token 消耗

_PRODUCT_TYPE_ENDINGS = {
    "壳", "套", "膜", "线", "带", "架", "机", "器",
    "垫", "座", "包", "盒", "袋", "杯", "灯", "盘",
    "笔", "纸", "布", "巾", "刷", "刀", "剪", "锁",
    "贴", "扣", "环", "链", "绳", "板", "棍", "管",
}
_PRICE_RATIO_MAX = 30.0


def _extract_product_type(title: str) -> set:
    """从标题提取品类词（中文2-gram，结尾字为壳/套/膜等）"""
    chinese = re.sub(r"[^\u4e00-\u9fff]", "", title)
    types = set()
    for i in range(len(chinese) - 1):
        bg = chinese[i : i + 2]
        if bg[-1] in _PRODUCT_TYPE_ENDINGS and bg not in _STOP_WORDS:
            types.add(bg)
    return types


def validate_match(pdd_item: dict, xy_item: dict, similarity: float) -> tuple:
    """校验匹配合理性（v1.2 严格版——品牌/型号必须一致）

    Returns:
        (is_valid: bool, reason: str)
    """
    pdd_title = pdd_item.get("title", "").lower()
    xy_title = xy_item.get("title", "").lower()
    pdd_price = float(pdd_item.get("price", 0))
    xy_price = float(xy_item.get("price", 0))

    # 1. 提取品牌/型号关键词
    xy_brands = _extract_brand_keywords(xy_title)
    pdd_brands = _extract_brand_keywords(pdd_title)

    # 2. 品牌/型号必须重叠
    if xy_brands and pdd_brands:
        common_brands = xy_brands & pdd_brands
        if not common_brands:
            return (False, f"品牌/型号不匹配: {xy_brands} vs {pdd_brands}")

    # 3. 品类校验
    pdd_type = _extract_product_type(pdd_title)
    xy_type = _extract_product_type(xy_title)
    if pdd_type and xy_type and not (pdd_type & xy_type) and similarity < 0.30:
        return (False, f"品类不匹配: {pdd_type} vs {xy_type}")

    # 4. 价格比 (v1.2: 收紧到 1.5-15x，过滤假匹配)
    if pdd_price > 0 and xy_price > 0:
        ratio = xy_price / pdd_price
        if ratio < 1.5:
            return (False, f"价差太小 x{ratio:.1f}")
        if ratio > 15 and similarity < 0.30:
            return (False, f"价差过大且相似度低 x{ratio:.1f}")

    # 5. 相似度硬门槛
    if similarity < 0.20:
        return (False, f"相似度太低 {similarity:.2f}")

    return (True, "ok")


def _extract_brand_keywords(title: str) -> set:
    """从标题提取品牌/型号关键词"""
    text = title.lower()
    brands = set()

    # 英文品牌词（3字母以上，非纯数字）
    for m in re.finditer(r"[a-z]{3,}[a-z0-9]*", text):
        w = m.group()
        if not w.isdigit() and len(w) >= 3:
            brands.add(w)

    # 中文品牌词（常见品牌）
    cn_brands = [
        "绿联", "品胜", "倍思", "安克", "图拉斯", "洛克", "绿光", "闪魔",
        "华为", "小米", "苹果", "三星", "OPPO", "vivo", "一加",
        "罗马仕", "羽博", "摩米士", "邦克仕", "亿色",
    ]
    for b in cn_brands:
        if b in text:
            brands.add(b)

    # 型号词（iPhone11, K60, Mate50 等）
    for m in re.finditer(r"[a-z]+\d+[a-z]*", text):
        brands.add(m.group())

    return brands


# ═══════════════════════════════════════════════════════════════
# v2.0 结构化匹配引擎
# ═══════════════════════════════════════════════════════════════

from dataclasses import dataclass, field


@dataclass
class ProductAttrs:
    """结构化商品属性"""
    raw_title: str = ""
    product_brand: str = ""       # 商品品牌: 闪魔/绿光/品胜
    device_brands: set = field(default_factory=set)  # 设备品牌: 苹果/小米/华为
    models: set = field(default_factory=set)          # 型号: K80, iPhone16Pro
    negative_models: set = field(default_factory=set) # 不兼容型号
    category: str = ""            # screen_protector/phone_case/cable/charger/earphone
    features: set = field(default_factory=set)        # 防窥/高清/磁吸
    material: str = ""            # 钢化/水凝/硅胶/TPU
    quantity: int = 1             # 数量: 1/2/3片
    bundle_items: list = field(default_factory=list)  # 套装内容
    color: str = ""
    confidence: float = 0.0       # 解析置信度


@dataclass
class MatchResult:
    """匹配结果"""
    decision: str = ""       # match / reject
    grade: str = "D"        # A/B/C/D
    final_score: float = 0.0
    match_confidence: float = 0.0
    price_confidence: float = 0.0
    model_score: float = 0.0
    category_score: float = 0.0
    feature_score: float = 0.0
    brand_score: float = 0.0
    text_similarity: float = 0.0
    price_ratio: float = 0.0
    conservative_roi: float = 0.0
    aggressive_roi: float = 0.0
    risk_flags: set = field(default_factory=set)
    reasons: list = field(default_factory=list)
    parsed_xianyu: "ProductAttrs" = None
    parsed_pdd: "ProductAttrs" = None


# ── 解析规则 ──

_DEVICE_BRANDS = {
    "苹果", "iphone", "小米", "红米", "redmi", "华为", "huawei",
    "vivo", "oppo", "荣耀", "honor", "三星", "samsung", "一加", "oneplus",
    "iqoo", "realme", "真我", "魅族", "努比亚", "摩托罗拉",
}

_PRODUCT_CATEGORIES = {
    "screen_protector": {
        "膜", "保护膜", "手机膜", "钢化膜", "防窥膜", "水凝膜",
        "磨砂膜", "高清膜", "蓝光膜", "全屏膜", "软膜", "硬膜",
        "前膜", "后膜", "镜头膜", "背膜", "AR膜",
    },
    "phone_case": {
        "手机壳", "保护壳", "保护套", "手机套", "外壳", "后盖",
        "硅胶壳", "透明壳", "磨砂壳", "气囊壳", "防摔壳",
    },
    "cable": {
        "数据线", "充电线", "快充线", "type-c线", "苹果线",
        "安卓线", "usb线", "编织线",
    },
    "charger": {
        "充电器", "充电头", "快充头", "氮化镓", "pd充电",
        "闪充", "充电套装", "电源适配器",
    },
    "earphone": {
        "耳机", "蓝牙耳机", "无线耳机", "耳塞", "airpods",
        "入耳式", "头戴式", "骨传导", "挂耳式",
    },
    "holder": {
        "支架", "手机支架", "车载支架", "桌面支架", "指环扣",
    },
}

_FEATURES = {
    "防窥", "高清", "蓝光", "磨砂", "透明", "全覆盖",
    "磁吸", "magsafe", "防摔", "抗摔", "防指纹",
    "快充", "闪充", "超级快充", "氮化镓", "编织",
    "液态硅胶", "tpu", "气囊", "超薄", "电镀",
}

QUANTITY_PATTERNS = [
    (r"(\d+)片装?", "piece"),
    (r"(\d+)片", "piece"),
    (r"买(\d+)送(\d+)", "bundle"),
    (r"(\d+)张", "piece"),
    (r"(\d+)个装?", "piece"),
    (r"套装", "set"),
    (r"全家桶", "set"),
]

_NON_BRAND_ENGLISH = {"type", "usb", "pd", "qc", "fast", "quick", "super",
                     "max", "pro", "plus", "ultra", "mini", "lite", "air",
                     "cable", "case", "film", "glass", "cover", "charger",
                     "data", "power", "wireless", "bluetooth", "smart"}

# 已知中文品牌（不包含设备品牌）
_KNOWN_PRODUCT_BRANDS = {
    "闪魔", "绿光", "绿联", "品胜", "倍思", "安克", "图拉斯",
    "洛克", "罗马仕", "羽博", "摩米士", "邦克仕", "亿色",
    "第一卫", "耐尔金", "决色", "贝尔金", "亿色", "京东京造",
    "小米", "华为",  # 这些也是设备品牌但也可以是产品品牌
}


def parse_product_title(title: str) -> ProductAttrs:
    """结构化解析商品标题"""
    attrs = ProductAttrs(raw_title=title)
    text = title.lower().strip()
    if not text:
        return attrs

    # ── 1. 品牌 ──
    # 商品品牌（标题开头的品牌词，排除设备品牌）
    first_word = text.split()[0] if text.split() else ""
    for b in _KNOWN_PRODUCT_BRANDS:
        if text.startswith(b.lower()):
            attrs.product_brand = b
            break
    if not attrs.product_brand:
        for m in re.finditer(r"[a-z]{3,}[a-z0-9]*", text[:30]):
            w = m.group()
            if w not in _DEVICE_BRANDS and not w.isdigit() and w not in _NON_BRAND_ENGLISH:
                attrs.product_brand = w
                break

    # ── 2. 设备品牌 ──
    for db in _DEVICE_BRANDS:
        if db in text:
            attrs.device_brands.add(db)

    # ── 3. 型号 ──
    # iPhone 型号
    for m in re.finditer(r"(iphone|xr|xs|se)\s*(\d+)\s*(pro|max|plus|mini|ultra|air)?\s*(pro|max|plus|mini|ultra|air)?", text):
        model = re.sub(r"\s+", "", m.group().lower())
        attrs.models.add(model)

    # 安卓型号: K80, Mate50, P60 等 (字母+数字)
    for m in re.finditer(r"([a-z]{1,10}\d+[a-z]*)", text):
        model = re.sub(r"\s+", "", m.group(1).lower())
        if len(model) >= 3 and not model.startswith(("3g", "4g", "5g", "2g")):
            attrs.models.add(model)

    # 后处理: 提取 pro/max/plus/ultra 后缀
    expanded = set()
    for m in list(attrs.models):
        for suffix in ["pro", "max", "plus", "ultra", "mini", "air", "t", "s"]:
            for pattern in [f"{m}{suffix}", f"{m} {suffix}", f"{m}{suffix}版"]:
                if pattern in text:
                    expanded.add(f"{m}{suffix}")
    attrs.models.update(expanded)

    # ── 4. 否定型号（不适用xxx, 非xxx, xxx不通用）──
    for pattern in [r"(?:不适用|非|不兼容|不适配|不通用|除|除了)([a-z0-9\s]+?)(?:[，,。.；;及和\s]|$)",
                     r"([a-z0-9]+)[不未无]通用"]:
        for m in re.finditer(pattern, text):
            neg = m.group(1).strip()
            for token in neg.split():
                if re.match(r"^[a-z]+\d+", token):
                    attrs.negative_models.add(token.lower())

    # ── 5. 品类 ──
    for cat, keywords in _PRODUCT_CATEGORIES.items():
        for kw in keywords:
            if kw in text:
                attrs.category = cat
                break
        if attrs.category:
            break

    # ── 6. 功能特征 ──
    for feat in _FEATURES:
        if feat in text:
            attrs.features.add(feat)

    # ── 7. 材质 ──
    for mat in ["钢化", "水凝", "液态硅胶", "TPU", "硅胶", "PC", "PP", "芳纶"]:
        if mat.lower() in text:
            attrs.material = mat
            break

    # ── 8. 数量 ──
    for pattern, qtype in QUANTITY_PATTERNS:
        m = re.search(pattern, text)
        if m:
            if qtype == "piece":
                attrs.quantity = int(m.group(1))
            elif qtype == "bundle":
                attrs.quantity = int(m.group(1)) + int(m.group(2))
            elif qtype == "set":
                attrs.quantity = 2  # 套装默认2
            break

    # ── 9. 颜色 ──
    for c in ["黑色", "白色", "透明", "蓝色", "红色", "绿色", "紫色", "粉色", "灰色"]:
        if c in text:
            attrs.color = c
            break

    attrs.confidence = _estimate_parse_confidence(attrs)
    return attrs


def _estimate_parse_confidence(attrs: ProductAttrs) -> float:
    score = 0.0
    if attrs.category: score += 0.3
    if attrs.product_brand: score += 0.15
    if attrs.device_brands: score += 0.15
    if attrs.models: score += 0.25
    if attrs.features: score += 0.1
    if attrs.quantity > 1: score += 0.05
    return min(score, 1.0)


# ── 风险标记 ──

def detect_risks(xy_attrs: ProductAttrs, pdd_attrs: ProductAttrs,
                 pdd_price: float, pdd_prices: list = None) -> set:
    """检测风险标记"""
    risks = set()

    # 多SKU
    if len(pdd_attrs.models) > 3:
        risks.add("multi_sku_listing")

    # 低价引流
    if pdd_price < 1.0:
        risks.add("low_price_teaser")

    # 数量不一致
    if xy_attrs.quantity > 0 and pdd_attrs.quantity > 0:
        if xy_attrs.quantity != pdd_attrs.quantity:
            risks.add("quantity_mismatch")

    # 价格不确定
    if pdd_prices and len(pdd_prices) > 1:
        pmin, pmax = min(pdd_prices), max(pdd_prices)
        if pmax > 0 and pmin / pmax < 0.3:
            risks.add("sku_price_uncertain")

    # 优惠券价格
    if "券后" in pdd_attrs.raw_title or "coupon" in pdd_attrs.raw_title.lower():
        risks.add("coupon_price")

    return risks


# ── 结构化校验 ──

def validate_match_v2(xy_attrs: ProductAttrs, pdd_attrs: ProductAttrs,
                      xy_price: float, pdd_price: float) -> MatchResult:
    """结构化匹配校验 v2.0"""
    result = MatchResult(parsed_xianyu=xy_attrs, parsed_pdd=pdd_attrs)

    # ── 品类校验 ──
    if xy_attrs.category and pdd_attrs.category:
        if xy_attrs.category == pdd_attrs.category:
            result.category_score = 1.0
        else:
            result.decision = "reject"
            result.grade = "D"
            result.reasons.append(f"品类冲突: {xy_attrs.category} vs {pdd_attrs.category}")
            return result
    elif xy_attrs.category or pdd_attrs.category:
        result.category_score = 0.3  # 一边未知
    else:
        result.category_score = 0.0

    # ── 型号校验 ──
    if xy_attrs.models:
        if pdd_attrs.negative_models & xy_attrs.models:
            result.decision = "reject"
            result.grade = "D"
            result.reasons.append(f"型号否定: {pdd_attrs.negative_models & xy_attrs.models}")
            return result

        if xy_attrs.models & pdd_attrs.models:
            result.model_score = 1.0
        else:
            partial = False
            for m in xy_attrs.models:
                for pm in pdd_attrs.models:
                    if m == pm:
                        partial = True; break
                    # 只有非iPhone型号才做子串匹配
                    if "iphone" not in m and "iphone" not in pm:
                        if m in pm or pm in m:
                            partial = True; break
            if partial:
                result.model_score = 0.4
                result.reasons.append(f"型号部分匹配: {xy_attrs.models} vs {pdd_attrs.models}")
            else:
                result.decision = "reject"
                result.grade = "D"
                result.reasons.append(f"型号不匹配: {xy_attrs.models} vs {pdd_attrs.models}")
                return result
    else:
        result.model_score = 0.3  # 闲鱼无明确型号

    # ── 品牌校验 ──
    if xy_attrs.product_brand and pdd_attrs.product_brand:
        if xy_attrs.product_brand.lower() == pdd_attrs.product_brand.lower():
            result.brand_score = 1.0
        elif xy_attrs.product_brand in _KNOWN_PRODUCT_BRANDS and pdd_attrs.product_brand in _KNOWN_PRODUCT_BRANDS:
            result.decision = "reject"
            result.grade = "D"
            result.reasons.append(f"强品牌冲突: {xy_attrs.product_brand} vs {pdd_attrs.product_brand}")
            return result
        else:
            result.brand_score = 0.2
            result.reasons.append(f"品牌不同: {xy_attrs.product_brand} vs {pdd_attrs.product_brand}")
    elif xy_attrs.product_brand or pdd_attrs.product_brand:
        result.brand_score = 0.5

    # 补充：设备品牌校验（当两边无商品品牌或无型号时）
    if xy_attrs.device_brands and pdd_attrs.device_brands and not xy_attrs.models:
        if not (xy_attrs.device_brands & pdd_attrs.device_brands):
            if result.decision != "reject":
                # 不是强拒绝，只降分
                result.brand_score = max(0, result.brand_score - 0.3)
                result.reasons.append(f"设备品牌不同(无型号): {xy_attrs.device_brands} vs {pdd_attrs.device_brands}")
                if result.final_score < 0.30:
                    result.decision = "reject"
                    result.grade = "D"
    else:
        result.brand_score = 0.3

    # ── 功能特征校验 ──
    if xy_attrs.features and pdd_attrs.features:
        common = xy_attrs.features & pdd_attrs.features
        # 冲突检测
        conflicts = {
            ("防窥", "高清"), ("水凝", "钢化"), ("磨砂", "透明"),
            ("磁吸", "magsafe"),  # 这两个不冲突但也不加分
        }
        has_conflict = False
        for c1, c2 in conflicts:
            if (c1 in xy_attrs.features and c2 in pdd_attrs.features) or \
               (c2 in xy_attrs.features and c1 in pdd_attrs.features):
                has_conflict = True
                break
        if has_conflict:
            result.feature_score = 0.1
            result.reasons.append(f"功能冲突")
        else:
            result.feature_score = len(common) / max(len(xy_attrs.features), 1) * 0.8 + 0.2
    else:
        result.feature_score = 0.4

    # ── 价格比 ──
    if pdd_price > 0 and xy_price > 0:
        result.price_ratio = xy_price / pdd_price
        if result.price_ratio < 1.2:
            result.reasons.append(f"价差太小 x{result.price_ratio:.1f}")
        elif result.price_ratio > 20:
            result.reasons.append(f"价差偏大 x{result.price_ratio:.1f}")

    # ── 综合评分 ──
    result.match_confidence = (
        result.model_score * 0.35 +
        result.category_score * 0.20 +
        result.feature_score * 0.15 +
        result.brand_score * 0.10
    )
    result.decision = "match"
    result.final_score = result.match_confidence

    # ── 定级 ──
    if result.match_confidence >= 0.75:
        result.grade = "A"
    elif result.match_confidence >= 0.55:
        result.grade = "B"
    elif result.match_confidence >= 0.30:
        result.grade = "C"
    else:
        result.grade = "D"
        result.decision = "reject"
        result.reasons.append(f"综合置信度过低: {result.match_confidence:.2f}")

    return result


def score_match_v2(xy_attrs: ProductAttrs, pdd_attrs: ProductAttrs,
                   result: MatchResult, similarities: list = None) -> MatchResult:
    """补充分数（文本相似度+价格合理性）"""
    # 文本相似度
    if similarities:
        result.text_similarity = max(similarities)

    # 最终分数
    result.final_score = (
        result.match_confidence * 0.7 +
        min(result.text_similarity, 1.0) * 0.2 +
        (0.1 if result.price_ratio >= 1.5 else 0.0)
    )
    return result


# ── 统一入口 ──

def match_products_v2(xy_item: dict, pdd_item: dict,
                      shipping: float = 3.0, fee_rate: float = 0.016) -> MatchResult:
    """v2.0 结构化匹配入口"""
    xy_title = xy_item.get("title", "")
    pdd_title = pdd_item.get("title", "")
    xy_price = float(xy_item.get("price", 0))
    pdd_price = float(pdd_item.get("price", 0))

    # 解析
    xy_attrs = parse_product_title(xy_title)
    pdd_attrs = parse_product_title(pdd_title)

    # 校验
    result = validate_match_v2(xy_attrs, pdd_attrs, xy_price, pdd_price)

    # 风险
    result.risk_flags = detect_risks(xy_attrs, pdd_attrs, pdd_price)

    # 补充分数
    sim = title_similarity(xy_title, pdd_title)
    result = score_match_v2(xy_attrs, pdd_attrs, result, [sim])

    # ROI
    if pdd_price > 0:
        total_cost = pdd_price + shipping
        seller_revenue = xy_price * (1 - fee_rate)
        result.aggressive_roi = ((seller_revenue - total_cost) / total_cost * 100) if total_cost > 0 else 0
        # conservative: use higher pdd price estimate
        conservative_pdd = pdd_price * 1.3  # 30% buffer
        conservative_cost = conservative_pdd + shipping
        result.conservative_roi = ((seller_revenue - conservative_cost) / conservative_cost * 100) if conservative_cost > 0 else 0

    # 价格不确定
    if xy_price < 1.0 or "PRICE_UNCERTAIN" in str(xy_item.get("price_confidence", "")):
        result.risk_flags.add("price_uncertain")
        result.price_confidence = 0.3
    else:
        result.price_confidence = 0.8

    return result


__all__.extend([
    "ProductAttrs", "MatchResult",
    "parse_product_title", "validate_match_v2",
    "match_products_v2", "detect_risks",
])
