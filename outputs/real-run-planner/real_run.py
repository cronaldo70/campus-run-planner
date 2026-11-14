"""Offline map and route preview for running on campus."""

import json
import math
import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from webbrowser import open as open_url

import real_position
import real_run_sim as bridge
from pedestrian_routes import Network, Ring
from read_checkpoints import APPROXIMATE_LABELS, read_checkpoints


PAPER = "#f5f5ef"
INK = "#1c332d"
GREEN = "#087765"
DEEP = "#12382f"
WHITE = "#ffffff"
RED = "#9a411d"
FONT = "Microsoft YaHei UI"
POINT_COLORS = ("#087765", "#a45120", "#6051a1", "#1f6179")
NAMES = ("起点", "打卡点 A", "打卡点 B", "终点", "途经点", "封闭路段")
# The label table now holds ~570 names taken from OSM; drawing all of them turns the
# map into a wall of text, so only names near the current route (or these landmarks
# when there is no route yet) are printed.
LANDMARKS = {
    "文典阁", "磬苑广场", "磬苑体育馆", "主体育场", "笃行北楼", "博学北楼", "博学南楼",
    "蕙园1栋", "校医院", "西门", "北门", "东门", "南门", "人文楼", "行政楼", "艺术楼",
}
LABEL_RADIUS = 70.0


