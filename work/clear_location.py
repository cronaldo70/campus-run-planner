"""Clear a simulated location and wait for the USB device's DVT reply."""

import asyncio
import sys

from pymobiledevice3 import usbmux
from pymobiledevice3.remote.userspace_tunnel import UserspaceRsdTunnel
from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider
from pymobiledevice3.services.dvt.instruments.location_simulation import LocationSimulation


async def clear_location() -> None:
    async with asyncio.timeout(25):
        devices = [device for device in await usbmux.list_devices() if device.is_usb]
        if len(devices) != 1:
            raise ValueError("Connect and unlock exactly one test iPhone or iPad over USB.")

        async with (
            UserspaceRsdTunnel(serial=devices[0].serial) as rsd,
            DvtProvider(rsd) as dvt,
            LocationSimulation(dvt) as location,
        ):
            async with asyncio.timeout(5):
                await location.service.invoke("stopLocationSimulation", expects_reply=True)
            print("Device replied to the stop request. Check the blue dot in Maps.", flush=True)
            await asyncio.sleep(8)


if __name__ == "__main__":
    try:
        asyncio.run(clear_location())
    except TimeoutError:
        sys.exit("Clear timed out. Check the phone, USB connection and Developer Mode.")
    except ValueError as error:
        sys.exit(str(error))
    except Exception as error:
        sys.exit(f"Clear failed ({type(error).__name__}). Check the USB connection and Developer Mode.")
