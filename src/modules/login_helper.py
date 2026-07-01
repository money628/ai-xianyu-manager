"""AI店长 v1.2 - 登录助手（Chrome 持久化模式）

用法:
  python -m src.modules.login_helper <platform> [--chrome]

--chrome 参数：使用系统 Chrome + 持久化配置（绕过风控）
"""
import json
import sys
import time
from pathlib import Path

LOGIN_URLS = {
    "1688": "https://login.taobao.com/member/login.jhtml",
    "pdd": "https://mobile.yangkeduo.com/login.html",
    "xianyu": "https://passport.goofish.com/mini_login.htm?appName=xianyu&appEntrance=web",
}
STATE_FILES = {
    "1688": "1688_state.json",
    "pdd": "pdd_state.json",
    "xianyu": "xianyu_state.json",
}
PLATFORM_NAMES = {
    "1688": "1688",
    "pdd": "pdd",
    "xianyu": "xianyu",
}
AUTH_COOKIES = {
    "1688": {"__cn_logon__", "cookie2", "t", "unb"},
    "pdd": {"PDDAccessToken", "pdd_user_id", "pdd_user_uin"},
    "xianyu": {"t", "cookie2", "unb"},
}
MIN_AUTH_COOKIES = {
    "1688": 2,
    "pdd": 1,
    "xianyu": 3,  # 必须三个都有才认为登录成功
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in LOGIN_URLS:
        print(f"Usage: python -m src.modules.login_helper <platform> [--chrome] [--force]")
        print(f"platforms: {', '.join(LOGIN_URLS.keys())}")
        sys.exit(1)

    platform = sys.argv[1]
    use_chrome = "--chrome" in sys.argv
    force = "--force" in sys.argv
    login_url = LOGIN_URLS[platform]
    state_file = STATE_FILES[platform]
    name = PLATFORM_NAMES[platform]
    auth_names = AUTH_COOKIES.get(platform, set())

    data_dir = Path(__file__).resolve().parent.parent.parent / "data"
    state_dir = data_dir / "login_states"
    state_dir.mkdir(parents=True, exist_ok=True)
    state_path = state_dir / state_file

    profile_dir = data_dir / "browser_profiles" / platform
    profile_dir.mkdir(parents=True, exist_ok=True)

    # 强制模式：删除旧 cookie 和 profile
    if force:
        import shutil
        if state_path.exists():
            state_path.unlink()
            print(f"Deleted old state: {state_path}")
        if profile_dir.exists():
            shutil.rmtree(str(profile_dir), ignore_errors=True)
            print(f"Deleted old profile: {profile_dir}")
        profile_dir.mkdir(parents=True, exist_ok=True)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Please install playwright: pip install playwright && playwright install chromium")
        sys.exit(1)

    print(f"\n========== Login {name} ==========")
    print(f"Profile: {profile_dir}")

    with sync_playwright() as p:
        args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--disable-features=IsolateOrigins,site-per-process",
            "--disable-infobars",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-networking",
            "--no-proxy-server",
        ]
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=False,
            channel="chrome",
            args=args,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            locale="zh-CN",
            ignore_default_args=["--enable-automation"],
        )

        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        # 注入反检测脚本
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
            Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh']});
            window.chrome = {runtime: {}};
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                Promise.resolve({state: Notification.permission}) :
                originalQuery(parameters)
            );
        """)

        # 应用 playwright-stealth
        try:
            from playwright_stealth import Stealth
            Stealth().apply_stealth_sync(page)
        except Exception:
            pass
        page.goto(login_url, timeout=30000, wait_until="domcontentloaded")

        print(f"\n[请扫码登录] Chrome 已打开 {name} 登录页")
        print("请在浏览器中扫码登录，登录成功后将自动保存状态")
        print("等待中... (5分钟超时)\n")

        import time as _time
        deadline = _time.time() + 300  # 5 min timeout
        logged_in = False

        while _time.time() < deadline:
            try:
                cookies = ctx.cookies()
            except Exception:
                _time.sleep(2)
                continue

            found = {c["name"] for c in cookies if c.get("name") in auth_names}
            min_required = MIN_AUTH_COOKIES.get(platform, 1)

            current_url = page.url.lower()
            on_xianyu = "goofish.com" in current_url
            on_login = "passport" in current_url or "login" in current_url

            if platform == "xianyu":
                # 必须不在登录页 + 有足够 cookie 才算真登录
                if not on_login and len(found) >= min_required:
                    # 再验证：导航到搜索页看是否跳转
                    try:
                        page.goto("https://www.goofish.com/search?q=test", timeout=15000, wait_until="domcontentloaded")
                        _time.sleep(2)
                        verify_url = page.url.lower()
                        if "passport" not in verify_url:
                            logged_in = True
                            print(f"\n[OK] 登录验证通过！")
                        else:
                            print(f"\n[!] 登录可能未成功，仍在登录页。请确认已扫码。")
                    except Exception:
                        if len(found) >= min_required:
                            logged_in = True
                elif on_xianyu and not on_login and len(found) >= min_required:
                    logged_in = True

            elif not on_login:
                if len(found) >= min_required:
                    logged_in = True

            if logged_in:
                print(f"Auth cookies: {', '.join(found)}")
                break

            _time.sleep(2)

        if not logged_in:
            print(f"\n! 超时或未检测到完整登录，正在保存当前 cookies...")
            input("按回车保存并退出: ")

        # Save state
        state = ctx.storage_state()
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

        cookie_names = {c.get("name", "") for c in state.get("cookies", [])}
        matched = auth_names & cookie_names

        print(f"\n[保存] {state_path}")
        print(f"Cookies: {len(state.get('cookies', []))} 个, 有效 {len(matched)} 个")
        if matched:
            print(f"Auth found: {', '.join(matched)}")

        ctx.close()


if __name__ == "__main__":
    main()
