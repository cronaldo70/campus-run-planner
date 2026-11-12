import json
import os
import subprocess
import sys
import time
from pathlib import Path

workspace = Path(__file__).resolve().parent.parent
mode = sys.argv[1]
pmd = workspace / "work" / ".venv" / "Scripts" / "pymobiledevice3.exe"
environment = dict(os.environ, PYTHONUNBUFFERED="1")
prefix = [str(pmd), "developer", "dvt", "simulate-location"]
usb_result = subprocess.run([str(pmd), "usbmux", "list", "--usb"], capture_output=True, text=True, timeout=15)
usb = json.loads(usb_result.stdout) if usb_result.returncode == 0 else []
if len(usb) != 1 or (usb[0].get("ProductType"), usb[0].get("ProductVersion"), usb[0].get("BuildVersion")) != (
    "iPhone15,3", "27.2", "24B119"
):
    sys.exit("Expected a single matching iOS 27.2 USB test device")
identity = usb[0].get("Identifier")
if not identity:
    ids = subprocess.run([str(pmd), "usbmux", "list", "--usb", "--simple"], capture_output=True, text=True, timeout=15)
    identifiers = json.loads(ids.stdout) if ids.returncode == 0 else []
    if len(identifiers) != 1:
        sys.exit("Could not select the USB test device")
    identity = identifiers[0]
device = ["--udid", identity]
if mode == "set":
    action = ["set", *device, "--", "37.7749", "-122.4194"]
    wait_for_prompt, hold = 20, 20
else:
    action = ["play", *device, str(workspace / "outputs" / "examples" / "demo_route.gpx")]
    wait_for_prompt, hold = 46, 6
log_path = workspace / "work" / f"device-{mode}.log"
process = None
ready = False
clear_exit = None
started = time.monotonic()
try:
    with log_path.open("wb") as log:
        process = subprocess.Popen(
            [*prefix, *action], stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT, env=environment,
        )
        while process.poll() is None and time.monotonic() - started < wait_for_prompt:
            if b"Press ENTER to exit>" in log_path.read_bytes():
                ready = True
                print(f"{mode}: hold prompt reached ({time.monotonic() - started:.1f}s after launch)", flush=True)
                time.sleep(hold)
                process.communicate(input=b"\r\n", timeout=10)
                break
            time.sleep(0.2)
        if process.poll() is None:
            process.terminate()
            process.communicate(timeout=5)
finally:
    if process is not None:
        if process.poll() is None:
            process.kill()
            process.communicate()
        clear_result = subprocess.run([*prefix, "clear", *device], capture_output=True, timeout=20)
        clear_exit = clear_result.returncode
        print(f"clear exit: {clear_exit}", flush=True)

print(f"{mode} exit: {process.returncode if process else 'not started'}")
lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
if mode == "play":
    for line in lines:
        for marker in ("set location to ", "waiting for "):
            if marker in line:
                print(marker + line.split(marker, 1)[1])
if not ready:
    for marker in ("InvalidServiceError", "LocationSimulation", "Failed to", "Timed out", "TimeoutError"):
        if any(marker in line for line in lines):
            print(f"Diagnostic marker: {marker}")
sys.exit(0 if ready and process.returncode == 0 and clear_exit == 0 else 1)
