"""Read visible checkpoint names from a USB screenshot using the existing OCR."""

import re
import sys
import tempfile
from pathlib import Path


# Share the screenshot and OCR modules without loading the other planner.
sys.path.append(str(Path(__file__).resolve().parents[1] / "run-planner"))
from checkpoint_reader import DISTANCE, flatten, ocr_lines
from phone_screen import capture_usb_screen


HEADER = re.compile(r"自由打卡.*(?:模式|打卡点)")
BUTTONS = ("开始乐跑", "长按暂停", "继续乐跑", "结束乐跑", "长按结束")
STATUS = re.compile(r"未打卡|已打卡")
APPROXIMATE_LABELS = {"蕙园", "文典阁西门", "篮球场南门"}
ANGLE = r"""(\d{1,3})[°º˚](\d{1,2})['′’](\d{1,2}(?:\.\d+)?)(?:["″”]|['′’]{2})"""
CHINESE_COORDS = re.compile(rf"([南北])纬{ANGLE}[，,]?([东西])经{ANGLE}")
ENGLISH_COORDS = re.compile(rf"{ANGLE}([NS])[，,]?{ANGLE}([EW])")


def checkpoint_rows(lines):
    names = {}
    in_list = False
    for _, _, raw in lines:
        text = flatten(raw)
        if "顺序打卡" in text:
            raise ValueError("该活动要求按顺序打卡。请按手机列出的顺序手动规划。")
        if HEADER.search(text):
            in_list = True
            continue
        if not in_list:
            continue
        if any(button in text for button in BUTTONS) or text in {"继续", "结束"}:
            break
        if text.startswith(("可自行安排", "本跑区", "请按顺序")):
            continue
        if text.startswith(("距你", "距离")):
            continue
        label = DISTANCE.sub("", STATUS.sub("", text)).replace("距你", "").replace("距离", "")
        label = re.sub(r"^[^\u4e00-\u9fffA-Za-z]+", "", label).strip("（）()。,，:：")
        if len(label) >= 2 and re.search(r"[\u4e00-\u9fff]", label):
            names[label] = None
    if not names or len(names) > 2:
        raise ValueError("未能确认打卡点列表。本版支持最多两个打卡点，请完整显示本次名单后重试。")
    return list(names)


def screen_lines(screen):
    if screen is None:
        screen = capture_usb_screen()
    with tempfile.TemporaryDirectory(prefix="real-run-screen-") as folder:
        image = Path(folder) / "screen.png"
        image.write_bytes(screen)
        return ocr_lines(image)


def read_checkpoints(labels, screen=None):
    return [(name, labels.get(name)) for name in checkpoint_rows(screen_lines(screen))]


def compass_coordinates(lines):
    """Extract a latitude/longitude pair from the iPhone Compass screen."""
    text = "".join(flatten(line) for _, _, line in lines).upper()
    match = CHINESE_COORDS.search(text)
    if match:
        ns, lat_d, lat_m, lat_s, ew, lon_d, lon_m, lon_s = match.groups()
    elif match := ENGLISH_COORDS.search(text):
        lat_d, lat_m, lat_s, ns, lon_d, lon_m, lon_s, ew = match.groups()
    else:
        raise ValueError("没有读到经纬度。请在手机打开「指南针」并显示坐标，或对照苹果地图手动标起点。")

    def decimal(degrees, minutes, seconds, limit):
        minutes, seconds = int(minutes), float(seconds)
        value = int(degrees) + minutes / 60 + seconds / 3600
        if minutes >= 60 or seconds >= 60 or value > limit:
            raise ValueError("指南针的坐标识别有误，请重试或手动标起点。")
        return value

    latitude = decimal(lat_d, lat_m, lat_s, 90)
    longitude = decimal(lon_d, lon_m, lon_s, 180)
    return (-latitude if ns in ("S", "南") else latitude, -longitude if ew in ("W", "西") else longitude)


def read_phone_coordinates():
    return compass_coordinates(screen_lines(None))
