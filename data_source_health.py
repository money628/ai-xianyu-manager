"""AI店长 v1.2 - 数据源健康检测 + 修复
检测: 闲鱼抓取 / PDD API / SQLite 数据库
用法: python data_source_health.py
"""
import logging
import os
import sys
import time
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(SCRIPT_DIR, "src"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("health_check")


# ── 1. 闲鱼检测 ──

def check_xianyu_by_requests() -> dict:
    """用 requests 探测闲鱼搜索 API（不依赖 Playwright）"""
    result = {"status": "unknown", "items": 0, "reason": "", "sample": []}

    try:
        import requests
        r = requests.get(
            "https://h5.m.goofish.com/api/search",
            params={"q": "手机壳", "page": 1},
            headers={"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_6 like Mac OS X) AppleWebKit/605.1.15",
                     "Accept": "text/html,application/xhtml+xml"},
            timeout=15,
        )
        result["http_status"] = r.status_code
        result["response_len"] = len(r.text)

        if r.status_code != 200:
            result["status"] = "page_error"
            result["reason"] = f"HTTP {r.status_code}"
            return result

        # 尝试从 HTML 中提取商品数据
        import re, json
        text = r.text

        # 方法1: 找 JSON-LD / SSR data
        items_found = []

        # 尝试找 script 中的 JSON 数据
        for pattern in [
            r'window\.__DATA__\s*=\s*({.+?});',
            r'window\.__PRELOADED_STATE__\s*=\s*({.+?});',
            r'"items"\s*:\s*(\[.+?\])',
            r'"itemList"\s*:\s*(\[.+?\])',
        ]:
            for m in re.finditer(pattern, text[:50000], re.DOTALL):
                try:
                    data = json.loads(m.group(1))
                    if isinstance(data, list) and len(data) > 0:
                        for item in data:
                            if isinstance(item, dict):
                                title = (item.get("title") or item.get("itemTitle") or
                                         item.get("goodsName") or item.get("name") or "")
                                price = (item.get("price") or item.get("itemPrice") or
                                         item.get("priceText") or "")
                                if title and price:
                                    items_found.append({"title": str(title)[:60], "price": str(price)})
                    elif isinstance(data, dict):
                        # 可能是嵌套结构
                        for list_key in ["items", "itemList", "list", "data"]:
                            if list_key in data and isinstance(data[list_key], list):
                                for item in data[list_key][:5]:
                                    if isinstance(item, dict):
                                        title = str(item.get("title", item.get("name", "")))
                                        price = str(item.get("price", ""))
                                        if title:
                                            items_found.append({"title": title[:60], "price": price})
                except (json.JSONDecodeError, TypeError):
                    continue
            if items_found:
                break

        # 方法2: 从 HTML 找商品卡片
        if not items_found:
            card_pattern = re.findall(r'<div[^>]*class="[^"]*card[^"]*"[^>]*>(.*?)</div>', text, re.DOTALL)
            for card in card_pattern[:10]:
                title_match = re.search(r'<[^>]+>([^<]{10,80})</', card)
                price_match = re.search(r'[¥￥]\s*([\d.]+)', card)
                if title_match:
                    items_found.append({
                        "title": title_match.group(1).strip()[:60],
                        "price": price_match.group(1) if price_match else "?"
                    })

        # 方法3: 页面文本探测
        if not items_found:
            # 检查是否被拦截
            if "login" in text.lower() or "登录" in text:
                result["status"] = "login_required"
                result["reason"] = "需要登录"
            elif "验证" in text or "captcha" in text.lower():
                result["status"] = "captcha"
                result["reason"] = "触发验证码"
            elif len(text) < 500:
                result["status"] = "blocked"
                result["reason"] = f"响应过短 ({len(text)}字节)"
            else:
                result["status"] = "dom_changed"
                result["reason"] = "DOM结构变更，无法提取商品"
            return result

        result["items"] = len(items_found)
        result["sample"] = items_found[:5]

        if len(items_found) >= 3:
            result["status"] = "ok"
            result["reason"] = f"成功提取 {len(items_found)} 个商品"
        elif len(items_found) > 0:
            result["status"] = "degraded"
            result["reason"] = f"仅提取 {len(items_found)} 个商品（不完整）"
        else:
            result["status"] = "dom_changed"
            result["reason"] = "页面可访问但无法提取商品"

    except Exception as e:
        result["status"] = "network_error"
        result["reason"] = str(e)[:100]

    return result


def check_xianyu_by_playwright() -> dict:
    """用 ScraperXianyu 真实抓取"""
    result = {"status": "unknown", "items": 0, "reason": "", "sample": []}

    try:
        from config import load_config
        from modules.scrapers.scraper_xianyu import ScraperXianyu

        cfg = load_config(os.path.join(SCRIPT_DIR, "config.ini")).as_dict()
        scraper = ScraperXianyu(cfg)

        if not scraper._has_login_state():
            result["status"] = "no_login"
            result["reason"] = "未登录闲鱼"
            return result

        items = scraper.fetch("手机壳", max_items=10)

        real_items = [i for i in items if not str(i.get("product_id", "")).startswith("demo")]
        result["items"] = len(real_items)
        result["sample"] = real_items[:5]

        if len(real_items) >= 3:
            result["status"] = "ok"
            result["reason"] = f"成功提取 {len(real_items)} 个商品"
        elif len(real_items) > 0:
            result["status"] = "degraded"
            result["reason"] = f"仅提取 {len(real_items)} 个商品"
        else:
            result["status"] = "dom_changed"
            result["reason"] = "DOM选择器全部失效，需更新"

    except Exception as e:
        result["status"] = "error"
        result["reason"] = str(e)[:100]

    return result


def _parse_price(text: str) -> float:
    import re
    m = re.search(r'[¥￥]\s*([\d,.]+)', text)
    if m:
        try: return float(m.group(1).replace(",",""))
        except: pass
    m = re.search(r'([\d.]+)\s*元', text)
    if m:
        try: return float(m.group(1))
        except: pass
    return 0.0


# ── 2. PDD 检测 ──

def check_pdd() -> dict:
    result = {"status": "unknown", "token_valid": False, "search_ok": False,
              "calls_today": 0, "reason": ""}

    try:
        from config import load_config
        from modules.scrapers import ScraperPddApi

        cfg = load_config(os.path.join(SCRIPT_DIR, "config.ini")).as_dict()
        pdd_cfg = cfg.get("pdd_api", {})

        # Token 是否存在
        token = pdd_cfg.get("access_token", "")
        result["has_token"] = bool(token)

        if not token:
            result["status"] = "no_token"
            result["reason"] = "未配置 access_token"
            return result

        # 验证 token
        scraper = ScraperPddApi.from_config(cfg)
        try:
            items = scraper.search("test", page=1, page_size=3)
            if items is not None:
                result["token_valid"] = True
                result["search_ok"] = True
                result["status"] = "ok"
                result["reason"] = f"Token有效，搜索返回 {len(items)} 个商品"
                result["sample_items"] = len(items)
            else:
                result["token_valid"] = True
                result["reason"] = "搜索返回空（可能是配额耗尽）"
                result["status"] = "quota_exhausted"
        except Exception:
            result["reason"] = "API调用异常"

        # 检查是否有 refresh_token 用于恢复
        result["has_refresh_token"] = bool(pdd_cfg.get("refresh_token", ""))

    except Exception as e:
        result["status"] = "error"
        result["reason"] = str(e)[:100]

    return result


# ── 3. 数据库检测 ──

def check_database() -> dict:
    result = {"status": "unknown", "products": 0, "opportunities": 0, "pdd_cache": 0}

    try:
        from database import Database
        db_path = os.path.join(SCRIPT_DIR, "data", "ai_storekeeper.db")
        exists = os.path.exists(db_path)
        result["db_exists"] = exists
        result["db_size_kb"] = os.path.getsize(db_path) // 1024 if exists else 0

        if not exists:
            result["status"] = "no_db"
            result["reason"] = "数据库文件不存在"
            return result

        db = Database(db_path)
        stats = db.get_stats()
        result["products"] = stats.get("total_products", 0)
        result["opportunities"] = stats.get("total_opportunities", 0)
        result["pending"] = stats.get("pending_count", 0)
        result["today_opps"] = stats.get("today_opportunities", 0)

        cached = db.get_recent_products(platform="pdd", limit=10)
        result["pdd_cache"] = len(cached)

        # 最近入库时间
        result["status"] = "ok"
        result["reason"] = f"{result['products']} 商品, {result['opportunities']} 机会, {result['pdd_cache']} PDD缓存"

    except Exception as e:
        result["status"] = "error"
        result["reason"] = str(e)[:100]

    return result


# ── 4. 综合报告 ──

def run_health_check():
    print("=" * 60)
    print(" AI店长 v1.2 — 数据源健康检测")
    print(f" 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 闲鱼（先用 requests，失败再用 Playwright）
    print("\n[检测闲鱼] requests 模式...")
    xy_r = check_xianyu_by_requests()
    print(f"  状态: {xy_r['status']}")
    print(f"  详情: {xy_r['reason']}")
    if xy_r.get("items", 0) < 3:
        print("  requests 不足，尝试 Playwright...")
        xy_p = check_xianyu_by_playwright()
        # Prefer Playwright result (more reliable)
        xy = xy_p
    else:
        xy = xy_r

    print(f"\n【闲鱼状态】")
    print(f"  最终状态: {xy['status']}")
    print(f"  原因: {xy['reason']}")
    print(f"  提取商品数: {xy['items']}")
    if xy.get("sample"):
        for i, item in enumerate(xy["sample"][:5]):
            print(f"    #{i+1} {item['title'][:50]}")
            print(f"       价格: {item.get('price','?')}")

    # PDD
    print("\n[检测PDD] ...")
    pdd = check_pdd()
    print(f"\n【PDD状态】")
    print(f"  状态: {pdd['status']}")
    print(f"  原因: {pdd['reason']}")
    print(f"  Token有效: {pdd.get('token_valid')}")
    print(f"  搜索可用: {pdd.get('search_ok')}")
    print(f"  有refresh_token: {pdd.get('has_refresh_token')}")

    # DB
    print("\n[检测数据库] ...")
    db = check_database()
    print(f"\n【数据库状态】")
    print(f"  状态: {db['status']}")
    print(f"  详情: {db['reason']}")
    print(f"  文件大小: {db.get('db_size_kb', 0)} KB")
    print(f"  PDD缓存: {db.get('pdd_cache', 0)} 条")

    # 综合判断
    print(f"\n{'='*60}")
    print("【PDD 账号池状态】")
    try:
        from modules.pdd_account_pool import PDDAccountPool
        pool = PDDAccountPool()
        for s in pool.get_status():
            print(f"  {s['name']}: {'可用' if s['available'] else '不可用'} | "
                  f"{s['calls']}/{2000} | 剩余 {s['remaining']}")
        print(f"  总可用: {pool.available_accounts}/{pool.total_accounts}")
        print(f"  今日总调用: {pool.total_calls_today}")
    except Exception as e:
        print(f"  账号池加载失败: {e}")

    print(f"\n{'='*60}")
    print("【当前是否可以运行套利主链路】")

    blockers = []
    if xy["status"] not in ("ok",):
        blockers.append(f"闲鱼: {xy['reason']}")
    if pdd["status"] not in ("ok",):
        blockers.append(f"PDD: {pdd['reason']}")
    if db["status"] != "ok":
        blockers.append(f"数据库: {db['reason']}")

    if not blockers:
        print("  [OK] 可以运行 - 所有数据源正常")
    else:
        print("  [FAIL] 不能运行")
        for b in blockers:
            print(f"    阻塞: {b}")

    print()
    print("【阻塞原因】")
    if xy["status"] == "dom_changed":
        print("  闲鱼前端DOM改版，Playwright选择器失效。")
        print("  需要更新 scraper_xianyu.py 中的CSS选择器。")
    if pdd["status"] == "quota_exhausted" or pdd.get("reason","") == "搜索返回空":
        print("  PDD API 今日配额耗尽（2000次/天）。")
        print("  需要多账号轮换以突破限制。")
    if db["pdd_cache"] == 0:
        print("  数据库中没有PDD历史缓存数据。")
        print("  当PDD限流时无法回退匹配。")

    print()
    print("【下一步修复建议】")
    if xy["status"] != "ok":
        print("  A. 继续修闲鱼抓取稳定性（更新DOM选择器）")
    elif pdd["status"] != "ok":
        print("  B. 增加PDD账号数量（多账号额度池）")
    else:
        print("  数据源已就绪，可恢复套利主链路")

    print("=" * 60)


if __name__ == "__main__":
    run_health_check()
