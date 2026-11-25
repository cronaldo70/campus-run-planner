"""Regression: the app's own checkpoint names and the blue-dot label.

Both were broken on 2026-11-25 and made the planner start 560 m off:

* the app calls the stadium 体育馆 and its gate 体育馆大门, which is not an OSM
  name at all — it has to be aliased to 主体育场南门;
* OCR of "体育馆大门（距你317米）" used to leave a hollow "（）" behind, which killed
  the exact match, dropped 体育馆大门 entirely and turned 文典阁西门 into 文典阁;
* two distances always give two mirror positions, and the map label printed next
  to the blue dot (榴园) is what picks the right one.
"""

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "outputs" / "real-run-planner"
sys.path.insert(0, str(HERE))

import real_position  # noqa: E402
import read_checkpoints  # noqa: E402
from checkpoint_reader import APP_ALIASES, match, parse  # noqa: E402

SCREEN = ROOT / "work" / "now-214420.png"

failures = []


def check(name, condition, detail=""):
    if condition:
        print(f"  OK   {name} {detail}")
    else:
        failures.append(name)
        print(f"  FAIL {name} {detail}")


labels = {name: tuple(point) for name, point in
          json.loads((HERE / "campus.json").read_text(encoding="utf-8"))["labels"]}

print("1. 名字清洗与别名")
rows = parse([(0, 210, "0 体 育 馆 大 门 （ 距 你 317 米 ）"),
              (0, 220, "0 文 典 阁 西 门 （ 距 你 378 米 ）")])
names = [name for name, _ in rows]
check("parse strips the hollow brackets", names == ["体育馆大门", "文典阁西门"], str(rows))
check("alias table has 体育馆大门", APP_ALIASES["体育馆大门"] == "主体育场南门")
pairs = match(names, labels)
check("体育馆大门 → 主体育场南门", pairs.get("体育馆大门") == "主体育场南门", str(pairs))
check("文典阁西门 keeps its gate", pairs.get("文典阁西门") == "文典阁西门")

print("2. 起点反解（真实截图）")
if not SCREEN.is_file():
    print(f"  SKIP 没有 {SCREEN.name}")
else:
    screen = SCREEN.read_bytes()
    anchor = real_position.map_anchor(labels, screen)
    check("蓝点旁的标签是榴园", anchor is not None and anchor[1] == "榴园",
          "" if anchor is None else anchor[1])
    fix = real_position.read_and_resolve(labels, labels, screen=screen)
    near = math.dist(fix.point, labels["榴园"])
    check("起点落在榴园附近", near <= 60.0, f"{near:.1f} 米")
    check("镜像解被压到别处", fix.alternative is None or math.dist(fix.point, fix.alternative) > 120.0,
          "" if fix.alternative is None else f"{math.dist(fix.point, fix.alternative):.0f} 米")
    resolved = read_checkpoints.read_checkpoints(labels, screen=screen)
    check("GUI 读到两个打卡点", len(resolved) == 2 and all(p is not None for _, p in resolved),
          str([(n, p is not None) for n, p in resolved]))

print()
if failures:
    print(f"failures: {len(failures)} -> {failures}")
    raise SystemExit(1)
print("failures: 0")