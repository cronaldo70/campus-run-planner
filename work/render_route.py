"""Render the bundled campus network and a sample loop to PNG for eyeballing."""

import json
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent
OUT = ROOT.parent / "outputs" / "run-planner"
sys.path.insert(0, str(OUT))

from road_network import RoadNetwork  # noqa: E402

DATA = json.loads((OUT / "campus_map.json").read_text(encoding="utf-8"))
NET = RoadNetwork(DATA)
SCALE = 1.35


def inside(point, polygon):
    x, y = point
    hit = False
    for (x1, y1), (x2, y2) in zip(polygon, polygon[1:] + polygon[:1]):
        if (y1 > y) != (y2 > y):
            cross = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if cross > x:
                hit = not hit
    return hit


def crosses(p, q, polygon):
    if inside(p, polygon) or inside(q, polygon):
        return True
    for (x1, y1), (x2, y2) in zip(polygon, polygon[1:] + polygon[:1]):
        d1 = (q[0] - p[0], q[1] - p[1])
        d2 = (x2 - x1, y2 - y1)
        den = d1[0] * d2[1] - d1[1] * d2[0]
        if abs(den) < 1e-12:
            continue
        t = ((x1 - p[0]) * d2[1] - (y1 - p[1]) * d2[0]) / den
        u = ((x1 - p[0]) * d1[1] - (y1 - p[1]) * d1[0]) / den
        if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
            return True
    return False


MIN_X, MIN_Y, MAX_X, MAX_Y = DATA["bounds"]
WIDTH = int((MAX_X - MIN_X) * SCALE) + 40
HEIGHT = int((MAX_Y - MIN_Y) * SCALE) + 40


def px(point):
    return (int((point[0] - MIN_X) * SCALE) + 20, HEIGHT - int((point[1] - MIN_Y) * SCALE) - 20)


def sample_route():
    labels = {name: point for name, point in DATA["labels"]}
    names = ["笃行北楼", "文典阁", "磬苑广场"]
    picks = [labels[name] for name in names if name in labels]
    if len(picks) < 2:
        raise SystemExit(f"缺少标注点，可用: {sorted(labels)}")
    positions = [NET.nearest(point) for point in picks]
    if len(positions) > 1:
        positions.append(positions[0])
    total, route, _ = NET.through(positions)
    return total, route, [name for name in names if name in labels]


def draw(route: list, path: Path, title: str):
    image = Image.new("RGB", (WIDTH, HEIGHT), "#f6f4ee")
    pen = ImageDraw.Draw(image)
    for kind, points in DATA["areas"]:
        colour = {"water": "#a9d3e8", "building": "#d9d3c6", "green": "#dcecd0", "sport": "#e8dcc8"}.get(kind)
        if not colour or len(points) < 3:
            continue
        pen.polygon([px(point) for point in points], fill=colour, outline="#c9c4b8")
    for a, b in NET.edges:
        pen.line([px(NET.nodes[a]), px(NET.nodes[b])], fill="#b8b2a6", width=1)
    if len(route) > 1:
        pen.line([px(point) for point in route], fill="#d6402c", width=4, joint="curve")
        pen.ellipse([px(route[0])[0] - 6, px(route[0])[1] - 6, px(route[0])[0] + 6, px(route[0])[1] + 6], fill="#1a7f37")
    for name, point in DATA["labels"]:
        x, y = px(point)
        pen.text((x + 4, y - 10), name, fill="#333333")
    pen.text((14, 12), title, fill="#111111")
    image.save(path)
    return path


if __name__ == "__main__":
    total, route, names = sample_route()
    polys = [points for kind, points in DATA["areas"] if kind in {"water", "building"}]
    bad = [math.dist(a, b) for a, b in zip(route, route[1:])
           if any(crosses(a, b, polygon) for polygon in polys)]
    print(f"route {total:.0f} m via {'-'.join(names)}: {len(route)} vertices, "
          f"{len(bad)} segments cross water/building, {sum(bad):.0f} m of it")
    out = draw(route, ROOT / "route_before.png", f"{'-'.join(names)}  {total/1000:.2f} km")
    print(out)