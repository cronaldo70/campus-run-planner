"""无头验收：屏幕上两个打卡点都不认识时，GUI 读完要自己补测距并把点位填进列表。

跑法：work\\.venv\\Scripts\\python.exe -B work\\test_gui_range.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLANNER = ROOT / "outputs" / "run-planner"
sys.path.insert(0, str(PLANNER))

import tkinter as tk  # noqa: E402

import checkpoint_reader as reader  # noqa: E402
import locate_checkpoints as ranging  # noqa: E402
import run_planner  # noqa: E402

FAKE_REPORT = {
    "checkpoints": [],
    "others": [
        {"ocr": "文典阁西门", "metres": 379.0},
        {"ocr": "体育馆大门", "metres": 503.0},
    ],
    "position": None,
    "position_error": 0.0,
    "warnings": ["屏幕上还有 2 个名字不在校园地图里：文典阁西门、体育馆大门"],
    "text": "体育馆大门 (距你 503 米) 未打卡 文典阁西门 已打卡",
    "running": True,
}

SOLVED = {
    "文典阁西门": {"point": (-187.7, -29.0), "samples": 3, "error": 0.4},
    "体育馆大门": {"point": (109.0, 867.0), "samples": 3, "error": 1.2},
}

state = {"done": False}


def main() -> int:
    reader.read_screen = lambda labels, screen=None: json.loads(json.dumps(FAKE_REPORT))
    ranging.locate_all = lambda data, network, labels, **kw: json.loads(json.dumps(SOLVED))

    data = json.loads((PLANNER / "campus_map.json").read_text(encoding="utf-8"))
    root = tk.Tk()
    root.withdraw()
    planner = run_planner.Planner(root, data)

    def poll():
        if planner.reading:
            root.after(80, poll)
            return
        state["done"] = True
        print("via:", planner.via_names)
        print("start:", planner.points.get("start", ("-",))[0])
        print("status:", planner.result.cget("text"))
        print("plan:", str(planner.plan_text).strip().splitlines()[:3])
        print("metrics:", [label.cget("text") for label in planner.metrics])
        print("button:", planner.read_button.cget("state"))
        root.quit()

    def watchdog():
        if not state["done"]:
            print("FAIL 读取在 15 秒内没有结束")
            root.quit()

    root.after(50, planner.read_from_phone)
    root.after(80, poll)
    root.after(15000, watchdog)
    root.mainloop()

    ok = (state["done"] and len(planner.via_names) == 2 and "start" in planner.points
          and str(planner.read_button.cget("state")) == "normal")
    root.destroy()
    print("OK" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())