class Planner:
    def __init__(self, root, data):
        self.root = root
        self.data = data
        self.campus = [Ring(ring) for ring in data["campus"]]
        self.campus_network = Network(data)
        self.network = self.campus_network
        self.local_network = None
        self.points = {}
        self.via = []
        self.mode = 0
        self.checkpoints = []
        self.path = []
        self.display_path = []
        self.snaps = []
        self.route_ready = False
        self.sim_window = None
        self.simulation = None
        self.usb_read = None
        self.discard_usb_result = False
        self.scale = 0
        self.center = (0, 0)
        self.drag = None
        self.loop = tk.BooleanVar(value=False)
        self.campus_only = tk.BooleanVar(value=True)
        self.minimum = tk.StringVar(value="2.5")
        self.pace = tk.StringVar(value="5:00")
        self.site = bridge.Site(data)
        bridge.set_site(self.site)

        root.title("校园实跑路线规划 · 开始跑步")
        root.geometry("1210x790")
        root.minsize(980, 680)
        root.configure(bg=PAPER)
        root.option_add("*Font", (FONT, 10))
        banner = tk.Frame(root, bg=DEEP, padx=18, pady=13)
        banner.pack(fill="x")
        self.label(banner, "校园实跑路线规划", bg=DEEP, fg=WHITE, size=17, bold=True).pack(side="left")
        self.label(banner, "安徽大学 · 磬苑校区", bg=DEEP, fg="#d7eadf").pack(side="right")

        body = tk.Frame(root, bg=PAPER, padx=12, pady=12)
        body.pack(fill="both", expand=True)
        side = tk.Frame(body, bg=WHITE, padx=14, pady=12)
        side.pack(side="left", fill="y", padx=(0, 10))
        self.build_controls(side)
        map_panel = tk.Frame(body, bg=WHITE)
        map_panel.pack(fill="both", expand=True)
        toolbar = tk.Frame(map_panel, bg=WHITE, padx=10, pady=5)
        toolbar.pack(fill="x")
        self.hint = self.label(toolbar, "", fg=GREEN, bold=True)
        self.hint.pack(side="left")
        for title, command in (("全图", self.fit), ("－", lambda: self.zoom(0.8)),
                               ("＋", lambda: self.zoom(1.25))):
            ttk.Button(toolbar, text=title, command=command, width=5).pack(side="right", padx=(4, 0))
        self.canvas = tk.Canvas(map_panel, bg=PAPER, highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _: self.draw() if self.scale else self.fit())
        self.canvas.bind("<ButtonPress-1>", self.press)
        self.canvas.bind("<B1-Motion>", self.pan)
        self.canvas.bind("<ButtonRelease-1>", self.release)
        self.canvas.bind("<MouseWheel>", lambda e: self.zoom(1.25 ** (e.delta / 120), (e.x, e.y)))
        footer = tk.Frame(map_panel, bg=WHITE, padx=10, pady=6)
        footer.pack(fill="x")
        self.sim_button = ttk.Button(footer, text="模拟跑这条路线（手机不用动）", command=self.start_sim,
                                     state="disabled")
        self.sim_button.pack(side="right", padx=(10, 0), ipadx=8, ipady=4)
        self.label(footer, "蓝色路段为桥 · 灰色虚线已避开 · 红色为手动封闭").pack(side="left")
        credits = self.label(footer, "© OpenStreetMap contributors · ODbL", cursor="hand2")
        credits.pack(side="right")
        credits.bind("<Button-1>", lambda _: open_url("https://www.openstreetmap.org/copyright"))
        self.minimum.trace_add("write", lambda *_: self.replan())
        self.replan()

    @staticmethod
    def label(parent, text, *, bg=WHITE, fg=INK, size=10, bold=False, **kwargs):
        return tk.Label(parent, text=text, bg=bg, fg=fg, font=(FONT, size, "bold" if bold else "normal"),
                        anchor="w", **kwargs)

    def build_controls(self, side):
        self.label(side, "路线标点", size=13, bold=True).pack(fill="x")
        self.read_button = ttk.Button(side, text="读取手机打卡点（自动规划）", command=self.read_phone)
        self.read_button.pack(fill="x", pady=(4, 3))
        self.position_button = ttk.Button(side, text="读取真实起点（自动）", command=self.read_position)
        self.position_button.pack(fill="x", pady=(0, 3))
        self.label(side, "起点不用手输：把步道乐跑停在打卡点列表页点上面那个按钮，"
                         "会按「距你 N 米」自动反推位置。", size=9, wraplength=230, justify="left").pack(fill="x", pady=(2, 8))
        self.label(side, "路线画好后点右下角「模拟跑这条路线」。", size=9, wraplength=230,
                   justify="left").pack(fill="x", pady=(0, 6))
        self.label(side, "先选左边的按钮，再点地图上的道路。", size=9).pack(fill="x", pady=(2, 8))
        self.buttons = []
        for key, name in enumerate(NAMES[:5]):
            button = ttk.Button(side, text=name, command=lambda key=key: self.select(key))
            button.pack(fill="x", pady=2)
            self.buttons.append(button)
        ttk.Button(side, text="撤销最后一个途经点", command=self.undo_via).pack(fill="x", pady=(2, 6))
        tk.Checkbutton(side, text="跑回起点", variable=self.loop, bg=WHITE, command=self.replan).pack(anchor="w")
        tk.Checkbutton(side, text="仅限校区内", variable=self.campus_only, bg=WHITE,
                       command=self.change_boundary).pack(anchor="w")

        ttk.Separator(side).pack(fill="x", pady=10)
        self.label(side, "临时封路", size=13, bold=True).pack(fill="x")
        ttk.Button(side, text="封闭 / 恢复一段路", command=lambda: self.select(5)).pack(fill="x", pady=(4, 3))
        self.label(side, "在地图上点路段，再点一次可恢复。", size=9).pack(fill="x")
        ttk.Separator(side).pack(fill="x", pady=10)
        minimum = tk.Frame(side, bg=WHITE)
        minimum.pack(fill="x")
        self.label(minimum, "最低里程").pack(side="left")
        ttk.Entry(minimum, textvariable=self.minimum, width=6).pack(side="left", padx=6)
        self.label(minimum, "公里").pack(side="left")
        pace_row = tk.Frame(side, bg=WHITE)
        pace_row.pack(fill="x", pady=(4, 0))
        self.label(pace_row, "目标配速").pack(side="left")
        ttk.Entry(pace_row, textvariable=self.pace, width=6).pack(side="left", padx=6)
        self.label(pace_row, "分:秒 / 公里").pack(side="left")
        self.distance = self.label(side, "—", size=20, fg=GREEN, bold=True)
        self.distance.pack(fill="x", pady=(7, 1))
        self.status = self.label(side, "", size=9, wraplength=230, justify="left")
        self.status.pack(fill="x")
        self.phone_status = self.label(side, "", size=9, wraplength=230, justify="left")
        self.phone_status.pack(fill="x", pady=(6, 0))
        ttk.Button(side, text="重选标点", command=self.reset).pack(side="bottom", fill="x")

    def select(self, mode):
        self.mode = mode
        self.hint.configure(text=f"在地图上选择：{self.selection_name()}")

    def selection_name(self):
        if self.mode in (1, 2) and len(self.checkpoints) >= self.mode:
            return self.checkpoints[self.mode - 1][0]
        return NAMES[self.mode]

    def read_phone(self):
        labels = {name: tuple(point) for name, point in self.data["labels"]}
        self.read_usb(lambda: read_checkpoints(labels), self.apply_phone_result, "正在读取打卡点… 请保持手机解锁。")

    def read_position(self):
        self.read_usb(self.auto_start, self.apply_position_fix,
                      "正在读起点：先清掉上次的模拟定位（大约 5 秒），再按打卡点距离反推真实位置。\n"
                      "请让步道乐跑停在「乐跑」打卡点列表页。")

    def stations(self):
        """Name -> map position for everything we can place."""
        found = {name: tuple(point) for name, point in self.data["labels"]}
        found.update({name: tuple(point) for name, point in self.checkpoints if point is not None})
        return found

    def auto_start(self):
        # The app measures distances from whatever position the phone believes
        # it has. A previous simulated run can leave it parked kilometres away,
        # so clear the fake position first and let Core Location settle.
        try:
            bridge.restore()
        except Exception:
            pass
        time.sleep(3.0)
        known = self.stations()
        try:
            return real_position.read_and_resolve(
                known, known,
                inside=self.site.inside, road=self.site.road, blocked=self.site.blocked,
                last=self.points.get(0),
            )
        except ValueError as error:
            raise ValueError(f"{error}（现在能对上路网的打卡点："
                             f"{sum(1 for name, _ in self.checkpoints if name in known) or 0} 个）") from None

    def apply_position_fix(self, fix):
        point = fix.point
        x0, y0, x1, y1 = self.data["bounds"]
        if not (x0 <= point[0] <= x1 and y0 <= point[1] <= y1):
            self.phone_status.configure(text="算出来的位置在地图范围外，请在地图上点选起点。", fg=RED)
            return
        position = self.network.nearest(point)
        offset = position.offset if position is not None else 999.0
        if position is not None and offset <= 45:
            point = position.point
        self.points[0] = point
        notes = [f"起点已自动算出（{fix.method}）：地图坐标 ({point[0]:.0f}, {point[1]:.0f})，"
                 f"离可跑路段 {offset:.0f} 米。"]
        if fix.note:
            notes.append(fix.note)
        self.phone_status.configure(text=" ".join(notes), fg=INK if offset <= 45 else RED)
        self.select(self.next_selection())
        self.replan()

    def read_usb(self, read, apply, message):
        if self.usb_read is not None:
            return
        responses = queue.Queue()
        self.usb_read = responses
        self.discard_usb_result = False

        def worker():
            try:
                responses.put((read(), ""))
            except Exception as error:
                responses.put((None, str(error) or type(error).__name__))

        def poll():
            try:
                result, error = responses.get_nowait()
            except queue.Empty:
                self.root.after(100, poll)
                return
            self.usb_read = None
            self.read_button.configure(state="normal")
            self.position_button.configure(state="normal")
            if self.discard_usb_result:
                return
            if result is None:
                self.phone_status.configure(text=error, fg=RED)
                return
            apply(result)

        self.read_button.configure(state="disabled")
        self.position_button.configure(state="disabled")
        self.phone_status.configure(text=message, fg=INK)
        threading.Thread(target=worker, daemon=True).start()
        self.root.after(100, poll)

    def apply_phone_result(self, checkpoints):
        self.checkpoints = checkpoints
        self.points.pop(1, None)
        self.points.pop(2, None)
        self.points.pop(3, None)
        self.via.clear()
        self.loop.set(False)
        names = "、".join(name for name, _ in checkpoints)
        unmapped = [name for name, point in checkpoints if point is None]
        approximate = [name for name, point in checkpoints if point is not None and name in APPROXIMATE_LABELS]
        notes = [f"本次读到 {names}。"]
        if unmapped:
            notes.append("请在地图标记 " + "、".join(unmapped) + "。")
        if approximate:
            notes.append("请核对 " + "、".join(approximate) + " 的入口位置。")
        if 0 not in self.points:
            notes.append("请读取真实起点，或对照手机地图点选。")
        self.phone_status.configure(text="".join(notes), fg=INK)
        self.select(self.next_selection())
        self.replan()

    def next_selection(self):
        if 0 not in self.points:
            return 0
        checkpoints = self.checkpoints or [("", None), ("", None)]
        return next((key for key, (_, point) in enumerate(checkpoints, 1)
                     if point is None and key not in self.points), 4)

    def reset(self):
        self.discard_usb_result = True
        self.points.clear()
        self.via.clear()
        self.checkpoints.clear()
        self.loop.set(False)
        self.phone_status.configure(text="")
        self.select(0)
        self.replan()

    def undo_via(self):
        if self.via:
            self.via.pop()
            self.replan()

    def change_boundary(self):
        closed = self.network.closed
        if self.campus_only.get():
            self.network = self.campus_network
        else:
            if self.local_network is None:
                self.local_network = Network(self.data, campus_only=False)
            self.network = self.local_network
        self.network.closed = closed
        self.replan()

    def fit(self):
        x0, y0, x1, y1 = self.data["bounds"]
        self.center = ((x0 + x1) / 2, (y0 + y1) / 2)
        width, height = self.canvas.winfo_width(), self.canvas.winfo_height()
        self.scale = max(0.03, min((width - 30) / (x1 - x0), (height - 30) / (y1 - y0)))
        self.draw()

    def screen(self, p):
        return (self.canvas.winfo_width() / 2 + (p[0] - self.center[0]) * self.scale,
                self.canvas.winfo_height() / 2 - (p[1] - self.center[1]) * self.scale)

    def world(self, x, y):
        return (self.center[0] + (x - self.canvas.winfo_width() / 2) / self.scale,
                self.center[1] - (y - self.canvas.winfo_height() / 2) / self.scale)

    def zoom(self, factor, pixel=None):
        x, y = pixel or (self.canvas.winfo_width() / 2, self.canvas.winfo_height() / 2)
        old = self.world(x, y)
        self.scale = max(0.1, min(9, self.scale * factor))
        new = self.world(x, y)
        self.center = tuple(c + a - b for c, a, b in zip(self.center, old, new))
        self.draw()

    def press(self, event):
        self.drag = (event.x, event.y, self.center)

    def pan(self, event):
        x, y, center = self.drag
        if abs(event.x - x) + abs(event.y - y) > 5:
            self.center = (center[0] - (event.x - x) / self.scale, center[1] + (event.y - y) / self.scale)
            self.draw()

    def release(self, event):
        x, y, _ = self.drag
        self.drag = None
        if abs(event.x - x) + abs(event.y - y) <= 5:
            self.place(self.world(event.x, event.y))

    def place(self, point):
        if self.mode == 5:
            position = self.network.nearest(point, for_closure=True)
            if position is None or position.offset > min(25, 14 / self.scale):
                self.status.configure(text="请放大并点中要封闭的路段。", fg=RED)
                return
            reason = self.network.segments[position.edge].reason
            if reason:
                self.status.configure(text=f"该路段已避开（{reason}）。", fg=RED)
                return
            self.network.closed.symmetric_difference_update({position.edge})
        else:
            if self.mode == 4:
                self.via.append(point)
            else:
                self.points[self.mode] = point
                self.mode = self.next_selection()
        self.replan()

    def replan(self):
        self.path = []
        self.display_path = []
        self.snaps = []
        self.route_ready = False
        self.sim_button.configure(state="disabled")
        self.hint.configure(text=f"在地图上选择：{self.selection_name()}")
        checkpoints = self.checkpoints or [(NAMES[i], None) for i in (1, 2)]
        checkpoint_points = [self.points.get(index, point) if index <= 2 else point
                             for index, (_, point) in enumerate(checkpoints, 1)]
        for index, button in enumerate(self.buttons[:4]):
            name, point = NAMES[index], self.points.get(index)
            if index in (1, 2) and index <= len(checkpoints):
                name, point = checkpoints[index - 1][0], checkpoint_points[index - 1]
            suffix = " · 已标记" if point is not None else " · 自动安排" if index == 3 and not self.loop.get() else ""
            button.configure(text=name + suffix,
                             state="disabled" if self.checkpoints and index == 2 and len(checkpoints) == 1 else "normal")
        self.buttons[4].configure(text=f"增加途经点 · {len(self.via)} 个")
        self.distance.configure(text="—")
        try:
            finish_required = not self.loop.get() and 3 in self.points
            names = [NAMES[0], *(name for name, _ in checkpoints)]
            points = [self.points.get(0), *checkpoint_points]
            if finish_required:
                names.append(NAMES[3])
                points.append(self.points.get(3))
            missing = [name for name, point in zip(names, points) if point is None]
            if missing:
                self.status.configure(text="请标记" + "、".join(missing) + "。", fg=INK)
                return
            points.extend(self.via)
            names.extend(f"途经点 {index}" for index in range(1, len(self.via) + 1))
            snapped = []
            for name, point in zip(names, points):
                position = self.network.nearest(point)
                if position is None or position.offset > 35:
                    raise ValueError(f"{name}附近没有可通行的道路。请放大地图，把标点移到入口或步道上。")
                snapped.append(position)
            self.snaps = [(point, position.point) for point, position in zip(points, snapped) if position.offset > 5]
            farthest = max(snapped, key=lambda item: item.offset)
            try:
                minimum = float(self.minimum.get())
                if not math.isfinite(minimum * 1000) or minimum <= 0:
                    raise ValueError
            except ValueError:
                raise ValueError("最低里程请填写大于零的公里数，例如 3。") from None
            count = len(checkpoints) + 1
            finish = snapped[0] if self.loop.get() else snapped[count] if finish_required else None
            via = snapped[count + int(finish_required):]
            meters, self.path, order = self.network.plan(
                snapped[0], snapped[1:count], via, finish,
                # Corner rounding shaves ~1-2 % off the centre-line length, and
                # the app measures the replayed track, not the plan, so ask for
                # a little extra to keep the recorded distance above the floor.
                minimum=minimum * 1000 * 1.02 + 25,
            )
            # what the canvas shows is what the phone will replay: rounded
            # corners and 1 m spacing instead of raw graph vertices
            self.display_path = bridge.display(self.path)
            self.distance.configure(text=f"{meters / 1000:.3f} 公里")
            remaining = minimum - meters / 1000
            heading = " → ".join([NAMES[0], *(checkpoints[i][0] for i in order)])
            if self.via:
                heading += f" → {len(self.via)} 个途经点"
            heading += " → " + ("起点" if self.loop.get() else "终点")
            outcome = "估算里程已达到门槛。" if remaining <= 1e-6 else f"还差约 {remaining:.3f} 公里，可加途经点。"
            if farthest.offset > 5:
                outcome += f"\n标点最远离道路约 {farthest.offset:.0f} 米，请核对入口。"
            self.status.configure(text=f"{heading}\n{outcome}", fg=INK if remaining <= 1e-6 else RED)
            self.route_ready = remaining <= 1e-6 and meters > 0
            if self.route_ready:
                self.sim_button.configure(state="normal")
                try:
                    pace = bridge.parse_pace(self.pace.get())
                except ValueError:
                    pace = None
                if pace:
                    text = self.status.cget("text")
                    self.status.configure(
                        text=text + f"\n按 {bridge.format_pace(pace)} 配速约需 "
                                    f"{bridge.format_time(meters / 1000 * pace)}，点「模拟跑」即可让手机自己记录。",
                        fg=INK)
        except ValueError as error:
            self.status.configure(text=str(error), fg=RED)
        finally:
            self.draw()

    def start_sim(self):
        if not self.route_ready or len(self.path) < 2:
            self.status.configure(text="先把路线画完整，再点「模拟跑」。", fg=RED)
            return
        if self.sim_window is not None:
            self.sim_window.lift()
            return
        try:
            pace = bridge.parse_pace(self.pace.get())
        except ValueError as error:
            self.status.configure(text=str(error), fg=RED)
            return

        window = tk.Toplevel(self.root)
        self.sim_window = window
        window.title("模拟跑 · 手机放口袋里就行")
        window.transient(self.root)
        window.configure(bg=WHITE, padx=18, pady=14)
        window.geometry("600x430")
        window.minsize(520, 380)
        self.label(window, f"计划路线 {self.distance.cget('text')}", size=14, bold=True).pack(anchor="w")
        self.label(window, self.status.cget("text").splitlines()[0], wraplength=540,
                   justify="left").pack(fill="x", pady=4)
        self.label(window, f"配速 {bridge.format_pace(pace)} / 公里 · 全程约 "
                           f"{bridge.format_time(self._path_meters() / 1000 * pace)}", size=9,
                   wraplength=540, justify="left").pack(fill="x", pady=(0, 4))
        self.label(window, "顺序：先在手机上点「开始乐跑」，再点下面的按钮；"
                           "跑完等提示出现，手机自己会恢复真实定位。", size=9,
                   wraplength=540, justify="left").pack(fill="x")
        detail = self.label(window, "", wraplength=540, justify="left")
        detail.pack(fill="x", pady=(6, 0))
        bar = ttk.Progressbar(window, maximum=100)
        bar.pack(fill="x", pady=8)
        clock = self.label(window, "0.00 公里 · 00:00", size=18, fg=GREEN, bold=True)
        clock.pack(anchor="w", pady=(0, 6))
        buttons = tk.Frame(window, bg=WHITE)
        buttons.pack(fill="x")
        start = ttk.Button(buttons, text="开始模拟跑")
        start.pack(side="left")
        halt = ttk.Button(buttons, text="停止并恢复真实定位", state="disabled")
        halt.pack(side="left", padx=8)
        ttk.Button(buttons, text="关闭", command=lambda: close()).pack(side="left")

        state = {"poll": None, "countdown": None, "closing": False, "stats": None}

        def poll():
            if self.simulation is None or state["closing"]:
                return
            while True:
                try:
                    kind, payload = self.simulation.events.get_nowait()
                except queue.Empty:
                    break
                if kind == "progress":
                    index, total, metres = payload
                    share = 0.0 if not total else index / total * 100.0
                    bar.configure(value=share)
                    spent = metres / 1000.0 * pace
                    minutes, seconds = divmod(int(spent), 60)
                    clock.configure(text=f"{metres / 1000:.2f} 公里 · {minutes:02d}:{seconds:02d}")
                    detail.configure(text=f"已发送 {index} / {total} 个位置点", fg=INK)
                elif kind == "done":
                    bar.configure(value=100)
                    splits = bridge.splits_text(state.get("stats") or {})
                    detail.configure(text="跑完了。手机已停止模拟，正在按真实定位显示。"
                                          + (f"\n{splits}" if splits else ""), fg=GREEN)
                    halt.configure(state="disabled")
                else:
                    detail.configure(text=f"回放中断：{payload}", fg=RED)
                    halt.configure(state="disabled")
            state["poll"] = window.after(300, poll)

        def stop_phone():
            error = self.simulation.stop_phone() if self.simulation else ""
            if state["closing"]:
                return
            if error:
                detail.configure(text=f"恢复真实定位时出错：{error}", fg=RED)
            else:
                detail.configure(text="已停止，手机恢复真实定位。", fg=INK)

        def begin():
            state["countdown"] = None
            try:
                floor = float(self.minimum.get()) * 1000.0
            except ValueError:
                floor = None
            try:
                points, stats = bridge.build(self.path, pace=pace, minimum=floor)
            except Exception as error:
                detail.configure(text=f"生成轨迹失败：{error}", fg=RED)
                start.configure(state="normal")
                return
            try:
                path = bridge.save(points)
            except Exception:
                path = None
            self.simulation = bridge.Simulation(points)
            self.simulation.start()
            halt.configure(state="normal")
            state["stats"] = stats
            short = stats.get("shortfall", 0.0)
            note = (f"轨迹 {len(points)} 个点 · 实际 {stats['meters'] / 1000:.2f} 公里 · "
                    f"名义 {bridge.format_time(stats['seconds'])}"
                    + (f"\nGPX 已存 {path.name}" if path else ""))
            if short and short > 1.0:
                note += f"\n实际里程比底线少 {short:.0f} 米（圆角会内切），App 可能不算达标。"
            detail.configure(text=note, fg=RED if short and short > 1.0 else INK)
            poll()

        def go():
            start.configure(state="disabled")
            bar.configure(value=0)
            seconds = {"left": 5}

            def tick():
                if state["closing"]:
                    return
                if seconds["left"] > 0:
                    detail.configure(text=f"{seconds['left']} 秒后开始，现在去手机上点「开始乐跑」…", fg=RED)
                    seconds["left"] -= 1
                    state["countdown"] = window.after(1000, tick)
                else:
                    begin()

            tick()

        def stop():
            halt.configure(state="disabled")
            if self.simulation is not None:
                self.simulation.halt()
            threading.Thread(target=stop_phone, daemon=True).start()

        def close():
            state["closing"] = True
            if state["poll"]:
                window.after_cancel(state["poll"])
            if state["countdown"]:
                window.after_cancel(state["countdown"])
            running = self.simulation is not None
            if running:
                self.simulation.halt()
            self.sim_window = None
            window.destroy()
            if running:
                threading.Thread(target=stop_phone, daemon=True).start()
            self.simulation = None

        start.configure(command=go)
        halt.configure(command=stop)
        window.protocol("WM_DELETE_WINDOW", close)

    def _path_meters(self):
        return sum(math.dist(a, b) for a, b in zip(self.path, self.path[1:]))

    def draw(self):
        if not self.scale:
            return
        canvas = self.canvas
        canvas.delete("all")

        def coords(points):
            return [value for point in points for value in self.screen(point)]

        fills = {"water": "#bfd9e6", "building": "#e3dfd6", "sport": "#d9e8cc", "green": "#e3ecda"}
        for kind, outer, holes in self.data["areas"]:
            canvas.create_polygon(coords(outer), fill=fills[kind])
            for hole in holes:
                canvas.create_polygon(coords(hole), fill=PAPER)
        for waterway in self.data["waterways"]:
            canvas.create_line(coords(waterway), fill=fills["water"], width=2)
        for (a, b), segment in self.network.segments.items():
            edge = a, b
            closed = edge in self.network.closed
            color = "#b94334" if closed else "#c3c6ba" if segment.reason else "#6e929c" if segment.bridge else "#a6b8a7"
            canvas.create_line(coords((self.network.nodes[a], self.network.nodes[b])), fill=color,
                               width=3 if closed or segment.bridge else 1.5,
                               dash=(4, 3) if closed or segment.reason else ())
        for ring in self.data["campus"]:
            canvas.create_line(coords(ring), fill="#798e75", dash=(4, 5))
        path = self.display_path or self.path
        self.draw_labels(path)
        if len(path) > 1:
            canvas.create_line(coords(path), fill=WHITE, width=8, joinstyle="round")
            canvas.create_line(coords(path), fill=GREEN, width=4, joinstyle="round")
            if not self.loop.get() and 3 not in self.points:
                self.pin(self.path[-1], "终", POINT_COLORS[3])
        for point, snap in self.snaps:
            canvas.create_line(coords((point, snap)), fill="#53665c", dash=(2, 3))
        for index, point in self.points.items():
            if index != 3 or not self.loop.get():
                self.pin(point, ("起", "A", "B", "终")[index], POINT_COLORS[index])
        for index, (_, point) in enumerate(self.checkpoints, 1):
            if (index > 2 or index not in self.points) and point is not None:
                self.pin(point, "AB"[index - 1] if index <= 2 else str(index), POINT_COLORS[1 + (index - 1) % 2])
        for number, point in enumerate(self.via, 1):
            self.pin(point, str(number), "#53665c")

    def draw_labels(self, path):
        """Print only names near the current route: the table now holds ~570 entries."""
        if not self.scale:
            return
        canvas = self.canvas
        if len(path) > 1:
            step = max(1, len(path) // 80)
            samples = path[::step]
        else:
            samples = []
        drawn = 0
        for label, point in self.data["labels"]:
            if samples:
                if not any(math.dist(point, sample) < LABEL_RADIUS for sample in samples):
                    continue
            elif label not in LANDMARKS:
                continue
            if drawn >= 70:
                break
            canvas.create_text(*self.screen(point), text=label, fill=INK, font=(FONT, 9))
            drawn += 1

    def pin(self, point, text, color):
        x, y = self.screen(point)
        self.canvas.create_oval(x - 12, y - 12, x + 12, y + 12, fill=color, outline=WHITE, width=2)
        self.canvas.create_text(x, y, text=text, fill=WHITE, font=(FONT, 9, "bold"))


if __name__ == "__main__":
    data = json.loads(Path(__file__).with_name("campus.json").read_text(encoding="utf-8"))
    root = tk.Tk()
    Planner(root, data)
    root.mainloop()
