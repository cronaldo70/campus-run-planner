"""Which OSM road types does the recorded track actually use?

If the first leg follows a `path`/`footway` that 高德 basemap does not draw, the
track looks like it cuts straight across the green belt even though it is glued to
a real OSM way.
"""
import json
import math
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, "outputs/real-run-planner")
sys.path.insert(0, "outputs/run-planner")

import location_sim as sim
from pedestrian_routes import Network

data = json.loads(Path("outputs/real-run-planner/campus.json").read_text(encoding="utf-8"))
net = Network(data, campus_only=True)

styles = Counter(segment.style for segment in net.segments.values())
print("edge styles on the map:", dict(styles))

walkable = Counter(segment.style for edge, segment in net.segments.items()
                   if not segment.reason and edge not in net.closed)
print("walkable edge styles:", dict(walkable))

points = sim.read_gpx("outputs/real-run-planner/generated/real-run-20261114-152125.gpx")
track = [sim.to_map(lat, lon) for lat, lon, _ in points]

cum = [0.0]
for a, b in zip(track, track[1:]):
    cum.append(cum[-1] + math.dist(a, b))


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
            best = (size, edge, segment, (a, b))
    return best


print("\nstyle used along the run:")
used = Counter()
for d, point in zip(cum, track):
    _, edge, segment, ends = edge_at(point)
    used[segment.style] += 1
    if d < 200 and int(d) % 20 == 0:
        print(f"  {d:5.0f} m  style={segment.style:12s} offset={math.dist(point, (0,0)) and 0:.0f} "
              f"edge {tuple(round(v,1) for v in ends[0])} -> {tuple(round(v,1) for v in ends[1])}")
print("\ncount by style along the track:", dict(used))
print("\nshare:", {k: f"{v / len(track):.0%}" for k, v in used.items()})