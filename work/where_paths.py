"""Where exactly is the 318 m of footpath in the 文典阁西门 route?"""
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, "outputs/real-run-planner")
sys.path.insert(0, "outputs/run-planner")

import real_run_sim as bridge
from pedestrian_routes import Network

data = json.loads(Path("outputs/real-run-planner/campus.json").read_text(encoding="utf-8"))
bridge.set_site(bridge.Site(data))
net = Network(data, campus_only=True)
labels = {name: tuple(point) for name, point in data["labels"]}

start = net.nearest(labels["文典阁西门"])
print(f"start edge {start.edge} style={net.segments[start.edge].style} offset={start.offset:.1f}")
metres, path, edges = net.plan(start, [net.nearest(labels["人文楼东侧"]), net.nearest(labels["行政楼"])],
                               via=[], finish=None, minimum=2500)

# walk the vertex list and print the style of every segment longer than 15 m
for i, (a, b) in enumerate(zip(path, path[1:])):
    step = math.dist(a, b)
    if step < 15:
        continue
    # find the edge that covers a->b
    best = (1e9, "")
    mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    for edge, segment in net.segments.items():
        if segment.reason or edge in net.closed:
            continue
        p, q = net.nodes[edge[0]], net.nodes[edge[1]]
        dx, dy = q[0] - p[0], q[1] - p[1]
        d2 = dx * dx + dy * dy
        t = 0.0 if d2 == 0 else max(0.0, min(1.0, ((mid[0] - p[0]) * dx + (mid[1] - p[1]) * dy) / d2))
        snap = (p[0] + dx * t, p[1] + dy * t)
        size = math.dist(mid, snap)
        if size < best[0]:
            best = (size, segment.style)
    print(f"  {i:3d} {step:6.1f} m  {best[1]:5s} {(a[0]):7.1f},{a[1]:7.1f} -> {b[0]:7.1f},{b[1]:7.1f}")