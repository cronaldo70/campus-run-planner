"""Check that a fresh copy of the project can bootstrap itself and open the GUI.

Simulates what a stranger does after unzipping the release: no work\\.venv
exists, so the launcher has to pick an interpreter, build the venv, install
requirements.txt and start the planner. The interpreter is injected through
CAMPUS_RUN_PYTHON so the test can run on machines where the py launcher only
knows a version pymobiledevice3 does not support yet.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
ZIP = ROOT / "dist" / "campus-run-planner-v0.6.zip"
WINDOW = "校园跑路线规划"


def unpack(target: pathlib.Path) -> pathlib.Path:
    with zipfile.ZipFile(ZIP) as bundle:
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


def main() -> int:
    if not ZIP.exists():
        raise SystemExit(f"build the release first: {ZIP}")
    work = ROOT / "work" / "release-test"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    project = unpack(work)
    print("unpacked:", project)

    bat = next(project.glob("*.bat"))
    env = dict(os.environ)
    env["CAMPUS_RUN_PYTHON"] = sys.executable
    env["CAMPUS_RUN_PIP_INDEX"] = env.get("CAMPUS_RUN_PIP_INDEX", "")
    if not env["CAMPUS_RUN_PIP_INDEX"]:
        env.pop("CAMPUS_RUN_PIP_INDEX")
    log = work / "launcher.log"
    with log.open("wb") as handle:
        child = subprocess.Popen(
            ["cmd", "/c", str(bat.name)], cwd=project,
            stdout=handle, stderr=subprocess.STDOUT, env=env,
        )
    print("launcher pid:", child.pid)

    venv_python = project / "work" / ".venv" / "Scripts" / "python.exe"
    deadline = time.time() + 420
    pid = None
    while time.time() < deadline:
        time.sleep(3)
        pid = window_pid(WINDOW)
        if pid:
            break
        if child.poll() is not None and not venv_python.exists():
            break
    print("venv:", venv_python.exists(), "window pid:", pid)
    if pid:
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
    if child.poll() is None:
        subprocess.run(["taskkill", "/PID", str(child.pid), "/T", "/F"], capture_output=True)
    tail = log.read_text("utf-8", errors="replace").strip().splitlines()[-6:]
    print("\n".join(tail))
    ok = venv_python.exists() and bool(pid)
    print("OK" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())