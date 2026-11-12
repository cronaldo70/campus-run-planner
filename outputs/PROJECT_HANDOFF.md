# 项目交接 · Windows 校园跑路线规划与 iPhone 定位调试

交接日期 **2026-11-12**。本机环境为 Windows 11 x64、Python 3.12.15、Tkinter 8.6 和 pymobiledevice3 11.52.1。真机为 iPhone `iPhone15,3`，系统 **iOS 27.2（24B119）**。最初目标为 iOS/iPadOS 26，实测版本以这台可用设备为准。

## 1. 交付范围

- **校园跑路线规划器**是 Windows 桌面界面，用于按本次打卡点、最低距离和配速设计实际跑步路线。它可以通过 USB 读取手机当前画面供对照，也可以离线手填。手机端的「开始乐跑」或「继续」负责正式记录和打卡，Windows 端的「开始实跑」打开路线计划和本地计时。
- **iPhone 定位调试工具**使用 pymobiledevice3 的 DVT 功能，在授权设备上测试固定位置、GPX 回放和真实定位恢复。调试观察使用苹果地图或自有测试 App，校园跑正式成绩以平台记录的实际运动为准。

## 2. 启动与安装

本机项目根目录为 `D:\gpt\2026-11-12\codex-handoff-ios26-location-test-md`。交付文件在 `outputs`，已安装的 Python 环境在 `work\.venv`。在资源管理器里双击[规划器启动器](run-planner/Open-Run-Planner.cmd)，窗口标题为「校园跑路线规划 · 实跑版」。从任意 PowerShell 目录也可以运行：

```powershell
$Project = 'D:\gpt\2026-11-12\codex-handoff-ios26-location-test-md'
$OutputDir = Join-Path $Project 'outputs'
$PythonExe = Join-Path $Project 'work\.venv\Scripts\python.exe'
$PmdExe = Join-Path $Project 'work\.venv\Scripts\pymobiledevice3.exe'
& (Join-Path $OutputDir 'run-planner\Open-Run-Planner.cmd')
```

迁移到新电脑时，在复制后的交付目录安装 Python 3.12（含 Tkinter）。纯路线规划可用 Python 标准库运行。USB 画面与定位调试需要安装 Apple Devices、连接并信任一台解锁的 iPhone、开启开发者模式，然后运行：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install "pymobiledevice3==11.52.1"
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\pythonw.exe .\run-planner\run_planner.py
```

本机 Python 启动器曾无法用 `py -3.12` 匹配已安装的 Astral 运行时。可用 `py -0p` 查找完整标签，或直接使用上面给出的本机解释器路径。[完整安装与 USB 排查](README.md)

## 3. 规划器操作

1. 每次活动先在手机确认本次名单。点击「更换打卡点」，可直接填写两个名称，或点击「读取手机画面」对照填写。当前默认的「文典阁西门」「笃行北楼」来自一次 USB 读取，活动刷新后按新名单修改。修改某一名称会清除该点的旧坐标。
2. 在校园底图上标记起点和两个打卡点。勾选「跑回起点」规划闭合路线，取消后可单独标记终点。自由打卡模式会比较两个顺序，也可以指定先经过 A 或 B。路线按 OpenStreetMap 路网估算，标点到所选道路的距离会显示在界面中。
3. 核对最低距离、允许的配速和目标配速。界面预填的 **3 公里、3:00–8:00/公里、目标 4:00/公里**来自本次对话和截图，按实际活动规则调整。开启「自动补足距离」时，闭合路线用整圈补足，单程路线用往返段补足并保留原终点。地图显示单圈或单程，底部显示次数和总距离。
4. 对于截图里的 **0.706 公里**单圈，3 公里门槛需要 **5 圈，约 3.530 公里**。按 4:00/公里估算用时 **14 分 07 秒**。如果活动限制重复路线，关闭自动补足并用「加途经点」规划其他路段。打卡半径、可跑区域和有效里程以手机活动规则及实际记录为准。
5. 点击「开始实跑」查看路线和本地计时。实际运动开始时，在手机的步道乐跑里点「开始乐跑」或「继续」。规划点位保存在当前窗口中，重开界面后需要重新标记。

## 4. 定位调试与恢复

以下命令使用第 2 节定义的 PowerShell 变量。先查看 USB 和开发者模式，确认苹果地图蓝点位于实际位置，再测试固定点或样例 GPX：

```powershell
& $PmdExe usbmux list --usb
& $PmdExe amfi developer-mode-status
& $PythonExe (Join-Path $OutputDir 'check_gpx.py') (Join-Path $OutputDir 'examples\demo_route.gpx')

