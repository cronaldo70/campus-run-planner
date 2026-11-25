"""Read the checkpoint list off the running app screen and locate the phone on campus.

The app shows every checkpoint it wants plus a "距你 N 米" distance. A USB
screenshot plus the OCR engine that ships with Windows turns that into numbers:
the names pick the road-network label, and three or more distances triangulate
where the phone actually stands, so the planner can start the run where the
runner is instead of at a hand-picked pin.

No credentials, no reverse engineering of the app: only what is already on the
screen.
"""

from __future__ import annotations

import difflib
import json
import math
import re
import subprocess
import sys
import tempfile
from pathlib import Path

Point = tuple[float, float]

# How far from a checkpoint the app still accepts a punch.
PUNCH_RADIUS = 50.0

OCR_SCRIPT = r"""
param([string]$Path, [string]$Out)
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, [type]$type) {
    $task = $asTask.MakeGenericMethod($type).Invoke($null, @($op))
    $task.Wait(-1) | Out-Null
    $task.Result
}
[Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime] | Out-Null
[Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType = WindowsRuntime] | Out-Null
[Windows.Media.Ocr.OcrEngine, Windows.Media.Ocr, ContentType = WindowsRuntime] | Out-Null
[Windows.Globalization.Language, Windows.Globalization, ContentType = WindowsRuntime] | Out-Null
$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($Path)) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$language = New-Object Windows.Globalization.Language 'zh-Hans-CN'
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($language)
if ($null -eq $engine) { $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages() }
if ($null -eq $engine) { Write-Output 'NO_ENGINE'; exit 2 }
$result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
$builder = New-Object System.Text.StringBuilder
foreach ($line in $result.Lines) {
    [void]$builder.AppendLine($line.Text)
}
[System.IO.File]::WriteAllText($Out, $builder.ToString(), (New-Object System.Text.UTF8Encoding $false))
"""

DISTANCE = re.compile(r"(\d+(?:\.\d+)?)\s*(公里|千米|km|KM|米|m|M)")
NOISE = re.compile(r"(打卡|未打卡|已打卡|签到|点位|距离|距你|当前|共|个点|/|\d+)")
# Words that belong to the run-record page, never to a checkpoint row.
RECORD_WORDS = ("里程", "用时", "配速", "成绩", "记录", "上传", "跑区", "分钟")


def flatten(text: str) -> str:
    """Drop OCR spacing and repair the decimal point OCR reads as a middle dot."""
    text = re.sub(r"\s+", "", text)
    return re.sub(r"(?<=\d)[·．。](?=\d)", ".", text)


def normalise(text: str) -> str:
    """Fold OCR spacing and drop the qualifiers that make the same place differ."""
    text = flatten(text)
    for suffix in ("西北门", "东北门", "西南门", "东南门", "西门", "东门", "南门", "北门",
                   "校区", "学院", "广场", "餐厅", "宿舍", "教学楼", "操场"):
        text = text.replace(suffix, "")
    return text


def ocr_lines(path) -> list[tuple[int, int, str]]:
    """[(x, y, text)] from the Windows OCR engine; raises if it is unavailable."""
    with tempfile.TemporaryDirectory(prefix="campus-run-ocr-") as temp:
        folder = Path(temp)
        script = folder / "ocr.ps1"
        script.write_text(OCR_SCRIPT, encoding="utf-8-sig")
        destination = folder / "lines.txt"
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
                 str(path), str(destination)],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                timeout=45,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError("OCR 45 秒没有返回，先关掉多余的窗口再试一次。") from None
        if result.returncode == 2:
            raise RuntimeError("这台电脑没有可用的 OCR 语言包，请在「设置 → 时间和语言」里安装中文识别。")
        if result.returncode or not destination.is_file():
            raise RuntimeError(f"OCR 失败：{(result.stderr or '').strip()[:200]}")
        text = destination.read_text(encoding="utf-8")
    lines = []
    for row in text.splitlines():
        row = row.strip()
        if row:
            # Reading order is enough: the app lists one checkpoint per line.
            lines.append((0, len(lines) * 10, row))
    return lines


