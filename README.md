# AI 闲鱼店长 v1.2

跨电商平台选品套利工具，扫描拼多多低价商品和闲鱼售价，自动发现搬砖/撸货机会。

## 功能

- **雷达扫描**：PDD API + 闲鱼 Playwright 双端搜索，关键词池自动循环
- **商品族聚合**：同品牌同系列多型号自动合并为一个商品族
- **AI 铺货**：DeepSeek API 自动生成闲鱼标题、描述、客服话术
- **自动上架**：Playwright 控制卖家中心自动填表
- **发货 SOP**：订单状态流转 + 买家地址复制 + PDD 进货链接一键跳转
- **流量复盘**：闲鱼卖家数据自动同步 + 曝光/浏览/想要趋势图
- **类目过滤**：服装/鞋帽等低利润品类自动拦截

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt
playwright install chromium

# 配置
cp config.ini.example config.ini
# 编辑 config.ini 填入 PDD API 密钥

# 启动
streamlit run app.py
```

访问 http://localhost:8501

## 配置

`config.ini` 必填项：
- `[pdd_api]` — client_id, client_secret, access_token, refresh_token, pid
- `[ai]` — api_key (DeepSeek API，可选)

## 技术栈

Python 3.11 / Streamlit / Playwright / FastAPI / SQLite / Plotly

## 声明

仅供学习研究，请遵守各平台使用协议。
