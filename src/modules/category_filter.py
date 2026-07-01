"""类目过滤器 — 拦截服装/低质量商品"""
import re

# 强制排除类目关键词
EXCLUDED_CATEGORIES = {
    "女装", "男装", "童装", "裤子", "牛仔裤", "短裤", "裙子",
    "T恤", "衬衫", "外套", "卫衣", "羽绒服", "内衣", "袜子",
    "鞋", "帽子", "围巾", "打底衫", "秋冬", "春夏", "四季",
    "爆款女装", "潮牌服饰", "大码女装", "运动服", "瑜伽裤",
    "连衣裙", "半身裙", "情侣装", "亲子装", "毛衣", "棉衣",
    "皮衣", "风衣", "吊带", "背心", "裤衩", "布鞋", "凉鞋",
    "拖鞋", "靴子", "高跟鞋", "平底鞋", "运动鞋", "帆布鞋",
}

# 优先扫描品类
PRIORITY_CATEGORIES = {
    "手机配件", "数码配件", "数据线", "充电器", "手机壳",
    "手机膜", "耳机配件", "收纳用品", "桌面小物", "车载配件",
    "宿舍用品", "小家电配件", "电脑配件", "游戏配件", "运动小配件",
    "宠物小用品", "工具配件", "生活耗材", "文具办公", "低客单价标品",
}

# 匹配型模式 (正则)
EXCLUDED_PATTERNS = [
    r'(秋冬|春夏|四季)\s*(新品|新款|爆款)?',
    r'(大码|特大码|加肥|加大)\s*(女装|男装|T恤|衬衫)?',
    r'(修身|显瘦|宽松|韩版|日系|欧美|街头)\s*(女|男)?',
]


def is_excluded_category(title: str, keyword: str = "") -> bool:
    """检查商品是否属于排除类目"""
    t = (title or "").lower()
    k = (keyword or "").lower()
    for cat in EXCLUDED_CATEGORIES:
        if cat in t or cat in k:
            return True
    for pat in EXCLUDED_PATTERNS:
        if re.search(pat, t):
            return True
    return False


def is_priority_category(title: str) -> bool:
    """检查是否属于优先类目"""
    t = (title or "").lower()
    for cat in PRIORITY_CATEGORIES:
        if cat in t:
            return True
    return False


def filter_opportunity(opp: dict) -> tuple:
    """过滤机会，返回 (是否通过, 原因)"""
    title = (opp.get("buy_title") or opp.get("title") or "")
    sell_title = opp.get("sell_title", "")
    
    if is_excluded_category(title):
        return False, "服装类目"
    if is_excluded_category(sell_title):
        return False, "服装类目(闲鱼)"
    return True, ""
