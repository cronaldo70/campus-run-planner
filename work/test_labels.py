"""Test the widened label table and the tolerant matcher."""
import json
import sys

sys.path.insert(0, "outputs/real-run-planner")
sys.path.insert(0, "outputs/run-planner")

import read_checkpoints as reader
from real_run_sim import Site
import real_run_sim as bridge

data = json.load(open("outputs/real-run-planner/campus.json", encoding="utf-8"))
labels = {name: tuple(point) for name, point in data["labels"]}
print(f"labels in campus.json: {len(labels)}")

# --- simulated 步道乐跑 checkpoint list (two names + distances) ---
lines = [
    (0, 0, "自由打卡（可自行安排）"),
    (0, 10, "人文楼东侧（距你 320 米）"),
    (0, 20, "行政楼（距你 480 米）"),
    (0, 30, "开始乐跑"),
]
names = reader.checkpoint_rows(lines)
print(f"parsed names: {names}")
resolved = [(name, reader.resolve(labels, name)) for name in names]
for name, point in resolved:
    print(f"  {name} -> {'MISSING' if point is None else f'({point[0]:.1f}, {point[1]:.1f})'}")

# --- matcher edge cases ---
cases = [
    "人文楼东侧",
    "人文楼东",
    "人文楼",
    "人文棧东侧",      # OCR drops a character
    "理工C楼西北侧",
    "蕙园3栋",
    "文典阁西门",
    "篮球场南门",
    "主体育场",
    "不存在的楼",
]
print("\nresolver:")
for case in cases:
    point = reader.resolve(labels, case)
    print(f"  {case:12s} -> {'MISSING' if point is None else f'({point[0]:.0f}, {point[1]:.0f})'}")

# --- every resolved point must be reachable: inside campus and near a road ---
site = Site(data)
bridge.set_site(site)
bad_inside = bad_road = blocked = 0
worst = (0.0, "")
for name, point in labels.items():
    if not site.inside(point):
        bad_inside += 1
    kind = site.blocked(point)
    if kind:
        blocked += 1
    off = site.road(point)
    if off > 60:
        bad_road += 1
    if off > worst[0]:
        worst = (off, name)
print(f"\nhygiene: outside campus={bad_inside}, in building/water={blocked}, >60 m from road={bad_road}")
print(f"worst road offset: {worst[0]:.1f} m ({worst[1]})")

# --- routing still works with the bigger label table ---
from pedestrian_routes import Network

net = Network(data, campus_only=True)
start = net.nearest(labels["文典阁西门"])
cps = [net.nearest(labels["人文楼东侧"]), net.nearest(labels["行政楼"])]
metres, path, order = net.plan(start, cps, via=[], finish=None, minimum=2500)
print(f"\nplan via 人文楼东侧+行政楼: {metres:.0f} m, {len(path)} pts")
point = site.blocked(path[0])
print(f"path start blocked? {point!r}")

OK = (
    all(p is not None for _, p in resolved)
    and bad_inside == 0
    and blocked == 0
    and reader.resolve(labels, "不存在的东西") is None
)
print("\nOK" if OK else "\nCHECK ABOVE")