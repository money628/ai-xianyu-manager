# AI 闲鱼店长 v1.2 — 项目体检报告

## 1. 技术栈

| 组件 | 技术 |
|------|------|
| 前端 | Streamlit 1.x, Plotly |
| 后端 | FastAPI (API), Python 3.11 |
| 数据库 | SQLite (raw sqlite3, 11 张表) |
| 爬虫 | Playwright + playwright-stealth + PDD Open API |
| 调度器 | threading.Thread + schedule 库 |
| 匹配引擎 | TF-IDF + Jaccard + v2.0 结构化匹配 |
| 推送 | Server酱 / 邮件 / 钉钉 Webhook |
| 测试 | pytest (68 测试) |

## 2. 目录结构

```
ai_storekeeper/
├── app.py                 # Streamlit 主入口 (8 页)
├── api.py                 # FastAPI REST API (/health 等)
├── main.py                # CLI 入口 (scan/daily/schedule/test)
├── launcher.py            # 一键启动
├── run_scan.py            # 任务计划器脚本
├── config.ini             # 配置 (含敏感信息!)
├── pages/                 # 8 个 Streamlit 页面
│   ├── home.py            # 首页 KPI + Top5
│   ├── radar.py           # 雷达扫描
│   ├── kanban.py          # 看板审核 + 铺货工作台
│   ├── shipping.py        # 发货 SOP
│   ├── dashboard.py       # 运营仪表盘
│   ├── traffic.py         # 流量分析
│   ├── tools.py           # 工具/登录/设置/黑名单
│   └── history.py         # 历史记录
├── src/
│   ├── database.py        # SQLite 数据层 (1288 行, 11 表)
│   ├── config.py          # 配置解析
│   └── modules/
│       ├── scheduler.py   # 后台调度器
│       ├── discovery.py   # 关键词池扩展
│       ├── matcher.py     # 交叉平台匹配 (990 行)
│       ├── arbitrage.py   # 套利计算
│       ├── family_aggregator.py  # 商品族聚合
│       ├── publisher.py   # 铺货草稿
│       ├── image_pack.py  # 图片下载打包
│       ├── shipping.py    # 发货逻辑
│       ├── pusher.py      # 多渠道推送
│       ├── reporter.py    # 日报周报
│       └── scrapers/      # 4 个爬虫
```

## 3. 数据库表 (11 张)

| 表 | 行数 | 用途 |
|----|------|------|
| products | 198 | 商品快照 |
| opportunities | 7 | 套利机会 |
| keyword_pool | 776 | 关键词池 |
| search_cache | 110 | PDD 搜索缓存 |
| shipping_orders | 9 | 发货订单 |
| traffic_data | 2 | 流量数据 |
| image_packs | 4 | 图片打包记录 |
| price_history | 72 | 价格历史 |
| workflow_runs | 2 | 扫描运行记录 |
| user_blacklist | 0 | 黑名单 |
| system_config | 3 | 系统配置键值 |

## 4. 扫描流程

```
关键词池取 20 个词
  → PDD API 搜索 (ScraperPddApi)
  → 闲鱼 Playwright 搜索 (ScraperXianyu)
  → 交叉匹配 (match_cross_platform, TF-IDF)
  → 套利计算 (calculate_arbitrage)
  → ROI >= 阈值 → 入库 (save_opportunity)
  → 标记关键词已扫描
```

## 5. 当前明显 Bug

| # | 严重度 | 文件 | 问题 |
|---|--------|------|------|
| 1 | 🔴 | run_scan.py:31 | 缩进错误，导入语句位置不对 |
| 2 | 🔴 | database.py:888 | `delete_opportunities_by_platform` 用了不存在的列名 |
| 3 | 🔴 | config.ini | 包含真实密钥 (SMTP密码, PDD token, 钉钉webhook) |
| 4 | 🟡 | tools.py:393 | 变量名错误 `startup_path` 应为 `startup_lnk` |
| 5 | 🟡 | database.py:1031 | `clear_all()` 缺少 4 张新表的清理 |

## 6. 最影响体验的问题

1. **服装类商品大量涌入** —— 无类目过滤，衣服裤子全部进入待审核
2. **同店铺重复刷屏** —— 同一店铺 春夏秋冬/颜色/尺码 全部推一遍
3. **同系列未合并** —— 苹果15/16/17 闪魔膜拆成多条
4. **图片下载不稳定** —— URL 失效无人处理
5. **商品多了难找进货链接** —— 无索引搜索
6. **客服工作量没法控制** —— 铺货无上限

## 7. 本次升级涉及文件

| 阶段 | 涉及文件 |
|------|---------|
| Bug 修复 | run_scan.py, database.py, tools.py, config.py |
| 扫描治理 | discovery.py, matcher.py, keyword_pool 表 |
| 商品族升级 | family_aggregator.py, product_families/variants 表 |
| 图片服务 | image_pack.py → image_service.py |
| 看板重构 | kanban.py |
| 发布中心 | publisher.py, kanban.py |
| 店长驾驶舱 | home.py |
| 客服/订单 | shipping.py, shipping 表 |
