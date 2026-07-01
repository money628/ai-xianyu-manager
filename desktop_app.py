"""AI店长 v1.2 - Windows 桌面GUI

双击运行，托盘图标常驻，定时扫描 + 实时推送。
"""
import os
import sys
import threading
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(SCRIPT_DIR, "src"))

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext


class AiStorekeeperApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("AI店长 v1.2 - 跨平台套利助手")
        self.root.geometry("680x520")
        self.root.resizable(True, True)
        self._scan_running = False
        self._stop_event = threading.Event()
        self._scan_thread = None
        self._setup_ui()
        self._center_window()

    def _center_window(self):
        self.root.update_idletasks()
        w, h = self.root.winfo_width(), self.root.winfo_height()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.root.geometry(f"+{x}+{y}")

    def _setup_ui(self):
        # 顶部标题
        header = ttk.Frame(self.root)
        header.pack(fill="x", padx=12, pady=8)
        ttk.Label(header, text="AI店长", font=("Microsoft YaHei", 18, "bold")).pack(side="left")
        self._status_label = ttk.Label(header, text="就绪", foreground="gray")
        self._status_label.pack(side="right")

        # 控制按钮
        ctrl = ttk.Frame(self.root)
        ctrl.pack(fill="x", padx=12, pady=4)
        self._btn_scan = ttk.Button(ctrl, text="立即扫描", command=self._manual_scan)
        self._btn_scan.pack(side="left", padx=4)
        self._btn_auto = ttk.Button(ctrl, text="启动定时扫描 (60分钟)", command=self._toggle_auto)
        self._btn_auto.pack(side="left", padx=4)
        self._btn_view = ttk.Button(ctrl, text="打开网页面板", command=self._open_web)
        self._btn_view.pack(side="left", padx=4)
        ttk.Button(ctrl, text="退出", command=self._quit).pack(side="right", padx=4)

        # Notebook 标签页
        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=12, pady=4)

        # 日志页
        log_frame = ttk.Frame(nb)
        nb.add(log_frame, text="运行日志")
        self._log_text = scrolledtext.ScrolledText(log_frame, wrap="word",
                                                     font=("Consolas", 9),
                                                     bg="#1e1e1e", fg="#d4d4d4")
        self._log_text.pack(fill="both", expand=True, padx=4, pady=4)

        # 状态页
        info_frame = ttk.Frame(nb)
        nb.add(info_frame, text="状态")
        self._info_text = scrolledtext.ScrolledText(info_frame, wrap="word",
                                                     font=("Microsoft YaHei", 10),
                                                     bg="#1e1e1e", fg="#d4d4d4",
                                                     height=10)
        self._info_text.pack(fill="both", expand=True, padx=4, pady=4)

        # 底部
        footer = ttk.Frame(self.root)
        footer.pack(fill="x", padx=12, pady=4)
        ttk.Label(footer, text="日志: data/scan_log.txt | 数据: data/ecom.db",
                  foreground="gray").pack(side="left")

    def _log(self, msg):
        timestamp = time.strftime("%H:%M:%S")
        self._log_text.insert("end", f"[{timestamp}] {msg}\n")
        self._log_text.see("end")

    def _set_status(self, text, color="gray"):
        self._status_label.config(text=text, foreground=color)

    def _manual_scan(self):
        if self._scan_running:
            messagebox.showinfo("提示", "扫描正在进行中")
            return
        self._scan_running = True
        self._btn_scan.config(state="disabled")
        self._set_status("扫描中...", "orange")
        self._log("=== 手动扫描开始 ===")
        threading.Thread(target=self._do_scan, daemon=True).start()

    def _toggle_auto(self):
        if self._scan_running:
            self._stop_auto()
        else:
            self._start_auto()

    def _start_auto(self):
        self._scan_running = True
        self._stop_event.clear()
        self._btn_auto.config(text="停止定时扫描")
        self._set_status("定时扫描运行中 (每60分钟)", "green")
        self._log("定时扫描已启动 (间隔: 60分钟)")
        self._scan_thread = threading.Thread(target=self._auto_loop, daemon=True)
        self._scan_thread.start()

    def _stop_auto(self):
        self._stop_event.set()
        self._scan_running = False
        self._btn_auto.config(text="启动定时扫描 (60分钟)")
        self._btn_scan.config(state="normal")
        self._set_status("已停止", "gray")
        self._log("定时扫描已停止")

    def _auto_loop(self):
        while not self._stop_event.is_set():
            self._do_scan()
            for _ in range(3600):
                if self._stop_event.is_set():
                    break
                time.sleep(1)
        self._scan_running = False
        self._btn_auto.config(text="启动定时扫描 (60分钟)")
        self._set_status("已停止", "gray")

    def _do_scan(self):
        try:
            from config import load_config
            from database import Database
            from modules.scrapers import ScraperPddApi, Scraper1688, ScraperXianyu
            from modules.matcher import bidirectional_scan
            from modules.pusher import Pusher
            from modules.discovery import expand_apple_keywords, expand_to_flat_list

            cfg_path = os.path.join(SCRIPT_DIR, "config.ini")
            cfg = load_config(cfg_path).as_dict()
            cfg["push"] = {"smtp_password": cfg.get("push", {}).get("smtp_pass", "")}

            db_path = os.path.join(SCRIPT_DIR, "data", "ecom.db")
            db = Database(db_path)
            shipping = float(cfg.get("finance", {}).get("domestic_shipping", 3))
            fee_rate = float(cfg.get("finance", {}).get("platform_fee_rate", 0.016))
            pusher = Pusher(cfg)

            keywords = db.get_next_keywords(3)
            if not keywords:
                self._log("关键词池空，正在扩展...")
                seeds = cfg.get("scanner", {}).get("seed_categories", [])
                all_kws = expand_to_flat_list(seeds)
                all_kws.extend(expand_apple_keywords())
                db.add_keywords(all_kws, source="auto")
                keywords = db.get_next_keywords(3)
                self._log(f"扩展完成: {len(all_kws)} 个关键词")

            total_opps = 0
            pushed = 0
            for kw in keywords:
                kw = kw.strip()
                if not kw or self._stop_event.is_set():
                    continue
                self._log(f"扫描: {kw}")

                pdd_items, xy_items = [], []
                try:
                    pdd_s = ScraperPddApi.from_config(cfg)
                    pdd_items = pdd_s.fetch(kw, 10)
                    db.save_products(pdd_items, "pdd")
                    self._log(f"  PDD: {len(pdd_items)} 个")
                except Exception as e:
                    self._log(f"  PDD 失败: {e}")

                try:
                    xy_s = ScraperXianyu(cfg)
                    xy_items = xy_s.fetch(kw, 3)
                    db.save_products(xy_items, "xianyu")
                    self._log(f"  闲鱼: {len(xy_items)} 个")
                except Exception as e:
                    self._log(f"  闲鱼 失败: {e}")

                try:
                    s1688 = Scraper1688(cfg)
                    db.save_products(s1688.fetch(kw, 5), "1688")
                except Exception:
                    pass

                if pdd_items and xy_items:
                    opps = bidirectional_scan(kw, pdd_s, xy_s, shipping, fee_rate,
                                              min_roi=15, min_similarity=0.12)
                    for d in opps:
                        d["status"] = "pending"
                        db.save_opportunity(d)
                        total_opps += 1
                        self._log(f"  >> ROI={d.get('roi',0):.0f}% | "
                                  f"{d.get('buy_price',0):.2f}→{d.get('sell_price',0):.2f} | "
                                  f"{d.get('buy_title','')[:25]}")
                        if d.get("roi", 0) >= 30:
                            if pusher.push_opportunity(d):
                                pushed += 1
                                self._log(f"  >> 已推送")

                db.save_price_snapshot(db.get_recent_products(limit=500))
                db.mark_keyword_scanned(kw)
                time.sleep(2)

            db.cleanup_old_data()
            self._log(f"扫描完成: {len(keywords)} 关键词, {total_opps} 机会, {pushed} 推送")

            info = db.get_stats()
            self._info_text.delete(1.0, "end")
            self._info_text.insert("end",
                f"今日机会: {info.get('today_opportunities',0)}\n"
                f"平均ROI: {info.get('avg_roi',0):.1f}%\n"
                f"商品总数: {info.get('total_products',0)}\n"
                f"机会总数: {info.get('total_opportunities',0)}\n"
                f"待审核: {info.get('pending_count',0)}\n"
                f"高ROI: {info.get('high_roi_count',0)}\n"
                f"已推送: {info.get('pushed_count',0)}\n"
            )

        except Exception as e:
            self._log(f"扫描异常: {e}")

        self._btn_scan.config(state="normal")
        self._set_status("就绪", "gray")

    def _open_web(self):
        import subprocess, webbrowser, time
        subprocess.Popen(
            ["streamlit", "run", os.path.join(SCRIPT_DIR, "app.py"),
             "--server.headless", "true"],
            cwd=SCRIPT_DIR,
        )
        time.sleep(3)
        webbrowser.open("http://localhost:8501")
        self._log("网页面板已启动: http://localhost:8501 （浏览器已自动打开）")

    def _quit(self):
        self._stop_event.set()
        self.root.destroy()

    def run(self):
        self._log("AI店长 v1.2 已启动")
        self._log("配置文件: config.ini")
        self._log("点击「立即扫描」开始或「定时扫描」挂机")
        self.root.mainloop()


if __name__ == "__main__":
    app = AiStorekeeperApp()
    app.run()
