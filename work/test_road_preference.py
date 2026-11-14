"""Regression: planned routes must stay on roads the phone's basemap actually draws.

步道乐跑 uses a 高德 basemap that does not render OSM footpaths, so a route that
follows `path` edges looks like it slices across lawns.  Every planned route should
keep footpath use to a few metres (the connector from a checkpoint into the network).
"""
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, "outputs/real-run-planner")
sys.path.insert(0, "outputs/run-planner")

import location_sim as sim
import real_run_sim as bridge
from pedestrian_routes import Network

LIMIT = 0.03  # 3 % of the route

data = json.loads(Path("outputs/real-run-planner/campus.json").read_text(encoding="utf-8"))
bridge.set_site(bridge.Site(data))
net = Network(data, campus_only=True)
labels = {name: tuple(point) for name, point in data["labels"]}


def edge_style(point):
    best = (1e9, "")
    for edge, segment in net.segments.items():
        if segment.reason or edge in net.closed:
            continue
        a, b = net.nodes[edge[0]], net.nodes[edge[1]]
        ax, ay = a
        dx, dy = b[0] - ax, b[1] - ay
        d2 = dx * dx + dy * dy
        t = 0.0 if d2 == 0 else max(0.0, min(1.0, ((point[0] - ax) * dx + (point[1] - ay) * dy) / d2))
        snap = (ax + dx * t, ay + dy * t)
        size = math.dist(point, snap)
        if size < best[0]:
            best = (size, segment.style)
    return best[1]


cases = [
    ("西门北侧", (-329.2, 272.8)),
    ("文典阁西门", (-192.1, -40.6)),
    ("校医院", (-443.6, 33.1)),
    ("人文楼东侧", (267.5, -267.7)),
    ("磬苑体育馆", (106.8, 871.6)),
]

failures = 0
for title, point in cases:
    start = net.nearest(point)
    # No checkpoints: this is the plain "go out and come back" loop, so every metre is
    # the planner's own choice - checkpoint spurs are not part of the measurement.
    metres, path, _ = net.plan(start, [], [], None, minimum=2500)
    display = bridge.display(path)
    steps = [math.dist(a, b) for a, b in zip(display, display[1:])]
    total = sum(steps)
    off = sum(step for step, point_a in zip(steps, display) if edge_style(point_a) == "path")
    share = off / total if total else 0.0
    ok = share <= LIMIT
    failures += 0 if ok else 1
    print(f"{title}: {metres:.0f} m plan / {total:.0f} m display, "
          f"footpath {off:.1f} m ({share:.1%}) {'OK' if ok else 'TOO MUCH'}, "
          f"vertices {len(path)}")

print("\nfailures:", failures)
raise SystemExit(1 if failures else 0)