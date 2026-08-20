"""Clash 节点筛选器桌面版。

界面使用 Tkinter，代理解析和网页测试由本地 Mihomo 核心提供。
测试目标是 HTTP/HTTPS 网页请求，不使用 ICMP ping。
"""

from __future__ import annotations

import csv
import ctypes
import json
import os
import queue
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from tkinter import END, BooleanVar, Canvas, StringVar, TclError, Tk, filedialog, messagebox, ttk

try:
    import websocket  # type: ignore
except ImportError:
    websocket = None


APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR / "backend"
BACKEND_EXE = BACKEND_DIR / "clash-speedtest.exe"
BACKEND_CONFIG = BACKEND_DIR / "desktop-config.yaml"
API_BASE = "http://127.0.0.1:18080"
WS_URL = "ws://127.0.0.1:18080/ws"

PLATFORMS = [
    ("Netflix", "流媒体", True),
    ("YouTube", "视频", True),
    ("Disney+", "流媒体", True),
    ("ChatGPT", "AI 服务", True),
    ("Spotify", "音乐", True),
    ("Bilibili", "区域内容", False),
]


@dataclass
class TestOptions:
    source: str
    server_url: str
    test_mode: str
    timeout: int
    concurrent: int
    max_latency: int
    download_size: int
    upload_size: int
    platforms: list[str]


