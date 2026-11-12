"""Capture a single screenshot of the authorized USB device for local preview."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path


def capture_usb_screen() -> bytes:
    pmd = Path(sys.executable).with_name("pymobiledevice3.exe")
    if not pmd.is_file():
        raise RuntimeError("当前 Python 环境缺少 pymobiledevice3。可以继续手动填写打卡点。")

    options = {
        "capture_output": True,
        "stdin": subprocess.DEVNULL,
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0),
    }
    try:
        device_list = subprocess.run(
            [str(pmd), "usbmux", "list", "--usb", "--simple"], timeout=12, **options
        )
        if device_list.returncode:
            raise RuntimeError("无法连接 Apple USB 服务。请检查 Apple Devices 和数据线。")
        devices = json.loads(device_list.stdout)
        if not isinstance(devices, list) or len(devices) != 1:
            raise RuntimeError("请连接并解锁一台 iPhone，再读取页面。")
        with tempfile.TemporaryDirectory(prefix="run-planner-screen-") as temp:
            destination = Path(temp) / "screen.png"
            result = subprocess.run(
                [str(pmd), "developer", "dvt", "screenshot", "--udid", devices[0], str(destination)],
                timeout=20,
                **options,
            )
            if result.returncode or not destination.is_file():
                raise RuntimeError("截图未返回。请确认手机已解锁，且开发者模式已开启。")
            return destination.read_bytes()
    except subprocess.TimeoutExpired:
        raise RuntimeError("读取超时。请检查 USB 连接后重试。") from None
    except (OSError, ValueError):
        raise RuntimeError("读取手机画面失败。请检查连接或手动填写打卡点。") from None
