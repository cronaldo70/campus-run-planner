"""Check that a fresh copy of the project can bootstrap itself and open the GUI.

Simulates what a stranger does after unzipping the release: no work\\.venv
exists, so `启动校园跑.bat` has to pick an interpreter, build the venv, install
requirements.txt and start the real-run planner. The interpreter is injected
through CAMPUS_RUN_PYTHON so the test can run on machines where the py launcher
only knows a version pymobiledevice3 does not support yet.

Two things get checked:
  1. plain double-click  -> window titled 校园实跑路线规划
  2. `check` argument    -> tools\\doctor.py runs and prints its verdict
The second run reuses the venv the first one built, which also proves the venv
is shared correctly.
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
LAUNCHER = "启动校园跑.bat"


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


def read_log(path: pathlib.Path) -> str:
    """A .bat echoes GBK on Chinese Windows while Python prints the console codepage,
    so try both and never let a decode error break the report."""
    raw = path.read_bytes()
    for encoding in ("gbk", "utf-8"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def show(lines: list[str]) -> None:
    for line in lines:
        try:
            print("  " + line)
        except UnicodeEncodeError:
            print("  " + line.encode(sys.stdout.encoding or "gbk", "replace").decode(
                sys.stdout.encoding or "gbk", "replace"))


def launch(project: pathlib.Path, bat: pathlib.Path, title: str, log: pathlib.Path) -> bool:
    env = dict(os.environ)
    env["CAMPUS_RUN_PYTHON"] = sys.executable
    show([f"launcher: {bat.name} -> expecting a window titled {title}"])
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
    show([f"venv: {venv_python.exists()} window pid: {pid}"])
    if pid:
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
    if child.poll() is None:
        subprocess.run(["taskkill", "/PID", str(child.pid), "/T", "/F"], capture_output=True)
    tail = read_log(log).strip().splitlines()[-6:]
    if tail:
        show(tail)
    return venv_python.exists() and bool(pid)


def doctor(project: pathlib.Path, log: pathlib.Path) -> bool:
    """`启动校园跑.bat check` 要能跑完自检（结尾会 pause，所以直接喂回车超时退出）。"""
    show([f"launcher: {LAUNCHER} check -> expecting the self-check report"])
    env = dict(os.environ)
    env["CAMPUS_RUN_PYTHON"] = sys.executable
    with log.open("wb") as handle:
        subprocess.run(["cmd", "/c", LAUNCHER, "check"], cwd=project, stdin=subprocess.DEVNULL,
                       stdout=handle, stderr=subprocess.STDOUT, env=env, timeout=240)
    text = read_log(log)
    show(text.strip().splitlines()[-8:])
    return "环境自检" in text and ("结论：环境就绪" in text or "结论：有" in text)


def main() -> int:
    show([f"zip: {release_zip().name}"])
    work = ROOT / "work" / "release-test"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    project = unpack(work)
    show([f"unpacked: {project}"])

    bat = project / LAUNCHER
    if not bat.exists():
        raise SystemExit(f"release is missing {LAUNCHER}")

    ok = launch(project, bat, "校园实跑路线规划", work / "launcher-real.log")
    ok = doctor(project, work / "launcher-check.log") and ok
    print("OK" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())