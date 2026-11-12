"""Offline campus route planner for a real run."""

import base64
import json
import math
import queue
import re
import socket
import threading
import time
import tkinter as tk
import traceback
import webbrowser
from pathlib import Path
from tkinter import messagebox, ttk

from phone_screen import capture_usb_screen
from road_network import RoadNetwork, RoadPosition

import auto_route
import checkpoint_reader as reader
import location_sim as sim


BG = "#f4f5ef"
SURFACE = "#ffffff"
INK = "#172c27"
MUTED = "#506860"
LINE = "#dbe4dc"
TEAL = "#087b66"
DEEP = "#12382f"
AMBER = "#9a5017"
MAP_BG = "#f3f2e9"
FONT = "Microsoft YaHei UI"
POINT_NAMES = {"start": "起点", "a": "文典阁西门", "b": "笃行北楼", "end": "终点", "via": "途经点"}
POINT_LABELS = {"start": "", "a": "A  ", "b": "B  ", "end": ""}
POINT_COLORS = {"start": "#137363", "a": "#93601c", "b": "#5844a3", "end": "#1a536e", "via": "#455e57"}
ORDERS = ("自由打卡 · 自动比较", "先 A 点", "先 B 点")
ATTRIBUTION = "© OpenStreetMap contributors · ODbL"
OSM_COPYRIGHT = "https://www.openstreetmap.org/copyright"


def parse_pace(value: str) -> int | None:
    value = value.strip().replace("：", ":")
    if not value:
        return None
    match = re.fullmatch(r"([0-9]{1,2}):([0-5][0-9])", value)
    if not match or not (seconds := int(match[1]) * 60 + int(match[2])):
        raise ValueError("配速请填 分:秒，例如 6:30。")
    return seconds


