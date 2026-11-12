"""Turn a planned campus route into a paced GPX track and play it over USB.

The planner draws the route in local metres (see work/prepare_campus_map.py),
so this module owns the inverse projection back to WGS-84 and the pacing maths.
"""

from __future__ import annotations

import argparse
import asyncio
import math
import os
import random
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

LAT0, LON0 = 31.769, 117.179
METERS_PER_DEGREE = 111195.0
X_FACTOR = METERS_PER_DEGREE * math.cos(math.radians(LAT0))

Point = tuple[float, float]


def to_wgs84(point: Point) -> tuple[float, float]:
    """Local map metres -> (lat, lon)."""
    x, y = point
    return LAT0 + y / METERS_PER_DEGREE, LON0 + x / X_FACTOR


def to_map(latitude: float, longitude: float) -> Point:
    return (longitude - LON0) * X_FACTOR, (latitude - LAT0) * METERS_PER_DEGREE


TAU = math.tau
# Corner radius used when a right-angle turn is rounded off, in metres.
CORNER_RADIUS = 16.0
# Peak sideways deviation of the pseudo-GPS wobble, in metres.
WOBBLE = 2.0


def path_length(route: list[Point]) -> float:
    return sum(math.dist(a, b) for a, b in zip(route, route[1:]))


def cumulative(route: list[Point]) -> list[float]:
    """Distance travelled at every vertex, starting at zero."""
    out = [0.0]
    for a, b in zip(route, route[1:]):
        out.append(out[-1] + math.dist(a, b))
    return out


def _unit(vector: Point) -> Point:
    length = math.hypot(vector[0], vector[1])
    if length == 0:
        return (0.0, 0.0)
    return vector[0] / length, vector[1] / length


def round_corners(route: list[Point], *, radius: float = CORNER_RADIUS, step: float = 1.0) -> list[Point]:
    """Replace each sharp vertex with a quadratic fillet, like a runner cutting in.

    Straight legs stay straight; only corners bend, and the bend never leaves the
    piece of pavement it was cut from (the fillet is tangent to both legs).
    """
    route = [point for index, point in enumerate(route) if index == 0 or math.dist(route[index - 1], point) > 1e-6]
    if len(route) < 3:
        return densify(route, step)
    out = [route[0]]
    for previous, corner, following in zip(route, route[1:-1], route[2:]):
        into = _unit((corner[0] - previous[0], corner[1] - previous[1]))
        away = _unit((following[0] - corner[0], following[1] - corner[1]))
        if into == (0.0, 0.0) or away == (0.0, 0.0):
            out.append(corner)
            continue
        # 0 for a straight leg, 1 for a full reversal.
        bend = 1.0 - (into[0] * away[0] + into[1] * away[1])
        if bend < 0.01:  # a hair under 10 degrees: leave it alone
            out.append(corner)
            continue
        cut = min(radius, 0.45 * math.dist(previous, corner), 0.45 * math.dist(corner, following))
        start = (corner[0] - into[0] * cut, corner[1] - into[1] * cut)
        end = (corner[0] + away[0] * cut, corner[1] + away[1] * cut)
        samples = max(3, int(math.ceil(2.0 * cut / max(step, 0.2))))
        for index in range(1, samples + 1):
            t = index / samples
            inverse = 1.0 - t
            out.append((
                inverse * inverse * start[0] + 2 * inverse * t * corner[0] + t * t * end[0],
                inverse * inverse * start[1] + 2 * inverse * t * corner[1] + t * t * end[1],
            ))
    out.append(route[-1])
    return [point for index, point in enumerate(out) if index == 0 or math.dist(out[index - 1], point) > 1e-9]


def wobble(points: list[Point], *, amplitude: float = WOBBLE, seed=None) -> list[Point]:
    """Push the track sideways by a smooth, GPS-like multi-scale offset.

    Three incommensurate wavelengths (about 40 m, 100 m and 260 m) add up to at
    most ``amplitude`` metres, which is what a phone in a pocket actually
    reports: never the geometric centreline, but never off the pavement either.
    """
    if len(points) < 3 or amplitude <= 0:
        return list(points)
    rng = random.Random(seed)
    waves = [(0.55, 38.0, rng.uniform(0, TAU)),
             (0.30, 97.0, rng.uniform(0, TAU)),
             (0.15, 263.0, rng.uniform(0, TAU))]
    travelled = cumulative(points)
    last = len(points) - 1
    out = []
    for index, point in enumerate(points):
        # A four-point window keeps the tangent stable on short segments.
        before = points[max(0, index - 2)]
        after = points[min(last, index + 2)]
        tangent = _unit((after[0] - before[0], after[1] - before[1]))
        if tangent == (0.0, 0.0):
            out.append(point)
            continue
        normal = (-tangent[1], tangent[0])
        shift = amplitude * sum(weight * math.sin(TAU * travelled[index] / wavelength + phase)
                                for weight, wavelength, phase in waves)
        out.append((point[0] + normal[0] * shift, point[1] + normal[1] * shift))
    return out


