"""Check that a fresh copy of the project can bootstrap itself and open both GUIs.

Simulates what a stranger does after unzipping the release: no work\\.venv
exists, so the launcher has to pick an interpreter, build the venv, install
requirements.txt and start the planner. The interpreter is injected through
CAMPUS_RUN_PYTHON so the test can run on machines where the py launcher only
knows a version pymobiledevice3 does not support yet.

Both front ends get a turn: the classic planner (启动规划器.bat) and the
obstacle-aware real-run planner (Start-Real-Run.bat). The second run reuses the
venv the first one built, which also proves the venv is shared correctly.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
import time
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"


def release_zip() -> pathlib.Path:
    candidates = sorted(DIST.glob("campus-run-planner-v*.zip"))
    if not candidates:
        raise SystemExit("build the release first: no dist\\campus-run-planner-v*.zip")

    def version(path: pathlib.Path) -> tuple[int, ...]:
        tail = path.stem.rsplit("-v", 1)[-1]
        return tuple(int(part) for part in tail.split(".") if part.isdigit())

    return max(candidates, key=version)


def unpack(target: pathlib.Path) -> pathlib.Path:
    with zipfile.ZipFile(release_zip()) as bundle:
        bundle.extractall(target)
    folders = [item for item in target.iterdir() if item.is_dir()]
    if len(folders) != 1:
        raise SystemExit(f"expected one folder in the zip, got {folders}")
    return folders[0]


def window_pid(title: str) -> int | None:
    script = (
        "$p = Get-Process | Where-Object { $_.MainWindowTitle -like '*"
        + title
        + "*' } | Select-Object -First 1; if ($p) { $p.Id }"
    )
    done = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True, text=True, timeout=60,
    )
    out = done.stdout.strip()
    return int(out) if out.isdigit() else None


def launch(project: pathlib.Path, bat: pathlib.Path, title: str, log: pathlib.Path) -> bool:
    env = dict(os.environ)
    env["CAMPUS_RUN_PYTHON"] = sys.executable
    if not env.get("CAMPUS_RUN_PIP_INDEX"):
        env.pop("CAMPUS_RUN_PIP_INDEX", None)
    print(f"launcher: {bat.name} -> expecting a window titled {title}")
    with log.open("wb") as handle:
        child = subprocess.Popen(
            ["cmd", "/c", bat.name], cwd=project,
            stdout=handle, stderr=subprocess.STDOUT, env=env,
        )
    deadline = time.time() + 420
    pid = None
    while time.time() < deadline:
        time.sleep(3)
        pid = window_pid(title)
        if pid:
            break
        if child.poll() is not None:
            break
    venv_python = project / "work" / ".venv" / "Scripts" / "python.exe"
    print("  venv:", venv_python.exists(), "window pid:", pid)
    if pid:
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
    if child.poll() is None:
        subprocess.run(["taskkill", "/PID", str(child.pid), "/T", "/F"], capture_output=True)
    tail = log.read_text("utf-8", errors="replace").strip().splitlines()[-6:]
    if tail:
        print("  " + "\n  ".join(tail))
    return venv_python.exists() and bool(pid)


def main() -> int:
    print("zip:", release_zip().name)
    work = ROOT / "work" / "release-test"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    project = unpack(work)
    print("unpacked:", project)

    plan_bat = project / "启动规划器.bat"
    if not plan_bat.exists():
        plan_bat = project / "Start-Planner.bat"
    real_bat = project / "Start-Real-Run.bat"
    if not real_bat.exists():
        raise SystemExit("release is missing Start-Real-Run.bat")

    ok = launch(project, plan_bat, "校园跑路线规划", work / "launcher-plan.log")
    ok = launch(project, real_bat, "校园实跑路线规划", work / "launcher-real.log") and ok
    print("OK" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())