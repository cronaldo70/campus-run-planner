"""Headless wiring test: Planner -> GPX -> (optionally) device playback."""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import tkinter as tk  # noqa: E402

import run_planner  # noqa: E402


def main():
    data = json.loads((HERE / "campus_map.json").read_text(encoding="utf-8"))
    root = tk.Tk()
    root.withdraw()
    planner = run_planner.Planner(root, data)

    net = planner.network
    for key, point in (("start", (-150.0, -41.0)), ("a", (-160.0, -41.0)), ("b", (-97.0, 150.0))):
        planner.points[key] = (point, net.nearest(point))
    planner.loop.set(True)
    planner.minimum.set("3")
    planner.target.set("6:00")
    planner.refresh()
    root.update_idletasks()

    print("plan_text:", planner.plan_text.replace("\n", " | "))
    print("passes:", planner.passes, "base_km:", round(planner.base_km, 3))

    points = planner.build_track()
    path = planner.save_track(points)
    print("points:", len(points), "first:", points[0], "last:", points[-1])
    print("gpx:", path, path.stat().st_size, "bytes")

    speed = sys.argv[1] if len(sys.argv) > 1 else None
    if speed:
        import location_sim as sim
        sim.play(points, speed=float(speed), on_progress=lambda d, t: None if d % 400 else print(" sent", d, "/", t))
        print("playback done")
    root.destroy()


if __name__ == "__main__":
    main()