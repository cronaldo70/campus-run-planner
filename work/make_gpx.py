"""Write a real 3-lap GPX for the sample route so the device can replay it."""

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "outputs" / "run-planner"
sys.path.insert(0, str(OUT))

import location_sim as sim  # noqa: E402
from road_network import RoadNetwork  # noqa: E402

data = json.loads((OUT / "campus_map.json").read_text(encoding="utf-8"))
net = RoadNetwork(data)
labels = {name: point for name, point in data["labels"]}
positions = [net.nearest(labels[name]) for name in ("笃行北楼", "文典阁", "磬苑广场")]
positions.append(positions[0])
total, route, _ = net.through(positions)
points = sim.build_track(route, pace=360.0, laps=3, loop=True, seed=11)
stats = sim.track_stats(points)
target = OUT / "generated" / f"route-human-{time.strftime('%Y%m%d-%H%M')}.gpx"
sim.write_gpx(points, target, name="campus-run-human")
print(f"{target.name}: {len(points)} points, {stats['meters']/1000:.3f} km, "
      f"{stats['seconds']/60:.2f} min, splits "
      f"{int(stats['fastest'])}-{int(stats['slowest'])} s/km")
print(target)