def format_time(seconds: float) -> str:
    hours, remainder = divmod(round(seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}时{minutes:02}分{seconds:02}秒" if hours else f"{minutes}分{seconds:02}秒"


def format_pace(seconds: float) -> str:
    """"5:44" style, the way runners quote a split."""
    minutes, rest = divmod(round(seconds), 60)
    return f"{minutes}:{rest:02d}"


def planned_passes(base_km: float, minimum_km: float | None, loop: bool) -> int:
    if base_km <= 0:
        raise ValueError("请把起点和打卡点标在不同位置的可跑道路上。")
    if minimum_km is None or base_km >= minimum_km:
        return 1
    ratio = minimum_km / base_km
    if not math.isfinite(ratio):
        raise ValueError("最短距离超出可计算范围。")
    passes = math.ceil(ratio)
    # An open route must finish at its chosen endpoint after all the return legs.
    return passes if loop or passes % 2 else passes + 1


class Planner:
    def __init__(self, root: tk.Tk, data: dict):
        self.root = root
        self.data = data
        self.network = RoadNetwork(data)
        self.road_lines = [(style, [self.network.nodes[i] for i in ids]) for style, _, ids in data["roads"]]
        self.points: dict[str, tuple[tuple[float, float], RoadPosition]] = {}
        self.via: list[tuple[tuple[float, float], RoadPosition]] = []
        self.route = []
        self.plan_text = ""
        self.passes = 1
        self.base_km = 0.0
        self.sim_stop = None
        self.sim_thread = None
        self.selected = "start"
        self.drag = None
        self.panned = False
        self.scale = 0.0
        self.center = (0.0, 0.0)
        self.loop = tk.BooleanVar(value=True)
        self.auto_distance = tk.BooleanVar(value=True)
        self.order = tk.StringVar(value=ORDERS[0])
        self.minimum = tk.StringVar(value="3")
        self.fastest = tk.StringVar(value="3:00")
        self.slowest = tk.StringVar(value="8:00")
        self.target = tk.StringVar(value="6:00")
        self.point_buttons = {}
        self.point_details = {}
        self.point_names = POINT_NAMES.copy()
        self.open_route = tk.BooleanVar(value=True)
        self.via_names: list[str] = []
        self.auto_result = None
        self.reading = False
        self.watchdog = None
        self.checkpoint_cache: dict[tuple[str, ...], dict] = {}

        root.title("校园跑路线规划 · 实跑版")
        root.configure(bg=BG)
        root.minsize(1120, 820)
        width, height = 1340, 840
        root.geometry(f"{width}x{height}+{max(0, (root.winfo_screenwidth() - width) // 2)}"
                      f"+{max(0, (root.winfo_screenheight() - height) // 2 - 25)}")
        root.option_add("*Font", (FONT, 10))
        style = ttk.Style(root)
        style.configure("TCombobox", padding=(5, 4))
        style.configure("TEntry", padding=(6, 4))
        self.build()
        for variable in (self.minimum, self.fastest, self.slowest, self.target):
            variable.trace_add("write", lambda *_: self.refresh())
        self.refresh()

    def label(self, parent, text, *, size=10, fg=INK, bg=SURFACE, bold=False, **options):
        return tk.Label(parent, text=text, fg=fg, bg=bg, font=(FONT, size, "bold" if bold else "normal"),
                        anchor="w", **options)

    def button(self, parent, text, action, *, primary=False, width=None):
        fill, foreground = (TEAL, SURFACE) if primary else (BG, INK)
        return tk.Button(parent, text=text, command=action, bg=fill, fg=foreground, activebackground="#dceee7",
                         activeforeground=INK, disabledforeground="#748580", relief="flat", borderwidth=0,
                         highlightthickness=0, cursor="hand2", padx=10, pady=6, width=width)

    def build(self):
        banner = tk.Frame(self.root, bg=DEEP, padx=23, pady=12)
        banner.pack(fill="x")
        self.label(banner, "校园跑路线规划", size=17, fg=SURFACE, bg=DEEP, bold=True).pack(side="left")
        self.label(banner, "安徽大学 · 磬苑校区", size=10, fg="#d7e9de", bg=DEEP).pack(side="right")

        body = tk.Frame(self.root, bg=BG, padx=14, pady=12)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        body.columnconfigure(0, minsize=352, weight=0)
        body.rowconfigure(0, weight=1)
        side = tk.Frame(body, bg=SURFACE, padx=14, pady=12, width=352, highlightbackground=LINE, highlightthickness=1)
        side.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        side.grid_propagate(False)
        self.build_sidebar(side)

        map_panel = tk.Frame(body, bg=SURFACE, highlightbackground=LINE, highlightthickness=1)
        map_panel.grid(row=0, column=1, sticky="nsew")
        tools = tk.Frame(map_panel, bg=SURFACE, padx=12, pady=8)
        tools.pack(fill="x")
        self.hint = self.label(tools, "", bold=True, fg=TEAL)
        self.hint.pack(side="left")
        for label, action in (("全图", self.fit_map), ("−", lambda: self.zoom(1 / 1.25)), ("+", lambda: self.zoom(1.25))):
            self.button(tools, label, action, width=3).pack(side="right", padx=(5, 0))

        self.canvas = tk.Canvas(map_panel, bg=MAP_BG, highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", self.on_resize)
        self.canvas.bind("<ButtonPress-1>", self.begin_drag)
        self.canvas.bind("<B1-Motion>", self.drag_map)
        self.canvas.bind("<ButtonRelease-1>", self.end_drag)
        self.canvas.bind("<MouseWheel>", lambda event: self.zoom(1.25 ** (event.delta / 120), event.x, event.y))

        legend = tk.Frame(map_panel, bg=SURFACE, padx=12, pady=5)
        legend.pack(fill="x")
        self.label(legend, "单击选点 · 拖动平移 · 滚轮缩放", fg=MUTED, size=9).pack(side="left")
        attribution = self.label(legend, ATTRIBUTION, fg=MUTED, size=9, cursor="hand2")
        attribution.pack(side="right")
        attribution.bind("<Button-1>", lambda _: webbrowser.open(OSM_COPYRIGHT))

        summary = tk.Frame(map_panel, bg=DEEP, padx=14, pady=10)
        summary.pack(fill="x")
        self.metrics = []
        for column, title in enumerate(("计划总距离", "预计用时", "打卡点")):
            summary.columnconfigure(column, weight=1)
            box = tk.Frame(summary, bg=DEEP)
            box.grid(row=0, column=column, sticky="w", padx=(0, 10))
            self.label(box, title, size=9, bg=DEEP, fg="#d3e5dc").pack(anchor="w")
            value = self.label(box, "—", size=16, bg=DEEP, fg=SURFACE, bold=True)
            value.pack(anchor="w")
            self.metrics.append(value)
        self.distance_detail = self.label(summary, "", size=9, bg=DEEP, fg="#d3e5dc")
        self.distance_detail.grid(row=1, column=0, columnspan=3, sticky="w")
        self.start_button = self.button(summary, "开始实跑", self.start_run, primary=True)
        self.start_button.grid(row=0, column=3, rowspan=2, sticky="e")

    def build_sidebar(self, side):
        heading = tk.Frame(side, bg=SURFACE)
        heading.pack(fill="x")
        self.label(heading, "起点与打卡点", size=13, bold=True).pack(side="left")
        self.button(heading, "更换打卡点", self.edit_checkpoints).pack(side="right")
        self.read_button = self.button(side, "读取手机打卡点（自动识别）", self.read_from_phone, primary=True)
        self.read_button.pack(fill="x", pady=(0, 6))
        self.label(side, "或者按左侧按钮，在地图上逐个标记。", fg=MUTED, size=9).pack(anchor="w", pady=(0, 8))
        for key, prefix in POINT_LABELS.items():
            row = tk.Frame(side, bg=SURFACE)
            row.pack(fill="x", pady=2)
            button = self.button(row, prefix + self.point_names[key], lambda key=key: self.select(key), width=14)
            button.configure(anchor="w")
            button.pack(side="left")
            self.point_buttons[key] = button
            detail = self.label(row, "待标记", fg=MUTED, size=9, width=14, padx=6)
            detail.pack(side="left")
            self.point_details[key] = detail

        tk.Checkbutton(side, text="不绕圈（起点=当前位置，终点不限）", variable=self.open_route,
                       command=self.toggle_open, bg=SURFACE, fg=INK, activebackground=SURFACE,
                       highlightthickness=0, selectcolor=SURFACE, cursor="hand2").pack(anchor="w", pady=(3, 2))
        self.loop_check = tk.Checkbutton(side, text="跑回起点", variable=self.loop, command=self.toggle_loop,
                                         bg=SURFACE, fg=INK, activebackground=SURFACE, highlightthickness=0,
                                         selectcolor=SURFACE, cursor="hand2")
        self.loop_check.pack(anchor="w", pady=(0, 2))
        order = ttk.Combobox(side, values=ORDERS, textvariable=self.order, state="readonly", width=25)
        order.pack(fill="x", pady=(2, 8))
        order.bind("<<ComboboxSelected>>", lambda _: self.refresh())
        self.order_box = order
        extra = tk.Frame(side, bg=SURFACE)
        extra.pack(fill="x")
        self.point_buttons["via"] = self.button(extra, "加途经点", lambda: self.select("via"))
        self.point_buttons["via"].pack(side="left", padx=(0, 5))
        self.undo = self.button(extra, "撤销", self.undo_via)
        self.undo.pack(side="left")
        self.via_count = self.label(extra, "", fg=MUTED, size=9, padx=6)
        self.via_count.pack(side="left")
        tk.Frame(side, bg=LINE, height=1).pack(fill="x", pady=10)

        rules_header = tk.Frame(side, bg=SURFACE)
        rules_header.pack(fill="x", pady=(0, 5))
        self.label(rules_header, "活动要求", size=13, bold=True).pack(side="left")
        tk.Checkbutton(rules_header, text="自动补足距离", variable=self.auto_distance, command=self.refresh,
                       bg=SURFACE, fg=INK, activebackground=SURFACE, highlightthickness=0,
                       selectcolor=SURFACE, cursor="hand2", font=(FONT, 9)).pack(side="right")
        for title, variable, unit in (
            ("最短距离", self.minimum, "公里"),
            ("最快配速", self.fastest, "分:秒 / 公里"),
            ("最慢配速", self.slowest, "分:秒 / 公里"),
            ("目标配速", self.target, "分:秒 / 公里"),
        ):
            row = tk.Frame(side, bg=SURFACE)
            row.pack(fill="x", pady=2)
            self.label(row, title, width=7).pack(side="left")
            ttk.Entry(row, textvariable=variable, width=7).pack(side="left")
            self.label(row, unit, fg=MUTED, size=9, padx=5).pack(side="left")
        actions = tk.Frame(side, bg=SURFACE)
        actions.pack(fill="x", side="bottom")
        self.copy_button = self.button(actions, "复制跑步计划", self.copy_plan, primary=True)
        self.copy_button.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.button(actions, "重选路线", self.reset_points).pack(side="right")
        self.result = self.label(side, "", fg=MUTED, size=9, wraplength=318, justify="left", height=4)
        self.result.pack(fill="x", side="bottom", pady=(8, 8))

    def edit_checkpoints(self):
        window = tk.Toplevel(self.root)
        window.title("本次打卡点")
        window.transient(self.root)
        window.configure(bg=SURFACE, padx=16, pady=12)
        window.grab_set()
        controls = tk.Frame(window, bg=SURFACE)
        controls.pack(side="left", anchor="n")
        self.label(controls, "本次打卡点", size=14, bold=True).pack(anchor="w", pady=(0, 8))
        self.label(controls, "手机打开活动地图后，可读取当前画面。", fg=MUTED).pack(anchor="w")
        names = {}
        for key, label in (("a", "打卡点 A"), ("b", "打卡点 B")):
            self.label(controls, label).pack(anchor="w", pady=(10, 2))
            names[key] = ttk.Entry(controls, width=29)
            names[key].insert(0, self.point_names[key])
            names[key].pack(fill="x")
        status = self.label(controls, "", size=9, fg=MUTED, wraplength=270, justify="left")
        status.pack(fill="x", pady=(9, 5))
        preview = tk.Label(window, bg=SURFACE, borderwidth=0)
        results = queue.Queue()

        def receive():
            if not window.winfo_exists():
                return
            try:
                payload = results.get_nowait()
            except queue.Empty:
                self.root.after(120, receive)
                return
            read_button.configure(state="normal")
            if isinstance(payload, str):
                status.configure(text=payload, fg=AMBER)
                return
            try:
                source = tk.PhotoImage(master=window, data=base64.b64encode(payload), format="png")
                scale = max(1, math.ceil(source.width() / 340), math.ceil(source.height() / 700))
                preview.image = source.subsample(scale, scale)
                preview.configure(image=preview.image)
                preview.pack(side="right", padx=(16, 0))
                status.configure(text="对照手机画面填写两个点，保存后在校园地图上标记。", fg=MUTED)
            except tk.TclError:
                status.configure(text="手机画面无法显示。请重试或手动填写。", fg=AMBER)

        def read_phone():
            def worker():
                try:
                    results.put(capture_usb_screen())
                except RuntimeError as error:
                    results.put(str(error))

            read_button.configure(state="disabled")
            status.configure(text="正在读取手机画面…", fg=MUTED)
            threading.Thread(target=worker, daemon=True).start()
            self.root.after(120, receive)

        def save():
            updated = {key: field.get().strip() for key, field in names.items()}
            if not all(updated.values()):
                status.configure(text="请填写两个打卡点的名称。", fg=AMBER)
                return
            self.update_checkpoints(updated)
            window.destroy()

        read_button = self.button(controls, "读取手机画面", read_phone)
        read_button.pack(fill="x", pady=(0, 5))
        self.button(controls, "保存本次打卡点", save, primary=True).pack(fill="x")
        names["a"].focus_set()

    def update_checkpoints(self, updated):
        changed = [key for key, name in updated.items() if self.point_names[key] != name]
        self.point_names.update(updated)
        for key in changed:
            self.points.pop(key, None)
        if changed:
            self.selected = changed[0]
        self.refresh()

    def fit_map(self):
        x0, y0, x1, y1 = self.data["bounds"]
        self.center = ((x0 + x1) / 2, (y0 + y1) / 2)
        width, height = self.canvas.winfo_width(), self.canvas.winfo_height()
        self.scale = max(0.05, min((width - 20) / (x1 - x0), (height - 20) / (y1 - y0)))
        self.draw()

    def on_resize(self, _event):
        if not self.scale:
            self.fit_map()
        else:
            self.draw()

    def screen(self, point):
        x, y = point
        return (self.canvas.winfo_width() / 2 + (x - self.center[0]) * self.scale,
                self.canvas.winfo_height() / 2 - (y - self.center[1]) * self.scale)

    def world(self, x, y):
        return (self.center[0] + (x - self.canvas.winfo_width() / 2) / self.scale,
                self.center[1] - (y - self.canvas.winfo_height() / 2) / self.scale)

    def zoom(self, ratio, x=None, y=None):
        if x is None:
            x, y = self.canvas.winfo_width() / 2, self.canvas.winfo_height() / 2
        anchor = self.world(x, y)
        self.scale = max(0.12, min(8.0, self.scale * ratio))
        new_anchor = self.world(x, y)
        self.center = tuple(value + previous - current for value, previous, current in zip(self.center, anchor, new_anchor))
        self.draw()

    def begin_drag(self, event):
        self.drag = event.x, event.y, self.center
        self.panned = False

    def drag_map(self, event):
        x, y, center = self.drag
        dx, dy = event.x - x, event.y - y
        if self.panned or abs(dx) + abs(dy) > 5:
            self.panned = True
            self.center = center[0] - dx / self.scale, center[1] + dy / self.scale
            self.draw()

    def end_drag(self, event):
        self.drag = None
        if not self.panned and self.selected:
            self.place(self.world(event.x, event.y))

    def place(self, point):
        position = self.network.nearest(point)
        if position.offset > 85:
            self.result.configure(text="这里离已绘制的道路较远。请放大地图，选择入口附近可跑的道路。", fg=AMBER)
            return
        if self.open_route.get():
            if "start" not in self.points:
                self.points["start"] = point, position
                self.selected = "via"
            else:
                self.via.append((point, position))
                self.via_names.append(f"点位 {len(self.via)}")
            self.refresh()
            return
        key = self.selected
        if key == "via":
            self.via.append((point, position))
        else:
            self.points[key] = point, position
            pending = ("start", "a", "b") if self.loop.get() else ("start", "a", "b", "end")
            self.selected = next((item for item in pending if item not in self.points), None)
        self.refresh()

    def toggle_open(self):
        if self.open_route.get():
            self.loop.set(False)
        if self.open_route.get() and "start" not in self.points:
            self.selected = "start"
        self.refresh()

    def select(self, key):
        self.selected = key
        self.refresh()

    def read_from_phone(self):
        """Screenshot the app, OCR the checkpoint list, and drop it into the plan."""
        if self.reading:
            return
        self.reading = True
        self.read_button.configure(state="disabled", text="正在读取手机…")
        self.result.configure(text="正在截屏并识别打卡点，大约 3–5 秒，手机保持解锁。", fg=MUTED)
        # A second window or a leftover script holding the tunnel would block the
        # fix for ever; make sure the button always comes back.
        self.watchdog = threading.Timer(150.0, self._read_timeout)
        self.watchdog.daemon = True
        self.watchdog.start()
        threading.Thread(target=self._read_worker, daemon=True).start()

    def _read_timeout(self):
        if self.reading:
            message = "读取超过 150 秒还没结束：多半是另一个窗口或后台脚本正占着定位隧道。" \
                      "把多余的规划器窗口和脚本关掉，再点一次读取。"
            self.root.after(0, lambda: self.finish_read(None, message))

    def show_progress(self, message):
        self.result.configure(text=message, fg=MUTED)

    def _read_worker(self):
        # Whatever happens in here, the button must come back: a raised thread
        # used to leave the window stuck on 「正在读取手机…」 for ever.
        try:
            self._read_body()
        except Exception as error:  # noqa: BLE001
            text = str(error) or type(error).__name__
            log = Path(__file__).with_name("planner-error.log")
            try:
                log.write_text(traceback.format_exc(), encoding="utf-8")
            except OSError:
                pass
            self.root.after(0, lambda: self.finish_read(None, f"读取出错：{text}"))

    def _read_body(self):
        labels = {name: tuple(point) for name, point in self.data["labels"]}
        try:
            report = reader.read_screen(labels)
        except (RuntimeError, OSError, ValueError) as error:
            self.root.after(0, lambda: self.finish_read(None, str(error) or type(error).__name__))
            return
        # App-only names (名人景观墙碑记 …) are not in campus_map: move the fix to
        # three road points and trilaterate them from the printed distances.
        others = report.get("others") or []
        if others or not report.get("checkpoints"):
            def label_of(item):
                return item.get("name") or item.get("ocr") or ""

            seen = tuple(sorted(label_of(item) for item in others)) or \
                   tuple(sorted(label_of(item) for item in report.get("checkpoints") or ()))
            solved = self.checkpoint_cache.get(seen)
            if solved is None:
                self.root.after(0, lambda: self.show_progress(
                    "打卡点名字不在路网里，正在三点测距定位（约 40 秒，先别点「开始乐跑」）…"))
                try:
                    import locate_checkpoints as ranging

                    solved = ranging.locate_all(
                        self.data, self.network, labels, settle=6.0,
                        progress=lambda message: self.root.after(0, lambda m=message: self.show_progress(m)))
                except Exception as error:  # noqa: BLE001 - any device hiccup must not freeze the window
                    solved = {}
                    text = str(error) or type(error).__name__
                    self.root.after(0, lambda: self.show_progress(f"测距没成功：{text}"))
                self.checkpoint_cache[seen] = solved
            for name, item in solved.items():
                report.setdefault("checkpoints", []).append(
                    {"name": name, "ocr": name, "point": tuple(item["point"]),
                     "metres": None, "error": item["error"]})
        self.root.after(0, lambda: self.finish_read(report, ""))

    def finish_read(self, report, error):
        self.reading = False
        watchdog = getattr(self, "watchdog", None)
        if watchdog is not None:
            watchdog.cancel()
            self.watchdog = None
        self.read_button.configure(state="normal", text="读取手机打卡点（自动识别）")
        if report is None:
            self.result.configure(text=error, fg=AMBER)
            return
        self.open_route.set(True)
        self.loop.set(False)
        x0, y0, x1, y1 = self.data["bounds"]
        position = report["position"]
        if position and x0 - 80 <= position[0] <= x1 + 80 and y0 - 80 <= position[1] <= y1 + 80:
            point = (position[0], position[1])
            self.points["start"] = point, self.network.nearest(point)
        else:
            position = None
        self.via.clear()
        self.via_names.clear()
        for item in report["checkpoints"]:
            point = tuple(item["point"])
            self.via.append((point, self.network.nearest(point)))
            self.via_names.append(item["name"])
        if not position and self.via:
            # Ranging always leaves a workable answer: start on the pavement next
            # to the first punch instead of asking for a manual click.
            anchor = self.via[0][0]
            point = self.network.nearest(anchor).point
            self.points["start"] = point, self.network.nearest(point)
        self.selected = "via"
        self.refresh()
        note = f"读到 {len(report['checkpoints'])} 个打卡点：" + "、".join(item["name"] for item in report["checkpoints"]) + "。"
        if position:
            note += f"当前位置约 ({position[0]:.0f}, {position[1]:.0f})，残差 {report['position_error']:.0f} 米。"
        elif self.via:
            note += "起点放在第一个打卡点旁边的路上（两点距离解不出唯一位置）。"
        if report["warnings"]:
            note += " " + " ".join(report["warnings"])
        self.result.configure(text=note, fg=AMBER if report["warnings"] else MUTED)

    def toggle_loop(self):
        if self.loop.get() and self.selected == "end":
            self.selected = None
        if not self.loop.get() and "end" not in self.points:
            self.selected = "end"
        self.refresh()

    def undo_via(self):
        if self.via:
            self.via.pop()
            if self.via_names:
                self.via_names.pop()
            self.refresh()

    def reset_points(self):
        self.points.clear()
        self.via.clear()
        self.via_names.clear()
        self.selected = "start"
        self.refresh()

    def draw(self):
        if not self.scale:
            return
        c = self.canvas
        c.delete("all")

        def coordinates(points):
            return [value for point in points for value in self.screen(point)]

        def visible(coords):
            xs, ys = coords[::2], coords[1::2]
            return max(xs) >= -20 and min(xs) <= c.winfo_width() + 20 and max(ys) >= -20 and min(ys) <= c.winfo_height() + 20

        colors = {"water": "#bfdce0", "sport": "#dbebd4", "green": "#e1ead8", "building": "#e3e1d6"}
        for kind, points in self.data["areas"]:
            coords = coordinates(points)
            if visible(coords):
                c.create_polygon(coords, fill=colors[kind], outline="#d7dbcf")
        for kind, points in self.road_lines:
            coords = coordinates(points)
            if not visible(coords):
                continue
            width = max(1.2, min(13, {"major": 10, "road": 5, "path": 2.5}[kind] * self.scale))
            if kind != "path":
                c.create_line(coords, fill="#d6d9c9", width=width + 1, capstyle="round", joinstyle="round")
            c.create_line(coords, fill={"major": "#fff9d9", "road": "#ffffff", "path": "#aebfb0"}[kind],
                          width=width, capstyle="round", joinstyle="round")

        labels = self.data["labels"]
        if self.scale < 0.45:
            labels = [item for item in labels if item[0] in {"文典阁", "笃行北楼", "榴园餐厅", "西门", "南篮球场", "磬苑体育馆"}]
        for name, point in labels:
            x, y = self.screen(point)
            if 20 < x < c.winfo_width() - 20 and 12 < y < c.winfo_height() - 12:
                c.create_text(x, y, text=name, fill="#445d4c", font=(FONT, 9, "bold"))

        if len(self.route) >= 2:
            coords = coordinates(self.route)
            c.create_line(coords, fill=SURFACE, width=8, capstyle="round", joinstyle="round")
            c.create_line(coords, fill=TEAL, width=4, capstyle="round", joinstyle="round")
        for key, (point, position) in self.points.items():
            if key != "end" or not self.loop.get():
                self.draw_pin(key, point, position, {"start": "起", "a": "A", "b": "B", "end": "终"}[key])
        for number, (point, position) in enumerate(self.via, 1):
            self.draw_pin("via", point, position, str(number))
        length = 100 if self.scale < 1.5 else 25
        bottom = c.winfo_height() - 19
        c.create_line(15, bottom, 15 + length * self.scale, bottom, width=2, fill=MUTED)
        c.create_text(15, bottom - 5, text=f"{length} 米", anchor="sw", fill=MUTED, font=(FONT, 8))

    def draw_pin(self, key, point, position, label):
        x, y = self.screen(point)
        rx, ry = self.screen(position.point)
        color = POINT_COLORS[key]
        if abs(x - rx) + abs(y - ry) > 4:
            self.canvas.create_line(x, y, rx, ry, fill=color, dash=(3, 3), width=2)
        radius = 13 if key != "via" else 10
        self.canvas.create_oval(x - radius, y - radius, x + radius, y + radius, fill=color, outline=SURFACE, width=2)
        self.canvas.create_text(x, y, text=label, fill=SURFACE, font=(FONT, 9, "bold"))

    def calculate_route(self):
        start = self.points["start"][1]
        end = start if self.loop.get() else self.points["end"][1]
        via = [position for _, position in self.via]
        order_choices = {ORDERS[1]: [("a", "b")], ORDERS[2]: [("b", "a")]}
        candidates = []
        for keys in order_choices.get(self.order.get(), [("a", "b"), ("b", "a")]):
            checkpoints = [self.points[key][1] for key in keys]
            try:
                route = self.network.through([start, *checkpoints, *via, end])
            except ValueError:
                continue
            candidates.append((*route, keys))
        if not candidates:
            raise ValueError("选中的位置之间没有连通的步行路网，请调整标点。")
        return min(candidates, key=lambda candidate: candidate[0])

    def minimum_distance(self):
        minimum = self.minimum.get().strip()
        if not minimum:
            return None
        try:
            distance = float(minimum)
        except ValueError:
            raise ValueError("最短距离请填数字，例如 3。") from None
        if not math.isfinite(distance) or distance <= 0:
            raise ValueError("最短距离请填大于零的公里数。")
        return distance

    def compare_rules(self, kilometers, distance):
        fast, slow, target = (parse_pace(field.get()) for field in (self.fastest, self.slowest, self.target))
        if fast is not None and slow is not None and fast > slow:
            raise ValueError("最快配速的每公里用时应小于或等于最慢配速。")
        messages = []
        if distance is None:
            messages.append("待填最短距离")
        elif kilometers < distance:
            remaining = distance - kilometers
            gap = f"{math.ceil(remaining * 1000)} 米" if remaining < 1 else f"{remaining:g} 公里"
            messages.append(f"还差约 {gap}，可加途经点")
        else:
            messages.append(f"已达到最短距离 {distance:g} 公里")
        if fast is None or slow is None:
            messages.append("待填配速范围")
        elif target is None:
            messages.append("可填写目标配速")
        elif fast <= target <= slow:
            messages.append("目标配速在范围内")
        else:
            messages.append("目标配速超出范围")
        duration = format_time(kilometers * target) if target is not None else "—"
        return messages, duration

    def refresh_open(self):
        """Open run: start where the phone is, punch everything, finish anywhere."""
        self.route = []
        self.plan_text = ""
        self.passes, self.base_km, self.auto_result = 1, 0.0, None
        self.loop.set(False)
        self.loop_check.configure(state="disabled")
        self.order_box.configure(state="disabled")
        self.hint.configure(text="点「读取手机打卡点」，或在地图上点一下起跑位置")
        for key, button in self.point_buttons.items():
            if key == "via":
                active = self.selected == "via"
                button.configure(bg=TEAL if active else BG, fg=SURFACE if active else INK, state="normal")
                continue
            active = self.selected == key
            button.configure(bg=TEAL if active else BG, fg=SURFACE if active else INK,
                             state="normal" if key == "start" else "disabled")
            if key in POINT_LABELS:
                button.configure(text=POINT_LABELS[key] + self.point_names[key])
        for key, label in self.point_details.items():
            if key == "start":
                if "start" in self.points:
                    offset = self.points["start"][1].offset
                    label.configure(text=f"离道路约 {offset:.0f} 米" if offset >= 4 else "已标记")
                else:
                    label.configure(text="待标记")
            else:
                label.configure(text=f"{len(self.via)} 个打卡点" if key == "via" else "不绕圈时不用")
        self.via_count.configure(text=f"{len(self.via)} 个打卡点")
        self.undo.configure(state="normal" if self.via else "disabled")
        for index in range(3):
            self.metrics[index].configure(text="—")
        self.distance_detail.configure(text="")
        status, color = "点「读取手机打卡点」自动填；也可以先在地图上点一下起跑位置，再逐个点打卡点。", MUTED
        if "start" in self.points and self.via:
            try:
                minimum = self.minimum_distance()
                target = parse_pace(self.target.get())
                points = [point for point, _ in self.via]
                result = auto_route.plan(self.network, self.points["start"][0], points,
                                         minimum=(minimum if minimum is not None else 2.5) * 1000)
                self.auto_result = result
                self.route = result["route"]
                kilometers = result["metres"] / 1000
                self.base_km = kilometers
                duration = format_time(kilometers * target) if target is not None else "—"
                self.metrics[0].configure(text=f"{kilometers:.3f} km")
                self.metrics[1].configure(text=duration)
                self.metrics[2].configure(text=f"{len(self.via)} 个")
                note = auto_route.describe(self.network, self.points["start"][0], points, result, self.via_names)
                shape_note, shape_status = self.describe_track(target, 1, False)
                checks, _ = self.compare_rules(kilometers, minimum)
                self.plan_text = (f"安徽大学磬苑校区跑步计划（不绕圈）\n{note}\n"
                                  f"全程约 {kilometers:.3f} 公里 · 预计用时 {duration}\n"
                                  f"{shape_note}" + "；".join(checks) + "。")
                status = note + shape_status + "\n" + "；".join(checks) + "。"
                color = INK
            except (ValueError, OverflowError) as error:
                status = str(error) if isinstance(error, ValueError) else "这条路线的里程超出可计算范围。"
                color = AMBER
        self.result.configure(text=status, fg=color)
        self.copy_button.configure(state="normal" if self.plan_text else "disabled")
        self.start_button.configure(state="normal" if self.plan_text else "disabled")
        self.draw()

    def refresh(self):
        if self.open_route.get():
            self.refresh_open()
            return
        self.route = []
        self.plan_text = ""
        self.passes = 1
        self.base_km = 0.0
        self.loop_check.configure(state="normal")
        self.order_box.configure(state="readonly")
        self.hint.configure(text=f"在地图上选{self.point_names[self.selected]}" if self.selected else "路线预览")
        for key, button in self.point_buttons.items():
            active = self.selected == key
            enabled = key != "end" or not self.loop.get()
            button.configure(bg=TEAL if active else BG, fg=SURFACE if active else INK,
                             state="normal" if enabled else "disabled")
            if key in POINT_LABELS:
                button.configure(text=POINT_LABELS[key] + self.point_names[key])
        for key, label in self.point_details.items():
            if key == "end" and self.loop.get():
                label.configure(text="返回起点")
            elif key in self.points:
                offset = self.points[key][1].offset
                label.configure(text=f"离道路约 {offset:.0f} 米" if offset >= 4 else "已标记")
            else:
                label.configure(text="待标记")
        self.via_count.configure(text=f"{len(self.via)} 个")
        self.undo.configure(state="normal" if self.via else "disabled")
        for index, value in enumerate(("—", "—", "—")):
            self.metrics[index].configure(text=value)
        self.distance_detail.configure(text="")
        missing = [key for key in ("start", "a", "b", "end") if key not in self.points and (key != "end" or not self.loop.get())]
        status, color = "配速按 分:秒 填写（如 6:30）。先标起点，再标两个打卡点。", MUTED
        if not missing:
            try:
                meters, self.route, distances, order = self.calculate_route()
                base_km = meters / 1000
                distance = self.minimum_distance()
                loop = self.loop.get()
                passes = planned_passes(base_km, distance if self.auto_distance.get() else None, loop)
                kilometers = base_km * passes
                self.passes, self.base_km = passes, base_km
                if not math.isfinite(kilometers):
                    raise ValueError("最短距离超出可计算范围。")
                unit = "圈" if loop else "段"
                if passes > 1:
                    detail = f"地图显示单{unit} {base_km:.3f} 公里 × {passes} {unit}"
                    self.distance_detail.configure(text=detail)
                self.metrics[0].configure(text=f"{kilometers:.3f} km")
                self.metrics[2].configure(text="2 / 2 途经")
                checks, duration = self.compare_rules(kilometers, distance)
                self.metrics[1].configure(text=duration)
                sequence = " → ".join(self.point_names[key] for key in order)
                status = sequence + "\n" + "；".join(checks) + "。"
                stops = "\n".join(f"{self.point_names[key]} · 约 {distance / 1000:.2f} 公里处"
                                  for key, distance in zip(order, distances))
                repeats = ""
                if passes > 1:
                    repeats = (f"沿地图路线跑 {passes} 圈，每圈约 {base_km:.3f} 公里。\n" if loop else
                               f"先按图跑到终点，再沿原路往返 {(passes - 1) // 2} 次，最后停在终点。\n")
                try:
                    target = parse_pace(self.target.get())
                except ValueError:
                    target = None
                shape_note, shape_status = self.describe_track(target, passes, loop)
                self.plan_text = (
                    f"安徽大学磬苑校区跑步计划\n{stops}\n"
                    f"{repeats}"
                    f"全程约 {kilometers:.3f} 公里 · 预计用时 {duration}\n"
                    f"{shape_note}" + "；".join(checks) + "。"
                )
                status = sequence + "\n" + "；".join(checks) + "。" + shape_status
            except (ValueError, OverflowError) as error:
                status = str(error) if isinstance(error, ValueError) else "最短距离超出可计算范围。"
                color = AMBER
        self.result.configure(text=status, fg=color)
        self.copy_button.configure(state="normal" if self.plan_text else "disabled")
        self.start_button.configure(state="normal" if self.plan_text else "disabled")
        self.draw()

    def describe_track(self, target, passes, loop):
        """Build the real track once so the plan can quote honest numbers."""
        if not self.route or target is None:
            return "", ""
        try:
            points = sim.build_track(self.route, pace=target, laps=passes, loop=loop)
        except (ValueError, OverflowError):
            return "", ""
        shape = sim.track_stats(points)
        lap = shape["meters"] / max(1, passes) / 1000
        note = (f"轨迹 {len(points)} 个点、单圈 {lap:.3f} 公里，"
                f"配速 {format_pace(shape['fastest'])}–{format_pace(shape['slowest'])}"
                f"（圆角 {sim.CORNER_RADIUS:.0f} 米 · 横向偏移 {sim.WOBBLE:.1f} 米）\n")
        solid = self.network.violations(self.route)
        warning = ""
        if solid:
            detail = "、".join(f"{'建筑' if kind == 'building' else '水域'} {meters:.0f} 米"
                              for kind, meters in solid)
            warning = f"\n⚠ 路线仍有 {detail} 穿行，建议调整标点。"
        return note, warning

    def copy_plan(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.plan_text)
        self.copy_button.configure(text="已复制")
        self.root.after(1300, lambda: self.copy_button.configure(text="复制跑步计划"))

    def plan_pace(self):
        target = parse_pace(self.target.get())
        if target is None:
            raise ValueError("请填写目标配速，例如 4:00。")
        fast = parse_pace(self.fastest.get())
        slow = parse_pace(self.slowest.get())
        if fast is not None and target < fast:
            raise ValueError(f"目标配速快于活动下限 {self.fastest.get()}，模拟跑会被判为异常。")
        if slow is not None and target > slow:
            raise ValueError(f"目标配速慢于活动上限 {self.slowest.get()}，模拟跑会被判为异常。")
        return target

    def build_track(self):
        if not self.route:
            raise ValueError("请先在地图上完成路线标点。")
        open_run = self.open_route.get()
        return sim.build_track(self.route, pace=self.plan_pace(),
                               laps=1 if open_run else self.passes,
                               loop=self.loop.get() and not open_run)

    def save_track(self, points):
        stamp = time.strftime("%Y%m%d-%H%M")
        return sim.write_gpx(points, Path(__file__).with_name("generated") / f"route-{stamp}.gpx")

    def export_only(self, status):
        try:
            points = self.build_track()
            path = self.save_track(points)
        except (ValueError, OSError) as error:
            status.configure(text=str(error), fg=AMBER)
            return
        status.configure(text=f"已导出 {path.name}：{len(points)} 个点，可用 "
                               f"pymobiledevice3 developer dvt simulate-location play 回放。", fg=MUTED)

    def start_run(self):
        window = tk.Toplevel(self.root)
        window.title("开始实跑 · 模拟定位")
        window.transient(self.root)
        window.configure(bg=SURFACE)
        self.root.update_idletasks()
        width, height = 520, 640
        left = self.root.winfo_rootx() + max(0, (self.root.winfo_width() - width) // 2)
        top = self.root.winfo_rooty() + 40
        window.geometry(f"{width}x{height}+{left}+{top}")
        window.minsize(500, 520)
        frame = tk.Frame(window, bg=SURFACE, padx=20, pady=14)
        frame.pack(fill="both", expand=True)

        self.label(frame, "开始模拟跑", size=16, bold=True).pack(anchor="w")
        self.label(frame, "① 手机步道乐跑点「开始乐跑」并开始计时 → ② 回来点下面这个按钮 → "
                           "③ 跑完先点「停止模拟并恢复定位」。", fg=MUTED, size=9, wraplength=460,
                   justify="left").pack(fill="x", pady=(4, 8))

        status = self.label(frame, "尚未开始。轨迹会同时保存为 GPX。", size=9, fg=MUTED,
                            wraplength=460, justify="left", height=2)
        status.pack(fill="x")
        progress = ttk.Progressbar(frame, mode="determinate", length=460, maximum=100)
        progress.pack(fill="x", pady=(4, 8))
        results = queue.Queue()

        plan_box = tk.Frame(frame, bg=BG, padx=12, pady=10, highlightbackground=LINE, highlightthickness=1)
        plan_box.pack(fill="both", expand=True, pady=(4, 10))
        self.label(plan_box, self.plan_text, size=9, bg=BG, wraplength=430, justify="left").pack(anchor="w")

        clock_row = tk.Frame(frame, bg=SURFACE)
        clock_row.pack(fill="x", side="bottom")
        clock = self.label(clock_row, "00:00", size=15, bold=True)
        clock.pack(side="left")
        self.label(clock_row, "本地计时（可选）", fg=MUTED, size=9, padx=8).pack(side="left")
        started = None
        timer = None

        def tick():
            nonlocal timer
            elapsed = int(time.monotonic() - started)
            minutes, seconds = divmod(elapsed, 60)
            clock.configure(text=f"{minutes:02}:{seconds:02}")
            timer = window.after(200, tick)

        def toggle():
            nonlocal started
            if started is None:
                started = time.monotonic()
                timer_button.configure(text="结束本地计时")
                tick()
            else:
                window.after_cancel(timer)
                started = None
                timer_button.configure(text="重新计时")

        timer_button = self.button(clock_row, "开始计时", toggle)
        timer_button.pack(side="left")

        def poll():
            if not window.winfo_exists():
                return
            while True:
                try:
                    message = results.get_nowait()
                except queue.Empty:
                    break
                kind = message[0]
                if kind == "progress":
                    done, total = message[1], message[2]
                    progress.configure(value=done * 100 / total)
                    status.configure(text=f"模拟跑进行中 {done}/{total} 个轨迹点", fg=MUTED)
                elif kind == "gpx":
                    status.configure(text=f"轨迹已保存：{message[1]}", fg=MUTED)
                elif kind == "done":
                    progress.configure(value=100)
                    status.configure(text="模拟跑结束，已请求设备恢复真实定位。在苹果地图点「我的位置」核对蓝点。", fg=TEAL)
                    start_button.configure(state="normal")
                    stop_button.configure(state="disabled")
                elif kind == "info":
                    progress.configure(value=0)
                    status.configure(text=message[1], fg=MUTED)
                    start_button.configure(state="normal")
                    stop_button.configure(state="disabled")
                else:
                    progress.configure(value=0)
                    status.configure(text=f"模拟跑中断：{message[1]}", fg=AMBER)
                    start_button.configure(state="normal")
                    stop_button.configure(state="disabled")
            window.after(150, poll)

        def worker(points, stop):
            try:
                sim.play(points, stop=stop,
                         on_progress=lambda done, total: results.put(("progress", done, total)))
                results.put(("done",))
            except BaseException as error:  # noqa: BLE001 - surface everything in the window
                if stop.is_set():
                    results.put(("info", "已手动停止，设备已确认恢复。在苹果地图点「我的位置」核对蓝点。"))
                else:
                    results.put(("error", str(error) or type(error).__name__))

        def begin():
            try:
                points = self.build_track()
                path = self.save_track(points)
            except (ValueError, OSError) as error:
                status.configure(text=str(error), fg=AMBER)
                return
            results.put(("gpx", path.name))
            stop = threading.Event()
            self.sim_stop = stop
            self.sim_thread = threading.Thread(target=worker, args=(points, stop), daemon=True)
            self.sim_thread.start()
            start_button.configure(state="disabled")
            stop_button.configure(state="normal")
            shape = sim.track_stats(points)
            status.configure(
                text=f"正在连接 iPhone…{len(points)} 个点 · {shape['meters'] / 1000:.3f} 公里 · "
                     f"预计 {format_time(shape['seconds'])} · "
                     f"配速 {format_pace(shape['fastest'])}–{format_pace(shape['slowest'])}",
                fg=MUTED)
            window.after(150, poll)

        def halt():
            if self.sim_stop is not None:
                self.sim_stop.set()
            stop_button.configure(state="disabled")
            status.configure(text="正在停止模拟并等待设备应答…", fg=MUTED)
            self.root.after(300, poll)

        controls = tk.Frame(frame, bg=SURFACE)
        controls.pack(fill="x", side="bottom", pady=(10, 0))
        start_button = self.button(controls, "开始模拟跑", begin, primary=True)
        start_button.configure(takefocus=0)
        start_button.pack(side="left")
        stop_button = self.button(controls, "停止模拟并恢复定位", halt)
        stop_button.configure(state="disabled")
        stop_button.pack(side="left", padx=(8, 0))
        self.button(controls, "只导出 GPX", lambda: self.export_only(status)).pack(side="left", padx=(8, 0))

        def close():
            if started is not None:
                window.after_cancel(timer)
            if self.sim_stop is not None:
                self.sim_stop.set()
            window.destroy()

        window.protocol("WM_DELETE_WINDOW", close)
        window.lift()
        window.focus_force()


def claim_single_instance() -> socket.socket | None:
    """Hold a local port so a second window cannot fight over the phone tunnel.

    Two planners open at once is the classic "正在读取手机…" hang: both hold a
    userspace tunnel against the same device and neither ever gets a reply.
    """
    guard = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        guard.bind(("127.0.0.1", 47653))
        guard.listen(1)
    except OSError:
        guard.close()
        return None
    return guard


def main():
    guard = claim_single_instance()
    root = tk.Tk()
    if guard is None:
        root.withdraw()
        messagebox.showwarning(
            "规划器已经在运行",
            "已经有一个规划器窗口开着，两个窗口会抢手机的定位通道，读取打卡点会一直卡住。\n"
            "请用已经打开的那个窗口；要重开就先把旧窗口关掉。")
        root.destroy()
        return
    data_path = Path(__file__).with_name("campus_map.json")
    try:
        data = json.loads(data_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        root.withdraw()
        messagebox.showerror("无法加载校园地图", "请将 campus_map.json 与 run_planner.py 放在同一目录。")
        root.destroy()
        return
    root.lift()
    root.attributes("-topmost", True)
    root.after(600, lambda: root.attributes("-topmost", False))
    try:
        Planner(root, data)
        root.mainloop()
    except Exception:
        # 双击启动时没有终端可看，把 traceback 落到文件里，别让窗口悄悄消失。
        log = Path(__file__).with_name("planner-error.log")
        log.write_text(traceback.format_exc(), encoding="utf-8")
        root.withdraw()
        messagebox.showerror("规划器启动失败",
                             f"{traceback.format_exc().strip().splitlines()[-1]}\n\n详情见 {log}")
        root.destroy()


if __name__ == "__main__":
    main()