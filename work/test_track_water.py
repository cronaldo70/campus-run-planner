"""Build a real planned route and count track points that land in water/buildings."""
import json
import sys

sys.path.insert(0, "outputs/real-run-planner")
sys.path.insert(0, "outputs/run-planner")

import location_sim as sim
import real_run_sim as bridge
from pedestrian_routes import Network

data = json.load(open("outputs/real-run-planner/campus.json", encoding="utf-8"))
site = bridge.Site(data)
bridge.set_site(site)
net = Network(data, campus_only=True)
labels = {name: tuple(point) for name, point in data["labels"]}

cases = [
    ("文典阁西门 → 人文楼东侧 + 行政楼", "文典阁西门", ["人文楼东侧", "行政楼"]),
    ("文典阁西门 → 磬苑体育馆 + 蕙园3栋", "文典阁西门", ["磬苑体育馆", "蕙园3栋"]),
    ("人文楼东侧 → 艺术楼 + 主体育场", "人文楼东侧", ["艺术楼", "主体育场"]),
    ("校医院 → 行政楼 + 磬苑体育馆", "校医院", ["行政楼", "磬苑体育馆"]),
]

report = []
for title, start_name, cp_names in cases:
    start = net.nearest(labels[start_name])
    cps = [net.nearest(labels[name]) for name in cp_names]
    metres, path, order = net.plan(start, cps, via=[], finish=None, minimum=2500)
    # gap: how far each checkpoint is from the walkable network
    pts, stats = bridge.build(path, pace=300, minimum=2500)
    water = sum(1 for p in pts if site.in_water(sim.to_map(p[0], p[1])))
    inside_b = sum(1 for p in pts if site.in_building(sim.to_map(p[0], p[1])))
    report.append(
        f"{title}\n"
        f"  规划 {metres:.0f} m / 轨迹 {stats['meters']:.0f} m / 点 {len(pts)}"
        f" / 水域点 {water} / 建筑点 {inside_b} / 补点 {stats.get('water_snapped', 0)}"
    )

# Also the raw display path (what the canvas draws)
path0 = None
start = net.nearest(labels["文典阁西门"])
metres, path0, _ = net.plan(start, [net.nearest(labels["人文楼东侧"])], via=[], finish=None, minimum=2500)
disp = bridge.display(path0)
water_disp = sum(1 for p in disp if site.in_water(p))
report.append(f"display path (rounded 12 m + 1.5 m sampling): {len(disp)} pts, water {water_disp}")

open("work/track_water.log", "w", encoding="utf-8").write("\n".join(report))
print("\n".join(report))