"""Zoomed render + back-tracking analysis of the real-run planner route."""

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


def plan():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    net = pr.Network(data)
    labels = {name: tuple(point) for name, point in data["labels"]}
    start = net.nearest(labels["文典阁西门"])
    aims = [net.nearest(labels["篮球场南门"]), net.nearest(labels["磬苑广场"])]
    metres, path, order = net.plan(start, aims, [], None, minimum=2500 * 1.02 + 25)
    return net, path, metres


def repeated(path):
    seen = {}
    for index, point in enumerate(path):
        key = (round(point[0], 1), round(point[1], 1))
        seen.setdefault(key, []).append(index)
    dupes = {key: idx for key, idx in seen.items() if len(idx) > 1}
    return dupes


def render_box(net, path, out: Path, *, box, width=1500, dot=True):
    x0, y0, x1, y1 = box
    scale = (width - 40) / (x1 - x0)
    height = int((y1 - y0) * scale) + 40

    def px(p):
        return 20 + (p[0] - x0) * scale, height - 20 - (p[1] - y0) * scale

    image = Image.new("RGB", (width, height), "#f6f4ee")
    draw = ImageDraw.Draw(image)
    for edge, segment in net.segments.items():
        a, b = net.nodes[edge[0]], net.nodes[edge[1]]
        if max(a[0], b[0]) < x0 or min(a[0], b[0]) > x1 or max(a[1], b[1]) < y0 or min(a[1], b[1]) > y1:
            continue
        draw.line([px(a), px(b)], fill="#c9ccc0" if not segment.reason else "#e8cdc8", width=2)
    for a, b in zip(path, path[1:]):
        draw.line([px(a), px(b)], fill="#1f8a4c", width=4)
    if dot:
        for point in path:
            x, y = px(point)
            draw.ellipse([x - 1.5, y - 1.5, x + 1.5, y + 1.5], fill="#c8372b")
    draw.text((12, 10), f"{x1 - x0:.0f} m wide", fill="#333")
    image.save(out)
    print("wrote", out, image.size, "scale", round(scale, 2), "px/m")


def main():
    net, path, metres = plan()
    import real_run_sim as bridge

    shown = bridge.display(path)
    xs = [p[0] for p in shown]
    ys = [p[1] for p in shown]
    box = (min(xs) - 40, min(ys) - 40, max(xs) + 40, max(ys) + 40)
    print("route box", [round(v, 1) for v in box], "metres", round(metres, 1))
    render_box(net, path, ROOT / "work" / "real-route-zoom.png", box=box, width=1500, dot=False)
    render_box(net, shown, ROOT / "work" / "real-route-zoom-after.png", box=box, width=1500, dot=False)

    print("--- 原始顶点")
    report(path)
    print("--- 画布/回放用的圆角路径")
    report(shown)


def report(path):
    dupes = repeated(path)
    print("repeated vertices", len(dupes))
    for key, idx in list(dupes.items())[:6]:
        print("  ", key, "at", idx)
    back = [index for index in range(1, len(path) - 1)
            if math.dist(path[index - 1], path[index + 1]) < 1e-6]
    print("immediate reversals (A->B->A):", back)
    angles = []
    for a, b, c in zip(path, path[1:], path[2:]):
        u = (b[0] - a[0], b[1] - a[1])
        v = (c[0] - b[0], c[1] - b[1])
        nu, nv = math.hypot(*u), math.hypot(*v)
        if nu < 1e-6 or nv < 1e-6:
            continue
        angles.append(math.degrees(math.acos(max(-1.0, min(1.0, (u[0] * v[0] + u[1] * v[1]) / (nu * nv))))))
    print("max turn", round(max(angles), 1), "deg, over 45 deg:", len([a for a in angles if a > 45]))


if __name__ == "__main__":
    main()