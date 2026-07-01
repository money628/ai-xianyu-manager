"""自动上架模块 — Playwright 控制闲鱼发布页（含风控）"""
import json, logging, os, random, sys, time
from pathlib import Path

logger = logging.getLogger(__name__)


def _human_type(page, element, text: str):
    """模拟真人逐字输入，随机间隔"""
    element.click()
    time.sleep(random.uniform(0.3, 0.8))
    element.select_text()
    element.press("Backspace")
    time.sleep(random.uniform(0.1, 0.3))
    for char in text:
        element.type(char, delay=random.randint(50, 180))
        if random.random() < 0.15:
            time.sleep(random.uniform(0.2, 0.6))
    time.sleep(random.uniform(0.3, 0.7))


def _random_scroll(page):
    """模拟真人滚动"""
    page.mouse.wheel(0, random.randint(100, 400))
    time.sleep(random.uniform(0.2, 0.6))
    if random.random() < 0.3:
        time.sleep(random.uniform(0.8, 2.0))


def auto_fill_listing(draft, opp: dict = None) -> dict:
    state_path = Path(__file__).resolve().parent.parent.parent / "data" / "login_states" / "xianyu_state.json"
    if not state_path.exists():
        return {"ok": False, "error": "请先用 Edge 提取闲鱼 cookie"}

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"ok": False, "error": "playwright 未安装"}

    title = getattr(draft, "title", "") or draft.get("title", "")
    desc = getattr(draft, "description", "") or draft.get("description", "")
    price = getattr(draft, "price", 0) or draft.get("price", 0)

    result = {"ok": False, "steps": [], "message": ""}

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False, channel="msedge",
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-proxy-server",
                "--disable-dev-shm-usage",
                "--disable-features=IsolateOrigins",
                "--disable-infobars",
            ],
        )
        ctx = browser.new_context(
            storage_state=str(state_path),
            viewport={"width": 1280, "height": 900},
            locale="zh-CN",
        )
        # 注入反检测 JS
        ctx.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            window.chrome = {runtime: {}};
        """)
        page = ctx.new_page()

        # 先打开首页，模拟真人行为
        page.goto("https://www.goofish.com/", timeout=20000, wait_until="domcontentloaded")
        time.sleep(random.uniform(1.5, 3.0))
        _random_scroll(page)

        # 打开发布页
        page.goto("https://seller.goofish.com/?site=COMMONPRO#/seller-item/publish", timeout=30000, wait_until="domcontentloaded")
        time.sleep(random.uniform(3, 5))
        result["steps"].append({"step": "open_page", "ok": True})
        _random_scroll(page)

        # 点"发闲置"按钮
        try:
            btn = page.locator("text=/发闲置|发布闲置|发布宝贝/i").first
            if btn.is_visible(timeout=3000):
                btn.click()
                result["steps"].append({"step": "click_publish", "ok": True})
                time.sleep(random.uniform(2, 3.5))
        except:
            pass

        _random_scroll(page)
        time.sleep(random.uniform(0.5, 1.5))

        # 标题
        try:
            title_els = page.locator("input[type=text], [contenteditable=true]").all()
            filled_title = False
            for el in title_els:
                if el.is_visible():
                    _human_type(page, el, title)
                    filled_title = True
                    break
            result["steps"].append({"step": "fill_title", "ok": filled_title})
            if filled_title:
                time.sleep(random.uniform(1, 2.5))
        except Exception as e:
            result["steps"].append({"step": "fill_title", "ok": False, "error": str(e)[:50]})

        _random_scroll(page)

        # 描述
        try:
            desc_els = page.locator("textarea, [role=textbox], [contenteditable=true]").all()
            filled_desc = False
            for el in desc_els:
                if el.is_visible() and el != (title_els[0] if 'title_els' in dir() and title_els else None):
                    _human_type(page, el, desc[:500])
                    filled_desc = True
                    break
            result["steps"].append({"step": "fill_desc", "ok": filled_desc})
        except Exception as e:
            result["steps"].append({"step": "fill_desc", "ok": False, "error": str(e)[:50]})

        _random_scroll(page)
        time.sleep(random.uniform(0.5, 1.0))

        # 价格
        try:
            price_els = page.locator("input[type=number], input[placeholder*=价格], input[placeholder*=￥]").all()
            filled_price = False
            for el in price_els:
                if el.is_visible():
                    _human_type(page, el, str(int(price)))
                    filled_price = True
                    break
            result["steps"].append({"step": "fill_price", "ok": filled_price})
        except Exception as e:
            result["steps"].append({"step": "fill_price", "ok": False, "error": str(e)[:50]})

        filled_count = sum(1 for s in result["steps"] if s.get("ok"))
        result["ok"] = filled_count >= 2

        result["title"] = title
        result["price"] = price
        result["filled_count"] = filled_count

        if result["ok"]:
            result["message"] = f"已填写 {filled_count} 个字段。浏览器保持打开，请手动上传图片 + 点发布"
        else:
            result["message"] = f"仅填写 {filled_count} 个字段，需手动补全"

        # 浏览器保持打开直到用户处理完
        # ctx.close() 和 browser.close() 不调用，让用户手动操作

    return result
