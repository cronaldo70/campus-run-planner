"""Throwaway probe: does this machine's Windows OCR read Chinese text out of a PNG?"""

import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
SAMPLE = HERE / "ocr_probe.png"

image = Image.new("RGB", (900, 420), "#ffffff")
pen = ImageDraw.Draw(image)
fonts = [r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf", r"C:\Windows\Fonts\simsun.ttc"]
font = None
for candidate in fonts:
    if Path(candidate).exists():
        font = ImageFont.truetype(candidate, 34)
        print("font", candidate)
        break
if font is None:
    sys.exit("no CJK font found")
lines = [
    "未打卡点",
    "文典阁西门   距你 249 米",
    "笃行北楼   距你 512 米",
    "磬苑广场   距你 780 米",
    "已打卡 1 / 3",
]
for index, text in enumerate(lines):
    pen.text((40, 30 + index * 66), text, fill="#111111", font=font)
image.save(SAMPLE)

script = r"""
param([string]$Path)
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
$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($Path)) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage((New-Object Windows.Globalization.Language 'zh-Hans-CN'))
if ($null -eq $engine) { $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages() }
if ($null -eq $engine) { Write-Output 'NO_ENGINE'; exit 2 }
$result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
Write-Output ("LANG " + $engine.RecognizerLanguage.LanguageTag)
foreach ($line in $result.Lines) { Write-Output ("LINE " + $line.Text) }
"""

probe = HERE / "ocr_probe.ps1"
probe.write_text(script, encoding="utf-8-sig")
out = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(probe), str(SAMPLE)],
                     capture_output=True, text=True, encoding="utf-8", errors="replace")
print("exit", out.returncode)
print(out.stdout)
print("ERR", out.stderr[:800])