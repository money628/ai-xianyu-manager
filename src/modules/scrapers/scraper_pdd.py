"""AI店长 v1.2 - 拼多多 Playwright 抓取器（反风控增强版）

核心改进：
1. 继承 PlaywrightBase 的全套反风控机制
2. 提取店铺链接（store_url）
3. 更精确的 DOM 选择器
4. 随机滚动 + 点击模拟
"""
import json
import logging
import random
import re
from typing import Any, Dict, List
from urllib.parse import quote_plus

from .playwright_base import PlaywrightScraper

logger = logging.getLogger(__name__)


class ScraperPdd(PlaywrightScraper):
    PLATFORM_NAME = "pdd"
    PLATFORM_KEY = "pdd"
    HEADLESS_DEFAULT = False  # PDD RiskControl 检测 headless，需用有头模式

    CONTEXT_CONFIG = {
        "viewport": {"width": 390, "height": 844},
        "is_mobile": True,
        "locale": "zh-CN",
    }

    BASE_URL = "https://mobile.yangkeduo.com"

    def fetch(self, keyword: str, max_items: int = 20) -> List[Dict[str, Any]]:
        if not self._has_login_state():
            logger.info("[pdd] no login state, using demo data for '%s'", keyword)
            return self._demo_data(keyword, max_items)
        return super().fetch(keyword, max_items)

    @staticmethod
    def _demo_data(keyword: str, n: int) -> List[Dict[str, Any]]:
        items = []
        base = random.uniform(10, 150)
        for i in range(min(n, 12)):
            items.append({
                "platform": "pdd",
                "product_id": f"demo_pdd_{i}",
                "title": f"{keyword} 实惠装{i+1} 包邮 热销爆款",
                "price": round(base + random.uniform(-5, 12), 2),
                "sales_count": random.randint(100, 10000),
                "seller_name": f"品牌{i+1}官方旗舰店",
                "seller_credit": "",
                "product_url": f"https://mobile.yangkeduo.com/goods.html?goods_id=demo_{i}",
                "store_url": f"https://mobile.yangkeduo.com/store.html?mall_id=demo_{i}",
                "image_url": "",
                "region": random.choice(["广东广州", "浙江义乌", "江苏苏州", "福建泉州"]),
                "raw_data": {},
            })
        return items

    def _build_search_url(self, keyword: str, page_num: int = 1) -> str:
        return f"{self.BASE_URL}/search_result.html?search_key={quote_plus(keyword)}&page={page_num}"

    def _wait_for_content(self, page, timeout: int = 20):
        """等待真实商品内容加载完成（React 动态渲染完成）

        在 headed + 持久化 Chrome 模式下，PDD 不再重定向到登录页，
        搜索 API 应该能正常返回数据。等待 dataMap 中出现商品列表。
        """
        import time
        deadline = time.time() + timeout
        min_items_found = 3

        while time.time() < deadline:
            # 检查是否被重定向到登录页
            if "login" in page.url.lower():
                logger.warning("[pdd] 被重定向到登录页，需要重新登录")
                return False

            # 方法1: 检查 dataMap 中的 goodsList
            goods_count = page.evaluate("""() => {
                const rd = window.rawData;
                if (!rd) return -1;
                const st = rd.stores?.store;
                if (!st) return -2;
                const dm = st.dataMap;
                if (!dm) return -3;
                let total = 0;
                for (const k of Object.keys(dm)) {
                    if (dm[k]?.goodsList) total += dm[k]?.goodsList?.length || 0;
                }
                return total;
            }""")
            if goods_count >= min_items_found:
                logger.info("[pdd] dataMap 已加载 %d 个商品", goods_count)
                return True

            # 方法2: 检查 DOM 中是否有价格
            try:
                body = page.inner_text("body")
                price_count = body.count("¥")
                if price_count >= min_items_found:
                    logger.info("[pdd] DOM 中发现 %d 个价格标签", price_count)
                    return True
            except Exception:
                pass

            time.sleep(1)

        logger.warning("[pdd] 等待超时 %ds (dataMap=%s)", timeout,
                       goods_count if 'goods_count' in dir() else '?')
        return False

    def _extract_items(self, page, keyword: str, max_items: int) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []

        # 等待动态内容加载完成
        self._wait_for_content(page, timeout=20)

        # 模拟真人浏览
        self._simulate_natural_scroll(page)

        # 方法1: JS 全局数据（最可靠）
        for js_expr in [
            "() => window.rawData ? JSON.stringify(window.rawData) : null",
            "() => window.__INITIAL_STATE__ ? JSON.stringify(window.__INITIAL_STATE__) : null",
            "() => window.__NUXT__ ? JSON.stringify(window.__NUXT__) : null",
        ]:
            try:
                raw = page.evaluate(js_expr)
                if raw:
                    data = json.loads(raw)
                    # 优先从 dataMap 提取（React 渲染后的数据结构）
                    data_map = (data.get("stores", {}).get("store", {}).get("dataMap", {})
                                or data.get("data", {}).get("dataMap", {}))
                    if data_map:
                        for tab_key in data_map:
                            tab = data_map[tab_key]
                            goods_list = tab.get("goodsList") or tab.get("list") or []
                            for item in goods_list[:max_items]:
                                parsed = self._parse_product(item)
                                if parsed:
                                    items.append(parsed)
                        if items:
                            return items

                    # 回退到旧数据路径
                    goods = (data.get("goodsList") or data.get("data", {}).get("goodsList")
                             or data.get("storeList", {}).get("goods")
                             or data.get("list") or data.get("data", {}).get("list") or [])
                    if goods:
                        for item in goods[:max_items]:
                            parsed = self._parse_product(item)
                            if parsed:
                                items.append(parsed)
                        if items:
                            return items
            except Exception:
                continue

        # 方法2: DOM 选择器（多版本兼容）
        card_selectors = [
            "[class*='goods-item']",
            "[class*='goodsItem']",
            "[class*='product-item']",
            ".goods-list > div",
            "[class*='item'] a[href*='goods']",
            "div[data-spm*='goods']",
        ]
        for sel in card_selectors:
            els = page.query_selector_all(sel)
            if len(els) >= 2:
                for el in els:
                    if len(items) >= max_items:
                        break
                    try:
                        # 模拟真人滚动到元素附近
                        self._simulate_scroll(page, random.randint(100, 300))

                        text = el.inner_text()
                        if "¥" not in text or len(text) < 15:
                            continue
                        parsed = self._parse_card_text(text, el)
                        if parsed:
                            items.append(parsed)
                    except Exception:
                        continue
                if items:
                    return items

        # 方法3: 含价格的容器
        try:
            els = page.query_selector_all("div:has(span:has-text('¥')):has(img)")
            for el in els[:max_items * 2]:
                if len(items) >= max_items:
                    break
                text = el.inner_text()
                if "¥" not in text or len(text) < 20:
                    continue
                parsed = self._parse_card_text(text, el)
                if parsed:
                    items.append(parsed)
        except Exception:
            pass

        return items

    def _parse_product(self, item: Dict[str, Any]) -> Dict[str, Any] | None:
        try:
            title = item.get("goods_name", "") or item.get("hdGoodsName", "") or item.get("name", "")
            if not title:
                return None

            price_raw = item.get("minNormalPrice", 0) or item.get("minGroupPrice", 0) or item.get("price", 0)
            price = float(price_raw) / 100 if price_raw else 0
            if price <= 0:
                return None

            product_id = str(item.get("goods_id", "") or item.get("goodsId", "") or item.get("id", ""))
            if not product_id:
                return None

            sales_text = str(item.get("sales", 0) or item.get("cnt", 0) or item.get("soldQuantity", 0))
            seller = item.get("mall_name", "") or item.get("merchantName", "") or item.get("shopName", "")
            if isinstance(seller, dict):
                seller = seller.get("name", "")

            # 提取店铺链接
            mall_id = str(item.get("mall_id", "") or item.get("mallId", "") or "")
            store_url = ""
            if mall_id:
                store_url = f"{self.BASE_URL}/store.html?mall_id={mall_id}"
            elif item.get("storeUrl"):
                store_url = item["storeUrl"]
            elif item.get("mallUrl"):
                store_url = item["mallUrl"]

            image_url = item.get("hdThumbUrl", "") or item.get("thumbUrl", "") or item.get("image", "")
            if image_url and not image_url.startswith("http"):
                image_url = "https:" + image_url

            goods_url = f"https://mobile.yangkeduo.com/goods.html?goods_id={product_id}"

            return {
                "platform": "pdd",
                "product_id": product_id,
                "title": title.strip(),
                "price": price,
                "sales_count": self._parse_sales(sales_text),
                "seller_name": seller,
                "seller_credit": "",
                "product_url": goods_url,
                "store_url": store_url,
                "image_url": image_url,
                "region": item.get("location", "") or item.get("region", "") or "",
                "raw_data": item,
            }
        except Exception:
            return None

    def _parse_card_text(self, text: str, el=None) -> Dict[str, Any] | None:
        try:
            lines = [l.strip() for l in text.split("\n") if l.strip()]
            if not lines:
                return None

            title = lines[0]
            price = 0.0
            sales = 0
            for l in lines:
                if "¥" in l:
                    p = self._parse_price(l)
                    if p > 0:
                        price = p
                if "售" in l or "已售" in l:
                    s = self._parse_sales(l)
                    if s > 0:
                        sales = s

            if price <= 0 or len(title) < 5:
                return None

            product_url = ""
            store_url = ""
            if el is not None:
                try:
                    href = el.get_attribute("href") or ""
                    if href and "goods_id" in href:
                        product_url = href if href.startswith("http") else f"{self.BASE_URL}{href}"
                except Exception:
                    pass
                # 尝试提取店铺链接
                try:
                    store_el = el.query_selector("a[href*='store'], a[href*='mall']")
                    if store_el:
                        store_href = store_el.get_attribute("href") or ""
                        if store_href:
                            store_url = store_href if store_href.startswith("http") else f"{self.BASE_URL}{store_href}"
                except Exception:
                    pass

            return {
                "platform": "pdd",
                "product_id": "",
                "title": title[:80],
                "price": price,
                "sales_count": sales,
                "seller_name": "",
                "seller_credit": "",
                "product_url": product_url,
                "store_url": store_url,
                "image_url": "",
                "region": "",
                "raw_data": {"text": text},
            }
        except Exception:
            return None


__all__ = ["ScraperPdd"]
