"""AI店长 v1.2 - Playwright 抓取器基类（反风控增强版 + 持久化配置文件）

核心功能：
1. playwright-stealth 全套反检测注入
2. 持久化用户配置目录（保持浏览器指纹一致）
3. 每平台可配 headless/headed 模式
4. 模拟真人鼠标轨迹（贝塞尔曲线）+ 自然滚动 + 随机延迟
5. User-Agent 轮换 + 窗口微调
"""
import json
import logging
import math
import os
import random
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_USER_AGENTS_DESKTOP = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.2 Safari/605.1.15",
]

_USER_AGENTS_MOBILE = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.2 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/131.0.6778.73 Mobile/15E148 Safari/604.1",
]


class PlaywrightScraper:
    """Playwright 抓取器基类（反风控增强版 + 持久化配置文件）"""

    PLATFORM_NAME: str = "base"
    PLATFORM_KEY: str = ""
    HEADLESS_DEFAULT: bool = True  # 子类可覆盖

    CONTEXT_CONFIG = {
        "viewport": {"width": 1280, "height": 800},
        "is_mobile": False,
        "locale": "zh-CN",
    }

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self._data_dir = Path(__file__).resolve().parent.parent.parent.parent / "data"
        self._state_dir = self._data_dir / "login_states"
        self._state_dir.mkdir(parents=True, exist_ok=True)
        self._profile_dir = self._data_dir / "browser_profiles"
        self._profile_dir.mkdir(parents=True, exist_ok=True)

    @property
    def _headless(self) -> bool:
        """获取是否为无头模式（环境变量 > 配置 > 子类默认值）"""
        # 支持环境变量覆盖（用于 Docker 部署）
        env_key = f"{self.PLATFORM_KEY.upper()}_HEADLESS"
        env_val = os.environ.get(env_key)
        if env_val is not None:
            return env_val.lower() in ("true", "1", "yes")
        antiscrap = self.config.get("antiscrap", {})
        platform_headless = antiscrap.get(f"{self.PLATFORM_KEY}_headless")
        if platform_headless is not None:
            return str(platform_headless).lower() == "true"
        return self.HEADLESS_DEFAULT

    def _get_state_filename(self) -> str:
        key = self.PLATFORM_KEY or self.PLATFORM_NAME.lower()
        return f"{key}_state.json"

    def _get_state_path(self) -> Path:
        return self._state_dir / self._get_state_filename()

    def _has_login_state(self) -> bool:
        return self._get_state_path().exists()

    def _get_profile_path(self) -> Path:
        """持久化用户配置目录（保持浏览器指纹和登录态）"""
        key = self.PLATFORM_KEY or self.PLATFORM_NAME.lower()
        return self._profile_dir / key

    # ---------- 工具方法 ----------

    @staticmethod
    def _parse_price(text: str) -> float:
        if not text:
            return 0.0
        m = re.search(r"(\d+(?:\.\d+)?)", str(text).replace(",", ""))
        return float(m.group(1)) if m else 0.0

    @staticmethod
    def _parse_sales(text: str) -> int:
        if not text:
            return 0
        text = str(text).replace(",", "").replace(" ", "")
        m = re.search(r"(\d+(?:\.\d+)?)([万千]?)", text)
        if not m:
            return 0
        num = float(m.group(1))
        unit = m.group(2)
        if unit == "万":
            num *= 10000
        elif unit == "千":
            num *= 1000
        return int(num)

    # ---------- 反风控：随机延迟 ----------

    @staticmethod
    def _random_delay(min_s: float = 0.5, max_s: float = 2.0):
        time.sleep(random.uniform(min_s, max_s))

    @staticmethod
    def _human_pause():
        time.sleep(random.uniform(0.3, 1.5))

    # ---------- 反风控：鼠标模拟 ----------

    @staticmethod
    def _bezier_curve(start: tuple, end: tuple, control: tuple, steps: int = 25) -> list:
        points = []
        for i in range(steps + 1):
            t = i / steps
            x = (1 - t) ** 2 * start[0] + 2 * (1 - t) * t * control[0] + t ** 2 * end[0]
            y = (1 - t) ** 2 * start[1] + 2 * (1 - t) * t * control[1] + t ** 2 * end[1]
            x += random.uniform(-2, 2)
            y += random.uniform(-2, 2)
            points.append((int(x), int(y)))
        return points

    def _simulate_mouse_move(self, page, target_x: int, target_y: int):
        try:
            viewport = page.viewport_size
            current_x = random.randint(100, (viewport["width"] if viewport else 1280) - 100)
            current_y = random.randint(100, (viewport["height"] if viewport else 800) - 100)
        except Exception:
            current_x, current_y = 640, 400

        ctrl_x = (current_x + target_x) / 2 + random.randint(-100, 100)
        ctrl_y = (current_y + target_y) / 2 + random.randint(-80, 80)
        steps = random.randint(15, 35)
        points = self._bezier_curve(
            (current_x, current_y), (target_x, target_y), (ctrl_x, ctrl_y), steps
        )
        for px, py in points:
            page.mouse.move(px, py)
            time.sleep(random.uniform(0.005, 0.025))

    def _simulate_mouse_click(self, page, selector: str):
        try:
            el = page.query_selector(selector)
            if not el:
                return False
            box = el.bounding_box()
            if not box:
                return False
            target_x = box["x"] + box["width"] * random.uniform(0.3, 0.7)
            target_y = box["y"] + box["height"] * random.uniform(0.3, 0.7)
            self._simulate_mouse_move(page, int(target_x), int(target_y))
            self._random_delay(0.1, 0.3)
            page.mouse.click(target_x, target_y)
            return True
        except Exception as e:
            logger.debug("模拟点击失败: %s", e)
            return False

    # ---------- 反风控：滚动模拟 ----------

    def _simulate_scroll(self, page, distance: int = 0):
        if distance == 0:
            distance = random.randint(200, 600)
        viewport = page.viewport_size
        max_scroll = (viewport["height"] if viewport else 800) * 3
        scrolled = 0
        while scrolled < distance and scrolled < max_scroll:
            chunk = random.randint(30, 120)
            page.mouse.wheel(0, chunk)
            scrolled += chunk
            time.sleep(random.uniform(0.05, 0.2))
            if random.random() < 0.3:
                time.sleep(random.uniform(0.5, 2.0))

    def _simulate_natural_scroll(self, page):
        self._simulate_scroll(page, random.randint(300, 500))
        self._human_pause()
        self._simulate_scroll(page, random.randint(100, 300))
        self._human_pause()
        if random.random() < 0.4:
            page.mouse.wheel(0, -random.randint(50, 150))
            self._human_pause()

    # ---------- 反风控：stealth 注入 ----------

    def _apply_stealth(self, page):
        """注入反检测脚本，优先使用 playwright-stealth"""
        try:
            from playwright_stealth import Stealth
            Stealth().apply_stealth_sync(page)
            logger.debug("[%s] playwright-stealth applied", self.PLATFORM_NAME)
        except ImportError:
            pass
        except Exception as e:
            logger.debug("[%s] playwright-stealth error: %s", self.PLATFORM_NAME, e)

    # ---------- 浏览器启动 ----------

    def _launch_browser(self):
        """启动浏览器实例，返回 (pw, page)。
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.error("未安装 playwright")
            return None, None

        self._pw_ctx = sync_playwright()
        p = self._pw_ctx.start()
        self._pw = p
        self._browser = None
        self._ctx = None
        self._page = None

        args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--disable-features=IsolateOrigins,site-per-process",
            "--disable-infobars",
            "--no-first-run",
            "--no-default-browser-check",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--no-proxy-server",
        ]

        try:
            if not self._headless:
                # 有头模式：系统 Chrome + storage_state（绕过指纹检测）
                try:
                    browser = p.chromium.launch(
                        headless=False,
                        channel="chrome",
                        args=args,
                    )
                except Exception:
                    browser = p.chromium.launch(
                        headless=False,
                        args=args,
                    )
                self._browser = browser
                ctx = self._make_context(browser)
                self._ctx = ctx
                page = ctx.new_page()

            else:
                # ── 无头模式：标准隔离上下文 ──
                browser = p.chromium.launch(headless=True, args=args)
                self._browser = browser
                ctx = self._make_context(browser)
                self._ctx = ctx
                page = ctx.new_page()

            self._page = page
            self._apply_stealth(page)
            return self._pw_ctx, page

        except Exception as e:
            logger.error("[%s] 浏览器启动失败: %s", self.PLATFORM_NAME, e)
            self._cleanup_browser()
            return None, None

    def _cleanup_browser(self):
        """安全关闭浏览器和相关资源"""
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
        self._browser = None
        self._ctx = None
        self._page = None
        self._pw = None
        self._pw_ctx = None

    def _restore_state(self, ctx):
        """将保存的登录态（cookie）导入浏览器上下文"""
        state_path = self._get_state_path()
        if not state_path.exists():
            return

        try:
            with open(str(state_path), "r", encoding="utf-8") as f:
                state = json.load(f)
        except Exception as e:
            logger.warning("[%s] 读取登录态失败: %s", self.PLATFORM_NAME, e)
            return

        # 导入 cookies
        cookies = state.get("cookies", [])
        valid_cookies = []
        for c in cookies:
            if c.get("name") and c.get("value"):
                try:
                    valid_cookies.append({
                        "name": c["name"],
                        "value": c["value"],
                        "domain": c.get("domain", ""),
                        "path": c.get("path", "/"),
                        "httpOnly": c.get("httpOnly", False),
                        "secure": c.get("secure", False),
                        "sameSite": c.get("sameSite", "Lax"),
                    })
                except Exception:
                    pass
        if valid_cookies:
            try:
                ctx.add_cookies(valid_cookies)
                logger.info("[%s] 已导入 %d 个 cookies", self.PLATFORM_NAME, len(valid_cookies))
            except Exception as e:
                logger.warning("[%s] 导入 cookies 失败: %s", self.PLATFORM_NAME, e)

    def _get_ua(self) -> str:
        if self.CONTEXT_CONFIG.get("is_mobile"):
            return random.choice(_USER_AGENTS_MOBILE)
        return random.choice(_USER_AGENTS_DESKTOP)

    def _make_context(self, browser):
        ua = self._get_ua()
        vp = self.CONTEXT_CONFIG["viewport"]
        width = vp["width"] + random.randint(-20, 20)
        height = vp["height"] + random.randint(-20, 20)
        ctx = browser.new_context(
            storage_state=str(self._get_state_path()) if self._has_login_state() else None,
            user_agent=ua,
            viewport={"width": width, "height": height},
            is_mobile=self.CONTEXT_CONFIG.get("is_mobile", False),
            locale=self.CONTEXT_CONFIG.get("locale", "zh-CN"),
            java_script_enabled=True,
            has_touch=self.CONTEXT_CONFIG.get("is_mobile", False),
            device_scale_factor=random.choice([1, 1.25, 1.5, 2]),
            color_scheme="light",
        )
        # 注入反检测 JS
        ctx.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            window.chrome = {runtime: {}};
        """)
        return ctx

    def _check_not_logged_in(self, page) -> bool:
        """检查是否真的需要登录"""
        url_lower = page.url.lower()
        if "passport" in url_lower or "signin" in url_lower or "login" in url_lower:
            return True
        return False

    # ---------- 核心抓取逻辑 ----------

    def _build_search_url(self, keyword: str, page_num: int = 1) -> str:
        raise NotImplementedError

    def _extract_items(self, page, keyword: str, max_items: int) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def fetch(self, keyword: str, max_items: int = 20) -> List[Dict[str, Any]]:
        """用 Playwright 抓取搜索结果（自动选择有头/无头模式）"""
        if not self._has_login_state():
            logger.warning("[%s] 无登录态，需先运行登录管理", self.PLATFORM_NAME)
            return []

        results: List[Dict[str, Any]] = []
        pw, page = self._launch_browser()
        if page is None:
            return []

        url = self._build_search_url(keyword)
        try:
            page.goto(url, timeout=30000, wait_until="domcontentloaded")
            self._random_delay(2, 4)

            # 尝试关闭各种弹窗(国家选择/广告/通知)
            try:
                for sel in ["text=中国", "text=关闭", "text=跳过", "text=确定",
                            "[class*=close]", "[class*=Close]", "[class*=cancel]", "[class*=Cancel]"]:
                    try:
                        el = page.locator(sel).first
                        if el.is_visible(timeout=1000):
                            el.click()
                            time.sleep(0.5)
                    except Exception:
                        continue
            except Exception:
                pass

            if self._check_not_logged_in(page):
                logger.warning("[%s] 登录态已失效，需重新登录", self.PLATFORM_NAME)
                return []

            self._simulate_natural_scroll(page)
            self._random_delay(1, 2)
            results = self._extract_items(page, keyword, max_items)
        except Exception as e:
            logger.error("[%s] 抓取 '%s' 异常: %s", self.PLATFORM_NAME, keyword, e)
        finally:
            self._cleanup_browser()

        logger.info("[%s] fetched %d items for '%s'", self.PLATFORM_NAME, len(results), keyword)
        return results

    def fetch_batch(self, keywords: List[str], max_items_per_kw: int = 10) -> Dict[str, List[Dict[str, Any]]]:
        if not self._has_login_state():
            logger.warning("[%s] 无登录态", self.PLATFORM_NAME)
            return {}

        results: Dict[str, List[Dict[str, Any]]] = {}
        pw, page = self._launch_browser()
        if page is None:
            return results

        for kw in keywords:
            url = self._build_search_url(kw)
            items = []
            try:
                page.goto(url, timeout=45000, wait_until="domcontentloaded")
                self._random_delay(1, 2)

                if self._check_not_logged_in(page):
                    logger.warning("[%s] batch: 登录态失效", self.PLATFORM_NAME)
                    break

                self._simulate_natural_scroll(page)
                self._random_delay(0.5, 1)
                items = self._extract_items(page, kw, max_items_per_kw)
            except Exception as e:
                logger.error("[%s] batch '%s' 异常: %s", self.PLATFORM_NAME, kw, e)

            results[kw] = items
            self._random_delay(0.5, 1.5)

        self._cleanup_browser()
        return results

    def _requests_get(self, url: str, timeout: int = 15) -> Optional[str]:
        try:
            import requests
            resp = requests.get(url, timeout=timeout, headers={
                "User-Agent": self._get_ua(),
            })
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or "utf-8"
            return resp.text
        except Exception as e:
            logger.debug("[%s] requests GET fallback failed: %s", self.PLATFORM_NAME, e)
            return None

    def health_check(self) -> bool:
        return self._has_login_state()


__all__ = ["PlaywrightScraper"]
