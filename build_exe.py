"""AI店长 - PyInstaller 打包配置

打包命令:
    pip install pyinstaller
    pyinstaller ai_storekeeper.spec

生成 dist/AI店长.exe（约 150MB，含 Playwright + Chrome）
"""
import sys
from pathlib import Path

# ---------- 配置 ----------
APP_NAME = "AI店长"
ENTRY_SCRIPT = "run_scan.py"  # 单次扫描入口
ICON_FILE = None  # 可指定 .ico 图标
CONSOLE_MODE = True  # True=控制台窗口, False=后台无窗口

# ---------- 隐匿数据 ----------
HIDDEN_IMPORTS = [
    "playwright", "playwright.sync_api",
    "requests", "urllib3", "certifi",
    "streamlit", "plotly", "pandas",
    "json", "logging", "hashlib", "re", "time", "random",
    "collections", "typing", "urllib.parse",
    "pathlib", "sqlite3", "datetime", "copy",
]

# Playwright 浏览器（Chromium）
PLAYWRIGHT_BROWSERS_DIR = str(
    Path.home() / "AppData/Local/ms-playwright"
)

# ---------- 构建 spec 文件 ----------
def generate_spec():
    return f"""
# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['{ENTRY_SCRIPT}'],
    pathex=['src'],
    binaries=[],
    datas=[
        ('config.ini', '.'),
        ('data', 'data'),
    ],
    hiddenimports={HIDDEN_IMPORTS},
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=['matplotlib', 'scipy', 'PIL', 'tkinter'],
)

# 包含 Playwright 浏览器
a.datas += Tree('{PLAYWRIGHT_BROWSERS_DIR}', prefix='ms-playwright')

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='{APP_NAME}',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console={CONSOLE_MODE},
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
"""


if __name__ == "__main__":
    spec_content = generate_spec()
    spec_path = Path(__file__).parent / "ai_storekeeper.spec"
    spec_path.write_text(spec_content, encoding="utf-8")
    print(f"Spec written to {spec_path}")
    print(f"Run: pyinstaller {spec_path}")
