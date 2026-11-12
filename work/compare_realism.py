"""Crop the same area out of the before/after renders and stack them side by side."""

import json
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "outputs" / "run-planner"
sys.path.insert(0, str(OUT))

from road_network import RoadNetwork  # noqa: E402

DATA = json.loads((OUT / "campus_map.json").read_text(encoding="utf-8"))
SCALE = 1.35
MIN_X, MIN_Y, MAX_X, MAX_Y = DATA["bounds"]
HEIGHT = int((MAX_Y - MIN_Y) * SCALE) + 40
PAD = 70.0


def px(point):
    return ((point[0] - MIN_X) * SCALE + 20, HEIGHT - (point[1] - MIN_Y) * SCALE - 20)


net = RoadNetwork(DATA)
labels = {name: point for name, point in DATA["labels"]}
positions = [net.nearest(labels[name]) for name in ("笃行北楼", "文典阁", "磬苑广场")]
positions.append(positions[0])
_, route, _ = net.through(positions)
xs = [point[0] for point in route]
ys = [point[1] for point in route]
box = (min(xs) - PAD, min(ys) - PAD, max(xs) + PAD, max(ys) + PAD)
left, top = px((box[0], box[3]))
right, bottom = px((box[2], box[1]))
crop = (int(left), int(top), int(right), int(bottom))
zoom = 2.4

panels = []
for name, caption in (("route_before.png", "处理前 · 直角机器人轨迹"), ("route_after.png", "处理后 · 圆角 + GPS 摆动")):
    image = Image.open(HERE / name).crop(crop)
    image = image.resize((int(image.width * zoom), int(image.height * zoom)), Image.LANCZOS)
    panel = Image.new("RGB", (image.width, image.height + 44), "#ffffff")
    panel.paste(image, (0, 44))
    pen = ImageDraw.Draw(panel)
    pen.text((12, 14), caption, fill="#111111")
    panels.append(panel)

gap = 16
combo = Image.new("RGB", (sum(panel.width for panel in panels) + gap, panels[0].height), "#ffffff")
x = 0
for panel in panels:
    combo.paste(panel, (x, 0))
    x += panel.width + gap
target = HERE / "compare_realism.png"
combo.save(target)
print(f"{target}  {combo.width}x{combo.height}  crop {crop}")