def thin(points: list[Point], minimum: float) -> list[Point]:
    """Drop points that sit closer together than ``minimum`` metres.

    Resampling a fillet can leave millimetre steps; those make the tangent (and
    therefore the sideways wobble) jump. The final point is kept so a loop stays
    closed.
    """
    if len(points) < 3:
        return list(points)
    out = [points[0]]
    for point in points[1:-1]:
        if math.dist(out[-1], point) >= minimum:
            out.append(point)
    if math.dist(out[-1], points[-1]) >= minimum:
        out.append(points[-1])
    else:
        out[-1] = points[-1]
    return out


def pace_profile(distances: list[float], *, pace: float, seed=None,
                 warmup: float = 22.0, variation: float = 0.075) -> list[float]:
    """Timestamps that beat like a person: a slow start, then uneven splits.

    The mean speed is normalised back to exactly ``1000 / pace``, so the average
    pace is the planned one while individual splits wander by a few percent.
    """
    base = 1000.0 / pace
    total = distances[-1] or 1.0
    rng = random.Random(seed)
    waves = [(0.60, 430.0, rng.uniform(0, TAU)),
             (0.28, 150.0, rng.uniform(0, TAU)),
             (0.12, 52.0, rng.uniform(0, TAU))]
    warm_metres = warmup * base * 1.6
    factors = []
    for distance in distances:
        factor = 1.0 + variation * sum(weight * math.sin(TAU * distance / wavelength + phase)
                                       for weight, wavelength, phase in waves)
        if warm_metres > 0 and distance < warm_metres:
            factor *= 0.76 + 0.24 * (distance / warm_metres)
        factors.append(max(0.5, factor))
    times = [0.0]
    for index in range(1, len(distances)):
        gap = distances[index] - distances[index - 1]
        times.append(times[-1] + gap / (base * 0.5 * (factors[index] + factors[index - 1])))
    if times[-1] <= 0:
        return times
    scale = (total / base) / times[-1]
    return [moment * scale for moment in times]


def densify(route: list[Point], step: float) -> list[Point]:
    """Resample a polyline so every gap is at most ``step`` metres."""
    if len(route) < 2:
        raise ValueError("路线至少需要两个点。")
    if step <= 0:
        raise ValueError("采样间距必须大于零。")
    out = [route[0]]
    for a, b in zip(route, route[1:]):
        length = math.dist(a, b)
        if length == 0:
            continue
        count = max(1, math.ceil(length / step))
        for index in range(1, count + 1):
            fraction = index / count
            out.append((a[0] + (b[0] - a[0]) * fraction, a[1] + (b[1] - a[1]) * fraction))
    return out


def build_track(route: list[Point], *, pace: float, laps: int = 1, loop: bool = True,
                step: float | None = None, start: datetime | None = None,
                human: bool = True, seed=None) -> list[tuple[float, float, datetime]]:
    """Return [(lat, lon, time)] moving at ``pace`` seconds per kilometre.

    ``laps`` repeats the route; for a loop the closing point is not duplicated so
    consecutive laps read as one continuous track. With ``human`` (the default)
    corners are rounded, a GPS-like sideways wobble is added and the timestamps
    follow an uneven pace instead of a metronome.
    """
    if pace <= 0:
        raise ValueError("配速必须大于零。")
    if laps < 1:
        raise ValueError("圈数至少为 1。")
    speed = 1000.0 / pace
    step = step if step is not None else max(1.0, speed * 0.8)
    body = round_corners(route, radius=CORNER_RADIUS, step=min(step, 1.0)) if human else densify(route, step)
    closed = math.dist(body[0], body[-1]) < 0.5
    if loop and closed:
        body = body[:-1]
    track: list[Point] = []
    for lap in range(laps):
        # An open route alternates direction so it finishes back at its endpoint.
        segment = body if loop or lap % 2 == 0 else list(reversed(body))
        if not track:
            track.extend(segment)
        elif math.dist(track[-1], segment[0]) < 1e-6:
            track.extend(segment[1:])
        else:
            track.extend(segment)
    if len(track) < 2:
        raise ValueError("路线太短，无法生成轨迹。")
    track = thin(densify(track, step), step * 0.6)
    if human:
        track = wobble(track, amplitude=WOBBLE, seed=seed)
    distances = cumulative(track)
    moments = pace_profile(distances, pace=pace, seed=seed)
    start = start or datetime.now(timezone.utc)
    points = []
    for point, seconds in zip(track, moments):
        latitude, longitude = to_wgs84(point)
        points.append((latitude, longitude, start + timedelta(seconds=seconds)))
    return points


