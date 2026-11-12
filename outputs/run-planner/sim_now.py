"""One-shot replay: newest planned GPX -> iPhone, Ctrl+C restores real GPS.

    python sim_now.py                 # newest generated\\*.gpx at real pace
    python sim_now.py --speed 10      # rehearsal
    python sim_now.py --gpx path.gpx
"""

from __future__ import annotations

import argparse
import math
import signal
import sys
import threading
from pathlib import Path

import location_sim as sim

HERE = Path(__file__).resolve().parent


def newest_track() -> Path:
    tracks = sorted((HERE / "generated").glob("*.gpx"), key=lambda item: item.stat().st_mtime)
    if not tracks:
        raise SystemExit("generated\\ 里还没有 GPX。先在规划器点「只导出 GPX」或「开始模拟跑」。")
    return tracks[-1]


def meters(points) -> list[float]:
    total = [0.0]
    for (lat1, lon1, _), (lat2, lon2, _) in zip(points, points[1:]):
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
        total.append(total[-1] + 2 * 6371000 * math.asin(math.sqrt(a)))
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay a planned track on the USB iPhone.")
    parser.add_argument("--gpx", type=Path, default=None)
    parser.add_argument("--speed", type=float, default=None, help="playback multiplier, default real pace")
    args = parser.parse_args()

    path = args.gpx or newest_track()
    points = sim.read_gpx(path)
    travelled = meters(points)
    span = (points[-1][2] - points[0][2]).total_seconds()
    print(f"轨迹 {path.name}: {len(points)} 点，{travelled[-1] / 1000:.3f} 公里，"
          f"名义时长 {int(span // 60)} 分 {int(span % 60):02d} 秒", flush=True)
    print("Ctrl+C 停止并恢复真实定位。", flush=True)

    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())

    def report(done: int, total: int) -> None:
        if done == 1 or done % 25 == 0 or done == total:
            print(f"  {done}/{total}  {travelled[done - 1] / 1000:.3f} 公里", flush=True)

    try:
        sim.play(points, stop=stop, speed=args.speed, on_progress=report)
        print("回放结束，已发送停止请求。在苹果地图点「我的位置」核对蓝点。", flush=True)
    except BaseException as error:  # noqa: BLE001
        if stop.is_set():
            print("已手动停止，设备已收到停止请求。", flush=True)
        else:
            print(f"回放中断：{type(error).__name__}: {error}", flush=True)
            sys.exit(1)


if __name__ == "__main__":
    main()