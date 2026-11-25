"""Read visible checkpoint names from a USB screenshot using the existing OCR."""

import difflib
import re
import sys
import tempfile
from pathlib import Path


# Share the screenshot and OCR modules without loading the other planner.
sys.path.append(str(Path(__file__).resolve().parents[1] / "run-planner"))
from checkpoint_reader import DISTANCE, flatten, ocr_lines
from phone_screen import capture_usb_screen


HEADER = re.compile(r"自由打卡")
BUTTONS = ("开始乐跑", "长按暂停", "继续乐跑", "结束乐跑", "长按结束")
STATUS = re.compile(r"未打卡|已打卡")
APPROXIMATE_LABELS = {"蕙园", "文典阁西门", "篮球场南门"}
ANGLE = r"""(\d{1,3})[°º˚](\d{1,2})['′’](\d{1,2}(?:\.\d+)?)(?:["″”]|['′’]{2})"""
CHINESE_COORDS = re.compile(rf"([南北])纬{ANGLE}[，,]?([东西])经{ANGLE}")
ENGLISH_COORDS = re.compile(rf"{ANGLE}([NS])[，,]?{ANGLE}([EW])")

# Longest first: 东北侧 must be tried before 东侧 and 东.
DIRECTIONS = (
    "东北侧", "西北侧", "东南侧", "西南侧",
    "东北门", "西北门", "东南门", "西南门",
    "东侧", "西侧", "南侧", "北侧",
    "东门", "西门", "南门", "北门",
    "东", "西", "南", "北",
)
# The app writes 人文楼东侧; the map often only has 人文楼.
BUILDING_SUFFIXES = ("", "楼", "馆", "园", "场", "中心", "大楼")

# The app does not use OSM names. 体育馆 in 步道乐跑 means the stadium (OSM 主体育场),
# and 大门 means its south gate — verified on 2026-11-25: the phone stood 41.7 m from
# 榴园, the app read 体育馆大门 317 米 / 文典阁西门 378 米, and only
# (主体育场南门 317, 文典阁西门 378) intersects there (the other two candidates have
# no intersection at all).
ALIASES = {
    "体育馆": "主体育场",
    "体育场": "主体育场",
    "体育馆大门": "主体育场南门",
    "体育场大门": "主体育场南门",
    "体育馆正门": "主体育场南门",
    "操场": "主体育场",
}
UNRESOLVED = Path(__file__).resolve().parent / "generated" / "unresolved.txt"
MAX_CHECKPOINTS = 4


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
        # OCR sometimes loses the header line; a "（距你 N 米）" row is proof enough.
        if not in_list and not ("距你" in text and DISTANCE.search(text)):
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
    if not names or len(names) > MAX_CHECKPOINTS:
        raise ValueError(
            f"未能确认打卡点列表（读到 {len(names)} 个，最多 {MAX_CHECKPOINTS} 个）。"
            "请完整显示本次名单后重试。"
        )
    return list(names)


def resolve(labels, name):
    """Match an OCR checkpoint name to a coordinate, tolerating small differences.

    Order: exact → app alias (体育馆大门 → 主体育场南门) → drop the direction
    (人文楼东侧 → 人文楼) → add a building suffix → closest spelling.
    """
    if name in labels:
        return labels[name]

    alias = ALIASES.get(name)
    if alias and alias in labels:
        return labels[alias]

    for suffix in DIRECTIONS:
        if not name.endswith(suffix):
            continue
        base = name[: -len(suffix)]
        if len(base) < 2:
            continue
        for tail in BUILDING_SUFFIXES:
            candidate = base + tail
            if candidate in labels:
                return labels[candidate]

    close = difflib.get_close_matches(name, labels.keys(), n=1, cutoff=0.78)
    if close:
        return labels[close[0]]
    return None


def note_unresolved(names):
    """Keep a list of names the map does not know, so they can be added later."""
    if not names:
        return
    try:
        UNRESOLVED.parent.mkdir(exist_ok=True)
        known = set()
        if UNRESOLVED.is_file():
            known = {line.strip() for line in UNRESOLVED.read_text(encoding="utf-8").splitlines()}
        fresh = [name for name in names if name not in known]
        if fresh:
            with UNRESOLVED.open("a", encoding="utf-8") as handle:
                for name in fresh:
                    handle.write(name + "\n")
    except OSError:
        pass


def screen_lines(screen):
    if screen is None:
        screen = capture_usb_screen()
    with tempfile.TemporaryDirectory(prefix="real-run-screen-") as folder:
        image = Path(folder) / "screen.png"
        image.write_bytes(screen)
        return ocr_lines(image)


def read_checkpoints(labels, screen=None):
    names = checkpoint_rows(screen_lines(screen))
    resolved = [(name, resolve(labels, name)) for name in names]
    note_unresolved([name for name, point in resolved if point is None])
    return resolved


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
