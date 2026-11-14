"""Compare the real-run route before/after rounding: turns, reversals, metres."""
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "outputs" / "real-run-planner"))
sys.path.insert(0, str(ROOT.parent / "outputs" / "run-planner"))

import json

import location_sim as sim
import pedestrian_routes as pr
import real_run_sim as bridge


def turns(points):
    angles = []
    for a, b, c in zip(points, points[1:], points[2:]):
        u = (b[0] - a[0], b[1] - a[1])
        v = (c[0] - b[0], c[1] - b[1])
        nu, nv = math.hypot(*u), math.hypot(*v)
        if nu < 1e-6 or nv < 1e-6:
            continue
        cos = max(-1.0, min(1.0, (u[0] * v[0] + u[1] * v[1]) / (nu * nv)))
        angles.append(math.degrees(math.acos(cos)))
    return angles


def reversals(points, tolerance=1.5):
    hits = []
    for i, (a, b, c) in enumerate(zip(points, points[1:], points[2:])):
        if math.dist(a, c) <= tolerance and math.dist(a, b) > 3:
            hits.append(i)
    return hits


def metres(points):
    return sum(math.dist(a, b) for a, b in zip(points, points[1:]))


def deviation(points, net):
    worst = []
    for point in points:
        position = net.nearest(point)
        worst.append(position.offset if position is not None else 999.0)
    worst.sort()
    return worst[len(worst) // 2], worst[int(len(worst) * 0.99)], worst[-1]


def report(name, points):
    angles = turns(points)
    over = [a for a in angles if a > 45]
    print(f"{name}: {len(points)} 点 / {metres(points):.1f} 米 / "
          f"最大转角 {max(angles):.1f}° / >45° {len(over)} 处 / "
          f"A-B-A 折返 {len(reversals(points))} 处")
    return points


def main():
    data = json.loads((ROOT.parent / "outputs" / "real-run-planner" / "campus.json").read_text(encoding="utf-8"))
    net = pr.Network(data)
    labels = {name: point for name, point in data["labels"]}
    start = net.nearest(tuple(labels["文典阁西门"]))
    aims = [net.nearest(tuple(labels["篮球场南门"])),
            net.nearest(tuple(labels["磬苑广场"]))]
    total, path, order = net.plan(start, aims, [], None, minimum=2500 * 1.02 + 25)
    report("规划路径（原始顶点）", path)
    display = bridge.display(path)
    report("画布路径（圆角 12 m + 1.5 m 采样）", display)
    points, stats = bridge.build(path, pace=270.0, seed=7, minimum=2500)
    track = [sim.to_map(point[0], point[1]) for point in points]
    report("手机回放轨迹（human=True）", track)
    for name, samples in (("画布路径", display), ("回放轨迹", track)):
        middle, tail, worst = deviation(samples, net)
        print(f"{name} 离路: 中位 {middle:.1f} 米 / 99% {tail:.1f} 米 / 最远 {worst:.1f} 米")
    print(f"统计: {stats['meters']:.1f} 米 / {stats['seconds']:.1f} 秒 / "
          f"配速 {stats['fastest']:.0f}-{stats['slowest']:.0f} 秒每公里 / "
          f"shortfall {stats.get('shortfall', 0):.1f} 米")


if __name__ == "__main__":
    main()