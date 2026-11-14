"""Why does the newest run look like it cuts across the green belt?

Reads the GPX the app just recorded from, projects it to campus metres, and reports
for the first N metres: straightness, distance to the nearest walkable road, and
which area polygons (green / water / building) the path passes through.
"""
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, "outputs/real-run-planner")
sys.path.insert(0, "outputs/run-planner")

import location_sim as sim
import real_run_sim as bridge
from pedestrian_routes import Network, Ring

gpx = Path("outputs/real-run-planner/generated/real-run-20261114-152125.gpx")
points = sim.read_gpx(gpx)
track = [sim.to_map(lat, lon) for lat, lon, _ in points]
print(f"{gpx.name}: {len(track)} pts")

data = json.loads(Path("outputs/real-run-planner/campus.json").read_text(encoding="utf-8"))
net = Network(data, campus_only=True)
areas = [(kind, Ring(outer), [Ring(h) for h in holes]) for kind, outer, holes in data["areas"]]

# cumulative distance
cum = [0.0]
for a, b in zip(track, track[1:]):
    cum.append(cum[-1] + math.dist(a, b))
total = cum[-1]
print(f"total {total:.1f} m, first={tuple(round(v,1) for v in track[0])}, last={tuple(round(v,1) for v in track[-1])}")

def nearest_road(point):
    best = (1e9, None, None)
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
            best = (size, snap, edge)
    return best

# how far from the road is every 5 m of the first 200 m?
print("\n  dist   offset-to-road  area")
marks = [d for d in (0, 10, 20, 40, 60, 80, 100, 130, 160, 200) if d <= total]
for mark in marks:
    index = max(i for i, d in enumerate(cum) if d <= mark) if mark else 0
    point = track[index]
    offset, snap, edge = nearest_road(point)
    kinds = [kind for kind, outer, holes in areas
             if outer.contains(point) and not any(hole.contains(point) for hole in holes)]
    print(f"  {mark:5.0f} m  {offset:6.1f} m        {'/'.join(kinds) or '-'}")

# straightness of the first 130 m
index130 = max(i for i, d in enumerate(cum) if d <= 130)
a, b = track[0], track[index130]
line = math.dist(a, b)
path = cum[index130]
print(f"\nfirst 130 m: straight-line {line:.1f} m vs path {path:.1f} m -> straightness {line / path:.4f}")

# worst offset over the whole track
worst = (0.0, 0.0)
for d, point in zip(cum, track):
    offset, _, _ = nearest_road(point)
    if offset > worst[0]:
        worst = (offset, d)
print(f"worst road offset: {worst[0]:.1f} m at {worst[1]:.0f} m into the run")

# count track points inside each area kind
counts = {}
for point in track:
    for kind, outer, holes in areas:
        if outer.contains(point) and not any(hole.contains(point) for hole in holes):
            counts[kind] = counts.get(kind, 0) + 1
print("points inside areas:", counts)