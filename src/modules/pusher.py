"""AI店长 v1.1 - 推送器（Server酱 + 邮件）

推送策略：
- 实时推送：ROI > 30% 时立即推送
- 日报推送：每天 9:00 / 21:00 推送 Top10
- 去重：同一商品 24h 内不重复推送
- 降级：Server酱失败时回退邮件
"""
import hashlib
import logging
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


class Pusher:
    """统一推送入口"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.push_cfg = config.get("push", {})
        self._sent_cache: Dict[str, float] = {}  # dedup: key -> timestamp

    # ---------- 去重检查 ----------
    def _is_duplicate(self, item_key: str, ttl_hours: int = 24) -> bool:
        now = time.time()
        if item_key in self._sent_cache:
            elapsed = now - self._sent_cache[item_key]
            if elapsed < ttl_hours * 3600:
                return True
        return False

    def _mark_sent(self, item_key: str) -> None:
        self._sent_cache[item_key] = time.time()

    @staticmethod
    def _make_key(product_id: str, platform: str) -> str:
        raw = f"{platform}:{product_id}"
        return hashlib.md5(raw.encode()).hexdigest()[:12]

    # ---------- Server酱 ----------
    def push_serverchan(self, title: str, content: str) -> bool:
        """通过 Server酱 推送微信消息"""
        send_key = self.push_cfg.get("serverchan_send_key", "")
        if not send_key:
            logger.warning("Server酱 SendKey 未配置")
            return False

        url = f"https://sctapi.ftqq.com/{send_key}.send"
        payload = {"title": title[:256], "desp": content}

        try:
            resp = requests.post(url, data=payload, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") == 0 or data.get("errno") == 0:
                logger.info("Server酱推送成功: %s", title[:30])
                return True
            else:
                logger.warning("Server酱推送失败: %s", data)
                return False
        except Exception as e:
            logger.error("Server酱请求异常: %s", e)
            return False

    # ---------- 邮件 ----------
    def push_email(self, subject: str, body_html: str) -> bool:
        """通过 SMTP 发送邮件"""
        smtp_host = self.push_cfg.get("smtp_host", "")
        smtp_port = int(self.push_cfg.get("smtp_port", 465))
        smtp_user = self.push_cfg.get("smtp_user", "")
        smtp_pass = self.push_cfg.get("smtp_password", "")
        email_to = self.push_cfg.get("email_to", "")

        if not all([smtp_host, smtp_user, smtp_pass, email_to]):
            logger.warning("邮件配置不完整")
            return False

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = smtp_user
        msg["To"] = email_to
        msg.attach(MIMEText(body_html, "html", "utf-8"))

        try:
            if smtp_port == 465:
                server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=15)
            else:
                server = smtplib.SMTP(smtp_host, smtp_port, timeout=15)
                server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, [email_to], msg.as_string())
            server.quit()
            logger.info("邮件发送成功: %s", subject[:30])
            return True
        except Exception as e:
            logger.error("邮件发送失败: %s", e)
            return False

    # ---------- 钉钉 Webhook ----------
    def push_dingtalk(self, title: str, content: str) -> bool:
        webhook = self.push_cfg.get("dingtalk_webhook", "")
        if not webhook:
            return False
        try:
            resp = requests.post(webhook, json={
                "msgtype": "markdown",
                "markdown": {
                    "title": title[:256],
                    "text": f"## {title}\n\n{content}\n\n> ai店长 自动推送",
                },
            }, timeout=15)
            resp.raise_for_status()
            if resp.json().get("errcode") == 0:
                logger.info("钉钉推送成功: %s", title[:30])
                return True
            logger.warning("钉钉推送失败: %s", resp.json())
            return False
        except Exception as e:
            logger.error("钉钉请求异常: %s", e)
            return False

    # ---------- 统一推送入口 ----------
    def push(self, title: str, content: str, level: str = "info") -> bool:
        method = self.push_cfg.get("method", "email")
        ok = False

        if method == "serverchan":
            ok = self.push_serverchan(title, content)
        elif method == "dingtalk":
            ok = self.push_dingtalk(title, content)
        elif method == "email":
            ok = self.push_email(title, content)
        elif method == "both":
            ok = self.push_serverchan(title, content)
            self.push_email(title, content)

        if not ok and method not in ("email", "both"):
            ok = self.push_email(title, content)

        # 钉钉额外通道
        if self.push_cfg.get("dingtalk_webhook", "") and method != "dingtalk":
            self.push_dingtalk(title, content)

        return ok

    # ---------- 价差机会推送 ----------
    def push_opportunity(self, item: Dict[str, Any]) -> bool:
        """推送单条套利机会（带去重 + HTML格式 + 图片链接）"""
        product_id = item.get("product_id", item.get("sell_product_id", ""))
        platform = item.get("sell_platform", "")
        key = self._make_key(product_id, platform)

        if self._is_duplicate(key):
            logger.debug("跳过重复推送: %s", product_id)
            return False

        roi = item.get("roi", 0)
        if roi < 20:
            return False

        emoji = "🔥" if roi >= 60 else "💰" if roi >= 30 else "📦"
        title = f"{emoji} 套利机会 ROI {roi:.0f}%"
        
        buy_img = item.get("buy_image", "")
        sell_img = item.get("sell_image", "")
        buy_url = item.get("buy_url", "#")
        sell_url = item.get("sell_url", "#")
        buy_title = item.get("buy_title", "")
        sell_title = item.get("sell_title", "")

        # HTML 邮件（含图片 + 可点击链接）
        content = f"""<html><body style="font-family:Arial,sans-serif;max-width:600px">
