"""Render the real-run planner's route over its own road graph.

Purpose: judge two complaints by eye and by number
  * "route looks like a chain of straight segments, not smooth"
  * "route leaves the drawn roads"

The picture is drawn with Pillow from campus.json alone, so it shows exactly the
geometry the GUI uses: graph nodes are OSM way vertices, edges are straight lines
between consecutive vertices.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "outputs" / "real-run-planner"))

import pedestrian_routes as pr  # noqa: E402

DATA = ROOT / "outputs" / "real-run-planner" / "campus.json"


def load():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    return data, pr.Network(data)


def stats(path):
    lengths = [math.dist(a, b) for a, b in zip(path, path[1:])]
    turns = []
    for a, b, c in zip(path, path[1:], path[2:]):
        u = (b[0] - a[0], b[1] - a[1])
        v = (c[0] - b[0], c[1] - b[1])
        nu, nv = math.hypot(*u), math.hypot(*v)
        if nu < 1e-6 or nv < 1e-6:
            continue
        cos = max(-1.0, min(1.0, (u[0] * v[0] + u[1] * v[1]) / (nu * nv)))
        turns.append(math.degrees(math.acos(cos)))
    turns.sort()
    return {
        "vertices": len(path),
        "length": sum(lengths),
        "seg_min": min(lengths) if lengths else 0.0,
        "seg_median": sorted(lengths)[len(lengths) // 2] if lengths else 0.0,
        "seg_max": max(lengths) if lengths else 0.0,
        "turn_median": sorted(turns)[len(turns) // 2] if turns else 0.0,
        "turn_max": max(turns) if turns else 0.0,
        "sharp": sum(1 for t in turns if t > 45),
    }


def render(net, path, out: Path, *, width=1500):
    boxes = [p for edge in net.segments for p in (net.nodes[edge[0]], net.nodes[edge[1]])]
    x0 = min(p[0] for p in boxes)
    x1 = max(p[0] for p in boxes)
    y0 = min(p[1] for p in boxes)
    y1 = max(p[1] for p in boxes)
    scale = (width - 40) / (x1 - x0)
    height = int((y1 - y0) * scale) + 40

    def px(p):
        return 20 + (p[0] - x0) * scale, height - 20 - (p[1] - y0) * scale

    image = Image.new("RGB", (width, height), "#f4f2ec")
    draw = ImageDraw.Draw(image)
    for edge, segment in net.segments.items():
        color = "#c9ccc0" if not segment.reason else "#e6c9c4"
        draw.line([px(net.nodes[edge[0]]), px(net.nodes[edge[1]])], fill=color, width=1)
    for a, b in zip(path, path[1:]):
        draw.line([px(a), px(b)], fill="#1f8a4c", width=3)
    for point in path:
        x, y = px(point)
        draw.ellipse([x - 1.6, y - 1.6, x + 1.6, y + 1.6], fill="#d1483b")
    draw.text((12, 10), f"{stats(path)['vertices']} vertices / {stats(path)['length'] / 1000:.2f} km", fill="#333")
    image.save(out)
    print("wrote", out, image.size)


def zoom(net, path, out: Path, center, metres=120, width=760):
    scale = (width - 40) / metres

    def px(p):
        return 20 + (p[0] - center[0] + metres / 2) * scale, width - 20 - (p[1] - center[1] + metres / 2) * scale

    image = Image.new("RGB", (width, width), "#f4f2ec")
    draw = ImageDraw.Draw(image)
    for edge, segment in net.segments.items():
        draw.line([px(net.nodes[edge[0]]), px(net.nodes[edge[1]])], fill="#c9ccc0", width=1)
    for a, b in zip(path, path[1:]):
        draw.line([px(a), px(b)], fill="#1f8a4c", width=3)
    for point in path:
        x, y = px(point)
        draw.ellipse([x - 2, y - 2, x + 2, y + 2], fill="#d1483b")
    image.save(out)
    print("wrote", out, image.size)


def main():
    data, net = load()
    labels = {name: tuple(point) for name, point in data["labels"]}
    start = net.nearest(labels["文典阁西门"])
    aims = [net.nearest(labels["篮球场南门"]), net.nearest(labels["磬苑广场"])]
    metres, path, order = net.plan(start, aims, [], None, minimum=2500 * 1.02 + 25)
    print("order", order, "metres", round(metres, 1))
    print("stats", stats(path))
    render(net, path, ROOT / "work" / "real-route.png")

    # zoom on the first bend with a sharp turn
    best, best_turn = None, 0.0
    for index in range(1, len(path) - 1):
        a, b, c = path[index - 1], path[index], path[index + 1]
        u = (b[0] - a[0], b[1] - a[1])
        v = (c[0] - b[0], c[1] - b[1])
        nu, nv = math.hypot(*u), math.hypot(*v)
        if nu < 1e-6 or nv < 1e-6:
            continue
        cos = max(-1.0, min(1.0, (u[0] * v[0] + u[1] * v[1]) / (nu * nv)))
        turn = math.degrees(math.acos(cos))
        if turn > best_turn:
            best, best_turn = b, turn
    print("sharpest bend", round(best_turn, 1), "deg at", tuple(round(v, 1) for v in best))
    zoom(net, path, ROOT / "work" / "real-route-zoom.png", best)


if __name__ == "__main__":
    main()