class ClashFilterApp:
    """桌面应用主窗口。"""

    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title("Clash 节点筛选器")
        self.root.geometry("1180x780")
        self.root.minsize(980, 650)
        self.root.configure(bg="#f4f6fb")

        self.backend: subprocess.Popen[str] | None = None
        self.event_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.results: list[dict] = []
        self.nodes: list[dict] = []
        self.testing = False
        self.fetching = False
        self.ws = None

        self.source_var = StringVar()
        self.server_var = StringVar(value="https://speed.cloudflare.com")
        self.mode_var = StringVar(value="网页可用性 + 速度")
        self.timeout_var = StringVar(value="8")
        self.concurrent_var = StringVar(value="3")
        self.latency_var = StringVar(value="1500")
        self.download_var = StringVar(value="5")
        self.upload_var = StringVar(value="2")
        self.status_var = StringVar(value="准备就绪 · 尚未加载订阅")
        self.progress_var = StringVar(value="0 / 0")
        self.summary_var = StringVar(value="0 个节点")
        self.platform_vars = {name: BooleanVar(value=enabled) for name, _, enabled in PLATFORMS}
        self.platform_buttons: dict[str, ttk.Button] = {}
        self.platform_status_var = StringVar()
        self._update_platform_status()

        self._setup_style()
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(100, self._drain_events)
        self.root.after(200, self._ensure_backend)

    def _setup_style(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("App.TFrame", background="#f4f6fb")
        style.configure("Panel.TFrame", background="#ffffff")
        style.configure("Panel2.TFrame", background="#f1f4fa")
        style.configure("Title.TLabel", background="#f4f6fb", foreground="#202735", font=("Segoe UI", 22, "bold"))
        style.configure("Subtitle.TLabel", background="#f4f6fb", foreground="#6d7687", font=("Segoe UI", 10))
        style.configure("Section.TLabel", background="#ffffff", foreground="#283142", font=("Segoe UI", 11, "bold"))
        style.configure("Muted.TLabel", background="#ffffff", foreground="#737c8c", font=("Segoe UI", 9))
        style.configure("Value.TLabel", background="#ffffff", foreground="#283142", font=("Segoe UI", 10))
        style.configure("Accent.TButton", background="#147fc2", foreground="#ffffff", font=("Segoe UI", 10, "bold"), padding=(16, 9))
        style.map("Accent.TButton", background=[("active", "#0d6eaa"), ("disabled", "#a9c8dc")])
        style.configure("Ghost.TButton", background="#eef2f8", foreground="#3e4a5c", font=("Segoe UI", 9), padding=(10, 7))
        style.map("Ghost.TButton", background=[("active", "#dce8f5")])
        style.configure("Danger.TButton", background="#f7e9ed", foreground="#ad4056", font=("Segoe UI", 9, "bold"), padding=(10, 7))
        style.map("Danger.TButton", background=[("active", "#f0d5dc")])
        style.configure("TEntry", fieldbackground="#f5f7fb", foreground="#283142", insertcolor="#283142", borderwidth=0, padding=7)
        style.configure("TCombobox", fieldbackground="#f5f7fb", foreground="#283142", arrowcolor="#147fc2", padding=6)
        style.configure("Mode.TCombobox", fieldbackground="#ffffff", background="#ffffff", foreground="#000000", selectbackground="#d8f3ec", selectforeground="#000000", arrowcolor="#116c5e", padding=6)
        style.map("Mode.TCombobox", fieldbackground=[("readonly", "#ffffff"), ("focus", "#ffffff")], foreground=[("readonly", "#000000"), ("focus", "#000000")])
        # 下拉列表由 Tk 原生 Listbox 绘制，显式指定黑字，确保高 DPI 和不同主题下都清晰可读。
        self.root.option_add("*TCombobox*Listbox*Foreground", "#000000")
        self.root.option_add("*TCombobox*Listbox*Background", "#ffffff")
        self.root.option_add("*TCombobox*Listbox*selectForeground", "#000000")
        self.root.option_add("*TCombobox*Listbox*selectBackground", "#d8f3ec")
        style.configure("TCheckbutton", background="#ffffff", foreground="#283142", font=("Segoe UI", 9))
        style.map("TCheckbutton", background=[("active", "#ffffff")])
        style.configure("Target.TRadiobutton", background="#f1f4fa", foreground="#3e4a5c", font=("Segoe UI", 9), padding=(7, 5))
        style.map("Target.TRadiobutton", background=[("selected", "#dceeff"), ("active", "#e7f2fc")], foreground=[("selected", "#126ca9")])
        style.configure("Target.TButton", background="#f1f4fa", foreground="#3e4a5c", font=("Segoe UI", 9), anchor="w", padding=(7, 5), borderwidth=0)
        style.map("Target.TButton", background=[("active", "#e7f2fc")], foreground=[("active", "#126ca9")])
        style.configure("TargetSelected.TButton", background="#dceeff", foreground="#126ca9", font=("Segoe UI", 9, "bold"), anchor="w", padding=(7, 5), borderwidth=0)
        style.map("TargetSelected.TButton", background=[("active", "#cbe4f8")], foreground=[("active", "#0d5f98")])
        style.configure("Treeview", background="#ffffff", fieldbackground="#ffffff", foreground="#3a4556", rowheight=32, borderwidth=0, font=("Segoe UI", 9))
        style.configure("Treeview.Heading", background="#eef2f8", foreground="#626d7e", font=("Segoe UI", 9, "bold"), padding=7)
        style.map("Treeview", background=[("selected", "#dceeff")], foreground=[("selected", "#126ca9")])
        style.configure("Horizontal.TProgressbar", troughcolor="#e5ebf4", background="#147fc2", borderwidth=0, thickness=6)

    def _build_ui(self) -> None:
        shell = ttk.Frame(self.root, style="App.TFrame", padding=(24, 20, 24, 18))
        shell.pack(fill="both", expand=True)

        header = ttk.Frame(shell, style="App.TFrame")
        header.pack(fill="x")
        ttk.Label(header, text="Clash 节点筛选器", style="Title.TLabel").pack(side="left")
        ttk.Label(header, text="网页可用性 · 延迟 · 下载速度", style="Subtitle.TLabel").pack(side="left", padx=(14, 0), pady=(8, 0))
        ttk.Label(header, text="本地测试工具", style="Subtitle.TLabel").pack(side="right", pady=(8, 0))

        source = ttk.Frame(shell, style="Panel.TFrame", padding=16)
        source.pack(fill="x", pady=(18, 12))
        ttk.Label(source, text="订阅来源", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(source, text="支持订阅 URL、Clash/Mihomo YAML、Base64 节点列表；多个来源用英文逗号分隔", style="Muted.TLabel").grid(row=1, column=0, columnspan=3, sticky="w", pady=(3, 12))
        entry = ttk.Entry(source, textvariable=self.source_var)
        entry.grid(row=2, column=0, sticky="ew", padx=(0, 8))
        source.columnconfigure(0, weight=1)
        ttk.Button(source, text="选择 YAML", style="Ghost.TButton", command=self._choose_file).grid(row=2, column=1, padx=(0, 8))
        self.fetch_button = ttk.Button(source, text="获取节点", style="Accent.TButton", command=self.fetch_nodes)
        self.fetch_button.grid(row=2, column=2)

        content = ttk.Frame(shell, style="App.TFrame")
        content.pack(fill="both", expand=True)
        content.columnconfigure(0, weight=0, minsize=292)
        content.columnconfigure(1, weight=1)
        content.rowconfigure(0, weight=1)

        controls_panel = ttk.Frame(content, style="Panel.TFrame")
        controls_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        controls_panel.rowconfigure(0, weight=1)
        controls_panel.columnconfigure(0, weight=1)
        self.controls_canvas = Canvas(controls_panel, background="#ffffff", highlightthickness=0, borderwidth=0)
        self.controls_canvas.grid(row=0, column=0, sticky="nsew")
        controls_scroll = ttk.Scrollbar(controls_panel, orient="vertical", command=self.controls_canvas.yview)
        controls_scroll.grid(row=0, column=1, sticky="ns")
        self.controls_canvas.configure(yscrollcommand=controls_scroll.set)
        controls = ttk.Frame(self.controls_canvas, style="Panel.TFrame", padding=16)
        self.controls_canvas.create_window((0, 0), window=controls, anchor="nw", tags="controls-inner")
        controls.bind("<Configure>", lambda _event: self.controls_canvas.configure(scrollregion=self.controls_canvas.bbox("all")))
        self.controls_canvas.bind("<Enter>", lambda _event: self.controls_canvas.bind_all("<MouseWheel>", self._scroll_controls))
        self.controls_canvas.bind("<Leave>", lambda _event: self.controls_canvas.unbind_all("<MouseWheel>"))
        self.controls_canvas.bind("<Configure>", self._resize_controls_inner)
        results = ttk.Frame(content, style="Panel.TFrame", padding=(14, 14, 14, 12))
        results.grid(row=0, column=1, sticky="nsew")
        results.rowconfigure(2, weight=1)
        results.columnconfigure(0, weight=1)

        self._build_controls(controls)
        self._build_results(results)

        footer = ttk.Frame(shell, style="App.TFrame")
        footer.pack(fill="x", pady=(12, 0))
        ttk.Label(footer, textvariable=self.status_var, style="Subtitle.TLabel").pack(side="left")
        ttk.Label(footer, text="所有请求仅在本机执行，不上传节点配置", style="Subtitle.TLabel").pack(side="right")

    def _resize_controls_inner(self, _event: object) -> None:
        self.controls_canvas.itemconfigure("controls-inner", width=self.controls_canvas.winfo_width())
        self.controls_canvas.configure(scrollregion=self.controls_canvas.bbox("all"))

    def _scroll_controls(self, event: object) -> None:
        delta = int(getattr(event, "delta", 0))
        self.controls_canvas.yview_scroll(-1 if delta > 0 else 1, "units")

    def _build_controls(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="测试设置", style="Section.TLabel").pack(anchor="w")
        ttk.Label(parent, text="通过真实网页请求判定节点，不发送 ICMP ping", style="Muted.TLabel").pack(anchor="w", pady=(3, 14))

        ttk.Label(parent, text="网页测速服务", style="Muted.TLabel").pack(anchor="w")
        server_box = ttk.Combobox(parent, textvariable=self.server_var, values=["https://speed.cloudflare.com"], state="normal")
        server_box.pack(fill="x", pady=(4, 12))
        ttk.Label(parent, text="末尾是否带 / 不影响访问，程序会自动规范化。", style="Muted.TLabel").pack(anchor="w", pady=(0, 10))

        ttk.Label(parent, text="测试模式", style="Muted.TLabel").pack(anchor="w")
        mode_box = ttk.Combobox(parent, textvariable=self.mode_var, values=["网页可用性 + 速度", "仅网页可用性", "仅速度"], state="readonly", style="Mode.TCombobox")
        mode_box.pack(fill="x", pady=(4, 12))

        ttk.Label(parent, text="国外网页目标", style="Muted.TLabel").pack(anchor="w")
        platforms = ttk.Frame(parent, style="Panel.TFrame")
        platforms.pack(fill="x", pady=(4, 12))
        for index, (name, category, _) in enumerate(PLATFORMS):
            button = ttk.Button(platforms, text="", style="Target.TButton", command=lambda selected=name: self._select_platform(selected))
            button.grid(row=index // 2, column=index % 2, sticky="ew", padx=(0, 8), pady=3)
            self.platform_buttons[name] = button
        platforms.columnconfigure(0, weight=1)
        platforms.columnconfigure(1, weight=1)
        self._refresh_platform_buttons()
        ttk.Label(parent, textvariable=self.platform_status_var, style="Muted.TLabel", wraplength=250).pack(anchor="w", pady=(0, 10))

        grid = ttk.Frame(parent, style="Panel.TFrame")
        grid.pack(fill="x", pady=(2, 12))
        fields = [("并发数", self.concurrent_var), ("超时（秒）", self.timeout_var), ("最大延迟（毫秒）", self.latency_var), ("下载样本（MB）", self.download_var), ("上传样本（MB）", self.upload_var)]
        for index, (label, variable) in enumerate(fields):
            row, column = divmod(index, 2)
            ttk.Label(grid, text=label, style="Muted.TLabel").grid(row=row * 2, column=column, sticky="w", padx=(0 if column == 0 else 8, 0), pady=(0, 3))
            ttk.Entry(grid, textvariable=variable, width=12).grid(row=row * 2 + 1, column=column, sticky="ew", padx=(0 if column == 0 else 8, 8 if column == 0 else 0), pady=(0, 10))
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)

        self.start_button = ttk.Button(parent, text="开始批量测试", style="Accent.TButton", command=self.start_test)
        self.start_button.pack(fill="x", pady=(4, 7))
        self.stop_button = ttk.Button(parent, text="停止当前测试", style="Danger.TButton", command=self.stop_test, state="disabled")
        self.stop_button.pack(fill="x")

        ttk.Separator(parent).pack(fill="x", pady=16)
        ttk.Label(parent, text="筛选建议", style="Section.TLabel").pack(anchor="w")
        ttk.Label(parent, text="先获取节点确认订阅可解析，再开始测试。网页可用性通过目标平台的 HTTPS 请求检测；测速使用 Cloudflare 下载/上传接口。", style="Muted.TLabel", wraplength=250, justify="left").pack(anchor="w", pady=(6, 0))

    def _build_results(self, parent: ttk.Frame) -> None:
        top = ttk.Frame(parent, style="Panel.TFrame")
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(0, weight=1)
        ttk.Label(top, text="节点结果", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(top, textvariable=self.summary_var, style="Muted.TLabel").grid(row=0, column=1, sticky="e")

        progress_row = ttk.Frame(parent, style="Panel.TFrame")
        progress_row.grid(row=1, column=0, sticky="ew", pady=(12, 12))
        progress_row.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(progress_row, mode="determinate", maximum=100, style="Horizontal.TProgressbar")
        self.progress.grid(row=0, column=0, sticky="ew", padx=(0, 12))
        ttk.Label(progress_row, textvariable=self.progress_var, style="Muted.TLabel", width=12, anchor="e").grid(row=0, column=1)

        table_frame = ttk.Frame(parent, style="Panel.TFrame")
        table_frame.grid(row=2, column=0, sticky="nsew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(1, weight=0)
        columns = ("name", "type", "server", "latency", "download", "web", "status")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="extended")
        headings = {"name": "节点", "type": "协议", "server": "服务器", "latency": "延迟", "download": "下载速度", "web": "网页可用", "status": "状态"}
        widths = {"name": 220, "type": 90, "server": 150, "latency": 75, "download": 100, "web": 100, "status": 85}
        for column in columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(column, width=widths[column], minwidth=80, stretch=False, anchor="w")
        scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        hscroll = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=scroll.set, xscrollcommand=hscroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        hscroll.grid(row=1, column=0, sticky="ew", pady=(6, 0))

        actions = ttk.Frame(parent, style="Panel.TFrame")
        actions.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        ttk.Button(actions, text="导出 JSON", style="Ghost.TButton", command=lambda: self.export_results("json")).pack(side="left")
        ttk.Button(actions, text="导出 CSV", style="Ghost.TButton", command=lambda: self.export_results("csv")).pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="清空结果", style="Ghost.TButton", command=self.clear_results).pack(side="right")

    def _choose_file(self) -> None:
        path = filedialog.askopenfilename(title="选择 Clash/Mihomo 配置", filetypes=[("YAML 文件", "*.yaml *.yml"), ("所有文件", "*.*")])
        if path:
            self.source_var.set(path)

    def _ensure_backend(self) -> None:
        if self._health_check():
            self.status_var.set("本地测试核心已连接 · 可以获取订阅")
            return
        if not BACKEND_EXE.exists():
            self.status_var.set("未找到测试核心，请先运行 build.ps1 构建")
            return
        threading.Thread(target=self._backend_worker, daemon=True).start()

    def _backend_worker(self) -> None:
        try:
            launch_kwargs: dict = {
                "cwd": str(BACKEND_DIR),
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
                "text": True,
            }
            if sys.platform == "win32":
                # Mihomo 核心是控制台程序，但桌面 GUI 不应额外弹出黑色终端窗口。
                launch_kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 0
                launch_kwargs["startupinfo"] = startupinfo
            self.backend = subprocess.Popen([str(BACKEND_EXE), f"-config={BACKEND_CONFIG.name}"], **launch_kwargs)
        except OSError as exc:
            self.event_queue.put(("error", f"测试核心启动失败：{exc}"))
            return
        for _ in range(30):
            if self._health_check():
                self.event_queue.put(("backend", "本地测试核心已连接 · 可以获取订阅"))
                return
            time.sleep(0.15)
        self.event_queue.put(("error", "测试核心启动超时，请检查 backend/logs"))

    def _health_check(self) -> bool:
        try:
            with urllib.request.urlopen(f"{API_BASE}/health", timeout=0.4) as response:
                return response.status == 200
        except (OSError, urllib.error.URLError):
            return False

    def _request_json(self, path: str, payload: dict | None = None, timeout: int = 30) -> dict:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(f"{API_BASE}{path}", data=data, headers={"Content-Type": "application/json"}, method="POST" if data else "GET")
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def _source(self) -> str:
        return self.source_var.get().strip()

    def fetch_nodes(self) -> None:
        if self.fetching or self.testing:
            return
        source = self._source()
        if not source:
            messagebox.showwarning("缺少订阅来源", "请粘贴订阅链接或选择一个 Clash/Mihomo YAML 文件。")
            return
        self.fetching = True
        self.fetch_button.configure(state="disabled")
        self.status_var.set("正在读取订阅并解析节点……")
        threading.Thread(target=self._fetch_worker, args=(source,), daemon=True).start()

    def _fetch_worker(self, source: str) -> None:
        payload = {"configPaths": source, "includeNodes": [], "excludeNodes": [], "protocolFilter": [], "stashCompatible": False}
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                response = self._request_json("/config/nodes", payload, timeout=45)
                if not response.get("success", False):
                    raise RuntimeError(response.get("error", "节点解析失败"))
                self.event_queue.put(("nodes", response.get("nodes", [])))
                return
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt == 0:
                    time.sleep(0.8)
        self.event_queue.put(("error", f"获取节点失败：{self._friendly_network_error(last_error)}"))

    @staticmethod
    def _friendly_network_error(error: Exception | None) -> str:
        text = str(error or "未知错误")
        lowered = text.lower()
        if "actively refused" in lowered or "目标计算机积极拒绝" in text or "connection refused" in lowered:
            return "订阅服务器拒绝了连接。请确认链接仍有效、端口可访问，或稍后重试；这通常是订阅服务端问题，不是节点测速失败。"
        if "timed out" in lowered or "超时" in text:
            return "订阅服务器响应超时。请检查网络、代理/VPN 状态，或稍后重试。"
        if "urlopen error" in lowered:
            return "无法连接订阅地址，请检查链接是否完整、是否需要登录，以及当前网络是否能访问该域名。"
        return text

    def _options(self) -> TestOptions:
        def number(var: StringVar, name: str, minimum: int, maximum: int) -> int:
            value = int(var.get().strip())
            if not minimum <= value <= maximum:
                raise ValueError(f"{name}需在 {minimum}～{maximum} 之间")
            return value

        selected = [name for name, _category, _enabled in PLATFORMS if self.platform_vars[name].get()]
        mode = {"网页可用性 + 速度": "both", "仅网页可用性": "unlock_only", "仅速度": "speed_only"}[self.mode_var.get()]
        return TestOptions(self._source(), self.server_var.get().strip().rstrip("/"), mode, number(self.timeout_var, "超时", 1, 300), number(self.concurrent_var, "并发数", 1, 20), number(self.latency_var, "最大延迟", 10, 10000), number(self.download_var, "下载样本", 1, 1000), number(self.upload_var, "上传样本", 1, 1000), selected)

    def _update_platform_status(self) -> None:
        selected = [name for name, _category, _enabled in PLATFORMS if self.platform_vars[name].get()]
        self.platform_status_var.set(f"已选择 {len(selected)} 个目标：{', '.join(selected) if selected else '未选择（将跳过网页解锁检测）'}")

    def _select_platform(self, name: str) -> None:
        """点击整块目标切换选中状态，并用勾号显示当前状态。"""
        self.platform_vars[name].set(not self.platform_vars[name].get())
        self._refresh_platform_buttons()
        self._update_platform_status()

    def _refresh_platform_buttons(self) -> None:
        for name, category, _enabled in PLATFORMS:
            selected = self.platform_vars[name].get()
            button = self.platform_buttons.get(name)
            if button is not None:
                button.configure(text=f"{'√' if selected else '□'} {name}  ·  {category}", style="TargetSelected.TButton" if selected else "Target.TButton")

    def start_test(self) -> None:
        if self.testing or self.fetching:
            return
        try:
            options = self._options()
        except (ValueError, KeyError) as exc:
            messagebox.showwarning("设置有误", str(exc))
            return
        if not options.source:
            messagebox.showwarning("缺少订阅来源", "请先输入订阅链接或选择本地配置。")
            return
        self.testing = True
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.fetch_button.configure(state="disabled")
        self.results.clear()
        self._render_results()
        self.progress.configure(value=0, mode="indeterminate")
        self.progress.start(12)
        self.progress_var.set("测试中……")
        self.status_var.set("已启动网页测试 · 正在逐个验证节点")
        threading.Thread(target=self._test_worker, args=(options,), daemon=True).start()

    def _test_payload(self, options: TestOptions) -> dict:
        return {"configPaths": options.source, "filterRegex": ".+", "includeNodes": [], "excludeNodes": [], "protocolFilter": [], "serverUrl": options.server_url, "downloadSize": options.download_size, "uploadSize": options.upload_size, "timeout": options.timeout, "concurrent": options.concurrent, "maxLatency": options.max_latency, "minDownloadSpeed": 0, "minUploadSpeed": 0, "stashCompatible": False, "fastMode": False, "renameNodes": False, "testMode": options.test_mode, "unlockEnabled": bool(options.platforms), "unlockPlatforms": options.platforms, "unlockConcurrent": min(options.concurrent + 1, 8), "unlockTimeout": options.timeout, "unlockRetry": False}

    def _test_worker(self, options: TestOptions) -> None:
        payload = self._test_payload(options)
        async_started = False
        if websocket is not None:
            try:
                # 读取消息使用短轮询，避免 websocket 在一次 recv 上无限阻塞。
                ws = websocket.create_connection(WS_URL, timeout=5)
                ws.settimeout(1)
                self.ws = ws
                response = self._request_json("/test/async", payload, timeout=15)
                if not response.get("success", False):
                    raise RuntimeError(response.get("error", "测试任务创建失败"))
                async_started = True
                started_at = time.monotonic()
                total_proxies = 0
                hard_deadline = started_at + max(180, options.timeout * 60)
                while True:
                    if time.monotonic() >= hard_deadline:
                        raise TimeoutError("实时测试超过整批任务保护时限，已自动结束等待")
                    try:
                        raw = ws.recv()
                    except Exception as recv_error:  # websocket-client 的超时类型跨版本不一致
                        timeout_type = getattr(websocket, "WebSocketTimeoutException", ())
                        if timeout_type and isinstance(recv_error, timeout_type):
                            continue
                        if "timed out" in str(recv_error).lower() or "timeout" in str(recv_error).lower():
                            continue
                        raise
                    if not raw:
                        break
                    message = json.loads(raw)
                    kind = message.get("type", "")
                    data = message.get("data", {})
                    if kind == "test_result":
                        self.event_queue.put(("result", data))
                    elif kind == "test_start":
                        total_proxies = int(data.get("total_proxies", 0) or 0)
                        if total_proxies:
                            hard_deadline = started_at + max(180, options.timeout * max(20, total_proxies * 4))
                        self.event_queue.put(("start", data))
                    elif kind == "test_progress":
                        self.event_queue.put(("progress", data))
                    elif kind == "test_complete":
                        self.event_queue.put(("complete", data))
                        break
                    elif kind == "test_cancelled":
                        self.event_queue.put(("cancelled", data))
                        break
                    elif kind == "error":
                        self.event_queue.put(("error", data.get("message", "测试失败")))
                        break
                ws.close()
                self.ws = None
                return
            except Exception as exc:  # noqa: BLE001
                try:
                    if self.ws is not None:
                        self.ws.close()
                except Exception:
                    pass
                self.ws = None
                if self.testing and not async_started:
                    self.event_queue.put(("notice", f"实时通道不可用，改用同步测试：{exc}"))
                elif self.testing and async_started:
                    self.event_queue.put(("error", f"实时测试未正常结束：{self._friendly_network_error(exc)}"))
                    return
        try:
            response = self._request_json("/test", payload, timeout=max(60, options.timeout * 30))
            if not response.get("success", False):
                raise RuntimeError(response.get("error", "测试失败"))
            for result in response.get("results", []):
                self.event_queue.put(("result", result))
            self.event_queue.put(("complete", {"total_tested": len(response.get("results", []))}))
        except Exception as exc:  # noqa: BLE001
            self.event_queue.put(("error", f"测试失败：{self._friendly_network_error(exc)}"))

    def stop_test(self) -> None:
        if not self.testing:
            return
        self.testing = False
        try:
            # 请求本机核心取消任务；此前仅关闭 WebSocket，会让后端继续测试。
            self._request_json("/test/stop", {}, timeout=3)
        except Exception:
            pass
        try:
            if self.ws is not None:
                self.ws.close()
        except Exception:
            pass
        self.status_var.set("已停止当前测试；未完成任务不会继续显示")
        self._finish_testing()

    def _finish_testing(self) -> None:
        self.testing = False
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        self.fetch_button.configure(state="normal")
        self.progress.stop()
        self.progress.configure(mode="determinate", value=100 if self.results else 0)
        self.progress_var.set(f"{len(self.results)} 条结果")

    def _drain_events(self) -> None:
        try:
            while True:
                kind, data = self.event_queue.get_nowait()
                if kind == "nodes":
                    self.nodes = list(data)  # type: ignore[arg-type]
                    self.summary_var.set(f"{len(self.nodes)} 个节点")
                    self.status_var.set(f"已解析 {len(self.nodes)} 个节点 · 可以开始测试")
                    self._render_nodes()
                    self.fetching = False
                    self.fetch_button.configure(state="normal")
                elif kind == "start":
                    total = int(data.get("total_proxies", 0))  # type: ignore[union-attr]
                    self.progress.configure(mode="determinate", maximum=100, value=0)
                    self.progress_var.set(f"0 / {total}")
                elif kind == "progress":
                    completed = int(data.get("completed_count", 0))  # type: ignore[union-attr]
                    total = max(int(data.get("total_count", 1)), 1)  # type: ignore[union-attr]
                    self.progress.configure(mode="determinate", value=completed / total * 100)
                    self.progress_var.set(f"{completed} / {total}")
                    self.status_var.set(f"正在测试：{data.get('current_proxy', '节点')} · {data.get('status', '')}")  # type: ignore[union-attr]
                elif kind == "result":
                    if self.testing:
                        self.results.append(dict(data))  # type: ignore[arg-type]
                        self._render_results()
                elif kind == "complete":
                    self.status_var.set(f"测试完成 · 已返回 {len(self.results)} 条结果")
                    self.summary_var.set(f"{len(self.results)} 条测试结果")
                    self._finish_testing()
                elif kind == "cancelled":
                    completed = int(data.get("completed_tests", len(self.results)))  # type: ignore[union-attr]
                    total = int(data.get("total_tests", completed))  # type: ignore[union-attr]
                    self.status_var.set(f"测试已停止 · 保留 {len(self.results)} 条结果（完成 {completed}/{total}）")
                    self.summary_var.set(f"{len(self.results)} 条测试结果")
                    self._finish_testing()
                elif kind == "notice":
                    self.status_var.set(str(data))
                elif kind == "backend":
                    self.status_var.set(str(data))
                elif kind == "error":
                    self.fetching = False
                    self._finish_testing()
                    messagebox.showerror("操作失败", str(data))
        except queue.Empty:
            pass
        self.root.after(100, self._drain_events)

    def _render_nodes(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for node in self.nodes:
            self.tree.insert("", END, values=(node.get("name", ""), node.get("type", ""), f"{node.get('server', '')}:{node.get('port', '')}", "—", "—", "—", "待测试"))

    def _render_results(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for result in sorted(self.results, key=self._download_mbps, reverse=True):
            latency = self._latency_ms(result)
            download = self._download_mbps(result)
            web = result.get("unlock_summary", {}) or {}
            supported = web.get("total_supported", 0) if isinstance(web, dict) else 0
            total = web.get("total_tested", 0) if isinstance(web, dict) else 0
            status = result.get("status", "")
            if not status:
                status = "可用" if float(result.get("packet_loss", 100) or 100) < 100 else "失败"
            self.tree.insert("", END, values=(result.get("proxy_name", ""), result.get("proxy_type", ""), result.get("proxy_ip", ""), f"{float(latency):.0f} ms" if latency else "—", f"{float(download):.2f} Mbps" if download else "—", f"{supported}/{total}" if total else "—", status))

    @staticmethod
    def _latency_ms(result: dict) -> float:
        """兼容 WebSocket 毫秒和同步接口 time.Duration 纳秒两种格式。"""
        if result.get("latency_ms") is not None:
            return float(result.get("latency_ms") or 0)
        raw = result.get("latency", 0) or 0
        if isinstance(raw, str):
            return float(raw[:-2] if raw.endswith("ms") else raw)
        value = float(raw)
        return value / 1_000_000 if value > 10_000 else value

    @staticmethod
    def _download_mbps(result: dict) -> float:
        """兼容 WebSocket Mbps 和同步接口 bytes/s 两种格式。"""
        if result.get("download_speed_mbps") is not None:
            return float(result.get("download_speed_mbps") or 0)
        return float(result.get("download_speed", 0) or 0) / (1024 * 1024)

    def clear_results(self) -> None:
        if self.testing:
            return
        self.results.clear()
        self._render_nodes()
        self.progress.configure(value=0)
        self.progress_var.set("0 / 0")
        self.status_var.set("已清空测试结果")

    def export_results(self, fmt: str) -> None:
        if not self.results:
            messagebox.showinfo("没有结果", "请先完成一次测试，再导出结果。")
            return
        suffix = ".json" if fmt == "json" else ".csv"
        path = filedialog.asksaveasfilename(title="导出测试结果", defaultextension=suffix, filetypes=[(fmt.upper(), f"*{suffix}"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            if fmt == "json":
                Path(path).write_text(json.dumps(self.results, ensure_ascii=False, indent=2), encoding="utf-8")
            else:
                fields = ["proxy_name", "proxy_type", "proxy_ip", "latency_ms", "jitter_ms", "packet_loss", "download_speed_mbps", "upload_speed_mbps", "status"]
                with Path(path).open("w", newline="", encoding="utf-8-sig") as handle:
                    writer = csv.DictWriter(handle, fieldnames=fields)
                    writer.writeheader()
                    writer.writerows({field: row.get(field, "") for field in fields} for row in self.results)
            self.status_var.set(f"已导出 {Path(path).name}")
        except OSError as exc:
            messagebox.showerror("导出失败", str(exc))

    def close(self) -> None:
        self.testing = False
        try:
            if self.ws is not None:
                self.ws.close()
            if self.backend is not None and self.backend.poll() is None:
                self.backend.terminate()
                self.backend.wait(timeout=3)
        except Exception:
            pass
        self.root.destroy()


def main() -> None:
    _enable_high_dpi()
    root = Tk()
    _configure_tk_scaling(root)
    try:
        root.iconname("Clash 节点筛选器")
    except Exception:
        pass
    ClashFilterApp(root)
    root.mainloop()


def _enable_high_dpi() -> None:
    """让 Windows 按真实 DPI 创建窗口，避免高分屏下文字和控件模糊。"""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def _configure_tk_scaling(root: Tk) -> None:
    """将 Tk 的点单位同步到当前显示器 DPI。"""
    try:
        dpi = float(root.winfo_fpixels("1i"))
        root.tk.call("tk", "scaling", max(1.0, dpi / 72.0))
    except (AttributeError, TclError, ValueError):
        pass


if __name__ == "__main__":
    main()
