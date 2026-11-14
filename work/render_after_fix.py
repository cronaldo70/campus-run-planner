"""Render the freshly planned route at high zoom: did the diagonal shortcut go away?"""
import json
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, "outputs/real-run-planner")
sys.path.insert(0, "outputs/run-planner")

import location_sim as sim
import real_run_sim as bridge
from pedestrian_routes import Network

data = json.loads(Path("outputs/real-run-planner/campus.json").read_text(encoding="utf-8"))
bridge.set_site(bridge.Site(data))
net = Network(data, campus_only=True)
labels = {name: tuple(point) for name, point in data["labels"]}

start = net.nearest((-329.2, 272.8))
metres, path, _ = net.plan(start, [net.nearest(labels["文典阁西门"]), net.nearest(labels["榴园餐厅"])],
                           via=[], finish=None, minimum=2500)
display = bridge.display(path)
print(f"plan {metres:.0f} m, display {len(display)} pts")

# crop around the first 500 m
window = []
total = 0.0
for a, b in zip(display, display[1:]):
    total += math.dist(a, b)
    window.append(a)
    if total > 520:
        break

xs = [p[0] for p in window]
ys = [p[1] for p in window]
x0, x1 = min(xs) - 30, max(xs) + 60
y0, y1 = min(ys) - 30, max(ys) + 60
scale = 7.0
width, height = int((x1 - x0) * scale), int((y1 - y0) * scale)
image = Image.new("RGB", (width, height), (245, 245, 239))
draw = ImageDraw.Draw(image)


def xy(point):
    return ((point[0] - x0) * scale, (y1 - point[1]) * scale)


fills = {"water": (191, 217, 230), "building": (227, 223, 214),
         "sport": (217, 232, 204), "green": (214, 232, 199)}
for kind, outer, holes in data["areas"]:
    if not (min(p[0] for p in outer) < x1 and max(p[0] for p in outer) > x0):
        continue
    if not (min(p[1] for p in outer) < y1 and max(p[1] for p in outer) > y0):
        continue
    draw.polygon([xy(p) for p in outer], fill=fills.get(kind, (235, 235, 228)))
    for hole in holes:
        draw.polygon([xy(p) for p in hole], fill=(245, 245, 239))

nodes = data["nodes"]
for ids, style, allowed, bridge_flag in data["roads"]:
    if not allowed:
        continue
    coords = [xy(nodes[i] if i in nodes else nodes[str(i)]) for i in ids]
    if style == "path":
        draw.line(coords, fill=(120, 120, 150), width=2)
    else:
        draw.line(coords, fill=(120, 140, 130), width=5)

draw.line([xy(p) for p in window], fill=(0, 200, 60), width=3, joint="curve")
draw.ellipse([xy(window[0])[0] - 6, xy(window[0])[1] - 6, xy(window[0])[0] + 6, xy(window[0])[1] + 6],
             fill=(0, 150, 40))
image.save("work/zoom_after_fix.png")
print("saved work/zoom_after_fix.png", image.size)

# quantify: how many metres of the display path sit on path edges
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
            best = (size, segment.style)
    return best


path_metres = sum(math.dist(a, b) for a, b in zip(display, display[1:])
                  if edge_at(a)[1] == "path")
print(f"display path on footpaths: {path_metres:.1f} m of {sum(math.dist(a, b) for a, b in zip(display, display[1:])):.0f} m")