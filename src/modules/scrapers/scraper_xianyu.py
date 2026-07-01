"""AI店长 v1.2 - 闲鱼 Playwright 抓取器（反风控增强版）

核心改进：
1. 继承 PlaywrightBase 的全套反风控机制
2. 提取店铺链接（store_url / user_url）
3. 更精确的 DOM 选择器
4. 随机滚动 + 点击模拟
"""
import json
import logging
import random
import re
import time
from typing import Any, Dict, List
from urllib.parse import quote_plus

from .playwright_base import PlaywrightScraper

logger = logging.getLogger(__name__)


class ScraperXianyu(PlaywrightScraper):
    PLATFORM_NAME = "闲鱼"
    PLATFORM_KEY = "xianyu"

    CONTEXT_CONFIG = {
        "viewport": {"width": 390, "height": 844},
        "is_mobile": True,
        "locale": "zh-CN",
    }

    SEARCH_URL = "https://www.goofish.com/search"

    def fetch(self, keyword: str, max_items: int = 20) -> List[Dict[str, Any]]:
        if not self._has_login_state():
            return self._demo_data(keyword, max_items)
        result = super().fetch(keyword, max_items)
        if not result:
            logger.info("[xianyu] fetch returned 0 items, using demo data")
            return self._demo_data(keyword, max_items)
        return result

    @staticmethod
    def _dismiss_country_selector(page) -> None:
        """关闭国家/地区选择器"""
        import time as _t
        try:
            page.keyboard.press("Escape")
            _t.sleep(0.5)
        except: pass
        try:
            # 检查是否真的需要关闭国家选择器
            body = page.inner_text("body")
            if not any(code in body for code in ['+82', '+81', '+44', '+1']):
                return  # 没有国家选择器，跳过
            
            # JS 点击 +86
            page.evaluate("""() => {
                const all = document.querySelectorAll('*');
                for (const el of all) {
                    const text = el.innerText || '';
                    if (text.includes('+86') && text.length < 30) {
                        el.click();
                        return 'clicked';
                    }
                }
                return 'not found';
            }""")
            _t.sleep(3)
        except Exception:
            pass

    @staticmethod
    def _demo_data(keyword: str, n: int) -> List[Dict[str, Any]]:
        items = []
        base = random.uniform(5, 120)
        for i in range(min(n, 12)):
            items.append({
                "platform": "xianyu",
                "product_id": f"demo_xianyu_{i}",
                "title": f"{keyword} 自用{i+1} 闲置转卖 成色极新",
                "price": round(base + random.uniform(-5, 15), 2),
                "sales_count": random.randint(1, 200),
                "seller_name": f"闲鱼卖家{i+1}",
                "seller_credit": "优秀",
                "product_url": f"https://www.goofish.com/item?id=demo_{i}",
                "store_url": f"https://www.goofish.com/user?id=demo_{i}",
                "image_url": "",
                "region": random.choice(["广东深圳", "上海", "北京朝阳", "浙江杭州", "四川成都"]),
                "raw_data": {},
            })
        return sorted(items, key=lambda x: x["price"])

    # ---------- 数据验证 ----------

    # 系统错误关键词，匹配则丢弃
    _ERROR_KEYWORDS = ["错误", "请稍后再试", "系统繁忙", "服务器错误",
                        "重新加载", "稍后重试", "网络异常", "访问过于频繁",
                        "出错了", "加载失败", "请求失败", "稍后再试",
                        "发生错误", "请稍后", "稍候再试", "繁忙"]

    # 非商品内容关键词（平台通知、推广等）
    _NOT_PRODUCT_KEYWORDS = ["功能", "升级啦", "网页版", "公告", "通知",
                              "版本", "APP", "客户端", "新功能", "活动",
                              "红包", "领券", "签到", "抽奖"]

    @classmethod
    def _is_valid_product(cls, item: Dict[str, Any]) -> bool:
        title = item.get("title", "")
        if not title or len(title) < 12:
            return False
        for kw in cls._ERROR_KEYWORDS:
            if kw in title:
                return False
        for kw in cls._NOT_PRODUCT_KEYWORDS:
            if kw in title:
                return False
        price = item.get("price", 0)
        if price <= 0:
            return False
        return True

    @classmethod
    def _deduplicate(cls, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen = set()
        result = []
        for it in items:
            key = (it.get("title", ""), it.get("price", 0))
            if key not in seen:
                seen.add(key)
                result.append(it)
        return result

    # ---------- 搜索 ----------

    @staticmethod
    def _dismiss_overlays(page) -> None:
        """关闭弹窗"""
        ScraperXianyu._dismiss_country_selector(page)
        try:
            for sel in ["text=关闭", "text=取消", "text=跳过", "[class*=close]", "[class*=Close]"]:
                try:
                    el = page.locator(sel).first
                    if el.is_visible(timeout=500):
                        el.click()
                        break
                except: continue
        except: pass

    def _build_search_url(self, keyword: str, page_num: int = 1) -> str:
        return f"{self.SEARCH_URL}?q={quote_plus(keyword)}&page={page_num}"

    def _extract_items(self, page, keyword: str, max_items: int) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        api_responses = []

        # NOTE: response listener already registered in _launch_browser/stealth
        # Re-register here for additional capture
        def on_response(response):
            try:
                url = response.url
                ct = response.headers.get("content-type", "")
                if response.status == 200 and ("json" in ct or "mtop" in url):
                    try:
                        api_responses.append(response.json())
                    except Exception:
                        pass
            except Exception:
                pass

        page.on("response", on_response)

        # 弹窗 + 滚动
        self._dismiss_overlays(page)
        self._simulate_natural_scroll(page)
        self._random_delay(4, 6)  # 等待 API 响应到达

        # 处理拦截到的 API 数据
        for data in api_responses:
            goods = self._extract_from_json_data(data)
            if goods:
                logger.info("[xianyu] API拦截成功: %d 商品", len(goods))
            for item in goods[:max_items]:
                parsed = self._parse_product(item)
                if parsed and self._is_valid_product(parsed):
                    items.append(parsed)
            if items:
                return self._deduplicate(items)

        if not api_responses:
            logger.info("[xianyu] 未拦截到API响应，尝试JS全局数据...")
        else:
            logger.info("[xianyu] 拦截到 %d 个API响应但未提取到商品", len(api_responses))

        # ── 策略2: JS 全局变量 ──
        for js_expr in [
            "() => window.__INIT_DATA__ ? JSON.stringify(window.__INIT_DATA__) : null",
            "() => window.__NUXT__ ? JSON.stringify(window.__NUXT__) : null",
            "() => window.pageData ? JSON.stringify(window.pageData) : null",
            "() => { try { return JSON.stringify(window.__RENDER_DATA__); } catch(e) { return null; } }",
        ]:
            try:
                raw = page.evaluate(js_expr)
                if raw:
                    data = json.loads(raw)
                    goods = self._extract_from_json_data(data)
                    if goods:
                        for item in goods[:max_items]:
                            parsed = self._parse_product(item)
                            if parsed and self._is_valid_product(parsed):
                                items.append(parsed)
                        if items:
                            items = self._deduplicate(items)
                            return items
            except Exception:
                continue

        # 方法2: DOM 卡片选择器（多版本兼容）
        card_selectors = [
            "[class*='card-item']",
            "[class*='goods-item']",
            "[class*='item-card']",
            "[class*='search-item']",
            "[class*='result-item']",
            "div[data-spm*='item']",
            "li[class*='item']",
            "div[class*='waterfall'] > div",
        ]
        for sel in card_selectors:
            els = page.query_selector_all(sel)
            if len(els) >= 2:
                for el in els:
                    if len(items) >= max_items:
                        break
                    try:
                        self._simulate_scroll(page, random.randint(100, 300))
                        text = el.inner_text()
                        if "¥" not in text or len(text) < 15:
                            continue
                        parsed = self._parse_card_text(text, el)
                        if parsed and self._is_valid_product(parsed):
                            items.append(parsed)
                    except Exception:
                        continue
                if items:
                    return self._deduplicate(items)

        # 方法3: 通用文本提取（最后备用）
        if not items:
            items = self._extract_from_text_scan(page, max_items)

        if not items:
            logger.info("[xianyu] 页面内容预览: %s", page.inner_text("body")[:300])

        return self._deduplicate(items)

    def _extract_from_text_scan(self, page, max_items: int) -> List[Dict[str, Any]]:
        """JS扫描DOM提取商品"""
        items = []
        try:
            result = page.evaluate("""() => {
                const items = [];
                const seen = new Set();

                function getPrice(text) {
                    const lines = text.split('\\n');
                    // 找短¥行（价格行通常<12字符）
                    for (const l of lines) {
                        const t = l.trim();
                        if ((t.startsWith('¥') || t.startsWith('￥')) && t.length < 12) {
                            const n = parseFloat(t.replace(/[¥￥\\s]/g, ''));
                            if (n > 0 && n < 99999) return n;
                        }
                    }
                    // 找任意含¥的短行
                    for (const l of lines) {
                        const t = l.trim();
                        if ((t.includes('¥') || t.includes('￥')) && t.length < 15) {
                            const m = t.match(/[¥￥]\\s*([\\d]+)/);
                            if (m) { const n = parseInt(m[1]); if (n > 0 && n < 99999) return n; }
                        }
                    }
                    return 0;
                }

                function getTitle(lines) {
                    for (const l of lines) {
                        const t = l.trim();
                        if (t.length > 8 && !/^[¥￥\\d.\\s]+$/.test(t)) return t;
                    }
                    return lines[0] || '';
                }

                const allLinks = document.querySelectorAll('a[href]');
                for (const link of allLinks) {
                    if (items.length >= 30) break;
                    const text = (link.innerText || '').trim();
                    if (!text.includes('¥') && !text.includes('￥')) continue;
                    if (text.length < 20 || text.length > 800) continue;

                    const price = getPrice(text);
                    if (price <= 0) continue;

                    const allLines = text.split('\\n').map(l => l.trim()).filter(l => l.length > 0);
                    const title = getTitle(allLines);
                    if (title.length < 6) continue;

                    const key = title.substring(0, 30);
                    if (seen.has(key)) continue;
                    seen.add(key);

                    let sales = 0, wantCount = 0, viewCount = 0, location = '', seller = '';
                    for (const l of allLines) {
                        if (/人想要/.test(l)) { const m = l.match(/(\\d+)/); if (m) wantCount = parseInt(m[1]); }
                        else if (/浏览/.test(l) || /次浏览/.test(l)) { const m = l.match(/(\\d+)/); if (m) viewCount = parseInt(m[1]); }
                        else if (/已售|卖出|累计交易/.test(l)) { const m = l.match(/(\\d+)/); if (m) sales = parseInt(m[1]); }
                        if (/广东|北京|上海|浙江|江苏|四川|深圳|广州|杭州/.test(l)) location = l;
                    }

                    items.push({
                        title: title.substring(0, 80),
                        price: price,
                        href: link.href || link.getAttribute('href') || '',
                        seller: seller, location: location, sales: sales,
                        wantCount: wantCount, viewCount: viewCount,
                    });
                }
                return JSON.stringify(items);
            }""")
            import json
            raw_items = json.loads(result)
            for item in raw_items[:max_items]:
                items.append({
                    "platform": "xianyu",
                    "product_id": f"js_{len(items)}",
                    "title": item.get("title", "")[:80],
                    "price": item.get("price", 0),
                    "sales_count": item.get("sales", 0),
                    "want_count": item.get("wantCount", 0),
                    "view_count": item.get("viewCount", 0),
                    "seller_name": item.get("seller", ""),
                    "seller_credit": "",
                    "product_url": item.get("href", ""),
                    "store_url": "",
                    "image_url": "",
                    "region": item.get("location", ""),
                    "raw_data": item,
                })
            logger.info("[xianyu] JS text scan: %d items", len(items))
        except Exception as e:
            logger.debug("JS text scan error: %s", e)

        return items

    def _extract_from_json_data(self, data: dict) -> List[dict]:
        paths = [
            ["data", "itemList"], ["data", "list"], ["data", "resultList"],
            ["data", "searchResult", "itemList"], ["props", "pageProps", "searchData", "itemList"],
            ["list"], ["resultList"], ["itemList"],
            ["data", "data", "itemList"],
        ]
        for path in paths:
            cur = data
            try:
                for key in path:
                    cur = cur[key]
                if isinstance(cur, list):
                    return cur
            except (KeyError, TypeError):
                continue
        return []

    def _parse_product(self, item: Dict[str, Any]) -> Dict[str, Any] | None:
        try:
            title = (item.get("title", "") or item.get("itemTitle", "")
                     or item.get("goodsName", "") or item.get("name", ""))
            if not title:
                return None
            title = re.sub(r"<[^>]+>", "", title).strip()
            if not title:
                return None

            price = self._parse_price(str(item.get("price", "") or item.get("priceText", "")
                                           or item.get("itemPrice", "")))
            if price <= 0:
                return None

            product_id = str(item.get("id", "") or item.get("itemId", "")
                             or item.get("itemIdStr", "") or item.get("goodsId", ""))
            if not product_id:
                return None

            sales_text = str(item.get("wantNum", 0) or item.get("soldNum", 0)
                             or item.get("likeCount", 0))
            sales = self._parse_sales(sales_text)

            seller = item.get("userNickName", "") or item.get("userName", "") or item.get("nick", "")

            # 提取用户/店铺主页链接
            user_id = str(item.get("userId", "") or item.get("sellerId", "") or "")
            store_url = ""
            if user_id:
                store_url = f"https://www.goofish.com/user?id={user_id}"
            elif item.get("userUrl"):
                store_url = item["userUrl"]
            elif item.get("sellerUrl"):
                store_url = item["sellerUrl"]

            image_url = item.get("picUrl", "") or item.get("pic", "") or item.get("image", "")
            if image_url and not image_url.startswith("http"):
                image_url = "https:" + image_url

            detail_url = item.get("detailUrl", "") or item.get("url", "") or item.get("itemUrl", "")
            if not detail_url and product_id:
                detail_url = f"https://m.goofish.com/item?id={product_id}"

            return {
                "platform": "xianyu",
                "product_id": product_id,
                "title": title,
                "price": price,
                "sales_count": sales,
                "seller_name": seller,
                "seller_credit": item.get("userCreditLevel", "") or item.get("credit", ""),
                "product_url": detail_url,
                "store_url": store_url,
                "image_url": image_url,
                "region": item.get("location", "") or item.get("region", "") or "",
                "raw_data": item,
            }
        except Exception as e:
            logger.debug("xianyu parse JSON error: %s", e)
            return None

    def _parse_card_text(self, text: str, el=None) -> Dict[str, Any] | None:
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

            sales_text = ""
            for l in lines:
                if "人想要" in l or "已售" in l or "want" in l.lower():
                    sales_text = l
                    break

            product_url = ""
            store_url = ""
            product_id = ""
            if el is not None:
                try:
                    href = el.get_attribute("href") or ""
                    if href:
                        product_url = href if href.startswith("http") else f"https://www.goofish.com{href}"
                        id_match = re.search(r"id[=/](\d+)", href)
                        if id_match:
                            product_id = id_match.group(1)
                except Exception:
                    pass
                # 尝试提取用户主页链接
                try:
                    user_el = el.query_selector("a[href*='user'], a[href*='seller'], a[href*='profile']")
                    if user_el:
                        user_href = user_el.get_attribute("href") or ""
                        if user_href:
                            store_url = user_href if user_href.startswith("http") else f"https://www.goofish.com{user_href}"
                except Exception:
                    pass

            return {
                "platform": "xianyu",
                "product_id": product_id,
                "title": title[:80],
                "price": price,
                "sales_count": self._parse_sales(sales_text),
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

    def health_check(self) -> bool:
        html = self._requests_get("https://www.goofish.com/")
        return html is not None and len(html) > 500


__all__ = ["ScraperXianyu"]
