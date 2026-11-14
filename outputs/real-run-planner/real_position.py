"""Work out where the phone really is, without anyone typing coordinates.

The Compass app stopped showing lat/lon in iOS 16 (it prints the city name
instead - verified on iOS 27.2: only "106° 东" and "安徽省合肥市"), so the old
"switch to Compass and read the numbers" step cannot work. This module gets the
position from the running app itself:

* the checkpoint list prints "距你 N 米" next to every checkpoint, and those
  numbers are measured from the phone's real position as long as no simulated
  location is active;
* two distances put you at one of two mirror points, three or more pin you down
  exactly.

Candidate points are then judged against the campus outline and the walkable
network, so the mirror image that sits inside a building, in the river or off
campus is dropped automatically.

The screenshot and OCR plumbing is shared with outputs/run-planner, so the
numbers here match what the other planner reads.
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "run-planner"))

import checkpoint_reader as reader  # noqa: E402


MIN_RANGE = 20.0
MAX_RANGE = 1800.0
BLOCK_PENALTY = 600.0
OUTSIDE_PENALTY = 400.0


@dataclass
class Candidate:
    point: tuple[float, float]
    score: float
    inside: bool
    road: float
    blocked: str
    last: float | None = None
    misfit: float = 0.0

    @property
    def error(self) -> float:
        """Rough RMS distance error implied by the readings, in metres."""
        return math.sqrt(max(0.0, self.misfit))

    @property
    def usable(self) -> bool:
        return not self.blocked and self.inside and self.road <= 60.0


@dataclass
class Fix:
    point: tuple[float, float]
    method: str
    residual: float
    note: str = ""
    alternative: tuple[float, float] | None = None
    candidates: list[Candidate] = field(default_factory=list)


def circle_pair(a, ra, b, rb):
    """Intersections of two distance circles (empty, one or two points)."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    d = math.hypot(dx, dy)
    if d < 1e-9 or d > ra + rb or d < abs(ra - rb):
        return []
    along = (ra * ra - rb * rb + d * d) / (2 * d)
    height2 = ra * ra - along * along
    height = math.sqrt(max(0.0, height2))
    mx, my = a[0] + along * dx / d, a[1] + along * dy / d
    if height < 1e-6:
        return [(mx, my)]
    ox, oy = -dy / d * height, dx / d * height
    return [(mx + ox, my + oy), (mx - ox, my - oy)]


def distances_from_screen(labels, screen=None):
    """[(name, metres)] straight off the checkpoint list, in list order."""
    report = reader.read_screen(labels, screen=screen)
    pairs = [(item.get("name") or item.get("ocr"), float(item["metres"]))
             for item in report["checkpoints"]]
    pairs += [(item.get("name") or item.get("ocr"), float(item["metres"]))
              for item in report["others"]]
    seen, ordered = set(), []
    for name, metres in pairs:
        key = reader.flatten(name)
        if not key or key in seen or not MIN_RANGE <= metres <= MAX_RANGE:
            continue
        seen.add(key)
        ordered.append((name, metres))
    if not ordered:
        far = [(name, metres) for name, metres in pairs if metres > MAX_RANGE]
        if far:
            raise ValueError(
                "屏幕上的距离是 " + "、".join(f"{reader.flatten(name)} {metres / 1000:.2f} 公里" for name, metres in far)
                + "：这时手机还在上一次模拟跑的位置上，先点「停止并恢复真实定位」，等蓝点回到你身边再读。")
        raise ValueError("屏幕上没有可用的「距你」距离，先把步道乐跑停在打卡点列表页。")
    return ordered


def _misfit(point, known):
    return sum((math.dist(point, center) - metres) ** 2 for center, metres in known)


def _pattern_search(start, known, steps=(40.0, 10.0, 3.0, 1.0)):
    """Cheap downhill walk on the sum of squared range errors."""
    x, y = start
    best = _misfit((x, y), known)
    for step in steps:
        improved = True
        while improved:
            improved = False
            for dx, dy in ((step, 0.0), (-step, 0.0), (0.0, step), (0.0, -step),
                           (step, step), (step, -step), (-step, step), (-step, -step)):
                trial = (x + dx, y + dy)
                value = _misfit(trial, known)
                if value < best - 1e-9:
                    x, y, best = trial[0], trial[1], value
                    improved = True
    return (x, y), best


def _score(point, *, inside, road, blocked, last, misfit=0.0):
    is_inside = inside(point) if inside else True
    offset = road(point) if road else 0.0
    obstacle = blocked(point) if blocked else ""
    score = offset + (0.0 if is_inside else OUTSIDE_PENALTY)
    if obstacle:
        score += BLOCK_PENALTY
    distance_last = math.dist(point, last) if last else None
    if distance_last is not None and distance_last > 5:
        score += min(60.0, distance_last * 0.05)
    # A position that contradicts the printed distances is worth less, but the
    # map names are only approximate, so this penalty is deliberately soft.
    score += min(300.0, math.sqrt(max(0.0, misfit)) * 1.5)
    return Candidate(point, score, is_inside, offset, obstacle, distance_last, misfit)


MIN_BASELINE = 20.0