def parse(lines: list[tuple[int, int, str]]) -> list[tuple[str, float]]:
    """Pull (checkpoint name, metres) pairs out of the OCR lines.

    The app puts the name and its distance on one line, but OCR sometimes splits
    them; a name on its own line adopts the distance that follows it.
    """
    found: list[tuple[str, float]] = []
    pending: str | None = None
    for _x, _y, raw in lines:
        text = flatten(raw.strip())
        if not text:
            continue
        # The record page also prints "里程 2.51 km" — those are results, not pins.
        if any(word in text for word in RECORD_WORDS):
            continue
        distance = DISTANCE.search(text)
        name = DISTANCE.sub("", text)
        name = re.sub(r"[\s,，.。:：%]+", "", name)
        name = NOISE.sub("", name)
        # "体育馆大门（距你317米）" loses the number and 距你 here, leaving a hollow
        # "体育馆大门（）" that then matches nothing (verified 2026-11-25: it made
        # 文典阁西门（） fall back to 文典阁 and dropped 体育馆大门 entirely).
        name = re.sub(r"[（(]\s*[）)]", "", name).strip("（）()")
        if distance:
            metres = float(distance.group(1))
            if distance.group(2) in ("公里", "千米", "km", "KM"):
                metres *= 1000.0
            # A checkpoint row always reads "（距你 N 米）"; anything else that
            # happens to contain a number is not a pin.
            if "距你" not in text and not re.search(r"[\u4e00-\u9fff]{2,}", name):
                continue
            if name:
                found.append((name, metres))
                pending = None
            elif pending:
                found.append((pending, metres))
                pending = None
            continue
        if len(name) >= 2 and not name.isdigit():
            pending = name
    return found


# 步道乐跑 does not use OSM names. It calls the stadium 体育馆, and 大门 means its
# south gate. Checked against the live list on 2026-11-25: the phone stood 41.7 m
# from 榴园, the app printed 体育馆大门 317 米 / 文典阁西门 378 米, and only the pair
# (主体育场南门, 文典阁西门) intersects there — the 磬苑体育馆* candidates are 270 m
# off and produce no intersection at all. Fuzzy matching alone would have picked
# 磬苑体育馆东门 and thrown the fix 600 m away.
APP_ALIASES = {
    "体育馆大门": "主体育场南门",
    "体育场大门": "主体育场南门",
    "体育馆正门": "主体育场南门",
    "体育场正门": "主体育场南门",
    "体育馆": "主体育场",
    "体育场": "主体育场",
    "操场": "主体育场",
    "田径场": "主体育场",
}


def match(names, labels: dict[str, Point], threshold: float = 0.55) -> dict[str, str]:
    """Map OCR spellings onto the road-network labels."""
    table = {key: normalise(key) for key in labels}
    pairs: dict[str, str] = {}
    for name in names:
        want = normalise(name)
        # Exact names win outright: normalise() drops 西门/南门…, so without this
        # 文典阁西门 ties with 文典阁 and loses to whichever comes first in the dict
        # (340 m away — verified 2026-11-25).
        if name in labels:
            pairs[name] = name
            continue
        alias = APP_ALIASES.get(name.strip()) or APP_ALIASES.get(want)
        if alias and alias in labels:
            pairs[name] = alias
            continue
        best, best_score = None, 0.0
        for key, folded in table.items():
            score = difflib.SequenceMatcher(None, want, folded).ratio()
            if folded and (folded in want or want in folded):
                score = max(score, 0.8)
            if score > best_score:
                best, best_score = key, score
        if best and best_score >= threshold:
            pairs[name] = best
    return pairs


