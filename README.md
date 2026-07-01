# 🐟 鱼多多雷达 — AI 闲鱼店长 v2.0

跨电商平台选品套利工具。扫描拼多多低价商品 + 闲鱼售价，自动发现搬砖/撸货机会，AI 辅助生成铺货文案、自动上架。

## 功能矩阵

| 模块 | 功能 |
|------|------|
| 📡 雷达扫描 | PDD API 双账号轮换 + 闲鱼 Playwright 搜索，803 关键词池自动循环 |
| 📋 商品族审核 | 同品牌同系列多型号自动合并，三栏看板审核（通过/拒绝/AI建议） |
| 🤖 AI 铺货 | DeepSeek 自动生成闲鱼标题、描述、客服话术、智能定价 |
| 🚀 自动上架 | Playwright 控制 seller.goofish.com 自动填表（标题/描述/价格） |
| 📦 订单履约 | 发货 SOP 状态流转、买家地址复制、PDD 进货链接一键跳转、批量操作 |
| 📈 流量复盘 | 闲鱼卖家数据自动同步、曝光/浏览/想要趋势图、AI 运营建议 |
| 🛡️ 类目过滤 | 服装/鞋帽等 30+ 低利润品类自动拦截 |

## 快速开始

```bash
# 1. 克隆
git clone https://github.com/money628/ai-xianyu-manager.git
cd ai-xianyu-manager

# 2. 安装依赖
pip install -r requirements.txt
playwright install chromium

# 3. 配置
cp config.docker.ini config.ini
# 编辑 config.ini，填入 PDD API 密钥（必填）和 AI API key（可选）

# 4. 启动
streamlit run app.py
# 访问 http://localhost:8501
```

## 配置说明

`config.ini` 关键配置：

```ini
[pdd_api]          # PDD 开放平台 API（必填）
client_id = ""     # 你的 client_id
client_secret = ""
access_token = ""
pid = ""

[pdd_accounts]     # 多账号轮换（可选，突破 2000次/天限制）
count = 1

[ai]               # DeepSeek API（可选，不填则用模板生成）
api_key = ""
```

## 技术栈

| 层 | 技术 |
|----|------|
| 前端 | Streamlit 1.x + Plotly |
| 后端 | FastAPI + Python 3.11 |
| 数据库 | SQLite（raw sqlite3，无需配置） |
| 爬虫 | Playwright + playwright-stealth（反检测） |
| API | 拼多多开放平台 pdd.ddk.goods.search |
| AI | DeepSeek Chat API |
| 测试 | pytest（68 例） |

## 项目结构

```
├── app.py                  # Streamlit 主入口
├── api.py                  # FastAPI REST API
├── pages/                  # 8 个页面
│   ├── home.py             # 店长驾驶舱
│   ├── radar.py            # 雷达扫描
│   ├── kanban.py           # 商品族审核 + 铺货工作台
│   ├── shipping.py         # 订单履约
│   ├── dashboard.py        # 运营仪表盘
│   ├── traffic.py          # 流量复盘
│   ├── tools.py            # 工具/登录/设置
│   └── history.py          # 历史记录
├── src/
│   ├── database.py         # SQLite 数据层（11 张表）
│   └── modules/
│       ├── scheduler.py    # 后台扫描调度器
│       ├── matcher.py      # 跨平台匹配引擎
│       ├── discovery.py    # 关键词池扩展
│       ├── publisher.py    # 铺货草稿生成
│       ├── ai_service.py   # AI 服务封装
│       ├── auto_listing.py # 自动上架模块
│       └── scrapers/       # PDD / 闲鱼 / 1688 爬虫
├── tests/                  # 68 个单元测试
└── docs/                   # 项目文档
```

## 部署

```bash
docker compose up -d
# Web UI: http://server:8501
# API: http://server:8000/health
```

详见 [DEPLOYMENT.md](DEPLOYMENT.md)

## 声明

仅供学习研究，请遵守各平台使用协议。不提供自动发布、绕过验证码等违规功能。
