"""Check that the generated splits look like the user's real records."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "outputs" / "real-run-planner"))
sys.path.insert(0, str(ROOT / "outputs" / "run-planner"))

import pedestrian_routes as pr
import real_run_sim as bridge

data = json.loads((ROOT / "outputs" / "real-run-planner" / "campus.json").read_text(encoding="utf-8"))
net = pr.Network(data)
labels = {name: tuple(point) for name, point in data["labels"]}
start = net.nearest(labels["文典阁西门"])
aims = [net.nearest(labels["篮球场南门"]), net.nearest(labels["磬苑广场"])]
metres, path, order = net.plan(start, aims, [], None, minimum=2500 * 1.02 + 25)

for pace_text, pace in (("5:00", 300.0), ("4:58", 298.0)):
    points, stats = bridge.build(path, pace=pace, seed=3, minimum=2500)
    average = stats["seconds"] / stats["meters"] * 1000.0
    print(f"配速 {pace_text}: {len(points)} 点 / {stats['meters']:.1f} 米 / "
          f"{bridge.format_time(stats['seconds'])} / 平均 {average:.0f} 秒每公里")
    print("  分段:", bridge.splits_text(stats))
    print(f"  200 米滑窗: {stats['fastest']:.0f} – {stats['slowest']:.0f} 秒每公里")

for pace_text in ("4:30", "6:00"):
    points, stats = bridge.build(path, pace=bridge.parse_pace(pace_text), seed=11, minimum=2500)
    print(f"对比 {pace_text}: 平均 {stats['seconds'] / stats['meters'] * 1000:.0f} / {bridge.splits_text(stats)}")