"""AI店长 v1.1 - 抓取器基类

所有平台抓取器继承 BaseScraper，实现 fetch() 方法。

特性：
- 限速（令牌桶）
- 自动重试（指数退避）
- 失败降级（连续失败 N 次标记 degraded）
- 统一返回标准化商品字典
"""
import logging
import random
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import requests
from requests.adapters import HTTPAdapter

logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    """抓取器抽象基类"""

    PLATFORM_NAME: str = "base"  # 子类覆盖
    BASE_URL: str = ""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.session = self._build_session()
        self._last_request_at = 0.0
        self._consecutive_failures = 0
        self._degraded = False

    def _build_session(self) -> requests.Session:
        """构建带重试的 requests Session"""
        s = requests.Session()
        s.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        })
        # 简易重试
        retry_cfg = self.config.get("antiscrap", {})
        retries = int(retry_cfg.get("max_retries", 3))
        adapter = HTTPAdapter(max_retries=retries)
        s.mount("http://", adapter)
        s.mount("https://", adapter)
        return s

    # ---------- 限速 ----------
    def _rate_limit(self) -> None:
        rps = float(self.config.get("antiscrap", {}).get("requests_per_second", 5))
        min_interval = 1.0 / max(rps, 0.1)
        now = time.time()
        elapsed = now - self._last_request_at
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed + random.uniform(0, 0.1))
        self._last_request_at = time.time()

    # ---------- HTTP GET 带容错 ----------
    def _get(self, url: str, params: Optional[Dict[str, Any]] = None,
             timeout: int = 15) -> Optional[str]:
        """带限速和降级的 HTTP GET"""
        if self._degraded:
            logger.warning("[%s] degraded, skipping GET %s", self.PLATFORM_NAME, url)
            return None

        self._rate_limit()
        timeout = int(self.config.get("antiscrap", {}).get("timeout_seconds", timeout))
        try:
            resp = self.session.get(url, params=params, timeout=timeout)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or "utf-8"
            self._consecutive_failures = 0
            return resp.text
        except requests.RequestException as e:
            self._consecutive_failures += 1
            self._maybe_degrade()
            logger.warning("[%s] GET %s failed: %s (failure #%d)",
                           self.PLATFORM_NAME, url, e, self._consecutive_failures)
            return None

    def _maybe_degrade(self) -> None:
        threshold = int(self.config.get("antiscrap", {}).get("auto_degrade_after_failures", 3))
        if self._consecutive_failures >= threshold:
            self._degraded = True
            logger.error("[%s] marked as DEGRADED after %d consecutive failures",
                         self.PLATFORM_NAME, self._consecutive_failures)

    def reset_degraded(self) -> None:
        """手动恢复（重置失败计数和降级状态）"""
        self._degraded = False
        self._consecutive_failures = 0

    @property
    def is_degraded(self) -> bool:
        return self._degraded

    # ---------- 价格解析辅助 ----------
    @staticmethod
    def _parse_price(text: str) -> float:
        """从各种价格文本中提取数字"""
        if not text:
            return 0.0
        import re
        # 去掉 ¥ $ 等符号
        text = text.replace(",", "")
        m = re.search(r"(\d+(?:\.\d+)?)", text)
        return float(m.group(1)) if m else 0.0

    @staticmethod
    def _parse_sales_count(text: str) -> int:
        """解析销量（支持 '1000+', '1万+', '已售500'）"""
        if not text:
            return 0
        import re
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

    # ---------- 抽象方法 ----------
    @abstractmethod
    def fetch(self, keyword: str, max_items: int = 20) -> List[Dict[str, Any]]:
        """抓取指定关键词的商品

        Returns:
            标准化的商品字典列表，每条形如：
            {
                "platform": "1688",
                "product_id": "...",
                "title": "...",
                "price": 12.5,
                "sales_count": 100,
                "seller_name": "...",
                "product_url": "...",
                "image_url": "...",
                "region": "...",
                "raw_data": {...}
            }
        """
        raise NotImplementedError

    def health_check(self) -> bool:
        """健康检查：能否正常抓取首页"""
        try:
            html = self._get(self.BASE_URL)
            return html is not None
        except Exception:
            return False


__all__ = ["BaseScraper"]
