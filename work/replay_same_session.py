"""Run one observed test on the connected iOS 27.2 iPhone."""

import asyncio
import json
import logging
import subprocess
from pathlib import Path

from pymobiledevice3.remote.userspace_tunnel import UserspaceRsdTunnel
from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider
from pymobiledevice3.services.dvt.instruments.location_simulation import LocationSimulation


ROOT = Path(__file__).resolve().parent.parent
PMD = ROOT / "work" / ".venv" / "Scripts" / "pymobiledevice3.exe"
ROUTE = ROOT / "outputs" / "examples" / "demo_route.gpx"


def usb_test_device() -> str:
    result = subprocess.run([str(PMD), "usbmux", "list", "--usb"], capture_output=True, text=True, timeout=15)
    devices = json.loads(result.stdout) if result.returncode == 0 else []
    if len(devices) != 1:
        raise ValueError("Expected one USB test device")
    device = devices[0]
    if (device.get("ProductType"), device.get("ProductVersion"), device.get("BuildVersion")) != (
        "iPhone15,3", "27.2", "24B119"
    ):
        raise ValueError("USB device does not match the iOS 27.2 test phone")
    result = subprocess.run(
        [str(PMD), "usbmux", "list", "--usb", "--simple"], capture_output=True, text=True, timeout=15
    )
    identifiers = json.loads(result.stdout) if result.returncode == 0 else []
    if len(identifiers) != 1:
        raise ValueError("Could not identify the test phone")
    return identifiers[0]


async def replay(serial: str) -> None:
    async with UserspaceRsdTunnel(serial=serial) as rsd, DvtProvider(rsd) as dvt, LocationSimulation(dvt) as location:
        try:
            async with asyncio.timeout(42):
                await location.play_gpx_file(str(ROUTE))
                print("Replay completed", flush=True)
                await asyncio.sleep(5)
        finally:
            async with asyncio.timeout(12):
                await location.clear()
                print("Clear sent on the playback session", flush=True)
                await asyncio.sleep(3)


def main() -> None:
    logger = logging.getLogger("LocationSimulation")
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(relativeCreated).0f ms %(message)s"))
    logger.addHandler(handler)
    try:
        asyncio.run(replay(usb_test_device()))
    except Exception as error:
        raise SystemExit(f"Replay failed: {type(error).__name__}") from None


if __name__ == "__main__":
    main()
