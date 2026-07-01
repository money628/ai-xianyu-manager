#!/bin/sh
# AI店长 v1.2 Docker 入口脚本
# 启动 FastAPI (端口 8000) + Streamlit (端口 8501)

echo "=== AI店长 v1.2 Docker ==="
echo "XIANYU_HEADLESS=${XIANYU_HEADLESS:-false}"
echo "PDD_HEADLESS=${PDD_HEADLESS:-false}"

# 确保数据目录存在
mkdir -p /app/data /app/storage/image-packs /app/logs

# 自动建表
python -c "from src.database import Database; Database('/app/data/ai_storekeeper.db')" 2>/dev/null || true

# 启动 API（后台）
python -m uvicorn api:app --host 0.0.0.0 --port 8000 --log-level warning &

# 启动 Streamlit（前台）
python -m streamlit run app.py --server.headless true
