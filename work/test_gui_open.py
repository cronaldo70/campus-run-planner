"""Headless GUI check: 读取手机 → 开放式路线 → 轨迹生成。"""

import json
import math
import sys
import tkinter as tk
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "outputs" / "run-planner"
sys.path.insert(0, str(OUT))

import checkpoint_reader as reader  # noqa: E402
import location_sim as sim  # noqa: E402
import run_planner  # noqa: E402

data = json.loads((OUT / "campus_map.json").read_text(encoding="utf-8"))
labels = {name: tuple(point) for name, point in data["labels"]}

shot = (HERE / "probe_checkpoints.png").read_bytes()
report = reader.read_screen(labels, shot)
print("OCR:", [(item["name"], round(item["metres"])) for item in report["checkpoints"]])
print("position:", [round(v, 1) for v in report["position"] or ()])

root = tk.Tk()
planner = run_planner.Planner(root, data)
planner.minimum.set("2.5")
planner.finish_read(report, "")
root.update_idletasks()
print("open mode:", planner.open_route.get(), "via:", len(planner.via), planner.via_names)
print("plan_text:\n" + planner.plan_text)
print("metrics:", [widget.cget("text") for widget in planner.metrics])
print("route vertices:", len(planner.route))
assert planner.route, "no route drawn"
assert planner.plan_text, "no plan text"
assert planner.passes == 1
points = planner.build_track()
print("track points:", len(points), "first", points[0][:1], "last", points[-1][:1])
assert len(points) > 100

# every checkpoint must be reachable: the track passes its road access point
track = [sim.to_map(point[0], point[1]) for point in points]
for item in report["checkpoints"]:
    access = planner.network.nearest(item["point"]).point
    gap = min(math.dist(access, vertex) for vertex in track)
    offset = math.dist(item["point"], access)
    print(f"  {item['name']}: 到接入点 {gap:.1f} 米（图上点位离路 {offset:.0f} 米）")
    assert gap <= 5.0, item["name"]

root.destroy()
print("OK")