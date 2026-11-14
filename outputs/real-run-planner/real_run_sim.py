"""Bridges this planner to the location-simulation code in ../run-planner.

Two jobs:

* ``Site`` gives cheap "is this point sane?" answers (inside the campus ring?
  how far from a walkable edge? inside a building or the river?) - the checks
  real_position.py needs to pick between mirror solutions;
* ``build`` / ``Simulation`` turn the planned route into a time-stamped track
  and replay it on the phone, so the running app records a real run while the
  phone stays in your pocket.
"""

from __future__ import annotations

import math
import queue
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "run-planner"))

import location_sim as sim  # noqa: E402
from pedestrian_routes import Network, Ring  # noqa: E402

HERE = Path(__file__).resolve().parent
GENERATED = HERE / "generated"
MAX_SPEED = 60.0


class Site:
    """Campus geometry + walkable network, used to judge candidate points."""

    def __init__(self, data):
        self.data = data
        self.campus = [Ring(ring) for ring in data["campus"]]
        self.solids = []
        for kind, outer, holes in data["areas"]:
            if kind in {"building", "water"}:
                self.solids.append((kind, Ring(outer), [Ring(hole) for hole in holes]))
        self.labels = {name: tuple(point) for name, point in data["labels"]}
        self._network = None

    @property
    def network(self):
        if self._network is None:
            self._network = Network(self.data, campus_only=True)
        return self._network

    def inside(self, point):
        return any(ring.contains(point, boundary=True) for ring in self.campus)

    def road(self, point):
        position = self.network.nearest(point)
        return position.offset if position is not None else 999.0

    def blocked(self, point):
        for kind, outer, holes in self.solids:
            if not outer.contains(point):
                continue
            if any(hole.contains(point) for hole in holes):
                continue
            return "建筑" if kind == "building" else "水域"
        return ""


def parse_pace(text):
    """'4:30' -> 270 seconds per kilometre."""
    raw = str(text).strip().replace("：", ":").replace("'", ":").replace('"', "")
    if not raw:
        raise ValueError("配速不能为空，例如 4:30。")
    parts = raw.split(":")
    try:
        values = [float(part) for part in parts]
    except ValueError:
        raise ValueError("配速要写成 4:30 或 5:00 这样的分:秒。") from None
    if len(values) == 1:
        seconds = values[0] * 60.0
    elif len(values) == 2:
        seconds = values[0] * 60.0 + values[1]
    elif len(values) == 3:
        seconds = values[0] * 3600.0 + values[1] * 60.0 + values[2]
    else:
        raise ValueError("配速要写成 4:30 或 5:00 这样的分:秒。")
    if not (120.0 <= seconds <= 1200.0):
        raise ValueError("配速请在 2:00 到 20:00 之间。")
    return seconds


def format_pace(seconds):
    seconds = int(round(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


def format_time(seconds):
    seconds = int(round(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours} 小时 {minutes} 分 {secs} 秒"
    return f"{minutes} 分 {secs} 秒"


def splits_text(stats):
    """Per-kilometre paces in the same shape as the app's record page."""
    parts = []
    for index, seconds in enumerate(stats.get("kms") or [], 1):
        parts.append(f"第 {index} 公里 {format_pace(seconds)}")
    tail = stats.get("tail")
    if tail:
        metres, seconds = tail
        parts.append(f"最后 {metres / 1000:.2f} 公里 {format_pace(seconds)}")
    return " · ".join(parts)


def restore():
    """Drop any simulated position so the phone reports where it really is."""
    return sim.stop_simulation()


def display(route, *, radius=12.0, step=1.5):
    """The route as it will look on the phone: rounded bends, one point per 1.5 m."""
    if len(route) < 3:
        return list(route)
    return sim.densify(sim.round_corners(route, radius=radius), step)


def build(route, *, pace, seed=None, minimum=None):
    """Return (points, stats) for a one-way run along ``route``."""
    if len(route) < 2:
        raise ValueError("路线还没有画出来。")
    points = sim.build_track(route, pace=pace, laps=1, loop=False, human=True, seed=seed)
    stats = sim.track_stats(points)
    if minimum is not None:
        stats["shortfall"] = max(0.0, float(minimum) - stats["meters"])
    return points, stats


def save(points, *, name=None):
    GENERATED.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = GENERATED / (name or f"real-run-{stamp}.gpx")
    return sim.write_gpx(points, path)


class Simulation:
    """Runs ``sim.play`` on a worker thread and reports progress through a queue."""

    def __init__(self, points, *, speed=None):
        self.points = points
        self.speed = speed
        self.stop = threading.Event()
        self.events = queue.Queue()
        self.thread = None
        self.distance = [0.0]
        for index in range(1, len(points)):
            step = math.dist(
                sim.to_map(points[index - 1][0], points[index - 1][1]),
                sim.to_map(points[index][0], points[index][1]),
            )
            self.distance.append(self.distance[-1] + step)
        self.total = self.distance[-1] if self.distance else 0.0

    def start(self):
        def run():
            try:
                sim.play(self.points, stop=self.stop, on_progress=self._on_progress, speed=self.speed)
            except BaseException as error:  # surface anything, including cancellation
                self.events.put(("error", str(error) or type(error).__name__))
            else:
                self.events.put(("done", None))

        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()

    def _on_progress(self, index, total):
        done = self.distance[min(index, len(self.distance) - 1)]
        self.events.put(("progress", (index, total, done)))

    def halt(self, *, wait=0.0):
        self.stop.set()
        if self.thread is not None and wait:
            self.thread.join(wait)

    def stop_phone(self):
        try:
            sim.stop_simulation()
        except Exception as error:
            return str(error) or type(error).__name__
        return ""