# AI店长 v1.2 — 项目状态

> 最后更新: 2026-06-27

---

## 项目概览

本地运行的跨平台价差套利工具：

```
关键词池 → PDD API(真实) + 闲鱼 Playwright(真实)
         → 双向交叉匹配 → ROI计算 → DB入库 → QQ邮箱推送
```

运行方式：`streamlit run app.py` / `python desktop_app.py` / `python run_scan.py`

---

## 已完成功能

- PDD API + 自动刷新 token (7201)
- 闲鱼 Playwright 真实抓取 + 反检测
- 双向匹配 + 品类校验 + 价格比校验
- 套利计算 (config 驱动权重) + 综合评分
- 邮件推送 QQ SMTP HTML 格式
- 日报 09:00/21:00 + 周报（周一自动）
- SQLite 8张表 + system_config
- 关键词池 29+444个 + 自动续词
- 桌面 GUI + Streamlit UI 暗色主题
- auto_run 自动启动调度器
- 黑名单 + DB 级去重 + top_n 限制
- 测试 47/47 pass

---

## 当前无已知 BUG

所有已知 BUG (BUG-1~6) 已修复。

---

## 下一步优化

详见 `NEXT_TASKS.md`：
- P0: 看板/首页卡片美化
- P1: 一键铺货、价格预警、仪表盘增强
- P2: 1688 攻克、打包 exe、云部署
