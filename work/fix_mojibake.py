"""Repair the Chinese literals that a PowerShell text pipeline mangled in location_sim.py."""

from pathlib import Path

TARGET = Path(r"D:\gpt\2026-11-12\codex-handoff-ios26-location-test-md\outputs\run-planner\location_sim.py")

# line number (1-based) -> exact replacement line
FIXES = {
    183: '        raise ValueError("路线至少需要两个点。")',
    185: '        raise ValueError("采样间距必须大于零。")',
    209: '        raise ValueError("配速必须大于零。")',
    211: '        raise ValueError("圈数至少为 1。")',
    229: '        raise ValueError("路线太短，无法生成轨迹。")',
    289: '        raise RuntimeError("请只连接并解锁一台 iPhone，再开始模拟跑。")',
    375: '        raise ValueError(f"{path} 里没有带时间戳的 trkpt。")',
    396: '            parser.error("需要 --route \'x,y;x,y\' 或 --play-gpx FILE")',
}

lines = TARGET.read_text(encoding="utf-8").splitlines()
for number, text in FIXES.items():
    old = lines[number - 1]
    lines[number - 1] = text
    print(f"{number}: {old.strip()[:40]!r} -> {text.strip()[:40]!r}")
TARGET.write_text("\n".join(lines) + "\n", encoding="utf-8")

verify = TARGET.read_text(encoding="utf-8")
bad = [ch for ch in verify if "\ue000" <= ch <= "\uf8ff"]
print("private-use chars left:", len(bad))
print("compile:", end=" ")
compile(verify, str(TARGET), "exec")
print("ok")