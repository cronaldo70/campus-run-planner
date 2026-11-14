"""Replan the user's last route with the new footpath penalty and measure road share."""
import json
import math
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, "outputs/real-run-planner")
sys.path.insert(0, "outputs/run-planner")

import location_sim as sim
import real_run_sim as bridge
from pedestrian_routes import Network, PATH_PENALTY

data = json.loads(Path("outputs/real-run-planner/campus.json").read_text(encoding="utf-8"))
site = bridge.Site(data)
bridge.set_site(site)
net = Network(data, campus_only=True)
labels = {name: tuple(point) for name, point in data["labels"]}

start_point = (-329.2, 272.8)
cps = [labels["文典阁西门"], labels["榴园餐厅"]]

start = net.nearest(start_point)
print(f"start snaps to edge {start.edge} offset {start.offset:.1f} m "
      f"style {net.segments[start.edge].style}")
metres, path, order = net.plan(start, [net.nearest(cps[0]), net.nearest(cps[1])],
                               via=[], finish=None, minimum=2500)
print(f"plan: {metres:.0f} m, {len(path)} vertices")

pts, stats = bridge.build(path, pace=300, minimum=2500)
track = [sim.to_map(lat, lon) for lat, lon, _ in pts]


def edge_at(point):
    best = (1e9, None)
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
            best = (size, edge, segment)
    return best


used = Counter()
offsets = []
for point in track:
    offset, edge, segment = edge_at(point)
    used[segment.style] += 1
    offsets.append(offset)
offsets.sort()
print(f"track: {stats['meters']:.0f} m, {len(pts)} pts, path share {used['path'] / len(track):.1%}")
print(f"style mix: {dict(used)}  (PATH_PENALTY={PATH_PENALTY})")
print(f"offset to nearest edge: median {offsets[len(offsets)//2]:.2f} m, "
      f"p99 {offsets[int(len(offsets) * 0.99)]:.2f} m, max {offsets[-1]:.2f} m")
print(f"water {sum(1 for p in track if site.in_water(p))}, "
      f"building {sum(1 for p in track if site.in_building(p))}")