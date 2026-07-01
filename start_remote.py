"""AI店长 v1.2 - 远程访问启动器（ngrok 隧道）

用法: python start_remote.py
自动启动 Streamlit + ngrok 隧道，手机可远程访问。

首次使用需要 ngrok 免费账号：
  1. 打开 https://dashboard.ngrok.com/signup 注册（免费）
  2. 复制你的 authtoken
  3. 运行: python start_remote.py --token <你的token>
  （只需设置一次，token 会保存到 config.ini）
"""
import logging
import os
import subprocess
import sys
import time
import threading

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("remote")


def get_token():
    """从 config.ini 或环境变量获取 ngrok token"""
    # 环境变量优先
    token = os.environ.get("NGROK_AUTH_TOKEN", "")
    if token:
        return token
    # config.ini
    try:
        import configparser
        cfg = configparser.ConfigParser()
        cfg.read(os.path.join(SCRIPT_DIR, "config.ini"), encoding="utf-8")
        return cfg.get("remote", "ngrok_token", fallback="")
    except Exception:
        return ""


def save_token(token: str):
    """保存 token 到 config.ini"""
    try:
        import configparser
        path = os.path.join(SCRIPT_DIR, "config.ini")
        cfg = configparser.ConfigParser()
        cfg.read(path, encoding="utf-8")
        if "remote" not in cfg:
            cfg["remote"] = {}
        cfg["remote"]["ngrok_token"] = token
        with open(path, "w", encoding="utf-8") as f:
            cfg.write(f)
        log.info("ngrok token 已保存到 config.ini")
    except Exception as e:
        log.warning("保存 token 失败: %s", e)


def start_tunnel(port: int = 8501) -> str:
    """启动 ngrok 隧道，返回公网 URL"""
    try:
        from pyngrok import ngrok, conf
    except ImportError:
        log.error("pyngrok 未安装，请运行: pip install pyngrok")
        return ""

    token = get_token()
    if not token:
        log.warning("未配置 ngrok token")
        log.warning("请访问 https://dashboard.ngrok.com/signup 注册免费账号")
        log.warning("然后运行: python start_remote.py --token <你的token>")
        return ""

    try:
        conf.get_default().auth_token = token
        tunnel = ngrok.connect(str(port), "http")
        url = tunnel.public_url
        log.info("ngrok 隧道已建立: %s", url)
        return url
    except Exception as e:
        log.error("ngrok 隧道失败: %s", e)
        return ""


def main():
    if "--token" in sys.argv:
        idx = sys.argv.index("--token")
        if idx + 1 < len(sys.argv):
            save_token(sys.argv[idx + 1])
            print("Token 已保存。现在可以启动远程访问了:")
            print("  python start_remote.py")
        else:
            print("用法: python start_remote.py --token <你的ngrok_token>")
        return

    # 启动 Streamlit
    log.info("启动 Streamlit...")
    streamlit_proc = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "app.py",
         "--server.address", "0.0.0.0",
         "--server.headless", "true"],
        cwd=SCRIPT_DIR,
    )

    time.sleep(3)

    # 启动 ngrok 隧道
    url = start_tunnel(8501)

    print()
    print("=" * 50)
    print("  AI店长 已启动")
    print("=" * 50)
    print(f"  电脑访问: http://localhost:8501")
    if url:
        print(f"  手机远程: {url}")
        print(f"  (任何地方都能访问，电脑不要关)")
    else:
        print(f"  同WiFi访问: 见上方IP地址")
    print()
    print("  按 Ctrl+C 停止")
    print("=" * 50)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("正在停止...")
        streamlit_proc.terminate()


if __name__ == "__main__":
    main()
