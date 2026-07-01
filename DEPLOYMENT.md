# AI店长 v1.2 — 云端部署文档

## 环境要求

| 项目 | 最低配置 |
|------|---------|
| CPU | 2 核 |
| 内存 | 4 GB |
| 磁盘 | 20 GB |
| 系统 | Ubuntu 22.04 (推荐) / Debian 12 |
| Docker | 24+ |
| Docker Compose | 2.20+ |

## 快速部署（5 分钟）

### 1. 安装 Docker

```bash
curl -fsSL https://get.docker.com | bash
sudo usermod -aG docker $USER
# 退出重新登录
```

### 2. 上传项目

```bash
# 方式 A: git clone
git clone <你的仓库地址> ai-storekeeper
cd ai-storekeeper

# 方式 B: scp 上传
scp -r ai-storekeeper user@server:/home/user/
```

### 3. 配置密钥

```bash
# 复制配置模板
cp config.docker.ini config.ini

# 编辑填入真实密钥
vim config.ini
```

**必须填写的项：**
- `[pdd_api]` — client_id, client_secret, access_token, refresh_token, pid
- `[pdd_accounts]` — 至少 account_1 的所有字段
- `[push]` — dingtalk_webhook / email 配置 (可选)

### 4. 构建并启动

```bash
docker compose up -d --build
```

### 5. 验证

```bash
# 健康检查
curl http://localhost:8000/health
# 返回: {"ok":true,"db":"ok","storage":"ok","time":"..."}

# 浏览器访问
http://<服务器IP>:8501
```

## 服务说明

| 服务 | 端口 | 说明 |
|------|------|------|
| Streamlit UI | 8501 | Web 界面 |
| FastAPI | 8000 | REST API + 健康检查 |
| Scheduler | — | 后台定时扫描 (60 分钟) |

## 配置说明

### 关键环境变量

Docker 容器通过环境变量覆盖本地配置：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `XIANYU_HEADLESS` | `true` | 闲鱼爬虫无头模式 (服务器必须 true) |
| `PDD_HEADLESS` | `true` | PDD 爬虫无头模式 |
| `TZ` | `Asia/Shanghai` | 时区 |

### config.ini 挂载

`config.ini` 通过只读卷挂载到容器：
```yaml
volumes:
  - ./config.ini:/app/config.ini:ro
```

修改 config.ini 后需重启：
```bash
docker compose restart
```

## 数据持久化

| Docker 卷 | 主机路径 | 内容 |
|-----------|---------|------|
| `ai_data` | Docker Volume | SQLite 数据库、登录态 |
| `ai_storage` | Docker Volume | 图片包、导出文件 |
| `ai_logs` | Docker Volume | 运行日志 |

**备份数据库：**
```bash
docker exec ai-storekeeper python -c "
from src.database import Database
Database('data/ai_storekeeper.db').backup()
"
```

## 常用命令

```bash
# 查看日志
docker compose logs -f app

# 查看调度器日志
docker compose logs -f scheduler

# 重启服务
docker compose restart

# 停止服务
docker compose stop

# 重建
docker compose up -d --build

# 进入容器
docker exec -it ai-storekeeper bash
```

## HTTPS 配置 (Nginx 反代)

```nginx
server {
    listen 443 ssl;
    server_name your-domain.com;
    ssl_certificate /etc/ssl/cert.pem;
    ssl_certificate_key /etc/ssl/key.pem;

    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 300s;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000/;
        proxy_set_header Host $host;
    }
}
```

## 防火墙

```bash
# 仅开放必要端口
sudo ufw allow 22
sudo ufw allow 80
sudo ufw allow 443
# 8501/8000 通过 Nginx 反代，不直接暴露
sudo ufw enable
```

## 安全注意事项

1. **config.ini 绝不提交 git** — 已加入 .gitignore
2. Docker 容器内日志不打印完整 token (代码已处理)
3. 生产环境用 Nginx 反代 + HTTPS
4. 定期备份 `data/ai_storekeeper.db`

## 故障排查

### Playwright 无法启动
```bash
docker exec ai-storekeeper playwright install chromium
docker exec ai-storekeeper playwright install-deps chromium
```

### 闲鱼爬虫不工作
确认 `XIANYU_HEADLESS=true` 已设置，且 `data/xianyu_state.json` 有有效登录态。

### 容器一直重启
```bash
docker compose logs app --tail 50
```

### 端口冲突
修改 `docker-compose.yml` 中的 `ports` 映射。
