"""Drive the real GUI flow: 开始模拟跑 -> 100% -> 恢复定位, then the manual stop path."""

import json
import os
import sys
import time
import tkinter as tk
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import run_planner  # noqa: E402


def find(widget, text, cls=tk.Button):
    for child in widget.winfo_children():
        if isinstance(child, cls) and child.cget("text") == text:
            return child
        found = find(child, text, cls)
        if found is not None:
            return found
    return None


def labels(widget, acc=None):
    acc = [] if acc is None else acc
    for child in widget.winfo_children():
        if isinstance(child, tk.Label):
            acc.append((child, child.cget("text")))
        labels(child, acc)
    return acc


def pump(root, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        root.update()
        time.sleep(0.05)


def status_of(window):
    try:
        return window.winfo_children()[3].cget("text")
    except Exception:
        return ""


def wait_for(root, window, needle, timeout):
    end = time.monotonic() + timeout
    seen = ""
    while time.monotonic() < end:
        root.update()
        texts = [text for _, text in labels(window)]
        for text in texts:
            if needle in text:
                return text
        status = [text for text in texts if "模拟跑" in text or "已" in text or "轨迹" in text]
        seen = " | ".join(status[-2:])
        time.sleep(0.1)
    return f"TIMEOUT (last: {seen})"


def main():
    data = json.loads((HERE / "campus_map.json").read_text(encoding="utf-8"))
    root = tk.Tk()
    root.withdraw()
    planner = run_planner.Planner(root, data)
    net = planner.network
    for key, point in (("start", (-150.0, -41.0)), ("a", (-160.0, -41.0)), ("b", (-97.0, 150.0))):
        planner.points[key] = (point, net.nearest(point))
    planner.target.set("6:00")
    planner.refresh()
    root.update()

    # ---- run 1: full simulated run at 20x ----
    os.environ["RUN_PLANNER_SPEED"] = "20"
    planner.start_run()
    root.update()
    window = [child for child in root.winfo_children() if isinstance(child, tk.Toplevel)][-1]
    print("window:", window.title())
    print("plan:", " ".join(t for _, t in labels(window) if "计划" in t or "公里" in t)[:180])
    find(window, "开始模拟跑").invoke()
    print("after start:", wait_for(root, window, "正在连接", 5))
    print("progress:", wait_for(root, window, "模拟跑进行中", 15))
    print("finish:", wait_for(root, window, "结束", 400))
    bar = [c for c in labels(window) if False]
    window.destroy()
    pump(root, 1.0)

    # ---- run 2: manual stop path (slow replay, stop after 8 s) ----
    os.environ["RUN_PLANNER_SPEED"] = "0.5"
    planner.start_run()
    root.update()
    window = [child for child in root.winfo_children() if isinstance(child, tk.Toplevel)][-1]
    find(window, "开始模拟跑").invoke()
    print("run2 progress:", wait_for(root, window, "模拟跑进行中", 20))
    find(window, "停止模拟并恢复定位").invoke()
    print("run2 stop:", wait_for(root, window, "已手动停止", 60))
    window.destroy()
    root.update()
    root.destroy()


if __name__ == "__main__":
    main()