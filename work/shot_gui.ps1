Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win2 {
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
}
"@
# ASCII only: PS 5.1 reads BOM-less scripts as ANSI, so no Chinese literals here.
$proc = Get-Process python, pythonw -ErrorAction SilentlyContinue |
    Where-Object { $_.MainWindowTitle -ne '' } | Select-Object -First 1
if (-not $proc) { Write-Output 'no window'; exit 1 }
Write-Output ("window title: " + $proc.MainWindowTitle)
[void][Win2]::SetForegroundWindow($proc.MainWindowHandle)
Start-Sleep -Milliseconds 800
$r = New-Object Win2+RECT
[void][Win2]::GetWindowRect($proc.MainWindowHandle, [ref]$r)
$w = $r.Right - $r.Left
$h = $r.Bottom - $r.Top
Write-Output ("size {0} x {1} at {2},{3}" -f $w, $h, $r.Left, $r.Top)
$bmp = New-Object System.Drawing.Bitmap $w, $h
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($r.Left, $r.Top, 0, 0, $bmp.Size)
$out = 'D:\gpt\2026-11-12\codex-handoff-ios26-location-test-md\work\gui-labels.png'
$bmp.Save($out, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose()
$bmp.Dispose()
Write-Output ('saved ' + $out)