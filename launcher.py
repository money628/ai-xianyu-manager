"""AI店长 launcher - 一键启动所有服务（无终端窗口）"""
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE)

# 隐藏窗口启动
NO_WINDOW = 0x08000000

# 1. Streamlit 网页
subprocess.Popen(
    [sys.executable, "-m", "streamlit", "run", "app.py",
     "--server.address", "0.0.0.0", "--server.headless", "false"],
    cwd=BASE,
    creationflags=NO_WINDOW,
)

# 2. 钉钉机器人
subprocess.Popen(
    [sys.executable, "dingtalk_server.py"],
    cwd=BASE,
    creationflags=NO_WINDOW,
)
