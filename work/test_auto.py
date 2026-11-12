"""Offline check: OCR reading, triangulation and the open-route planner."""

import json
import math
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "outputs" / "run-planner"
sys.path.insert(0, str(OUT))

import auto_route  # noqa: E402
import checkpoint_reader as reader  # noqa: E402
from road_network import RoadNetwork  # noqa: E402

data = json.loads((OUT / "campus_map.json").read_text(encoding="utf-8"))
labels = {name: tuple(point) for name, point in data["labels"]}
net = RoadNetwork(data)

# --- 1. OCR + triangulation on a synthesised checkpoint screen ---------------
truth = (12.0, 6.0)
picks = ["文典阁", "笃行北楼", "磬苑广场"]
rows = [(name, math.dist(labels[name], truth)) for name in picks]
print("truth", truth, " distances", [f"{name} {metres:.0f}" for name, metres in rows])

image = Image.new("RGB", (900, 300), "#ffffff")
pen = ImageDraw.Draw(image)
font = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 32)
pen.text((36, 16), "未打卡点", fill="#111111", font=font)
for index, (name, metres) in enumerate(rows):
    pen.text((36, 80 + index * 62), f"{name}   距你 {metres:.0f} 米", fill="#111111", font=font)
shot = HERE / "probe_checkpoints.png"
image.save(shot)

lines = reader.ocr_lines(shot)
parsed = reader.parse(lines)
print("parsed", [(name, round(metres)) for name, metres in parsed])
report = reader.read_screen(labels, shot.read_bytes())
print("checkpoints", [(item["name"], round(item["metres"])) for item in report["checkpoints"]])
if report["position"]:
    print(f"located {report['position'][0]:.1f}, {report['position'][1]:.1f}  "
          f"error {math.dist(report['position'], truth):.1f} m  residual {report['position_error']:.1f} m")
for warning in report["warnings"]:
    print("!", warning)

# --- 2. open route through every checkpoint --------------------------------
points = [labels[name] for name in labels]
start = time.time()
result = auto_route.plan(net, truth, points, minimum=2500.0, seed=3)
print(f"\nplan {result['metres']:.0f} m in {time.time() - start:.1f} s, "
      f"{len(result['route'])} vertices, tail legs {result['tail_legs']}, violations {net.violations(result['route'])}")
print(auto_route.describe(net, truth, points, result, list(labels)))
gaps = [reached for reached, _offset in result["access"]]
offsets = [offset for _reached, offset in result["access"]]
print(f"checkpoint access: max gap {max(gaps):.1f} m, label offset {min(offsets):.0f}-{max(offsets):.0f} m")
assert result["metres"] >= 2500, "route shorter than the required distance"
assert max(gaps) <= 5.0, "a checkpoint is not actually on the route"
assert not net.violations(result["route"]), "route cuts through a building or water"

# a lighter task: three checkpoints only, still must reach 2.5 km
small = [labels[name] for name in ("文典阁", "笃行北楼", "磬苑广场")]
quick = auto_route.plan(net, truth, small, minimum=2500.0, seed=5)
print(f"\n3 checkpoints -> {quick['metres']:.0f} m, tail legs {quick['tail_legs']}, "
      f"violations {net.violations(quick['route'])}")
assert quick["metres"] >= 2500
print("\nOK")