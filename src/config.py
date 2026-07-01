"""AI店长 v1.1 - 配置管理模块

负责加载和解析 config.ini，提供全局配置对象。
支持从环境变量覆盖敏感信息（如 SendKey、邮箱密码）。
"""
import logging
import os
from configparser import ConfigParser
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = "config.ini"

# 布尔转换
_TRUE = {"true", "1", "yes", "on", "y", "t"}
_FALSE = {"false", "0", "no", "off", "n", "f"}


def _to_bool(value: str) -> bool:
    if str(value).strip().lower() in _TRUE:
        return True
    if str(value).strip().lower() in _FALSE:
        return False
    return bool(value)


def _to_list(value: str) -> List[str]:
    """将 '["a", "b"]' 转为 ['a', 'b']"""
    if not value:
        return []
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        import ast
        try:
            return [str(x) for x in ast.literal_eval(value)]
        except Exception:
            pass
    return [x.strip() for x in value.split(",") if x.strip()]


class AppConfig:
    """全局配置对象，支持点号访问"""

    def __init__(self, raw: Dict[str, Dict[str, str]]):
        self._raw = raw
        self.system = self._parse_system()
        self.scanner = self._parse_scanner()
        self.platforms = self._parse_platforms()
        self.finance = self._parse_finance()
        self.arbitrage = self._parse_arbitrage()
        self.push = self._parse_push()
        self.antiscrap = self._parse_antiscrap()
        self.database = self._parse_database()

    def _parse_system(self) -> Dict[str, Any]:
        s = self._raw.get("system", {})
        return {
            "version": s.get("version", "1.1"),
            "mode": s.get("mode", "arbitrage"),
            "auto_run": _to_bool(s.get("auto_run", "true")),
            "log_level": s.get("log_level", "INFO"),
        }

    def _parse_scanner(self) -> Dict[str, Any]:
        s = self._raw.get("scanner", {})
        return {
            "seed_categories": _to_list(s.get("seed_categories", "")),
            "keywords_per_round": int(s.get("keywords_per_round", 20)),
            "scan_interval_minutes": int(s.get("scan_interval_minutes", 60)),
            "realtime_push_threshold": float(s.get("realtime_push_threshold", 0.30)),
            "daily_report_times": _to_list(s.get("daily_report_times", '["09:00", "21:00"]')),
            "top_n": int(s.get("top_n", 10)),
            "max_push_per_item": int(s.get("max_push_per_item", 1)),
        }

    def _parse_platforms(self) -> Dict[str, Any]:
        s = self._raw.get("platforms", {})
        return {
            "enabled_1688": _to_bool(s.get("enabled_1688", "true")),
            "enabled_pdd": _to_bool(s.get("enabled_pdd", "true")),
            "enabled_xianyu": _to_bool(s.get("enabled_xianyu", "true")),
            "remote_regions": _to_list(s.get("remote_regions", "[]")),
        }

    def _parse_finance(self) -> Dict[str, Any]:
        s = self._raw.get("finance", {})
        return {
            "xianyu_fee": float(s.get("xianyu_fee", 0.016)),
            "domestic_shipping": float(s.get("domestic_shipping", 3.0)),
            "return_reserve": float(s.get("return_reserve", 0.0)),
            "ad_cost": float(s.get("ad_cost", 0.0)),
        }

    def _parse_arbitrage(self) -> Dict[str, Any]:
        s = self._raw.get("arbitrage", {})
        return {
            "weight_roi": float(s.get("weight_roi", 0.5)),
            "weight_sales": float(s.get("weight_sales", 0.3)),
            "weight_confidence": float(s.get("weight_confidence", 0.2)),
            "min_roi_threshold": float(s.get("min_roi_threshold", 0.15)),
            "min_confidence": float(s.get("min_confidence", 0.6)),
        }

    def _parse_push(self) -> Dict[str, Any]:
        s = self._raw.get("push", {})
        sendkey = os.environ.get("SERVERCHAN_SENDKEY", s.get("serverchan_sendkey", ""))
        email_pass = os.environ.get("EMAIL_PASS", s.get("smtp_pass", ""))
        return {
            "method": s.get("method", "email"),
            "serverchan_sendkey": sendkey,
            "serverchan_send_key": sendkey,
            "dingtalk_webhook": os.environ.get("DINGTALK_WEBHOOK", s.get("dingtalk_webhook", "")),
            "email_enabled": _to_bool(s.get("email_enabled", "false")),
            "smtp_host": s.get("smtp_host", "smtp.qq.com"),
            "smtp_port": int(s.get("smtp_port", 587)),
            "smtp_user": os.environ.get("EMAIL_USER", s.get("smtp_user", "")),
            "smtp_pass": email_pass,
            "smtp_password": email_pass,
            "email_to": os.environ.get("EMAIL_TO", s.get("email_to", "")),
        }

    def _parse_antiscrap(self) -> Dict[str, Any]:
        s = self._raw.get("antiscrap", {})
        return {
            "requests_per_second": float(s.get("requests_per_second", 5)),
            "max_retries": int(s.get("max_retries", 3)),
            "timeout_seconds": int(s.get("timeout_seconds", 15)),
            "auto_degrade_after_failures": int(s.get("auto_degrade_after_failures", 3)),
            "use_playwright": _to_bool(s.get("use_playwright", "false")),
        }

    def _parse_database(self) -> Dict[str, Any]:
        s = self._raw.get("database", {})
        return {
            "path": s.get("path", "data/ai_storekeeper.db"),
            "retention_days": int(s.get("retention_days", 30)),
            "price_curve_days": int(s.get("price_curve_days", 10)),
        }

    def as_dict(self) -> Dict[str, Any]:
        result = {
            "system": self.system,
            "scanner": self.scanner,
            "platforms": self.platforms,
            "finance": self.finance,
            "arbitrage": self.arbitrage,
            "push": self.push,
            "antiscrap": self.antiscrap,
            "database": self.database,
        }
        # 透传所有未解析的原始节（如 pdd_api）
        for section, items in self._raw.items():
            if section not in result:
                result[section] = items
        return result


