"""Measure how much of the bundled walkable network cuts through water or buildings."""

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT.parent / "outputs" / "run-planner"
sys.path.insert(0, str(OUT))

from road_network import RoadNetwork  # noqa: E402

DATA = json.loads((OUT / "campus_map.json").read_text(encoding="utf-8"))


def inside(point, polygon):
    x, y = point
    hit = False
    for (x1, y1), (x2, y2) in zip(polygon, polygon[1:] + polygon[:1]):
        if (y1 > y) != (y2 > y):
            cross = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if cross > x:
                hit = not hit
    return hit


def crosses(p, q, polygon):
    if inside(p, polygon) or inside(q, polygon):
        return True
    for (x1, y1), (x2, y2) in zip(polygon, polygon[1:] + polygon[:1]):
        d1 = (q[0] - p[0], q[1] - p[1])
        d2 = (x2 - x1, y2 - y1)
        den = d1[0] * d2[1] - d1[1] * d2[0]
        if abs(den) < 1e-12:
            continue
        t = ((x1 - p[0]) * d2[1] - (y1 - p[1]) * d2[0]) / den
        u = ((x1 - p[0]) * d1[1] - (y1 - p[1]) * d1[0]) / den
        if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
            return True
    return False


areas = {}
for kind, points in DATA["areas"]:
    areas.setdefault(kind, []).append(points)
for kind, polys in areas.items():
    print(f"{kind}: {len(polys)} polygons, {sum(len(p) for p in polys)} vertices")

net = RoadNetwork(DATA)
print(f"nodes {len(net.nodes)}  edges {len(net.edges)}")
lengths = [math.dist(net.nodes[a], net.nodes[b]) for a, b in net.edges]
print(f"edge length: min {min(lengths):.1f}  mean {sum(lengths)/len(lengths):.1f}  max {max(lengths):.1f}")

for kind in ("water", "building"):
    polys = areas.get(kind, [])
    hits = []
    for a, b in net.edges:
        pa, pb = net.nodes[a], net.nodes[b]
        for polygon in polys:
            if crosses(pa, pb, polygon):
                hits.append((a, b, math.dist(pa, pb)))
                break
    total = sum(length for _, _, length in hits)
    print(f"edges crossing {kind}: {len(hits)}  total {total:.0f} m")
    for a, b, length in sorted(hits, key=lambda row: -row[2])[:8]:
        print(f"   {a}-{b}  {length:6.1f} m  {net.nodes[a]} -> {net.nodes[b]}")

# how the road styles are distributed
roads = DATA["roads"]
walkable = sum(1 for _, ok, _ in roads if ok)
print(f"roads {len(roads)}  walkable {walkable}")
for index, style, ok in roads[:3]:
    print("sample", index, style, ok)