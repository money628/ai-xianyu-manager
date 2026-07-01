"""AI店长 v1.2 - PDD 多账号额度池

支持配置多个 PDD 账号，自动轮换，每日额度独立追踪。
每个账号独立记录调用次数，达到限额自动切换。

配置格式 (config.ini):
[pdd_accounts]
# 账号数量
count = 2

# 账号1
account_1_client_id = "xxx"
account_1_client_secret = "xxx"
account_1_access_token = "xxx"
account_1_refresh_token = "xxx"
account_1_pid = "xxx"

# 账号2 ...
account_2_client_id = "xxx"
...
"""
import json
import logging
import os
import time
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 默认每日调用上限
DAILY_QUOTA = 2000
# 安全余量（提前停止，避免触发限流）
SAFE_MARGIN = 50

_SCRIPT_DIR = Path(__file__).resolve().parent.parent.parent  # 项目根目录


class PDDAccount:
    """单个PDD账号"""

    def __init__(self, name: str, cfg: Dict[str, str]):
        self.name = name
        self.client_id = cfg.get("client_id", "")
        self.client_secret = cfg.get("client_secret", "")
        self.access_token = cfg.get("access_token", "")
        self.refresh_token = cfg.get("refresh_token", "")
        self.pid = cfg.get("pid", "")

        # 运行时状态
        self._calls_today = 0
        self._date = date.today().isoformat()
        self.last_success = None
        self.last_error = None
        self._disabled = False

        self._load_state()

    @property
    def state_file(self) -> Path:
        name_safe = self.name.replace("/", "_").replace("\\", "_")
        return _SCRIPT_DIR / "data" / f"pdd_account_{name_safe}.json"

    @property
    def calls_used(self) -> int:
        return self._calls_today

    @property
    def calls_remaining(self) -> int:
        return max(0, DAILY_QUOTA - self._calls_today - SAFE_MARGIN)

    @property
    def is_available(self) -> bool:
        if self._disabled:
            return False
        if not all([self.client_id, self.client_secret, self.access_token]):
            return False
        return self.calls_remaining > 0

    @property
    def status(self) -> dict:
        return {
            "name": self.name,
            "available": self.is_available,
            "calls": self._calls_today,
            "remaining": self.calls_remaining,
            "last_success": self.last_success,
            "last_error": self.last_error,
        }

    def _load_state(self):
        """从文件恢复今日调用次数"""
        if not self.state_file.exists():
            return
        try:
            with open(self.state_file, "r") as f:
                data = json.load(f)
            stored_date = data.get("date", "")
            today = date.today().isoformat()
            if stored_date == today:
                self._calls_today = data.get("calls", 0)
            else:
                self._calls_today = 0  # 新的一天
            self.last_success = data.get("last_success")
            self.last_error = data.get("last_error")
        except Exception:
            pass

    def _save_state(self):
        """保存状态到文件"""
        os.makedirs(self.state_file.parent, exist_ok=True)
        try:
            with open(self.state_file, "w") as f:
                json.dump({
                    "date": date.today().isoformat(),
                    "calls": self._calls_today,
                    "last_success": self.last_success,
                    "last_error": self.last_error,
                    "name": self.name,
                }, f)
        except Exception as e:
            logger.warning("PDD account state save failed: %s", e)

    def record_call(self, success: bool = True, error: str = ""):
        """记录一次API调用"""
        self._calls_today += 1
        if success:
            self.last_success = datetime.now().isoformat()
            self.last_error = None
        else:
            self.last_error = f"{datetime.now().isoformat()}: {error[:100]}"
        self._save_state()

    def record_limit(self):
        """记录被限流"""
        self.last_error = f"{datetime.now().isoformat()}: 限流 (50001)"
        self._calls_today = DAILY_QUOTA  # 标记为耗尽
        self._save_state()

    def make_scraper(self):
        """创建此账号的 PDD scraper"""
        from modules.scrapers.scraper_pdd_api import ScraperPddApi
        return ScraperPddApi(
            client_id=self.client_id,
            client_secret=self.client_secret,
            pid=self.pid,
            access_token=self.access_token,
            refresh_token=self.refresh_token,
        )