<h2 style="color:#e65100">{emoji} ROI {roi:.0f}% 套利机会</h2>
<table style="width:100%;border-collapse:collapse;margin:12px 0">
<tr><td style="width:60px;padding:4px;vertical-align:top">
  <a href="{buy_url}"><img src="{buy_img}" width="60" style="border-radius:6px"></a>
</td><td style="padding:4px">
  <a href="{buy_url}" style="color:#333;text-decoration:none">
    <b>🛒 进价 ¥{item.get('buy_price',0):.2f}</b><br>
    <span style="color:#666;font-size:12px">{buy_title[:50]}</span>
  </a>
</td></tr></table>
<div style="text-align:center;font-size:18px;padding:8px">⬇️ 转卖 ⬇️</div>
<table style="width:100%;border-collapse:collapse;margin:12px 0">
<tr><td style="width:60px;padding:4px;vertical-align:top">
  <a href="{sell_url}"><img src="{sell_img}" width="60" style="border-radius:6px"></a>
</td><td style="padding:4px">
  <a href="{sell_url}" style="color:#333;text-decoration:none">
    <b>💵 售价 ¥{item.get('sell_price',0):.2f}</b><br>
    <span style="color:#666;font-size:12px">{sell_title[:50]}</span>
  </a>
</td></tr></table>
<table style="width:100%;border-collapse:collapse;background:#f5f5f5;border-radius:8px;padding:12px">
<tr><td>📦 运费</td><td style="text-align:right">¥{item.get('shipping_cost',3):.2f}</td></tr>
<tr><td>💰 净利润</td><td style="text-align:right;font-weight:bold;color:#2e7d32">¥{item.get('profit',0):.2f}</td></tr>
<tr><td>📊 ROI</td><td style="text-align:right;font-weight:bold;color:#e65100;font-size:18px">{roi:.1f}%</td></tr>
<tr><td>🎯 置信度</td><td style="text-align:right">{item.get('confidence',0):.0%}</td></tr>
</table>
<p style="color:#999;font-size:11px;margin-top:16px">AI店长 v1.2 · 自动发现 · 操作前请核实商品信息</p>
</body></html>"""

        ok = self.push(title, content)
        if ok:
            self._mark_sent(key)
        return ok

    # ---------- 日报推送 ----------
    def push_daily_report(self, items: List[Dict[str, Any]], time_slot: str = "09:00") -> bool:
        """推送每日套利日报（HTML格式）"""
        if not items:
            title = f"📋 AI店长日报 ({time_slot}) - 暂无新机会"
            return self.push(title, "今日扫描未发现符合条件的套利机会。")

        top10 = items[:10]
        title = f"📋 AI店长日报 ({time_slot}) - {len(items)}个机会"

        rows = []
        for i, item in enumerate(top10, 1):
            rows.append(
                f"<tr><td>{i}</td><td>{item.get('buy_title','')[:25]}</td>"
                f"<td>¥{item.get('buy_price',0):.0f}</td><td>¥{item.get('sell_price',0):.0f}</td>"
                f"<td style='color:#e65100;font-weight:bold'>{item.get('roi',0):.0f}%</td>"
                f"<td>¥{item.get('profit',0):.0f}</td></tr>"
            )

        content = (
            "<html><body style='font-family:Arial,sans-serif;max-width:600px'>"
            f"<h2>📋 AI店长日报 ({time_slot})</h2>"
            "<table style='width:100%;border-collapse:collapse'>"
            "<tr style='background:#f5f5f5'><th>#</th><th>商品</th><th>进价</th><th>售价</th><th>ROI</th><th>净利润</th></tr>"
            + "".join(rows) +
            f"</table><p style='color:#999;margin-top:12px'>共 {len(items)} 个机会 · AI店长 v1.2</p>"
            "</body></html>"
        )

        return self.push(title, content)


__all__ = ["Pusher"]
