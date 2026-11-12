"""给「不认识的打卡点」定位：挪动模拟位置，用 App 报的距离做三点测距。

步道乐跑里的打卡点名字（名人景观墙碑记、篮球场南门……）比 campus_map.json
里的 13 个地标细得多，靠名字匹配永远会漏。但 App 每一行都写着「距你 N 米」，
而这些距离就是当前模拟位置到打卡点的直线距离——把模拟位置依次放到三个已知
路点上，同一个打卡点的三条距离相交处，就是它自己的坐标。

    python locate_checkpoints.py                 # 现场测三个点，打印结果
    python locate_checkpoints.py --settle 6      # App 刷新慢时多等一会
    python locate_checkpoints.py --out ck.json   # 同时写文件，供别的脚本用
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import checkpoint_reader as reader  # noqa: E402
import location_sim as sim  # noqa: E402
import road_network  # noqa: E402

MAP = HERE / "campus_map.json"
GENERATED = HERE / "generated"

# Beyond this the printed integer metres are too coarse to help much.
MAX_RANGE = 1600.0
MIN_RANGE = 15.0


def load_map() -> dict:
    return json.loads(MAP.read_text(encoding="utf-8"))


def label_table(data: dict) -> dict:
    return {name: tuple(point) for name, point in data["labels"]}


def vantage_points(data: dict, network) -> list[tuple[float, float]]:
    """Three road points spread across the campus, so the circles cross sharply.

    The network carries a few arterial roads that run kilometres off campus, so
    the spread comes from the published bounds, not from the node extremes.
    """
    low_x, low_y, high_x, high_y = data["bounds"]
    span_x, span_y = high_x - low_x, high_y - low_y
    wanted = [
        (low_x + 0.25 * span_x, low_y + 0.20 * span_y),
        (high_x - 0.22 * span_x, low_y + 0.26 * span_y),
        (low_x + 0.48 * span_x, high_y - 0.16 * span_y),
    ]
    picked, seen = [], set()
    for point in wanted:
        snapped = network.nearest(point).point
        key = (round(snapped[0], 1), round(snapped[1], 1))
        if key in seen:
            continue
        seen.add(key)
        picked.append(snapped)
    return picked


def read_once(labels: dict, *, attempt: str) -> list[tuple[str, float]]:
    """One screenshot, parsed into (name, metres) pairs — names may be unknown."""
    report = reader.read_screen(labels, None)
    pairs = [(item["ocr"] or item["name"], item["metres"]) for item in report["checkpoints"]]
    pairs += [(item["ocr"], item["metres"]) for item in report.get("others") or []]
    print(f"  {attempt}: " + "、".join(f"{name} {metres:.0f} 米" for name, metres in pairs))
    return pairs


def harvest(data: dict, labels: dict, network, *, settle: float, dry_run: bool,
            say=None) -> dict:
    """Move the fix around and collect distance readings per checkpoint name."""
    tell = say or print
    readings: dict[str, list[tuple[tuple[float, float], float]]] = {}
    for index, vantage in enumerate(vantage_points(data, network), start=1):
        tell(f"[{index}] 把模拟位置放到 ({vantage[0]:.0f}, {vantage[1]:.0f})")
        if not dry_run:
            sim.hold(vantage, seconds=settle)
        else:
            time.sleep(0.2)
        try:
            pairs = read_once(labels, attempt=f"第 {index} 个点")
        except Exception as error:
            tell(f"  截图失败：{error}")
            continue
        for name, metres in pairs:
            if MIN_RANGE <= metres <= MAX_RANGE:
                readings.setdefault(name, []).append((vantage, metres))
    return readings


def solve(readings: dict) -> dict:
    """Trilaterate every name that got at least two readings."""
    solved = {}
    for name, observations in readings.items():
        if len(observations) < 2:
            continue
        try:
            point = reader.locate(observations)
        except Exception as error:
            print(f"  {name}: 解不出来（{error}）")
            continue
        residuals = [abs(math.dist(point, centre) - metres) for centre, metres in observations]
        solved[name] = {
            "point": point,
            "samples": len(observations),
            "error": max(residuals),
            "residuals": [round(value, 1) for value in residuals],
        }
    return solved


def clean_name(name: str) -> str:
    """Drop the empty brackets OCR leaves where the distance used to be."""
    name = re.sub(r"[（(][^）)]*[）)]?$", "", name.strip())
    name = re.sub(r"[（(）)]", "", name)
    return name.strip()


def locate_all(data: dict, network, labels: dict, *, settle: float = 6.0,
               progress=None) -> dict:
    """Range every checkpoint the app lists; returns {name: {point, error, samples}}."""
    say = progress or (lambda message: None)
    readings = harvest(data, labels, network, settle=settle, dry_run=False, say=say)
    solved = {}
    for name, item in solve(readings).items():
        key = clean_name(name)
        if key:
            solved[key] = item
    say(f"测到 {len(solved)} 个打卡点的坐标")
    return solved


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--settle", type=float, default=5.0, help="每次挪位置后等 App 刷新几秒")
    parser.add_argument("--out", type=Path, help="把结果写成 JSON")
    parser.add_argument("--dry-run", action="store_true", help="不碰定位，只看当前屏幕")
    args = parser.parse_args()

    data = load_map()
    network = road_network.RoadNetwork(data)
    labels = label_table(data)
    print("截图 + 解析（名字不认识也没关系，只用距离）")
    readings = harvest(data, labels, network, settle=args.settle, dry_run=args.dry_run)
    solved = solve(readings)

    print("\n定位结果：")
    if not solved:
        print("  没有拿到两个以上的距离，检查手机是否停在打卡点列表页。")
    for name, item in solved.items():
        access = network.nearest(item["point"]).point
        gap = math.dist(item["point"], access)
        flag = "✓" if gap < 40 else "?"
        print(f"  {flag} {name:<16} ({item['point'][0]:>7.1f}, {item['point'][1]:>7.1f})  "
              f"{item['samples']} 条距离 · 残差 {item['error']:.0f} 米 · 离路 {gap:.0f} 米")

    if args.out:
        GENERATED.mkdir(exist_ok=True)
        payload = {
            "created": datetime.now().isoformat(timespec="seconds"),
            "checkpoints": {name: {"point": list(item["point"]), "error": item["error"]}
                            for name, item in solved.items()},
        }
        args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n已写入 {args.out}")


if __name__ == "__main__":
    main()