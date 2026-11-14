"""Zoomed picture of the first 200 m: is our line on an OSM road or across green?

Layers: areas (green / water / building) -> roads (road) -> paths (path) -> track.
"""
import json
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, "outputs/real-run-planner")
sys.path.insert(0, "outputs/run-planner")

import location_sim as sim

data = json.loads(Path("outputs/real-run-planner/campus.json").read_text(encoding="utf-8"))
points = sim.read_gpx("outputs/real-run-planner/generated/real-run-20261114-152125.gpx")
track = [sim.to_map(lat, lon) for lat, lon, _ in points][:220]

xs = [p[0] for p in track] + [-340, -230]
ys = [p[1] for p in track] + [230, 430]
x0, x1 = min(xs) - 25, max(xs) + 25
y0, y1 = min(ys) - 25, max(ys) + 25
scale = 8.0
width = int((x1 - x0) * scale)
height = int((y1 - y0) * scale)
print(f"crop {x0:.0f},{y0:.0f} - {x1:.0f},{y1:.0f}  -> {width}x{height}")

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
for ids, style, allowed, bridge in data["roads"]:
    if not allowed:
        continue
    coords = [xy(nodes[str(i)] if str(i) in nodes else nodes[i]) for i in ids]
    if style == "path":
        draw.line(coords, fill=(150, 150, 170), width=2)
    else:
        draw.line(coords, fill=(120, 140, 130), width=5)

draw.line([xy(p) for p in track], fill=(0, 200, 60), width=3, joint="curve")
draw.ellipse([xy(track[0])[0] - 6, xy(track[0])[1] - 6, xy(track[0])[0] + 6, xy(track[0])[1] + 6],
             fill=(0, 150, 40))
out = "work/zoom_first200.png"
image.save(out)
print("saved", out)