def locate(observations: list[tuple[Point, float]], guess: Point | None = None,
           iterations: int = 80) -> Point:
    """Least squares position from distances to known points (Gauss-Newton).

    Two distances leave one degree of freedom, and today's screen often only
    shows two checkpoints, so a small ridge term pulls the solution toward the
    middle of the known points instead of letting it run off to infinity.
    """
    if len(observations) < 2:
        raise ValueError("至少需要两个打卡点的距离才能定位，请让页面完整显示打卡点后重试。")
    if guess is None:
        guess = (sum(p[0] for p, _ in observations) / len(observations),
                 sum(p[1] for p, _ in observations) / len(observations))
    prior = guess
    ridge = 0.0 if len(observations) >= 3 else 0.08
    x, y = guess
    for _ in range(iterations):
        jtj = [[0.0, 0.0], [0.0, 0.0]]
        jtr = [0.0, 0.0]
        for (px, py), distance in observations:
            dx, dy = x - px, y - py
            span = math.hypot(dx, dy) or 1e-6
            residual = span - distance
            jacobian = (dx / span, dy / span)
            for row in range(2):
                for column in range(2):
                    jtj[row][column] += jacobian[row] * jacobian[column]
                jtr[row] += jacobian[row] * residual
        jtj[0][0] += ridge
        jtj[1][1] += ridge
        jtr[0] += ridge * (x - prior[0])
        jtr[1] += ridge * (y - prior[1])
        determinant = jtj[0][0] * jtj[1][1] - jtj[0][1] * jtj[1][0]
        if abs(determinant) < 1e-12:
            break
        step_x = (jtj[1][1] * jtr[0] - jtj[0][1] * jtr[1]) / determinant
        step_y = (jtj[0][0] * jtr[1] - jtj[1][0] * jtr[0]) / determinant
        damping = 0.6
        x -= step_x * damping
        y -= step_y * damping
        if math.hypot(step_x, step_y) < 0.05:
            break
    return (x, y)


def read_screen(labels: dict[str, Point], screen: bytes | None = None) -> dict:
    """OCR the app screen and return checkpoints, position estimate and warnings."""
    if screen is None:
        from phone_screen import capture_usb_screen

        screen = capture_usb_screen()
    with tempfile.TemporaryDirectory(prefix="campus-run-ocr-") as folder:
        shot = Path(folder) / "screen.png"
        shot.write_bytes(screen)
        lines = ocr_lines(shot)
    found = parse(lines)
    flat = flatten("".join(text for _x, _y, text in lines))
    if not found:
        if "开始乐跑" in flat:
            raise RuntimeError("屏幕上还没有打卡点列表：先在地图上等下打卡点加载出来。")
        raise RuntimeError("这不是打卡点页面（看起来是记录页/首页），请回到「乐跑」页再读取。")
    pairs = match([name for name, _ in found], labels)
    checkpoints, observations, unmatched, others = [], [], [], []
    for name, metres in found:
        key = pairs.get(name)
        if key is None:
            unmatched.append(name)
            others.append({"ocr": name, "metres": metres})
            continue
        point = labels[key]
        checkpoints.append({"name": key, "ocr": name, "metres": metres, "point": point})
        if metres <= 900:
            observations.append((point, metres))
    result = {
        "checkpoints": checkpoints,
        "unmatched": unmatched,
        "others": others,
        "position": None,
        "position_error": None,
        "warnings": [],
        "text": "\n".join(text for _x, _y, text in lines),
        "running": False,
    }
    result["running"] = ("开始乐跑" not in flat) and ("用时" in flat)
    if len(observations) >= 2:
        position = locate(observations)
        residuals = [abs(math.dist(position, point) - metres) for point, metres in observations]
        result["position"] = position
        result["position_error"] = max(residuals)
        if len(observations) == 2:
            result["warnings"].append(
                "今天只有两个打卡点，位置是按两条距离估算的（误差可能上百米）；路线仍会按 50 米内经过全部打卡点。")
        if max(residuals) > 150:
            result["warnings"].append(f"定位残差 {max(residuals):.0f} 米偏大，可能有个打卡点识别错了；建议在地图上点一下起点。")
    else:
        result["warnings"].append("能用于定位的打卡点不足两个，起点请在地图上手动点选。")
    if unmatched:
        result["warnings"].append("没匹配到路网的名称：" + "、".join(unmatched))
    return result


def main() -> None:
    data = json.loads((Path(__file__).with_name("campus_map.json")).read_text(encoding="utf-8"))
    labels = {name: tuple(point) for name, point in data["labels"]}
    shot = None
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        shot = Path(sys.argv[1]).read_bytes()
    report = read_screen(labels, shot)
    print(f"打卡点 {len(report['checkpoints'])} 个：")
    for item in report["checkpoints"]:
        x, y = item["point"]
        print(f"  {item['name']:<8} 距你 {item['metres']:>6.0f} 米   ({x:.0f}, {y:.0f})   识别自「{item['ocr']}」")
    if report["position"]:
        print(f"当前位置约 ({report['position'][0]:.0f}, {report['position'][1]:.0f})，"
              f"最大残差 {report['position_error']:.0f} 米")
    for warning in report["warnings"]:
        print("! " + warning)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
