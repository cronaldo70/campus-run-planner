import asyncio
import collections
import os
import re
import subprocess
import threading
import time

from replay_same_session import PMD, usb_test_device
from pymobiledevice3.dtx.exceptions import DTXNsError
from pymobiledevice3.remote.userspace_tunnel import UserspaceRsdTunnel
from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider
from pymobiledevice3.services.dvt.instruments.location_simulation import LocationSimulation

MARKERS = {
    "simulation": re.compile(r"simulat|\bgpx\b|location override", re.I),
    "stop or clear": re.compile(r"stop.{0,30}simulat|simulat.{0,30}stop|clear.{0,30}simulat|simulat.{0,30}clear|stopLocationSimulation", re.I),
    "simulation error": re.compile(r"simulat.{0,80}(?:error|fail|denied|invalid|reject)|(?:error|fail|denied|invalid|reject).{0,80}simulat", re.I),
}

class LogSummary:
    def __init__(self, serial):
        self.phase = "before set"
        self.counts = collections.Counter()
        self.process = subprocess.Popen(
            [str(PMD), "syslog", "live", "--udid", serial, "--process-name", "locationd"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=dict(os.environ, PYTHONUNBUFFERED="1"),
            text=True, encoding="utf-8", errors="replace",
        )
        self.reader = threading.Thread(target=self.read, daemon=True)
        self.reader.start()

    def read(self):
        for line in self.process.stdout:
            if not re.search(r"\blocationd(?:\[|\b)", line, re.I):
                continue
            phase = self.phase
            self.counts[phase, "lines"] += 1
            for marker, pattern in MARKERS.items():
                if pattern.search(line):
                    self.counts[phase, marker] += 1

    def close(self):
        running = self.process.poll() is None
        if running:
            self.process.terminate()
        self.process.wait(timeout=8)
        self.reader.join(timeout=3)
        self.process.stdout.close()
        print(f"locationd stream running at end: {running}", flush=True)
        for phase in ("before set", "fixed location", "after stop"):
            values = ", ".join(f"{marker}={self.counts[phase, marker]}" for marker in ("lines", *MARKERS))
            print(f"locationd {phase}: {values}", flush=True)

async def exercise(serial, logs):
    async with (
        asyncio.timeout(50),
        UserspaceRsdTunnel(serial=serial) as rsd,
        DvtProvider(rsd) as dvt,
        LocationSimulation(dvt) as location,
    ):
        await asyncio.sleep(2)
        try:
            logs.phase = "fixed location"
            await location.set(37.7749, -122.4194)
            print("Fixed point accepted by DVT", flush=True)
            await asyncio.sleep(15)
        finally:
            logs.phase = "after stop"
            started = time.monotonic()
            try:
                async with asyncio.timeout(5):
                    response = await location.service.invoke("stopLocationSimulation", expects_reply=True)
                print(f"Stop DTX reply in {time.monotonic() - started:.2f}s, result type {type(response).__name__}", flush=True)
            except DTXNsError as error:
                details = str(error)
                match = re.search(r"(?:code|Code)[=: ]+(-?\d+)", details)
                print("Stop returned a DTX error" + (f", code {match[1]}" if match else ""), flush=True)
                await location.clear()
                print("Standard stop sent after DTX error", flush=True)
            except Exception as error:
                print(f"Stop with reply ended with {type(error).__name__}", flush=True)
                await location.clear()
                print("Standard stop sent after reply failure", flush=True)
            await asyncio.sleep(8)

def main():
    try:
        serial = usb_test_device()
        logs = LogSummary(serial)
        try:
            asyncio.run(exercise(serial, logs))
        finally:
            logs.close()
    except Exception as error:
        raise SystemExit(f"Diagnostic ended with {type(error).__name__}") from None

if __name__ == "__main__":
    main()
