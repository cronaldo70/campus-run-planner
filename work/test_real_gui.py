"""Headless check of the real-run planner: auto start + simulation window."""

import json
import sys
import tkinter as tk
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "outputs" / "real-run-planner"
sys.path.insert(0, str(HERE))

import real_position  # noqa: E402
import real_run as runner  # noqa: E402
import real_run_sim as bridge  # noqa: E402


def main():
    data = json.loads((HERE / "campus.json").read_text(encoding="utf-8"))
    root = tk.Tk()
    root.withdraw()
    planner = runner.Planner(root, data)
    root.update()

    stations = {name: tuple(point) for name, point in data["labels"]}
    truth = (-134.3, -295.8)
    pairs = sorted(((name, __import__("math").dist(truth, point)) for name, point in stations.items()),
                   key=lambda item: item[1])[:2]
    fix = real_position.resolve(pairs, stations, inside=planner.site.inside, road=planner.site.road,
                                blocked=planner.site.blocked)
    planner.apply_position_fix(fix)
    root.update()
    print("auto start:", planner.points.get(0), "status:", planner.phone_status.cget("text")[:90])

    planner.checkpoints = [("文典阁西门", stations["文典阁西门"]), ("篮球场南门", stations["篮球场南门"])]
    planner.apply_phone_result(planner.checkpoints)
    root.update()
    print("route ready:", planner.route_ready, "distance:", planner.distance.cget("text"))
    print("sim button:", planner.sim_button.cget("state"))
    print("status:", planner.status.cget("text").replace("\n", " | ")[:160])

    planner.start_sim()
    root.update()
    window = planner.sim_window
    print("sim window:", "open" if window is not None else "missing",
          "title:", window.title() if window else "")
    labels = [child.cget("text") for child in window.winfo_children()
              if child.winfo_class() == "Label"] if window else []
    print("window labels:", labels[:4])
    if window:
        window.destroy()
        planner.sim_window = None
    root.destroy()
    print("OK")


if __name__ == "__main__":
    main()