"""How much does raising the footpath penalty help? Sweep it."""
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, "outputs/real-run-planner")
sys.path.insert(0, "outputs/run-planner")

import location_sim as sim
import real_run_sim as bridge
import pedestrian_routes as pr

data = json.loads(Path("outputs/real-run-planner/campus.json").read_text(encoding="utf-8"))
bridge.set_site(bridge.Site(data))
labels = {name: tuple(point) for name, point in data["labels"]}

cases = [
    ("西门北侧", (-329.2, 272.8), ["文典阁西门", "榴园餐厅"]),
    ("文典阁西门", None, ["人文楼东侧", "行政楼"]),
    ("校医院", None, ["磬苑体育馆", "蕙园3栋"]),
    ("人文楼东侧", None, ["艺术楼", "主体育场"]),
]


def measure(net, path):
    display = bridge.display(path)
    total = off = 0.0
    for a, b in zip(display, display[1:]):
        step = math.dist(a, b)
        total += step
        best = (1e9, "")
        for edge, segment in net.segments.items():
            if segment.reason or edge in net.closed:
                continue
            p, q = net.nodes[edge[0]], net.nodes[edge[1]]
            dx, dy = q[0] - p[0], q[1] - p[1]
            d2 = dx * dx + dy * dy
            t = 0.0 if d2 == 0 else max(0.0, min(1.0, ((a[0] - p[0]) * dx + (a[1] - p[1]) * dy) / d2))
            snap = (p[0] + dx * t, p[1] + dy * t)
            size = math.dist(a, snap)
            if size < best[0]:
                best = (size, segment.style)
        if best[1] == "path":
            off += step
    return total, off


for penalty in (3.0, 6.0, 12.0):
    pr.PATH_PENALTY = penalty
    net = pr.Network(data, campus_only=True)
    print(f"\n--- PATH_PENALTY = {penalty} ---")
    for title, point, cp_names in cases:
        start = net.nearest(point or labels[cp_names[0]])
        cps = [net.nearest(labels[name]) for name in cp_names]
        try:
            metres, path, _ = net.plan(start, cps, via=[], finish=None, minimum=2500)
        except ValueError as error:
            print(f"  {title}: plan failed ({error})")
            continue
        total, off = measure(net, path)
        print(f"  {title}: {metres:.0f} m, display {total:.0f} m, footpath {off:.1f} m ({off / total:.1%})")