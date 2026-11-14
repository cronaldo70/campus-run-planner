"""Offline check: can the start be recovered from checkpoint distances alone?"""

import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "outputs" / "real-run-planner"
sys.path.insert(0, str(HERE))

import real_position  # noqa: E402
import real_run_sim as bridge  # noqa: E402


def main():
    data = json.loads((HERE / "campus.json").read_text(encoding="utf-8"))
    site = bridge.Site(data)
    stations = {name: tuple(point) for name, point in data["labels"]}
    network = site.network

    truths = [
        (-150.0, -300.0),
        (60.0, 240.0),
        (300.0, -120.0),
        (-380.0, 120.0),
    ]
    names = list(stations)
    failures = 0
    print("campus rings:", len(site.campus), "labels:", len(names))
    for truth in truths:
        position = network.nearest(truth)
        truth = position.point if position is not None else truth
        offset = position.offset if position is not None else -1
        pairs = [(name, math.dist(truth, stations[name])) for name in names]
        pairs.sort(key=lambda item: item[1])
        # Two checkpoints on the same spot cannot pin a position, so pick the two
        # nearest *different* ones - that is what the app lists anyway.
        near2 = [pairs[0]]
        for name, metres in pairs[1:]:
            if math.dist(stations[near2[0][0]], stations[name]) >= 40:
                near2.append((name, metres))
                break
        print(f"\n真值 {tuple(round(v, 1) for v in truth)} 离路 {offset:.1f} 米 · 两个最近 "
              f"{near2[0][0]} {near2[0][1]:.0f} 米 / {near2[1][0]} {near2[1][1]:.0f} 米")
        fix = real_position.resolve(near2, stations, inside=site.inside, road=site.road,
                                    blocked=site.blocked)
        error = math.dist(fix.point, truth)
        chosen = "OK" if error <= 25 else "WRONG"
        if chosen == "WRONG":
            failures += 1
        print(f"  -> 解出 {tuple(round(v, 1) for v in fix.point)} 误差 {error:.1f} 米 {chosen}")
        for candidate in fix.candidates:
            print(f"     候选 {tuple(round(v, 1) for v in candidate.point)} 分 {candidate.score:.1f} "
                  f"{'校内' if candidate.inside else '校外'} 离路 {candidate.road:.0f} {candidate.blocked or ''}")

        wide = pairs[:4]
        fix3 = real_position.resolve(wide, stations, inside=site.inside, road=site.road,
                                     blocked=site.blocked)
        error3 = math.dist(fix3.point, truth)
        print(f"  -> 四点最小二乘 {tuple(round(v, 1) for v in fix3.point)} 误差 {error3:.2f} 米 "
              f"{'OK' if error3 <= 5 else 'WRONG'}")
        if error3 > 5:
            failures += 1

    print("\nfailures:", failures)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())