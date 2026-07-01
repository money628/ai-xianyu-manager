"""创建桌面快捷方式 — v1.2"""
import os
import subprocess
import sys

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DESKTOP = os.path.join(os.path.expanduser("~"), "Desktop")

BAT_STREAMLIT = os.path.join(APP_DIR, "启动Streamlit.bat")
SHORTCUT_WEB = os.path.join(DESKTOP, "AI店长.lnk")

# 1. 创建 Streamlit 启动脚本
with open(BAT_STREAMLIT, "w", encoding="utf-8") as f:
    f.write(f'''@echo off
cd /d "{APP_DIR}"
echo AI店长 v1.2 启动中...

taskkill /f /im python.exe >nul 2>&1
taskkill /f /im pythonw.exe >nul 2>&1

start "AI店长" /min cmd /c "streamlit run app.py --server.headless true --server.enableCORS false --browser.gatherUsageStats false"
timeout /t 5 /nobreak >nul
start http://localhost:8501
echo 浏览器已打开: http://localhost:8501
''')

# 2. Streamlit 网页版快捷方式（唯一入口）
ps1 = f'''
$ws = New-Object -ComObject WScript.Shell
$s = $ws.CreateShortcut("{SHORTCUT_WEB}")
$s.TargetPath = "cmd.exe"
$s.Arguments = '/c "{BAT_STREAMLIT}"'
$s.WorkingDirectory = "{APP_DIR}"
$s.IconLocation = "shell32.dll,14"
$s.Description = "AI店长 - Streamlit 网页版"
$s.Save()
'''
subprocess.run(["powershell", "-Command", ps1], capture_output=True)

print("桌面快捷方式已创建:")
print(f"  网页版: {SHORTCUT_WEB}")
