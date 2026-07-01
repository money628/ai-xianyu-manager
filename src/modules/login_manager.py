"""AI店长 v1.1 - 登录态管理器

用户手动在各平台登录一次，Cookie/StorageState 持久化到磁盘。
后续 Playwright 抓取器加载这些 state，免登录复用。

使用：
  python -m src.modules.login_manager login 1688      # 弹出浏览器让用户手动登录 1688
  python -m src.modules.login_manager login pdd       # 登录拼多多
  python -m src.modules.login_manager login xianyu    # 登录闲鱼
  python -m src.modules.login_manager login all       # 依次登录三平台
  python -m src.modules.login_manager status          # 查看登录状态
"""
import json
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# storage state 持久化目录
STATE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "login_states"

# 各平台登录入口配置
PLATFORMS = {
    "1688": {
        "name": "1688",
        "login_url": "https://login.1688.com/member/signin.htm",
        "verify_url": "https://www.1688.com/",
        "verify_keyword": "1688",  # 登录成功后页面标题/url 中包含的关键词
        "state_file": "1688_state.json",
    },
    "pdd": {
        "name": "拼多多",
        "login_url": "https://mobile.yangkeduo.com/login.html",
        "verify_url": "https://mobile.yangkeduo.com/",
        "verify_keyword": "yangkeduo",
        "state_file": "pdd_state.json",
    },
    "xianyu": {
        "name": "闲鱼",
        "login_url": "https://passport.goofish.com/mini_login.htm?appName=xianyu&appEntrance=web",
        "verify_url": "https://www.goofish.com/",
        "verify_keyword": "goofish",
        "state_file": "xianyu_state.json",
    },
}


def get_state_path(platform: str) -> Path:
    """获取某平台 storage state 文件路径"""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    return STATE_DIR / PLATFORMS[platform]["state_file"]


def is_logged_in(platform: str) -> bool:
    """检查某平台是否已存在登录态"""
    path = get_state_path(platform)
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        cookies = data.get("cookies", [])
        return len([c for c in cookies if c.get("name", "").lower() in
                    ("login","sid","token","_m_h5_tk","cookie2","unb","_tb_token_","sgcookie")]) > 0
    except Exception:
        return False


def login_platform(platform: str, timeout_minutes: int = 5, force: bool = False) -> bool:
    """启动可见浏览器，让用户手动登录某平台

    Args:
        platform: 平台 key (1688/pdd/xianyu)
        timeout_minutes: 最长等待用户登录完成的时间（分钟）
        force: 超时后不管是否检测到登录，都强制保存 state

    Returns:
        是否登录成功并已保存 storage state
    """
    if platform not in PLATFORMS:
        logger.error("未知平台: %s", platform)
        return False

    cfg = PLATFORMS[platform]
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.error("未安装 playwright: pip install playwright && playwright install chromium")
        return False

    state_path = get_state_path(platform)

    print(f"\n========== 登录 {cfg['name']} ==========")
    print(f"即将打开浏览器，请在弹出窗口中手动完成登录")
    print(f"登录成功后浏览器会自动关闭，登录态将持久化到: {state_path}")
    if force:
        print(f"【自动保存模式】{timeout_minutes} 分钟后自动保存当前状态，无需手动确认")
    print(f"超时时间: {timeout_minutes} 分钟\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=["--start-maximized"])
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        page = ctx.new_page()
        page.goto(cfg["login_url"], timeout=30000)

        # 轮询等待用户登录成功（检测 URL 或页面元素）
        import time
        deadline = time.time() + timeout_minutes * 60
        logged = False
        while time.time() < deadline:
            try:
                current_url = page.url
                if cfg["verify_keyword"] in current_url.lower() and "login" not in current_url.lower():
                    logged = True
                    break
            except Exception:
                pass
            try:
                page.wait_for_timeout(2000)
            except Exception:
                break

        if not logged and not force:
            # 非 force 模式：交互式确认
            try:
                user_confirm = input("\n未自动检测到登录成功。如果已登录，输入 y 保存当前状态，其他键放弃: ").strip().lower()
            except (EOFError, OSError):
                # 无终端交互时默认放弃
                user_confirm = "n"
            if user_confirm != "y":
                browser.close()
                print("已放弃")
                return False

        # 保存 storage state
        state = ctx.storage_state()
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        browser.close()

    print(f"\n✅ {cfg['name']} 登录态已保存到: {state_path}")
    return True


def login_all(force: bool = False) -> dict:
    """依次登录所有平台，返回各平台登录结果"""
    results = {}
    for pf in PLATFORMS:
        results[pf] = login_platform(pf, force=force)
    return results


def status() -> dict:
    """查看各平台登录状态"""
    return {pf: is_logged_in(pf) for pf in PLATFORMS}


def main():
    """CLI 入口"""
    if len(sys.argv) < 2:
        print("用法:")
        print("  python -m src.modules.login_manager login <platform|all> [--force]")
        print("  python -m src.modules.login_manager status")
        print(f"  支持平台: {', '.join(PLATFORMS.keys())}")
        sys.exit(1)

    cmd = sys.argv[1]
    force = "--force" in sys.argv or "-f" in sys.argv

    if cmd == "status":
        s = status()
        print("\n=== 登录状态 ===")
        for pf, logged in s.items():
            mark = "✅ 已登录" if logged else "❌ 未登录"
            print(f"  {PLATFORMS[pf]['name']:6s} {mark}")
    elif cmd == "login":
        args = [a for a in sys.argv[2:] if not a.startswith("-")]
        if len(args) < 1:
            print(f"请指定平台: {', '.join(PLATFORMS.keys())} 或 all")
            sys.exit(1)
        target = args[0]
        if target == "all":
            login_all(force=force)
        elif target in PLATFORMS:
            login_platform(target, force=force)
        else:
            print(f"未知平台: {target}, 支持: {', '.join(PLATFORMS.keys())}")
            sys.exit(1)
    else:
        print(f"未知命令: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()