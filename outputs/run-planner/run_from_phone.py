"""从手机屏幕读出打卡点，直接排一条不绕圈路线并回放。

先在手机步道乐跑里点「开始乐跑」，等地图上的打卡点列表出现，再运行本脚本。

    python run_from_phone.py                    # 等打卡点出现 -> 规划 -> 按真实配速回放
    python run_from_phone.py --dry-run           # 只读+规划，不碰定位
    python run_from_phone.py --shot shot.png     # 用已有截图，不连设备
    python run_from_phone.py --minimum 3 --pace 5:50
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import auto_route  # noqa: E402
import checkpoint_reader as reader  # noqa: E402
import location_sim as sim  # noqa: E402
import road_network  # noqa: E402

MAP = HERE / "campus_map.json"
GENERATED = HERE / "generated"


def parse_pace(text: str) -> float:
    minutes, _, seconds = text.replace("：", ":").partition(":")
    return int(minutes) * 60 + (int(seconds) if seconds else 0)


def label_table() -> dict:
    data = json.loads(MAP.read_text(encoding="utf-8"))
    return {name: tuple(point) for name, point in data["labels"]}


def wait_for_checkpoints(labels: dict, *, wait: float, every: float = 2.5) -> dict:
    """Wait until the app lists checkpoints, without caring whether the run started."""
    from phone_screen import capture_usb_screen  # noqa: F401  (early failure if missing)

    deadline = time.time() + wait
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        try:
            report = reader.read_screen(labels)
        except Exception as error:  # no device, tunnel busy, wrong screen
            print(f"[{attempt}] 截图失败：{error}")
            time.sleep(every)
            continue
        found = report.get("checkpoints") or []
        others = report.get("others") or []
        print(f"[{attempt}] 认出 {len(found) + len(others)} 个打卡点："
              + "、".join(f"{item['name']} {item['metres']:.0f} 米" for item in found)
              + "".join(f"、{item['ocr']} {item['metres']:.0f} 米" for item in others))
        if found or others:
            return report
        time.sleep(every)
    raise SystemExit("等待超时：先在手机上点「开始乐跑」，让打卡点列表出现在屏幕上，再重跑本脚本。")


def wait_for_start(labels: dict, *, wait: float, every: float = 2.5) -> None:
    """Hold until the「开始乐跑」button is gone, i.e. the app is recording."""
    deadline = time.time() + wait
    said = False
    while time.time() < deadline:
        try:
            report = reader.read_screen(labels)
        except Exception as error:
            print(f"  截图失败：{error}")
            time.sleep(every)
            continue
        if report.get("running"):
            print("检测到跑步已开始，接管定位。")
            return
        if not said:
            print("路线已准备好：在手机上点「开始乐跑」，我立刻开始按这条线跑。")
            said = True
        time.sleep(every)
    raise SystemExit("等不到「开始乐跑」：点一下它再来，或者用 --dry-run 只看规划。")


def punch_gaps(points, checkpoints, network) -> list[tuple[str, float, float, float]]:
    """Distance from the track to each checkpoint's pavement access point."""
    track = [sim.to_map(lat, lon) for lat, lon, _ in points]
    out = []
    for item in checkpoints:
        access = network.nearest(item["point"]).point
        gap = min(math.dist(access, vertex) for vertex in track)
        out.append((item["name"], gap, item["metres"], math.dist(item["point"], access)))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--minimum", type=float, default=2.5, help="总里程下限（公里）")
    parser.add_argument("--pace", default="6:00", help="目标配速，形如 6:00")
    parser.add_argument("--minutes", type=float,
                        help="按总时长反推配速（分钟），优先于 --pace")
    parser.add_argument("--speed", type=float, default=1.0, help="回放倍速，1 为真实配速")
    parser.add_argument("--shot", type=Path, help="用离线截图代替设备")
    parser.add_argument("--wait", type=float, default=600.0, help="等打卡点出现的秒数")
    parser.add_argument("--seed", type=int, help="轨迹随机种子，换一条同长度的路线")
    parser.add_argument("--dry-run", action="store_true", help="只规划不回放")
    parser.add_argument("--range-only", action="store_true",
                        help="只做三点测距，打印打卡点坐标后退出")
    parser.add_argument("--no-range", action="store_true",
                        help="不测距，只用 campus_map 里的地标名匹配")
    parser.add_argument("--settle", type=float, default=6.0, help="每次挪位置后等 App 刷新几秒")
    args = parser.parse_args()

    labels = label_table()
    data = json.loads(MAP.read_text(encoding="utf-8"))
    network = road_network.RoadNetwork(data)

    # Step 1: what checkpoints does the app list right now?
    if args.shot:
        report = reader.read_screen(labels, args.shot.read_bytes())
    else:
        report = wait_for_checkpoints(labels, wait=args.wait)
    listed = [(item["name"], item["metres"]) for item in report.get("checkpoints") or []]
    listed += [(item["ocr"], item["metres"]) for item in report.get("others") or []]
    print("\n屏幕上的打卡点：" + "、".join(f"{name}({metres:.0f} 米)" for name, metres in listed)
          if listed else "\n屏幕上的打卡点：一个也没读到")

    # Step 2: names like 名人景观墙碑记 are not in campus_map, so range them:
    # move the simulated fix to three road points and trilaterate each pin from
    # the distances the app prints. This also gives the true punch points.
    checkpoints = []
    ranged = {}
    if not args.no_range and listed:
        import locate_checkpoints as ranging

        print("\n三点测距给每个打卡点定位（会挪动模拟位置三次，约 40 秒）…")
        try:
            ranged = ranging.locate_all(data, network, labels, settle=args.settle, progress=print)
        except Exception as error:
            print(f"  测距失败：{error}")
    for name, metres in listed:
        key = next((cand for cand in ranged if cand and (cand in name or name in cand)), None)
        if key:
            checkpoints.append({"name": key, "point": tuple(ranged[key]["point"]), "metres": metres})
            continue
        matched = reader.match([name], labels)
        if matched:
            label = next(iter(matched.values()))
            checkpoints.append({"name": label, "point": labels[label], "metres": metres})
    if not checkpoints:
        raise SystemExit("没读到可用的打卡点。确认 App 停在打卡点列表页，再重跑本脚本。")
    print("用于规划的打卡点：" + "、".join(f"{item['name']}" for item in checkpoints))

    if args.range_only:
        for item in checkpoints:
            print(f"  {item['name']:<14} ({item['point'][0]:.1f}, {item['point'][1]:.1f})")
        return

    # Step 3: where to start. Ranging left the fix on the last vantage point, so
    # walk it onto the pavement next to the closest checkpoint: the run then opens
    # at a punch instead of teleporting from a stranded spot.
    position = report.get("position")
    if ranged:
        anchor = checkpoints[0]["point"]
        position = network.nearest(anchor).point
        if not args.dry_run and not args.shot:
            sim.hold(position, seconds=3)
        print(f"起点放在第一个打卡点旁边的路上：({position[0]:.1f}, {position[1]:.1f})")
    if not position:
        anchor = checkpoints[0]["point"]
        position = network.nearest(anchor).point
        print(f"解不出精确位置，起点改放在打卡点旁边的路上：({position[0]:.1f}, {position[1]:.1f})")
    result = auto_route.plan(network, position, [item["point"] for item in checkpoints],
                             minimum=args.minimum * 1000.0, seed=args.seed)
    print("\n" + auto_route.describe(network, position, [item["point"] for item in checkpoints],
                                    result, [item["name"] for item in checkpoints]))

    pace = parse_pace(args.pace)
    if args.minutes:
        kilometres = result["metres"] / 1000.0
        pace = args.minutes * 60.0 / kilometres
        print(f"路线 {kilometres:.2f} 公里，按 {args.minutes:.0f} 分钟完成 → 配速 "
              f"{int(pace // 60)}:{int(pace % 60):02d}")
        if not 3 * 60 <= pace <= 10 * 60:
            print(f"  ⚠ 配速 {pace / 60:.2f} 分/公里超出多数校园跑的有效区间（3:00–10:00）")
    points = sim.build_track(result["route"], pace=pace, laps=1, loop=False, seed=args.seed)
    stats = sim.track_stats(points)
    print(f"轨迹 {len(points)} 点 · {stats['meters'] / 1000:.3f} 公里 · "
          f"{stats['seconds'] / 60:.1f} 分钟 · 分段 "
          f"{min(stats['splits']):.0f}–{max(stats['splits']):.0f} 秒/公里")

    for name, gap, seen, offset in punch_gaps(points, checkpoints, network):
        flag = "✓" if gap <= reader.PUNCH_RADIUS else "!"
        extra = f"，图上位置离路 {offset:.0f} 米" if offset > 20 else ""
        print(f"  {flag} {name}：轨迹离打卡点路面 {gap:.0f} 米（屏幕上距你 {seen:.0f} 米{extra}）")

    GENERATED.mkdir(exist_ok=True)
    path = GENERATED / f"open-{datetime.now():%Y%m%d-%H%M}.gpx"
    sim.write_gpx(points, path, name="campus-open-run")
    print(f"\nGPX：{path}")
    if args.dry_run:
        print("（--dry-run，未回放）")
        return

    print(f"开始回放，倍速 {args.speed}。Ctrl+C 立即停止并恢复真实定位。")
    if not args.shot:
        wait_for_start(labels, wait=args.wait)
    sim.play(points, speed=args.speed)
    print("回放结束，模拟定位已清除。")


if __name__ == "__main__":
    main()