# 任选一项测试，观察苹果地图后退出命令
& $PmdExe developer dvt simulate-location set -- 37.7749 -122.4194
# & $PmdExe developer dvt simulate-location play (Join-Path $OutputDir 'examples\demo_route.gpx')

# 退出测试命令后，再单独执行清除
& $PythonExe (Join-Path $OutputDir 'clear_location.py')
```

清除脚本只接受一台 USB 设备。它等待 DVT 的 `stopLocationSimulation` 应答。看到 `Device replied to the stop request` 后，在苹果地图点「我的位置」，以蓝点回到测试前区域作为恢复标准。若蓝点仍停在模拟区域，手动重启 iPhone，再确认实际位置。[恢复细节](TEST_REPORT.md#免重启恢复复测) · [Apple 重启步骤](https://support.apple.com/zh-cn/118259)

## 5. 验收与待接手

| 项目 | 已有证据与待验项 |
| --- | --- |
| Windows / USB | 已验证 Apple Devices 启动后的 USB 枚举、开发者模式状态和 DVT 只读连接。另已从 `C:\Windows\System32` 验证本机绝对路径能启动清除脚本和规划器。 |
| 固定点与恢复 | iOS 27.2 上苹果地图显示固定点。上游 `clear` 曾退出成功但位置未恢复。等待设备应答的清除方式分别在原会话和新会话测试成功，用户两次确认免重启回到真实位置。手动重启也已验证可恢复。先前清除失败的底层原因仍未确定。 |
| GPX | 离线校验 **10 项通过**，样例为 4 点、首尾 24 秒。真机经上游 Python API 回放约 24.1 秒，苹果地图出现沿路线的移动。待验「GPX 回放退出后执行独立清除脚本」、中途 Ctrl+C、拔线重连和 iOS/iPadOS 26。 |
| 规划器 | 本机验证启动、选点、计算路线、替换打卡点后清除旧坐标、自动补足距离、本地计时和 USB 画面预览。界面的里程为地图估算。步道乐跑的实际运动里程、打卡和成绩计入尚未验收。 |
| 步道乐跑位置排查 | 一次读取时页面显示「GPS 信号弱」，活动处于暂停状态。用户后来报告开始后位置未动，尚未收到实际走动时苹果地图与步道乐跑的对比结果。接手时优先区分固定的「始」标记、实际当前位置和顶部里程，再检查定位权限与精确位置。[Apple 定位权限说明](https://support.apple.com/zh-cn/102647) |

本机离线复测先执行 `Set-Location -LiteralPath $OutputDir`，再执行 `& $PythonExe -B -m unittest discover -s tests -v`。真机复测先记录测试前区域，最后由设备端确认位置恢复。交接和日志记录型号、系统版本与现象即可，设备标识和真实坐标留在本机。

## 6. 源码索引

| 文件 | 用途 |
| --- | --- |
| [run_planner.py](run-planner/run_planner.py) | Tkinter 主界面、打卡点编辑、圈数和配速计算、跑步计划及计时 |
| [road_network.py](run-planner/road_network.py) | 标点吸附到路段、按步行路网寻路 |
| [campus_map.json](run-planner/campus_map.json) | 安徽大学磬苑校区附近的离线底图和路网，地图数据按 ODbL 1.0 分发 |
| [phone_screen.py](run-planner/phone_screen.py) | 对单台 USB 设备执行 DVT 截图，在 Windows 本地预览 |
| [check_gpx.py](check_gpx.py) · [test_gpx.py](tests/test_gpx.py) · [demo_route.gpx](examples/demo_route.gpx) | 调试轨迹校验、单元测试和样例 |
| [clear_location.py](clear_location.py) | 请求设备停止位置模拟并等待应答 |
| [README.md](README.md) · [TEST_REPORT.md](TEST_REPORT.md) | 逐步使用说明与定位调试验收证据 |

底图提取脚本及当时的原始数据保存在工作区的 `work/prepare_campus_map.py` 和 `work/campus.osm`。维护地图时保留数据许可和界面署名。WanderPin 的可选安装步骤见 README，本次真机验收使用 pymobiledevice3。[地图数据来源](https://api.openstreetmap.org/api/0.6/map?bbox=117.1698,31.7578,117.1893,31.7805) · [OpenStreetMap 署名与许可](https://www.openstreetmap.org/copyright)
