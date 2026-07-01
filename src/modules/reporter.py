"""AI店长 v1.1 - 日报/周报生成器

负责汇总扫描结果，生成结构化报告：
- 每日报告：Top10 + 统计摘要
- 每周报告：趋势 + 品类分析
- 报告持久化到 data/reports/
"""
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class Reporter:
    """报告生成器"""

    def __init__(self, config: Dict[str, Any], output_dir: str = "outputs/reports"):
        self.config = config
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def _today_str(self) -> str:
        return datetime.now().strftime("%Y-%m-%d")

    def _now_str(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def generate_daily_report(
        self,
        opportunities: List[Dict[str, Any]],
        stats: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """生成每日报告

        Args:
            opportunities: 今日发现的套利机会列表
            stats: 额外统计数据

        Returns:
            结构化报告字典
        """
        top10 = sorted(opportunities, key=lambda x: x.get("roi", 0), reverse=True)[:10]

        # 品类统计
        platform_stats = {}
        for opp in opportunities:
            bp = opp.get("buy_platform", "unknown")
            platform_stats[bp] = platform_stats.get(bp, 0) + 1

        # ROI 分布
        roi_ranges = {"60%+": 0, "30-60%": 0, "20-30%": 0}
        for opp in opportunities:
            roi = opp.get("roi", 0)
            if roi >= 60:
                roi_ranges["60%+"] += 1
            elif roi >= 30:
                roi_ranges["30-60%"] += 1
            else:
                roi_ranges["20-30%"] += 1

        report = {
            "report_type": "daily",
            "generated_at": self._now_str(),
            "date": self._today_str(),
            "summary": {
                "total_opportunities": len(opportunities),
                "avg_roi": (
                    round(sum(o.get("roi", 0) for o in opportunities) / len(opportunities), 1)
                    if opportunities else 0
                ),
                "max_roi": max((o.get("roi", 0) for o in opportunities), default=0),
                "total_profit_potential": round(
                    sum(o.get("profit", 0) for o in opportunities), 2
                ),
                "platform_distribution": platform_stats,
                "roi_distribution": roi_ranges,
            },
            "top10": [
                {
                    "rank": i + 1,
                    "title": opp.get("buy_title", "")[:50],
                    "buy_platform": opp.get("buy_platform", ""),
                    "sell_platform": opp.get("sell_platform", ""),
                    "buy_price": opp.get("buy_price", 0),
                    "sell_price": opp.get("sell_price", 0),
                    "profit": opp.get("profit", 0),
                    "roi": opp.get("roi", 0),
                    "confidence": opp.get("confidence", 0),
                }
                for i, opp in enumerate(top10)
            ],
            "all_opportunities": opportunities,
        }

        if stats:
            report["extra_stats"] = stats

        # 持久化
        filename = f"daily_{self._today_str()}.json"
        filepath = os.path.join(self.output_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        logger.info("日报已保存: %s", filepath)

        return report

    def format_daily_text(self, report: Dict[str, Any]) -> str:
        """将日报格式化为纯文本（适合推送）"""
        summary = report.get("summary", {})
        top10 = report.get("top10", [])

        lines = [
            f"📊 AI店长日报 {report.get('date', '')}",
            "=" * 40,
            "",
            f"📈 发现机会: {summary.get('total_opportunities', 0)} 个",
            f"💰 平均ROI: {summary.get('avg_roi', 0):.1f}%",
            f"🔥 最高ROI: {summary.get('max_roi', 0):.1f}%",
            f"💵 总潜在利润: ¥{summary.get('total_profit_potential', 0):.0f}",
            "",
            "🏆 Top10 机会",
            "-" * 40,
        ]

        for item in top10:
            lines.append(
                f"#{item['rank']} [{item['buy_platform']}→{item['sell_platform']}] "
                f"ROI {item['roi']:.0f}% | ¥{item['buy_price']:.0f}→¥{item['sell_price']:.0f} "
                f"| +¥{item['profit']:.0f}"
            )
            lines.append(f"   {item['title'][:35]}...")
            lines.append("")

        return "\n".join(lines)

    def list_reports(self, days: int = 7) -> List[str]:
        """列出最近 N 天的报告文件"""
        reports = []
        for i in range(days):
            date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            filename = f"daily_{date}.json"
            filepath = os.path.join(self.output_dir, filename)
            if os.path.exists(filepath):
                reports.append(filepath)
        return reports

    def load_report(self, filepath: str) -> Optional[Dict[str, Any]]:
        """加载一份报告"""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error("加载报告失败: %s", e)
            return None


    def generate_weekly_report(
        self,
        opportunities: List[Dict[str, Any]],
        stats: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """生成周报（汇总近 7 天数据）

        Args:
            opportunities: 本周所有套利机会
            stats: 额外统计数据

        Returns:
            结构化报告字典
        """
        today = datetime.now()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)

        top20 = sorted(opportunities, key=lambda x: x.get("roi", 0), reverse=True)[:20]

        # 按天统计
        daily_counts = {}
        for opp in opportunities:
            d = (opp.get("discovered_at") or "")[:10]
            if d:
                daily_counts[d] = daily_counts.get(d, 0) + 1

        # 品类统计
        platform_stats = {}
        for opp in opportunities:
            bp = opp.get("buy_platform", "unknown")
            platform_stats[bp] = platform_stats.get(bp, 0) + 1

        # ROI 分布
        roi_ranges = {"60%+": 0, "30-60%": 0, "15-30%": 0}
        for opp in opportunities:
            roi = opp.get("roi", 0)
            if roi >= 60:
                roi_ranges["60%+"] += 1
            elif roi >= 30:
                roi_ranges["30-60%"] += 1
            elif roi >= 15:
                roi_ranges["15-30%"] += 1

        report = {
            "report_type": "weekly",
            "generated_at": self._now_str(),
            "week_range": {
                "start": week_start.strftime("%Y-%m-%d"),
                "end": week_end.strftime("%Y-%m-%d"),
            },
            "summary": {
                "total_opportunities": len(opportunities),
                "avg_roi": (
                    round(sum(o.get("roi", 0) for o in opportunities) / len(opportunities), 1)
                    if opportunities else 0
                ),
                "max_roi": max((o.get("roi", 0) for o in opportunities), default=0),
                "total_profit_potential": round(
                    sum(o.get("profit", 0) for o in opportunities), 2
                ),
                "active_days": len(daily_counts),
                "avg_daily_opportunities": round(len(opportunities) / max(len(daily_counts), 1), 1),
                "platform_distribution": platform_stats,
                "roi_distribution": roi_ranges,
                "daily_counts": daily_counts,
            },
            "top20": [
                {
                    "rank": i + 1,
                    "title": opp.get("buy_title", "")[:50],
                    "buy_platform": opp.get("buy_platform", ""),
                    "sell_platform": opp.get("sell_platform", ""),
                    "buy_price": opp.get("buy_price", 0),
                    "sell_price": opp.get("sell_price", 0),
                    "profit": opp.get("profit", 0),
                    "roi": opp.get("roi", 0),
                    "confidence": opp.get("confidence", 0),
                }
                for i, opp in enumerate(top20)
            ],
        }

        if stats:
            report["extra_stats"] = stats

        filename = f"weekly_{week_start.strftime('%Y%m%d')}_{week_end.strftime('%Y%m%d')}.json"
        filepath = os.path.join(self.output_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        logger.info("周报已保存: %s", filepath)

        return report

    def format_weekly_text(self, report: Dict[str, Any]) -> str:
        """将周报格式化为纯文本（适合推送）"""
        summary = report.get("summary", {})
        week = report.get("week_range", {})
        top5 = report.get("top20", [])[:5]

        lines = [
            f"📊 AI店长周报 {week.get('start', '')} ~ {week.get('end', '')}",
            "=" * 50,
            "",
            f"📈 本周发现机会: {summary.get('total_opportunities', 0)} 个",
            f"📅 活跃天数: {summary.get('active_days', 0)} 天",
            f"📊 日均机会: {summary.get('avg_daily_opportunities', 0)} 个",
            f"💰 平均ROI: {summary.get('avg_roi', 0):.1f}%",
            f"🔥 最高ROI: {summary.get('max_roi', 0):.1f}%",
            f"💵 总潜在利润: ¥{summary.get('total_profit_potential', 0):.0f}",
            "",
        ]

        roi = report.get("summary", {}).get("roi_distribution", {})
        if roi:
            lines.append("📊 ROI 分布:")
            for rng, cnt in roi.items():
                lines.append(f"   {rng}: {cnt} 个")
            lines.append("")

        lines.extend(["🏆 Top 5 机会", "-" * 50])
        for item in top5:
            lines.append(
                f"#{item['rank']} [{item['buy_platform']}→{item['sell_platform']}] "
                f"ROI {item['roi']:.0f}% | ¥{item['buy_price']:.0f}→¥{item['sell_price']:.0f} "
                f"| +¥{item['profit']:.0f}"
            )
            lines.append(f"   {item['title'][:40]}")
            lines.append("")

        return "\n".join(lines)


__all__ = ["Reporter"]
