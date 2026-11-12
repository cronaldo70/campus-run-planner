"""Headless smoke test: does the planner build a plan with the new realism line?"""

import json
import sys
import tkinter as tk
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "outputs" / "run-planner"
sys.path.insert(0, str(OUT))

import run_planner  # noqa: E402

data = json.loads((OUT / "campus_map.json").read_text(encoding="utf-8"))
root = tk.Tk()
root.withdraw()
planner = run_planner.Planner(root, data)
labels = {name: point for name, point in data["labels"]}
for key, name in (("start", "笃行北楼"), ("a", "文典阁"), ("b", "磬苑广场")):
    point = labels[name]
    planner.points[key] = (point, planner.network.nearest(point))
planner.target.set("6:00")
planner.refresh()
root.update_idletasks()
print(planner.plan_text)
print("---")
print("status:", planner.result.cget("text"))
print("metrics:", [item.cget("text") for item in planner.metrics])
print("start button:", planner.start_button.cget("state"))
root.destroy()