def _distinct(known):
    """Collapse checkpoint names that share one spot.

    The generated table gives 人文楼东侧 and 人文楼东门 the same coordinate, and the
    app can list both; two circles with one centre say nothing, so only the first of
    each cluster keeps its distance.
    """
    out = []
    for point, metres in known:
        if any(math.dist(point, other) < MIN_BASELINE for other, _ in out):
            continue
        out.append((point, metres))
    return out


def _ring(start, metres, count=72):
    """Points ``metres`` away from ``start``: all that one distance can tell us."""
    if metres <= 0:
        return [start]
    return [(start[0] + metres * math.cos(2 * math.pi * i / count),
             start[1] + metres * math.sin(2 * math.pi * i / count)) for i in range(count)]


def candidates(pairs, stations, *, inside=None, road=None, blocked=None, last=None):
    """Every point consistent with the distances, ranked by plausibility."""
    known = [(tuple(point), metres) for name, metres in pairs
             for point in [stations.get(name)] if point is not None]
    known = _distinct(known)
    if len(known) < 2 and not known:
        raise ValueError("能对上的打卡点不足两个，起点无法反解，请在地图上点选。")
    if len(known) < 2:
        # One usable distance: walk the circle it draws and let the map decide.
        point, metres = known[0]
        scored = []
        for seed in _ring(point, metres):
            found, misfit = _pattern_search(seed, known)
            scored.append(_score(found, inside=inside, road=road, blocked=blocked,
                                 last=last, misfit=misfit))
        scored.sort(key=lambda item: item.score)
        return scored
    ordered = sorted(known, key=lambda item: item[1])
    seeds = []
    for (a, ra), (b, rb) in zip(ordered, ordered[1:]):
        seeds.extend(circle_pair(a, ra, b, rb))
    try:
        seeds.append(tuple(reader.locate(known)))
    except ValueError:
        pass
    seeds.append((sum(c[0] for c, _ in known) / len(known),
                  sum(c[1] for c, _ in known) / len(known)))
    scored, points = [], []
    for seed in seeds:
        point, misfit = _pattern_search(seed, known)
        if any(math.dist(point, other) < 3.0 for other in points):
            continue
        points.append(point)
        scored.append(_score(point, inside=inside, road=road, blocked=blocked,
                             last=last, misfit=misfit))
    if not scored:
        raise ValueError("这几组距离解不出位置，请重读一次屏幕。")
    scored.sort(key=lambda item: item.score)
    return scored


def resolve(pairs, stations, *, inside=None, road=None, blocked=None, last=None):
    """Best position plus a sentence explaining how sure we are."""
    scored = candidates(pairs, stations, inside=inside, road=road, blocked=blocked, last=last)
    best = scored[0]
    rival = scored[1] if len(scored) > 1 else None
    note = ""
    if rival is not None:
        gap = rival.score - best.score
        separation = math.dist(best.point, rival.point)
        if best.usable and rival.usable and gap < 12.0:
            if separation <= 120.0:
                note = (f"两组距离的镜像解只差 {separation:.0f} 米，已取离路更近的一处；"
                        "如果「起」标记不在你脚下，直接在地图上点一下覆盖。")
            else:
                note = (f"还有一个同样对得上距离的候选在 ({rival.point[0]:.0f}, {rival.point[1]:.0f})，"
                        "已按「在校内、离路近」取了这一处；如果明显不对，在地图上点一下覆盖即可。")
        elif not best.usable and best.blocked:
            note = "解出的位置落在%s里，请在地图上点选真实起点。" % best.blocked
    if not note and best.error > 60:
        note = (f"路网里这几个打卡点只有近似位置，距离对不上 {best.error:.0f} 米，"
                "算出的起点可能偏几十米，请在地图上核对「起」标记。")
    return Fix(best.point, f"{len(pairs)} 组距离", best.error, note,
               rival.point if rival else None, scored)


def matches(pairs, stations):
    """How many listed names map onto known map positions."""
    return sum(1 for name, _ in pairs if name in stations)


def read_and_resolve(labels, stations, *, inside=None, road=None, blocked=None, last=None, screen=None):
    pairs = distances_from_screen(labels, screen=screen)
    fix = resolve(pairs, stations, inside=inside, road=road, blocked=blocked, last=last)
    fix.method = f"{len(pairs)} 个打卡点的距离"
    fix.note = (fix.note + " " if fix.note else "") + "读数：" + "、".join(
        f"{reader.flatten(name)} {metres:.0f} 米" for name, metres in pairs)
    return fix


def main() -> int:
    import json

    here = Path(__file__).resolve().parent
    data = json.loads((here / "campus.json").read_text(encoding="utf-8"))
    stations = {name: tuple(point) for name, point in data["labels"]}
    screen = Path(sys.argv[1]).read_bytes() if len(sys.argv) > 1 else None
    try:
        fix = read_and_resolve(stations, stations, screen=screen)
    except Exception as error:
        print("读不到起点：", error)
        return 1
    print("位置", tuple(round(value, 1) for value in fix.point), "方式", fix.method)
    for candidate in fix.candidates:
        print("  候选", tuple(round(value, 1) for value in candidate.point),
              "分", round(candidate.score, 1), "校内" if candidate.inside else "校外",
              "离路", round(candidate.road, 1), candidate.blocked or "")
    print("说明", fix.note)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())