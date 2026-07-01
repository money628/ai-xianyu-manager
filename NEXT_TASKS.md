# AI店长 v1.2 — 下一步优化清单

> 给下一个模型：读完此文件即可接手上手

---

## 项目快速恢复

```bash
cd D:\ecom_product_research_workflow\ai_storekeeper

# 启动网页
streamlit run app.py

# 跑测试
python -m pytest tests -q

# 跑端到端测试
python test_e2e_live.py
```

---

## 一、已完成功能（不用再碰）

| 功能 | 说明 |
|------|------|
| PDD API + 自动刷新 token | 7201 → refresh_token 换新 |
| 闲鱼 Playwright 真实抓取 | 含反检测+去噪 |
| 双向匹配 + 质量校验 | 品类+价格比 2-30x |
| 套利计算 + 综合评分 | config 驱动 ROI×0.5 +销量×0.3 + 置信度×0.2 |
| 邮件推送 QQ SMTP HTML | 图片+链接+利润表格 |
| 日报 + 周报 | 09:00/21:00 日报，周一自动周报 |
| SQLite 8表 + 自动清理 | 30天 |
| 关键词池 29+444 自动续词 | expand_apple_keywords |
| 玻璃卡片 UI | 统一暗色主题 CSS，看板/首页/历史 |
| 历史页搜索+分页 | ROI 颜色高亮，CSV/JSON 导出 |
| 价格预警 | 降价>10% 自动推送（需价格数据积累） |
| 仪表盘 | 品类饼图 + 近7天趋势折线 |
| auto_run 自动启动 | 雷达页打开即启动调度器 |
| 黑名单 + 去重 | DB 级 24h + top_n 限制 |
| 测试 47/47 pass | E2E 正常 |

---

## 二、待实现功能（优先级）

### P1 — 功能增强

**1. 一键铺货**
- 文件：`pages/kanban.py` 中"一键铺货"按钮
- 当前：显示"功能开发中..."
- 方向：用 Playwright 模拟闲鱼发布流程（需登录态）
- 难度：高，闲鱼没有 API

**2. 更多品类扩展**
- 文件：`src/modules/discovery.py`
- 方向：从实时热搜/榜单自动发现新品类关键词
- 参考：`expand_apple_keywords` 的生成策略

### P2 — 长期

**3. 1688 真实抓取**
- 文件：`src/modules/scrapers/scraper_1688.py`（已禁用）
- config.ini 中 `enabled_1688 = false`
- 方向：扫码登录 Playwright 或第三方 API

**4. PyInstaller 打包 exe**
- 入口：`desktop_app.py`
- 命令：`pyinstaller --onefile --windowed desktop_app.py`
- 注意：Playwright 浏览器需单独安装

**5. 云部署**
- 平台：Railway / Render 免费套餐
- 注意：Playwright 在云端需要特别配置

---

## 三、关键文件索引

```
ai_storekeeper/
├── config.ini              ← PDD API 凭据在这里
├── app.py                  ← Streamlit 入口
├── desktop_app.py          ← 桌面 GUI
├── test_e2e_live.py        ← 真实 API 端到端测试
├── src/
│   ├── config.py           ← 配置解析
│   ├── database.py         ← SQLite (含 delete_opportunities_by_platform)
│   └── modules/
│       ├── matcher.py      ← bidirectional_scan + validate_match
│       ├── arbitrage.py    ← 套利计算 (config 驱动)
│       ├── scheduler.py    ← 后台调度 (含周报+价格预警)
│       ├── pusher.py       ← 邮件推送
│       ├── reporter.py     ← 日报+周报
│       ├── discovery.py    ← 关键词扩展
│       ├── price_alert.py  ← 价格预警 ✨ v1.2 新增
│       └── scrapers/
│           ├── scraper_pdd_api.py   ← PDD API (含 token 自动刷新)
│           ├── scraper_xianyu.py    ← 闲鱼 Playwright
│           └── scraper_1688.py      ← 1688 (已禁用)
└── pages/
    ├── __init__.py         ← 共享组件 (optimized CSS v1.2)
    ├── home.py             ← 首页 (KPI+饼图+趋势图 v1.2)
    ├── radar.py            ← 雷达/扫描 (auto_run)
    ├── kanban.py           ← 看板/审核 (玻璃卡片 v1.2)
    ├── tools.py            ← 工具 (价格预警按钮 v1.2)
    └── history.py          ← 历史 (搜索+分页+ROI着色 v1.2)
```

---

## 四、测试验证

```bash
# 单元测试（47个）
python -m pytest tests -q

# 端到端测试（真实 API，3-5分钟）
python test_e2e_live.py

# 验证价格预警模块
python -c "import sys; sys.path.insert(0,'src'); from modules.price_alert import scan_price_drops; print('OK')"

# 启动后验证步骤：
# 1. streamlit run app.py
# 2. 首页 → 看 KPI / 饼图 / 趋势折线 / Top 5 玻璃卡片
# 3. 雷达 → 点"立即扫描"
# 4. 看板 → 玻璃卡片 (进价红/售价绿/净利绿 + 链接按钮)
# 5. 工具 → 点"检查价格预警"
# 6. 历史 → 搜索/分页/ROI 着色/导出 CSV
```

---

## 五、PDD API 凭据（勿泄露）

```
client_id:     5faa6042b15e47a9b069ecb4bc341e99
client_secret: 15b3790d5bac81b2c1b20a89396e4dbca073fb9a
pid:           44528269_316642966
api_url:       https://gw-api.pinduoduo.com/api/router
```
