"""Open the planner with the 实跑 window on screen, for visual checks."""

import json
import sys
import time
import tkinter as tk
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import run_planner  # noqa: E402


def main():
    data = json.loads((HERE / "campus_map.json").read_text(encoding="utf-8"))
    root = tk.Tk()
    planner = run_planner.Planner(root, data)
    net = planner.network
    for key, point in (("start", (-150.0, -41.0)), ("a", (-160.0, -41.0)), ("b", (-97.0, 150.0))):
        planner.points[key] = (point, net.nearest(point))
    planner.target.set("4:00")
    planner.minimum.set("2.5")
    planner.refresh()
    root.update()
    planner.start_run()
    root.update()
    deadline = time.monotonic() + float(sys.argv[1] if len(sys.argv) > 1 else 25)
    while time.monotonic() < deadline:
        root.update()
        time.sleep(0.05)
    root.destroy()


if __name__ == "__main__":
    main()