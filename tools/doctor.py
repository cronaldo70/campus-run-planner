"""环境自检：Python / 依赖 / 手机连接 / 底图数据。

用法：
    work\\.venv\\Scripts\\python.exe -B tools\\doctor.py
或在界面里点「工具 → 环境自检」。

只做检查，不动手机、不改文件；最后给一句结论。
"""

from __future__ import annotations

import json
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENV = ROOT / "work" / ".venv"
CAMPUS = ROOT / "outputs" / "real-run-planner" / "campus.json"
USBMUX = ("127.0.0.1", 27015)
APP_BUNDLE = "com.lepao.lptiyu"

OK = "[ OK ]"
BAD = "[ !! ]"
WARN = "[ ?? ]"

fixes: list[str] = []


def say(tag: str, text: str) -> None:
    print(f"{tag} {text}")


def bad(text: str, fix: str | None = None) -> None:
    say(BAD, text)
    if fix:
        fixes.append(fix)


def warn(text: str) -> None:
    say(WARN, text)


def port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def check_python() -> None:
    say(OK, f"Python {sys.version.split()[0]} · {sys.executable}")
    if VENV.is_dir() and Path(sys.prefix).resolve() == VENV.resolve():
        say(OK, "运行在 work\\.venv 里")
    elif VENV.is_dir():
        warn(f"不在 work\\.venv 里（sys.prefix = {sys.prefix}），依赖可能对不上")


def check_deps() -> None:
    try:
        import pymobiledevice3  # noqa: F401
        from importlib.metadata import PackageNotFoundError, version as dist_version

        try:
            say(OK, f"pymobiledevice3 {dist_version('pymobiledevice3')}")
        except PackageNotFoundError:
            say(OK, "pymobiledevice3 已安装（版本号读不到）")
    except Exception as exc:  # noqa: BLE001 - 报出来比吞掉更有用
        bad(f"pymobiledevice3 导入失败：{exc}", "python -m pip install -r requirements.txt")
    try:
        import tkinter

        say(OK, f"tkinter · Tk {tkinter.TkVersion}")
    except Exception as exc:  # noqa: BLE001
        bad(f"tkinter 不可用：{exc}", "装官方 CPython（不要用 Microsoft Store 版），Tk 随安装包自带")


def check_device() -> None:
    if not port_open(*USBMUX):
        bad(
            "usbmuxd 没在 127.0.0.1:27015 监听 —— 电脑这边没识别到 iPhone",
            "按顺序查：① 换一根能传数据的线（纯充电线不行）② 手机上点「信任此电脑」并输密码 "
            "③ 装 Apple Devices（或 iTunes）补上 Apple Mobile Device 驱动 ④ 设置 → 隐私与安全性 → "
            "开发者模式 打开后重启手机 ⑤ 换 USB 口，别走 USB Hub",
        )
        return
    try:
        import asyncio

        from pymobiledevice3.usbmux import list_devices

        devices = asyncio.run(list_devices())
    except Exception as exc:  # noqa: BLE001
        bad(f"usbmuxd 有响应但取设备列表失败：{exc}", "重插手机；还不行就重启 Apple Mobile Device Service")
        return
    if not devices:
        bad("usbmuxd 在跑，但没有任何设备", "手机解锁状态下重新插一次 USB，并在弹窗里点「信任」")
        return
    if len(devices) > 1:
        warn(f"接了 {len(devices)} 台设备，模拟跑会挑第一台；只留一台最稳")
    for device in devices:
        say(OK, f"设备 {device.serial} · 连接方式 {device.connection_type}")
    say(OK, f"目标 App：步道乐跑（{APP_BUNDLE}）—— 「开始乐跑」要在手机上自己点，脚本点不了屏幕")


def check_data() -> None:
    if not CAMPUS.is_file():
        bad(f"找不到底图 {CAMPUS.name}", "重新 clone 仓库，campus.json 不能少")
        return
    try:
        data = json.loads(CAMPUS.read_text(encoding="utf-8"))
        say(OK, f"底图 {len(data['labels'])} 个打卡点名 · {len(data['nodes'])} 个节点 · "
                f"{len(data['roads'])} 段路 · {len(data['areas'])} 个建筑/水域")
    except Exception as exc:  # noqa: BLE001
        bad(f"底图读不动：{exc}", "删掉 campus.json 重新 clone")
        return
    generated = CAMPUS.parent / "generated"
    try:
        generated.mkdir(parents=True, exist_ok=True)
        probe = generated / ".write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        say(OK, f"生成的轨迹会写到 {generated}")
    except Exception as exc:  # noqa: BLE001
        bad(f"轨迹目录不可写：{exc}", "别把项目放在只读位置（如 Program Files），挪到桌面或 D 盘")


def main() -> int:
    # 不要强制 utf-8：中文 Windows 的控制台是 936，强制 utf-8 会让所有中文变成乱码。
    # 只有父进程把管道设成 utf-8 而控制台是 936 时才需要兜底，交给 Python 自己按
    # locale 选择即可（launcher 已经清掉了外部继承的 PYTHONIOENCODING / PYTHONUTF8）。
    try:
        print("校园跑 · 环境自检")
    except UnicodeEncodeError:
        sys.stdout.reconfigure(errors="replace")
        print("校园跑 · 环境自检")
    print("-" * 56)
    check_python()
    check_deps()
    check_data()
    check_device()
    print("-" * 56)
    if fixes:
        print(f"结论：有 {len(fixes)} 处要处理。")
        for index, fix in enumerate(fixes, 1):
            print(f"  {index}. {fix}")
        return 1
    print("结论：环境就绪，双击「启动校园跑.bat」即可。")
    return 0


if __name__ == "__main__":
    sys.exit(main())