"""Compare the raw graph route with the humanised track, and draw both."""

import json
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent
OUT = ROOT.parent / "outputs" / "run-planner"
sys.path.insert(0, str(OUT))

import location_sim as sim  # noqa: E402
from road_network import RoadNetwork  # noqa: E402

DATA = json.loads((OUT / "campus_map.json").read_text(encoding="utf-8"))
NET = RoadNetwork(DATA)
SCALE = 1.35
MIN_X, MIN_Y, MAX_X, MAX_Y = DATA["bounds"]
WIDTH = int((MAX_X - MIN_X) * SCALE) + 40
HEIGHT = int((MAX_Y - MIN_Y) * SCALE) + 40
NAMES = ["笃行北楼", "文典阁", "磬苑广场"]


def px(point):
    return (int((point[0] - MIN_X) * SCALE) + 20, HEIGHT - int((point[1] - MIN_Y) * SCALE) - 20)


def base_image():
    image = Image.new("RGB", (WIDTH, HEIGHT), "#f6f4ee")
    pen = ImageDraw.Draw(image)
    for kind, points in DATA["areas"]:
        colour = {"water": "#a9d3e8", "building": "#d9d3c6", "green": "#dcecd0", "sport": "#e8dcc8"}.get(kind)
        if colour and len(points) >= 3:
            pen.polygon([px(point) for point in points], fill=colour, outline="#c9c4b8")
    for a, b in NET.edges:
        pen.line([px(NET.nodes[a]), px(NET.nodes[b])], fill="#b8b2a6", width=1)
    return image, pen


def corner_angles(route):
    out = []
    for previous, corner, following in zip(route, route[1:-1], route[2:]):
        v1 = (corner[0] - previous[0], corner[1] - previous[1])
        v2 = (following[0] - corner[0], following[1] - corner[1])
        l1, l2 = math.hypot(*v1), math.hypot(*v2)
        if l1 < 1e-6 or l2 < 1e-6:
            continue
        cosine = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (l1 * l2)))
        out.append(math.degrees(math.acos(cosine)))
    return out


labels = {name: point for name, point in DATA["labels"]}
picks = [labels[name] for name in NAMES]
positions = [NET.nearest(point) for point in picks]
positions.append(positions[0])
total, route, _ = NET.through(positions)
print(f"route {total:.0f} m, {len(route)} vertices, violations {NET.violations(route)}")
print(f"raw corner angles: max {max(corner_angles(route)):.0f}°, straight-ish "
      f"{sum(1 for a in corner_angles(route) if a > 45):d} sharp turns")

for pace in (360.0,):
    points = sim.build_track(route, pace=pace, laps=1, loop=True, seed=7)
    stats = sim.track_stats(points)
    track = [sim.to_map(lat, lon) for lat, lon, _ in points]
    angles = corner_angles(track)
    print(f"track pace {pace/60:.2f}: {len(points)} points, {stats['meters']/1000:.3f} km, "
          f"{stats['seconds']:.0f} s ({stats['seconds']/60:.2f} min), "
          f"mean {stats['seconds']/(stats['meters']/1000):.0f} s/km")
    print(f"   splits {int(stats['fastest'])}-{int(stats['slowest'])} s/km, corners max {max(angles):.0f}°")
    print(f"   straight legs >40 m: {sum(1 for a, b in zip(track, track[1:]) if math.dist(a, b) > 40)}")

image, pen = base_image()
pen.line([px(point) for point in route], fill="#d6402c", width=3)
pen.line([px(point) for point in track], fill="#1d6fb8", width=3, joint="curve")
pen.text((14, 12), f"{'-'.join(NAMES)}  raw(red) vs humanised(blue)  {total/1000:.2f} km", fill="#111111")
image.save(ROOT / "route_after.png")
print(ROOT / "route_after.png")