def track_stats(points: list[tuple[float, float, datetime]]) -> dict:
    """Distance, duration and the fast/slow ends of the resulting splits."""
    if len(points) < 2:
        return {"meters": 0.0, "seconds": 0.0, "fastest": 0.0, "slowest": 0.0, "splits": []}
    samples = [to_map(latitude, longitude) for latitude, longitude, _ in points]
    distances = cumulative(samples)
    seconds = (points[-1][2] - points[0][2]).total_seconds()
    splits, window = [], 200.0
    start = 0
    for end in range(1, len(distances)):
        while distances[end] - distances[start] > window:
            start += 1
        span = distances[end] - distances[start]
        elapsed = (points[end][2] - points[start][2]).total_seconds()
        if span >= window * 0.85 and elapsed > 0:
            splits.append(elapsed / span * 1000.0)
    return {
        "meters": distances[-1],
        "seconds": seconds,
        "fastest": min(splits) if splits else seconds,
        "slowest": max(splits) if splits else seconds,
        "splits": splits,
    }


def write_gpx(points: list[tuple[float, float, datetime]], path: Path, name: str = "campus-run") -> Path:
    rows = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<gpx version="1.1" creator="campus-run-planner" xmlns="http://www.topografix.com/GPX/1/1">',
        f"<trk><name>{name}</name><trkseg>",
    ]
    for latitude, longitude, moment in points:
        stamp = moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        rows.append(f'<trkpt lat="{latitude:.7f}" lon="{longitude:.7f}"><time>{stamp}</time></trkpt>')
    rows.append("</trkseg></trk></gpx>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return path


async def _single_device() -> str:
    """Import lazily so the offline planner never needs pymobiledevice3."""
    from pymobiledevice3 import usbmux

    devices = [device for device in await usbmux.list_devices() if device.is_usb]
    if len(devices) != 1:
        raise RuntimeError("请只连接并解锁一台 iPhone，再开始模拟跑。")
    return devices[0].serial


async def _play(points, stop: threading.Event | None, on_progress=None, speed: float = 1.0) -> None:
    from pymobiledevice3.remote.userspace_tunnel import UserspaceRsdTunnel
    from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider
    from pymobiledevice3.services.dvt.instruments.location_simulation import LocationSimulation

    serial = await _single_device()
    first = points[0][2]
    async with (
        UserspaceRsdTunnel(serial=serial) as rsd,
        DvtProvider(rsd) as dvt,
        LocationSimulation(dvt) as location,
    ):
        try:
            await location.set(points[0][0], points[0][1])
            for index, (latitude, longitude, moment) in enumerate(points):
                if index:
                    delay = (moment - points[index - 1][2]).total_seconds() / speed
                    slept = 0.0
                    while slept < delay:
                        if stop is not None and stop.is_set():
                            raise asyncio.CancelledError
                        chunk = min(0.25, delay - slept)
                        await asyncio.sleep(chunk)
                        slept += chunk
                if stop is not None and stop.is_set():
                    raise asyncio.CancelledError
                await location.set(latitude, longitude)
                if on_progress:
                    on_progress(index + 1, len(points))
            # Hold the last fix briefly so the app commits it, then restore.
            await asyncio.sleep(2)
        except asyncio.CancelledError:
            raise
        finally:
            async with asyncio.timeout(6):
                await location.service.invoke("stopLocationSimulation", expects_reply=True)
            await asyncio.sleep(3)


def play(points, stop: threading.Event | None = None, on_progress=None, speed: float | None = None) -> None:
    """Replay the track. speed=None uses RUN_PLANNER_SPEED (default 1 = real pace)."""
    if speed is None:
        try:
            speed = float(os.environ.get("RUN_PLANNER_SPEED", "1"))
        except ValueError:
            speed = 1.0
    asyncio.run(_play(points, stop, on_progress, max(0.1, speed)))


async def _hold(point: Point, seconds: float) -> None:
    from pymobiledevice3.remote.userspace_tunnel import UserspaceRsdTunnel
    from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider
    from pymobiledevice3.services.dvt.instruments.location_simulation import LocationSimulation

    serial = await _single_device()
    latitude, longitude = to_wgs84(point)
    async with (
        UserspaceRsdTunnel(serial=serial) as rsd,
        DvtProvider(rsd) as dvt,
        LocationSimulation(dvt) as location,
    ):
        await location.set(latitude, longitude)
        # The app needs a moment to re-read the fix and reprint the distances.
        await asyncio.sleep(max(1.0, seconds))


def hold(point: Point, seconds: float = 4.5) -> None:
    """Put the simulated fix at one map point and leave it there.

    The fix survives the connection closing, which is what the checkpoint
    ranging needs: move, read the app, move again.
    """
    asyncio.run(_hold(point, seconds))


def stop_simulation() -> None:
    """Ask the device to drop the simulation, waiting for its reply (phased clear)."""
    from pymobiledevice3.remote.userspace_tunnel import UserspaceRsdTunnel
    from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider
    from pymobiledevice3.services.dvt.instruments.location_simulation import LocationSimulation

    async def worker() -> None:
        serial = await _single_device()
        async with (
            UserspaceRsdTunnel(serial=serial) as rsd,
            DvtProvider(rsd) as dvt,
            LocationSimulation(dvt) as location,
        ):
            async with asyncio.timeout(6):
                await location.service.invoke("stopLocationSimulation", expects_reply=True)
            await asyncio.sleep(3)

    asyncio.run(worker())


def read_gpx(path) -> list:
    """Read a track written by write_gpx (trkpt lat/lon + UTC time)."""
    import re
    from datetime import datetime

    text = Path(path).read_text(encoding="utf-8")
    points = []
    for match in re.finditer(
        r'<trkpt lat="([-0-9.]+)" lon="([-0-9.]+)">\s*<time>([^<]+)</time>', text
    ):
        moment = datetime.fromisoformat(match[3].replace("Z", "+00:00"))
        points.append((float(match[1]), float(match[2]), moment))
    if not points:
        raise ValueError(f"{path} 里没有带时间戳的 trkpt。")
    return points


def main() -> None:
    parser = argparse.ArgumentParser(description="Play a planned campus route as a paced GPX track.")
    parser.add_argument("--route", help="planner route: x,y;x,y;... in map metres")
    parser.add_argument("--play-gpx", type=Path, help="replay an existing GPX instead of building one")
    parser.add_argument("--pace", type=float, default=240.0, help="seconds per kilometre, default 240")
    parser.add_argument("--laps", type=int, default=1)
    parser.add_argument("--open", action="store_true", help="route is not a closed loop")
    parser.add_argument("--speed", type=float, default=1.0, help="playback speed multiplier, e.g. 10 for a rehearsal")
    parser.add_argument("--gpx", type=Path, default=None, help="where to write the track")
    parser.add_argument("--offline", action="store_true", help="only write the GPX, do not touch the device")
    args = parser.parse_args()

    if args.play_gpx:
        points = read_gpx(args.play_gpx)
        print(f"{len(points)} track points from {args.play_gpx}", flush=True)
    else:
        if not args.route:
            parser.error("需要 --route 'x,y;x,y' 或 --play-gpx FILE")
        route = [tuple(float(value) for value in pair.split(",")) for pair in args.route.split(";") if pair.strip()]
        points = build_track(route, pace=args.pace, laps=args.laps, loop=not args.open)
        target = args.gpx or Path(__file__).with_name("last_route.gpx")
        write_gpx(points, target)
        print(f"{len(points)} track points, {path_length(route) * args.laps / 1000:.3f} km -> {target}")
    if not args.offline:
        play(points, speed=args.speed, on_progress=lambda done, total: print(f"{done}/{total}", flush=True))


if __name__ == "__main__":
    if len(sys.argv) == 1:
        parser_hint = ("usage: python location_sim.py --route 'x,y;x,y' [--pace 240] [--laps 5]\n"
                       "       python location_sim.py --play-gpx generated\\route-YYYYMMDD-HHMM.gpx [--speed 10]")
        sys.exit(parser_hint)
    main()