class PDDAccountPool:
    """PDD 多账号额度池"""

    def __init__(self, config: Dict[str, Any] = None):
        self.accounts: List[PDDAccount] = []
        self._current_idx = 0

        if config:
            self._load_from_config(config)
        else:
            self._load_from_file()

    def _load_from_config(self, cfg: Dict[str, Any]):
        """从配置字典加载"""
        pdd_cfg = cfg.get("pdd_api", {})
        if pdd_cfg:
            # 单账号模式（兼容旧配置）
            self.accounts.append(PDDAccount("default", {
                "client_id": pdd_cfg.get("client_id", ""),
                "client_secret": pdd_cfg.get("client_secret", ""),
                "access_token": pdd_cfg.get("access_token", ""),
                "refresh_token": pdd_cfg.get("refresh_token", ""),
                "pid": pdd_cfg.get("pid", ""),
            }))

        # 多账号配置
        accounts_cfg = cfg.get("pdd_accounts", {})
        count = int(accounts_cfg.get("count", 0) or 0)
        for i in range(1, count + 1):
            prefix = f"account_{i}_"
            acc_cfg = {}
            for key in ["client_id", "client_secret", "access_token", "refresh_token", "pid"]:
                acc_cfg[key] = accounts_cfg.get(f"{prefix}{key}", "")
            if acc_cfg["client_id"]:
                self.accounts.append(PDDAccount(f"account_{i}", acc_cfg))

        if not self.accounts:
            logger.warning("PDD AccountPool: 无可用账号")

    def _load_from_file(self):
        """从 config.ini 直接加载"""
        try:
            from config import load_config
            cfg_path = _SCRIPT_DIR / "config.ini"
            cfg = load_config(str(cfg_path)).as_dict()
            self._load_from_config(cfg)
        except Exception as e:
            logger.error("PDD AccountPool init failed: %s", e)

    @property
    def total_accounts(self) -> int:
        return len(self.accounts)

    @property
    def available_accounts(self) -> int:
        return sum(1 for a in self.accounts if a.is_available)

    @property
    def is_any_available(self) -> bool:
        return self.available_accounts > 0

    @property
    def total_calls_today(self) -> int:
        return sum(a._calls_today for a in self.accounts)

    @property
    def total_remaining(self) -> int:
        return sum(a.calls_remaining for a in self.accounts)

    def get_status(self) -> List[dict]:
        return [a.status for a in self.accounts]

    def get_scraper(self) -> Optional[Any]:
        """获取下一个可用账号的 Scraper，自动跳过不可用账号"""
        if not self.accounts:
            return None

        # 从上次位置开始
        for _ in range(len(self.accounts)):
            acc = self.accounts[self._current_idx]
            self._current_idx = (self._current_idx + 1) % len(self.accounts)

            if acc.is_available:
                return acc.make_scraper()

        return None  # 全部不可用

    def get_account(self) -> Optional[PDDAccount]:
        """获取下一个可用账号对象"""
        if not self.accounts:
            return None
        for _ in range(len(self.accounts)):
            acc = self.accounts[self._current_idx]
            self._current_idx = (self._current_idx + 1) % len(self.accounts)
            if acc.is_available:
                return acc
        return None

    def record_after_call(self, scraper, success: bool, error: str = ""):
        """根据 scraper 对象找到对应账号并记录"""
        if hasattr(scraper, "client_id"):
            for acc in self.accounts:
                if acc.client_id == scraper.client_id:
                    acc.record_call(success, error)
                    return
        # fallback: 记录到当前账号
        if self.accounts:
            idx = (self._current_idx - 1) % len(self.accounts)
            self.accounts[idx].record_call(success, error)

    def record_limit(self, scraper):
        """记录当前账号被限流"""
        if hasattr(scraper, "client_id"):
            for acc in self.accounts:
                if acc.client_id == scraper.client_id:
                    acc.record_limit()
                    return

    def fetch_with_retry(self, keyword: str, max_items: int = 10,
                         max_retries: int = None) -> tuple:
        """使用账号池抓取 PDD，自动切换账号

        Returns:
            (items: list, scraper: object or None)
        """
        if max_retries is None:
            max_retries = max(1, self.available_accounts)

        last_error = ""

        for attempt in range(max_retries):
            acc = self.get_account()
            if not acc:
                logger.warning("PDD pool: 所有账号不可用")
                break

            scraper = acc.make_scraper()
            try:
                items = scraper.fetch(keyword, max_items=max_items)
                acc.record_call(success=True)

                # 如果返回了空列表但没报错，可能是限流
                if not items:
                    acc.record_call(success=False, error="返回空（可能限流）")
                    last_error = "返回空"
                    continue

                return items, scraper

            except Exception as e:
                err_str = str(e)
                acc.record_call(success=False, error=err_str)

                if "50001" in err_str or "限流" in err_str:
                    acc.record_limit()
                    logger.warning("PDD pool: %s 被限流，切换账号", acc.name)
                else:
                    logger.warning("PDD pool: %s 调用失败: %s", acc.name, err_str[:50])

                last_error = err_str
                continue

        logger.error("PDD pool: 全部账号重试后仍失败: %s", last_error[:100])
        return [], None


# ── 快速创建 ──

def create_pool(config: Dict[str, Any] = None) -> PDDAccountPool:
    return PDDAccountPool(config)


__all__ = ["PDDAccountPool", "PDDAccount", "create_pool", "DAILY_QUOTA"]