def _strip_inline_comments(text: str) -> str:
    """移除每行行内注释（# 前必须有空格），保留 # 在引号内的值

    简化策略：仅在 # 前有空白时剥离行内注释。引号内含 # 的情况本项目暂无。
    """
    import re
    out_lines = []
    for line in text.splitlines():
        # 去掉 " #..." 形式的行内注释（# 前至少一个空白）
        stripped = re.sub(r"\s+#.*$", "", line)
        out_lines.append(stripped)
    return "\n".join(out_lines)


def load_config(path: str = DEFAULT_CONFIG_PATH) -> AppConfig:
    """加载配置文件"""
    p = Path(path)
    if not p.exists():
        logger.warning("Config not found: %s, using defaults", path)
        return AppConfig({})

    raw_text = p.read_text(encoding="utf-8")
    cleaned = _strip_inline_comments(raw_text)

    parser = ConfigParser(interpolation=None)
    parser.read_string(cleaned)

    raw = {section: dict(parser.items(section)) for section in parser.sections()}
    # 去掉值两侧的引号（"..." 或 '...'）
    for section, items in raw.items():
        for k, v in items.items():
            v = v.strip()
            if len(v) >= 2 and v[0] in "\"'" and v[-1] == v[0]:
                v = v[1:-1]
            items[k] = v
    logger.info("Config loaded from %s (sections=%s)", path, list(raw.keys()))
    return AppConfig(raw)


def save_config(cfg: Dict[str, Any], path: str = DEFAULT_CONFIG_PATH) -> None:
    """保存配置到 INI 文件（简易实现，支持扁平 dict-of-dicts）"""
    parser = ConfigParser(interpolation=None)
    for section, items in cfg.items():
        if not isinstance(items, dict):
            continue
        parser[section] = {}
        for k, v in items.items():
            if isinstance(v, list):
                import json as _json
                parser[section][k] = _json.dumps(v, ensure_ascii=False)
            elif isinstance(v, bool):
                parser[section][k] = "true" if v else "false"
            else:
                parser[section][k] = str(v)
    with open(path, "w", encoding="utf-8") as f:
        parser.write(f)
    logger.info("Config saved to %s", path)


__all__ = ["load_config", "AppConfig", "save_config"]
