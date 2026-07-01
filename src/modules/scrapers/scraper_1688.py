"""AI店长 v1.2 - 1688 Playwright 抓取器

使用 Chrome 持久化配置 + stealth 反检测抓取 1688 搜索结果。
"""
import json
import logging
import random
import re
import time
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import quote_plus

from .playwright_base import PlaywrightScraper

logger = logging.getLogger(__name__)


class Scraper1688(PlaywrightScraper):
    PLATFORM_NAME = "1688"
    PLATFORM_KEY = "1688"
    HEADLESS_DEFAULT = False

    CONTEXT_CONFIG = {
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "viewport": {"width": 1280, "height": 800},
        "is_mobile": False,
        "locale": "zh-CN",
    }

    BASE_URL = "https://s.1688.com/selloffer/offer_search.htm"

    def _launch_browser(self):
        """1688 专用：使用系统 Chrome + storage_state 注入 cookie"""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.error("未安装 playwright")
            return None, None

        self._pw_ctx = sync_playwright()
        p = self._pw_ctx.start()
        self._pw = p

        args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--no-sandbox",
        ]

        try:
            # 使用系统 Chrome 启动（与登录时保持指纹一致）
            try:
                browser = p.chromium.launch(headless=False, channel="chrome", args=args)
            except Exception:
                browser = p.chromium.launch(headless=False, args=args)
            self._browser = browser

            # 用 storage_state 注入登录 cookie
            ctx = browser.new_context(
                storage_state=str(self._get_state_path()) if self._has_login_state() else None,
                user_agent=self.CONTEXT_CONFIG["user_agent"],
                viewport=self.CONTEXT_CONFIG["viewport"],
                locale="zh-CN",
            )
            self._ctx = ctx
            page = ctx.new_page()
            self._page = page
            self._apply_stealth(page)
            return self._pw_ctx, page

        except Exception as e:
            logger.error("[1688] Browser launch failed: %s", e)
            self._cleanup_browser()
            return None, None

    def _cleanup_browser(self):
        """安全关闭"""
        try:
            if self._ctx:
                self._ctx.close()
            if self._browser:
                self._browser.close()
        except Exception:
            pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        try:
            if self._pw_ctx:
                self._pw_ctx.stop()
        except Exception:
            pass
        self._ctx = None
        self._page = None
        self._browser = None
        self._pw = None
        self._pw_ctx = None

    def fetch(self, keyword: str, max_items: int = 20) -> List[Dict[str, Any]]:
        if not self._has_login_state():
            logger.info("[1688] no login state, using demo data for '%s'", keyword)
            return self._demo_data(keyword, max_items)
        results: List[Dict[str, Any]] = []
        pw, page = self._launch_browser()
        if page is None:
            return self._demo_data(keyword, max_items)

        url = self._build_search_url(keyword)
        try:
            page.goto(url, timeout=30000, wait_until="domcontentloaded")
            self._random_delay(3, 5)

            current_url = page.url.lower()
            if "login" in current_url or "signin" in current_url:
                logger.warning("[1688] Login required, state may be expired")
                return self._demo_data(keyword, max_items)

            self._simulate_natural_scroll(page)
            self._random_delay(2, 3)
            results = self._extract_items(page, keyword, max_items)
        except Exception as e:
            logger.error("[1688] Fetch '%s' error: %s", keyword, e)
        finally:
            self._cleanup_browser()

        if not results:
            logger.warning("[1688] No items found for '%s', page URL: %s", keyword, page.url if page else "N/A")
        else:
            logger.info("[1688] Fetched %d items for '%s'", len(results), keyword)
        return results

    @staticmethod
    def _demo_data(keyword: str, n: int) -> List[Dict[str, Any]]:
        items = []
        base = random.uniform(5, 80)
        for i in range(min(n, 12)):
            items.append({
                "platform": "1688", "product_id": f"demo_1688_{i}",
                "title": f"{keyword} 批发{i+1} 高品质 一手货源",
                "price": round(base + random.uniform(-3, 8), 2),
                "sales_count": random.randint(50, 5000),
                "seller_name": f"义乌{i+1}号批发商",
                "product_url": "#", "image_url": "",
                "region": "浙江金华", "raw_data": {},
            })
        return sorted(items, key=lambda x: x["price"])

    def _build_search_url(self, keyword: str, page_num: int = 1) -> str:
        return f"{self.BASE_URL}?keywords={quote_plus(keyword)}&beginPage={page_num}"

    def _extract_items(self, page, keyword: str, max_items: int) -> List[Dict[str, Any]]:
        items_raw: List[Dict[str, Any]] = []

        # 方法1: 尝试从 window.__data / window.__INIT_DATA 提取 JSON
        for js_expr in [
            "() => window.__data ? JSON.stringify(window.__data) : null",
            "() => window.__INIT_DATA ? JSON.stringify(window.__INIT_DATA) : null",
            "() => window.__INITIAL_STATE__ ? JSON.stringify(window.__INITIAL_STATE__) : null",
        ]:
            try:
                raw = page.evaluate(js_expr)
                if raw:
                    data = json.loads(raw)
                    offer_list = (data.get("offerList") or data.get("data", {}).get("offerList")
                                  or data.get("resultList") or data.get("data", {}).get("resultList") or [])
                    if offer_list:
                        for item in offer_list[:max_items]:
                            parsed = self._parse_product(item)
                            if parsed:
                                items_raw.append(parsed)
                        if items_raw:
                            return items_raw
            except Exception:
                continue

        # 方法2: DOM 商品卡片
        card_selectors = [
            '[data-spm="doffer"]', '.sm-offer-card', '[class*="offer-card"]',
            '[class*="offerCard"]', 'div[data-id]', '[class*="offer-item"]',
        ]
        for sel in card_selectors:
            els = page.query_selector_all(sel)
            if len(els) >= 2:
                for el in els:
                    if len(items_raw) >= max_items:
                        break
                    try:
                        text = el.inner_text()
                        parsed = self._parse_card_text(text, page, el)
                        if parsed:
                            items_raw.append(parsed)
                    except Exception:
                        continue
                if items_raw:
                    return items_raw

        # 方法3: 全文找所有包含价格的卡片
        cards = page.query_selector_all("div:has(img):has(span:has-text('¥'))")
        for card in cards[:max_items * 3]:
            if len(items_raw) >= max_items:
                break
            try:
                text = card.inner_text()
                if "¥" not in text or len(text) < 20:
                    continue
                parsed = self._parse_card_text(text, page, card)
                if parsed and parsed["price"] > 0:
                    items_raw.append(parsed)
            except Exception:
                continue

        return items_raw

    def _parse_product(self, item: Dict[str, Any]) -> Dict[str, Any] | None:
        """从 JSON 商品对象解析"""
        try:
            title = item.get("subject", "") or item.get("title", "")
            if not title:
                return None
            price_raw = item.get("priceInfo", {})
            price_str = ""
            if isinstance(price_raw, dict):
                price_str = price_raw.get("price", "") or price_raw.get("promotionPrice", "")
            elif isinstance(price_raw, str):
                price_str = price_raw
            price = self._parse_price(price_str)
            if price <= 0:
                return None
            product_id = str(item.get("id", "") or item.get("offerId", ""))
            if not product_id:
                return None
            sales_text = str(item.get("sales", "") or item.get("monthSold", ""))
            if isinstance(item.get("tradeQuantity"), dict):
                sales_text = str(item["tradeQuantity"].get("number", ""))
            seller = item.get("company", "") or item.get("shopName", "")
            if isinstance(seller, dict):
                seller = seller.get("name", "")
            image_url = item.get("image", "") or item.get("imageUrl", "")
            if image_url and not image_url.startswith("http"):
                image_url = "https:" + image_url
            offer_url = item.get("detailUrl", "") or item.get("url", "")
            if not offer_url and product_id:
                offer_url = f"https://detail.1688.com/offer/{product_id}.html"
            return {
                "platform": "1688", "product_id": product_id, "title": title.strip(),
                "price": price, "sales_count": self._parse_sales(sales_text),
                "seller_name": seller, "product_url": offer_url,
                "image_url": image_url, "raw_data": item,
            }
        except Exception as e:
            logger.debug("1688 parse JSON error: %s", e)
            return None

    def _parse_card_text(self, text: str, page=None, el=None) -> Dict[str, Any] | None:
        """从卡片文本解析（回退方案）"""
        try:
            lines = [l.strip() for l in text.split("\n") if l.strip()]
            if not lines:
                return None
            title = lines[0]
            if "¥" not in text or len(title) < 5:
                return None
            price = 0.0
            for l in lines:
                if "¥" in l:
                    p = self._parse_price(l)
                    if p > 0:
                        price = p
                        break
            if price <= 0:
                return None
            sales = 0
            for l in lines:
                if "售" in l:
                    s = self._parse_sales(l)
                    if s > 0:
                        sales = s
                        break
            product_url = ""
            product_id = ""
            if el is not None:
                try:
                    href = el.get_attribute("data-offerid") or ""
                    if href:
                        product_id = href
                        product_url = f"https://detail.1688.com/offer/{href}.html"
                except Exception:
                    pass
            return {
                "platform": "1688", "product_id": product_id, "title": title[:80],
                "price": price, "sales_count": sales, "seller_name": "",
                "product_url": product_url, "image_url": "", "raw_data": {"text": text},
            }
        except Exception:
            return None


__all__ = ["Scraper1688"]
