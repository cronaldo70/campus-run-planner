# Windows 上测试 iPhone 开发调试定位

使用免费的开源工具 **pymobiledevice3 11.52.1**，通过 USB 测试系统定位。本次使用现有的 **iOS 27.2 iPhone** 验收。操作在 Windows PowerShell 执行，观察端使用苹果地图或你自己的定位测试 App。各项实测结果见 [验收报告](TEST_REPORT.md)。[上游 CLI 源码](https://github.com/doronz88/pymobiledevice3/blob/v11.52.1/pymobiledevice3/cli/developer/dvt/simulate_location.py)

## 校园跑路线规划界面

在 Windows 资源管理器里双击 [Open-Run-Planner.cmd](run-planner/Open-Run-Planner.cmd)。本项目可直接使用已有的 Python 环境。界面使用磬苑校区的离线底图。

1. 打卡点变更时，点「更换打卡点」。可以直接填名字，也可以在解锁的 USB iPhone 上打开活动地图后，点「读取手机画面」对照填写。界面预填本次读到的 **文典阁西门** 和 **笃行北楼**。
2. 单击地图选起点，再按 App 标记两个打卡点。勾选「跑回起点」会规划闭合路线，取消后可单独选终点。滚轮缩放，拖动地图平移。更改某个打卡点名称后，请重新在地图标记它。
3. 默认比较两个自由打卡顺序。你也可以指定先经过 A 或 B，或在两个打卡点之后加途经点来延长路线。界面会显示各标点到所选道路的偏移。
4. 按本次活动规则填写距离和配速。开启「自动补足距离」后，闭合路线按整圈计算，单程路线在终点后安排沿原路往返，直到估算总里程达到门槛。地图显示一圈或一段，下方会列出次数和总里程。例如单圈 0.706 公里，最短 3 公里时，规划为 5 圈、约 3.530 公里。若活动要求使用不同路段，可关闭自动补足，手动增加途经点。
5. 点右下角「开始实跑」查看路线和本地计时。正式记录在手机的步道乐跑点「开始乐跑」或「继续」。打卡位置、跑区和实际计入结果以手机 App 的显示为准。

### 从规划到真机回放

规划器已与 DVT 定位回放打通，不需要另开终端拼命令。[location_sim.py](run-planner/location_sim.py) 把地图路线按目标配速加密采样成 GPX，再在同一个 DVT 会话里逐点发送，结束时在同一会话发送 `stopLocationSimulation` 并等待设备应答。

1. 用数据线连好并解锁 iPhone，只接一台。规划器在「开始实跑」窗口里自己找设备，接多台会提示只连一台。
2. 手机打开步道乐跑，进入跑区页面点绿色「开始乐跑」。这一步必须在手机上点，USB 通道没有触屏注入能力。
3. 回到规划器点「开始模拟跑」。窗口显示进度条与「模拟跑进行中 n/N 个轨迹点」，生成的 GPX 同时保存在 `run-planner/generated/route-<时间>.gpx`。
4. 到目标距离后点「停止模拟并恢复定位」，或者让它跑完整个轨迹；两种情况都会清除模拟并等设备应答。随后在苹果地图点「我的位置」，蓝点回到真实位置才算恢复成功。
5. 只想留一份 GPX 给 CLI 或别的工具，点「只导出 GPX」。

回放节奏由 GPX 时间戳和目标配速决定：单圈 0.752 公里、目标配速 6:00、自动补足到 3 公里时，规划为 4 圈、3.007 公里、18 分 02 秒、1280 个轨迹点。调试时可以设环境变量 `RUN_PLANNER_SPEED` 加速，例如 `20` 表示 20 倍速，只加快发送间隔、不改变轨迹形状。

**配速别贴着自己的下限填。** 目标配速 4:00 对应每公里 4 分钟、3 公里 12 分钟，真人跑不出来，App 侧容易按异常配速判掉。校园跑常见可用区间是 5:00–7:00，建议先填 `6:00`。

不想开界面时，直接回放 `generated\` 里最新的轨迹（Ctrl+C 立即停止并恢复定位）：

```powershell
.\.venv\Scripts\python.exe -B .\run-planner\sim_now.py            # 真配速
.\.venv\Scripts\python.exe -B .\run-planner\sim_now.py --speed 10 # 排练
```

### 轨迹真实感与避障

规划器交给设备的不再是沿着路网折线走的直角轨迹。三层处理都在 [location_sim.py](run-planner/location_sim.py) 的 `build_track` 里，默认开启：

1. **圆角**（`round_corners`，`CORNER_RADIUS = 16.0`）：每个转角替换成与两段相切的二次贝塞尔曲线，等价于真人在路口切内弯。直路完全不弯，只削掉转角，整圈因此短 2% 左右。
2. **横向摆动**（`wobble`，`WOBBLE = 2.0` 米）：38 米、97 米、263 米三条互不整除的波长按 0.55/0.30/0.15 叠加成平滑偏移，模拟口袋里手机的 GPS 位置误差。真实手机上报的从来不是道路中心线。
3. **配速波动**（`pace_profile`，起始 22 秒渐加速、±7.5% 起伏）：时间戳由速度积分得到，平均配速仍严格等于设定值。目标 6:00 时，实际分段时间落在 5:46–6:27，和真人跑一次的成绩分布一致。

实测同一圈路线（笃行北楼—文典阁—磬苑广场，路网折线 1.399 公里）：16 个 112° 的硬拐变成最大 53° 的连续弯，单圈轨迹 1.367 公里；3 圈共 4.106 公里、24.64 分钟、2011 个轨迹点、分段 345–398 秒/公里。前后对比图见 `work/route_before.png` 与 `work/route_after.png`。

避障在 [road_network.py](run-planner/road_network.py)：路网里 3247 条边先用校园水域和建筑多边形做相交检测，压过建筑的边权重乘 40，踩到水面的边同样处理，因此 Dijkstra 会绕开；标点吸附时也会宁可多走 30 米，也不选一条穿过楼的路。全校区 131.7 公里步行路网里，0.43 公里属于这类需绕行的边。剩余穿楼只发生在标点本身落在建筑内部时，规划器会在状态栏提示「⚠ 路线仍有 建筑 X 米 穿行，建议调整标点」。

不需要仿真时可以关掉：`sim.build_track(route, pace=360, human=False)` 会退回到贴中心线的原样轨迹，`RoadNetwork(data, avoid=())` 会退回不避障的最短路径。

### 读取手机打卡点与不绕圈路线

界面左侧第一颗按钮「读取手机打卡点（自动识别）」会自己截一张设备屏幕、用 Windows 自带 OCR 读出打卡点和「距你 N 米」，再按三边定位算出你当前站在哪，然后直接排出一条开放式路线。

1. 手机上把步道乐跑停在显示打卡点的地图页（未开始乐跑），屏幕别锁。
2. 点「读取手机打卡点」。按钮变成「正在读取手机…」，几秒后地图上出现起点和每个打卡点，右侧列出名字。
3. 勾选「不绕圈（起点=当前位置，终点不限）」——默认已勾。规划器用 Held-Karp 求一条从当前位置出发、经过全部打卡点、终点自由的最短顺序；不足 2.5 公里时自动在后半段接一段绕行把里程补够，不会整圈重复。
4. 需要额外多经过某个地方，就在地图上再点一下，它作为途经点插进顺序里。

识别原理在 [checkpoint_reader.py](run-planner/checkpoint_reader.py)：OCR 只给出「名字 + 距离」，所以用双曲线定位的迭代解（Gauss-Newton，阻尼 0.6）在校园坐标系里反解坐标。实测用合成截图（真值 (12.0, 6.0)，距离为 140/161/191 米）解出 (12.1, 5.5)，误差 0.5 米，最大残差 0.2 米；读数超过 900 米的不参与定位，残差大于 150 米会在状态栏告警。今天只有两个打卡点时也能解（加了 ridge 阻尼，把解拉在两个已知点之间），不再要求三个方向。

### 打卡点名字不在路网里？用三点测距

步道乐跑的打卡点叫「名人景观墙碑记」「篮球场南门」这种细名字，campus_map.json 只有 13 个地标，靠名字匹配一定会漏——漏了就摆不出路线。现在的做法不认名字，只认数字：把模拟位置依次放到校园三个已知路点上，同一个打卡点三次「距你 N 米」的圆交点就是它自己的坐标。

```powershell
.\work\.venv\Scripts\python.exe -B .\outputs\run-planner\locate_checkpoints.py --settle 6
.\work\.venv\Scripts\python.exe -B .\outputs\run-planner\run_from_phone.py --minutes 11 --minimum 2.55
```

实测（2026-11-12，两个打卡点）：笃行北楼解出 (-65.6, 115.5)、文典阁西门解出 (-187.7, -29.0)，三次距离残差都是 0 米；和 campus_map 的地标中心相差 32 米与 68 米，差值正是「楼体中心 vs 楼门口」的距离，说明测距抓到的是 App 真正让你打卡的那个点。GUI 里的「读取手机打卡点」遇到不认识的名单会自动走这套测距（约 40 秒，会挪动模拟位置三次，所以必须在点「开始乐跑」之前做）。

`run_from_phone.py` 的顺序是：等打卡点列表 → 三点测距 → 排路线 → 等你点「开始乐跑」→ 按真实配速回放。加 `--range-only` 只看测距结果，加 `--no-range` 跳过测距。

屏幕上现在显示的是记录页时，读取会直接报「这不是打卡点页面」，不会把「有效里程 2.51 km」误当成一个打卡点。

路网标签离道路的距离决定了能不能「50 米内打卡」：磬苑广场 12.1、西门 5.2、南篮球场 15.8 米这些标签就在路边；文典阁 56.6、磬苑体育馆 49.6 米是因为标签在楼体中心，真实打卡点设在楼门口。所以规划器按「到道路接入点的距离」判定经过（实测 0.3–1.0 米），超过 45 米的点位会在计划里提示「图上位置离道路 N 米（多半在楼里），出发前确认一下」。

排路逻辑在 [auto_route.py](run-planner/auto_route.py)：`plan(net, start, checkpoints, minimum=2500.0, punch=50.0)` 先给每个标点算接入点，再用 `best_order()` 的 Held-Karp 动态规划（dp[1<<n][n]，起点固定、终点自由）串起来，最后用 `tail_legs` 补里程。13 个打卡点、起点 (12, 6) 的场景出来 4.72 公里、292 个顶点、0.1 秒、避障违规 0 项。

### 路线不能跑出校区

`campus_map.json` 的 `bounds` 是校区范围，但路网里带着几条伸到校外的城市干道（繁华大道方向能拉出两公里）。补里程的尾段如果落到那些干道上，App 会按「不在学校跑区」不给成绩，看起来就是「路线超出范围了」。

现在的约束做在 `road_network.py` 里：`RoadNetwork.__init__(..., container=None, outside_penalty=8.0)`，container 默认取 `bounds` 内缩 25 米（`(-844.73, -1220.38, 948.72, 1253.74)`），凡是中点落在 container 外的边，权重乘 8，Dijkstra 只有在别无选择时才会走；`auto_route.py` 的补里程候选也只用 `net.inside(node)` 为真的节点。`plan()` 返回 `outside` 米数，超过 30 米时计划里会写「⚠ 有 N 米在校区范围外」。

实测同一条「起点 (-220.99, -28.61) → 文典阁西门 → 体育馆大门、下限 2.5 公里」：2513 米、补里程 2 段、`outside` 0 米、避障违规 0 项、轨迹包围盒 (-221, -29, 481, 1030) 全在校区内。

### 右侧状态列怎么更新

读完手机后，起点 / A / B / 途经 / 终点这五行的名字和状态就地改写，不再靠底部一条说明：

```text
起点   已标记
A      文典阁西门     已定位 · 离路 33 米
B      体育馆大门     已定位 · 离路 50 米
途经   2 个打卡点
终点   不限
```

`render_rows()` 负责这件事：状态取「待标记 / 已标记 / 已定位 / 已定位 · 离路 N 米 / 不限 / 返回起点」，名字超过 8 个字截断加省略号。界面默认最短距离已从 3 公里改成 2.5 公里。

验收用的两个脚本直接驱动同一套界面逻辑，可在项目目录运行：

```powershell
.\.venv\Scripts\python.exe -B .\run-planner\test_wiring.py        # 规划 -> GPX 落盘
.\.venv\Scripts\python.exe -B .\run-planner\test_gui_flow.py      # 界面按钮 -> 真机回放 -> 恢复
```

`test_gui_flow.py` 会真的连设备，跑完整轨迹和手动停止两条路径，约 4 分钟。

地图由 OpenStreetMap 的校园附近路网提取，按 ODbL 1.0 分发。规划器的源码和地图数据在同一目录。[地图数据来源](https://api.openstreetmap.org/api/0.6/map?bbox=117.1698,31.7578,117.1893,31.7805) · [OpenStreetMap 署名与许可](https://www.openstreetmap.org/copyright)

## 1. 安装与检查

1. 从 Microsoft Store 安装并打开 **Apple Devices（Apple 设备）**。已安装的可直接打开。[Microsoft Store](https://apps.microsoft.com/detail/9np83lwlpz9k) · [Apple 安装说明](https://support.apple.com/en-mide/guide/devices-windows/mchl5ded2763/1.4/windows/10)
2. 执行 `py -3.12 --version`。如果缺少 `py`，先安装官方 Python 安装管理器，再打开一个新的 PowerShell 窗口。若管理器提示没有 3.12，执行 `py install 3.12`。如果 `py -0p` 已列出带发行方的 3.12，可用对应标签创建虚拟环境，例如本机的 `py -V:Astral\CPython3.12.15 -m venv .venv`。[Python 安装管理器](https://www.python.org/downloads/) · [Windows Python 文档](https://docs.python.org/3/using/windows.html)
3. 在含本 README 的目录执行下面的命令。虚拟环境可直接使用，所有命令从普通 PowerShell 启动即可。DVT 命令默认建立进程内 USB 隧道，本次已在 iOS 27.2 上验证该通道。[PyPI 固定版本](https://pypi.org/project/pymobiledevice3/11.52.1/) · [上游隧道说明](https://github.com/doronz88/pymobiledevice3/blob/v11.52.1/docs/guides/ios17-tunnels.md)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install "pymobiledevice3==11.52.1"
.\.venv\Scripts\python.exe -m pip check
$pmd = ".\.venv\Scripts\pymobiledevice3.exe"
& $pmd version
& $pmd doctor
```

`version` 应输出 `11.52.1`。若 `doctor` 提示 `usbmux daemon not reachable`，请在接上设备后按下一节重试。可以先执行离线检查。

```powershell
.\.venv\Scripts\python.exe .\check_gpx.py .\examples\demo_route.gpx
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

样例应报告 4 个轨迹点、首尾间隔 24 秒。自备 GPX 使用 `trk / trkseg / trkpt` 轨迹点。给每点添加含 `Z` 或 UTC 偏移的严格递增时间戳。独立航点 `wpt` 或路线点 `rtept` 需先导出为轨迹格式。校验通过后再回放。原始时间差决定各点的发送间隔。[GPX 1.1 规范](https://www.topografix.com/GPX/1/1/) · [上游 GPX 播放实现](https://github.com/doronz88/pymobiledevice3/blob/v11.52.1/pymobiledevice3/services/dvt/instruments/location_simulation_base.py)

## 2. USB 连接与真实位置基线

1. 每次只接一台测试设备。用支持数据传输的线直连 Windows，解锁设备，在 Apple Devices 和设备上按提示选择「信任」。确认 Apple Devices 侧边栏出现目标设备。[Apple USB 识别与排查](https://support.apple.com/en-ie/108643)
2. 在设备打开「设置 → 隐私与安全性 → 开发者模式」，按提示重启，解锁后确认开启。如果开关未出现，先在下列命令中运行 USB 列表，确认能读取设备，再运行 `& $pmd amfi reveal-developer-mode` 请求显示开关。随后在设备上手动开启。[Apple 开发者模式](https://developer.apple.com/documentation/xcode/enabling-developer-mode-on-a-device) · [上游命令实现](https://github.com/doronz88/pymobiledevice3/blob/v11.52.1/pymobiledevice3/cli/amfi.py)
3. 执行以下命令。验收时确认 USB 列表中出现你要测试的设备及其系统版本，并且开发者模式状态为 `true`。列表可含 UDID 和设备名称，结果仅在本机查看。如果 CLI 提示选择设备，选择刚才列出的 USB 设备。报告仅记录型号、系统版本和构建号。

```powershell
& $pmd usbmux list --usb
& $pmd amfi developer-mode-status
```

4. 在苹果地图点击「我的位置」并等待蓝点稳定，记录真实位置的大致区域和精度圈，供恢复时比较。也可在自有 App 中记录新收到的 Core Location 样本。样例位于旧金山，若与当前实际位置重合，请用一个明显不同的固定点和测试轨迹。

## 3. 固定位置、GPX 回放、恢复

每个命令在同一个 PowerShell 窗口顺序执行。新窗口需重新设置 `$pmd`。若用过 WanderPin，先结束其会话再开始此流程。

**固定位置。** 在运行期间观察地图蓝点移到示例坐标，确认的是「我的位置」蓝点。检查位置是否持续稳定，记录实际保持时长。看到 `Press ENTER to exit>` 后可按 Enter，也可按 Ctrl+C，等原命令退出再清除。

```powershell
& $pmd developer dvt simulate-location set -- 37.7749 -122.4194
```

结束固定位置测试后先执行下方的恢复验收，再开始 GPX。

**GPX 回放。** 从第一点开始观察蓝点依次移动，四个点的名义时间是 0、8、16、24 秒。用自有 App 可记录每次位置变化，地图可能合并或延迟显示更新。末点发出后，CLI 会继续保持会话直到按 Enter 或 Ctrl+C。回放中按 Ctrl+C 可停止。需要重播时清除后重新运行，会从第一点开始。该 CLI 没有暂停后续播命令。[上游命令实现](https://github.com/doronz88/pymobiledevice3/blob/v11.52.1/pymobiledevice3/cli/developer/dvt/simulate_location.py)

```powershell
& $pmd developer dvt simulate-location play .\examples\demo_route.gpx
```

**恢复验收。** 结束定位模拟进程，只保留一台解锁的 USB 测试设备，然后运行清除脚本。它使用 pymobiledevice3 发送清除请求并等待设备应答。使用本机已安装的环境时，这条命令可以在任意 PowerShell 目录运行：

```powershell
& 'D:\gpt\2026-11-12\codex-handoff-ios26-location-test-md\work\.venv\Scripts\python.exe' 'D:\gpt\2026-11-12\codex-handoff-ios26-location-test-md\outputs\clear_location.py'
```

如果你按第 1 节自行建了 `.venv`，请在包含该虚拟环境和本 README 的目录执行：

```powershell
.\.venv\Scripts\python.exe .\clear_location.py
```

看到 `Device replied to the stop request` 后，在苹果地图重新点「我的位置」，或在自有 App 中请求新的 Core Location 样本。以蓝点是否回到基线区域作为恢复标准。可以同时记录耗时和精度圈。

独立脚本已在 **iOS 27.2 固定点退出后** 验证免重启恢复。GPX 回放本身已通过，回放后接新版清除脚本的完整流程还待复测。若脚本报错或蓝点仍停在模拟区域，手动重启 iPhone 并确认蓝点回到基线，再做下一次模拟。[Apple 重启步骤](https://support.apple.com/zh-cn/118259)

如需验收中断场景，分别在回放途中按 Ctrl+C 和拔掉 USB 数据线，再验证清除。拔线后先结束原进程，重新接上同一设备、解锁并确认 USB 列表，再运行清除脚本。这两个场景本次未实测。

## 4. 排查

| 现象 | 操作 |
| --- | --- |
| `python` 打开商店或 `py -3.12` 找不到版本 | 用 `py -0p` 查运行时。通过安装管理器装 3.12，或使用已有 3.12 的标签或完整路径。虚拟环境建好后用其中的 `python.exe`。 |
| `Failed to connect to usbmuxd socket` | 先让 Apple Devices 识别设备，再运行 `Get-Service -DisplayName 'Apple Mobile Device Service' -ErrorAction SilentlyContinue` 和 `Test-NetConnection 127.0.0.1 -Port 27015`。若服务存在但已停，按 Apple 指南启动并重连。若 Apple Devices 仍无法提供 CLI 可访问的 USB 服务，检查 Apple 驱动并修复安装，或按上游 Windows 安装说明改用 Apple 官方 iTunes 安装程序提供的服务。[Apple 服务排查](https://support.apple.com/en-us/102347) · [pymobiledevice3 Windows 安装说明](https://github.com/doronz88/pymobiledevice3/blob/v11.52.1/docs/installation.md) |
| USB 列表为空或要求重新信任 | 解锁设备，换数据线或 USB 口并在 Apple Devices 确认设备出现。如果此前点了「不信任」，参考 Apple 步骤重置位置与隐私设置后再配对，该操作会重置 App 的隐私授权。[Apple 信任提示](https://support.apple.com/en-il/109054) |
| `InvalidServiceError`、开发者模式或隧道错误 | 先确认 USB 和开发者模式状态，再检查版本与完整报错。可用 `& $pmd -v developer dvt simulate-location set --userspace -- 37.7749 -122.4194` 强制默认的进程内路径并查看诊断。11.52.1 上游说明 iOS 17+ 的 DVT 通常无需挂载 DDI。仅在相关工具明确提示缺少 DDI 时，参考 `& $pmd mounter auto-mount` 和上游排查说明。[上游故障排查](https://github.com/doronz88/pymobiledevice3/blob/v11.52.1/docs/guides/troubleshooting.md) |
| 固定点很快跳回或 GPX 播完后进程仍在 | 确认使用 11.52.1、终端保持打开、USB 稳定。旧版的 userspace 等待逻辑曾导致隧道提前断开。回放后保持会话是预期行为，退出后运行清除脚本。[上游修复记录](https://github.com/doronz88/pymobiledevice3/releases/tag/v11.50.1) |
| 地图只显示末点或跳点 | 先看离线校验的点数和时长，确认使用样例、未加 `--disable-sleep`。对照终端的坐标与等待日志，用自有 App 或苹果地图的蓝点验证设备端变化。 |
| 规划器提示「请只连接并解锁一台 iPhone」 | USB 上有多台设备或设备未解锁。拔掉多余的设备，解锁目标机，再点「开始模拟跑」。 |
| `A userspace tunnel is already active in this process` | 同一进程里已有回放占用隧道。用界面上的「停止模拟并恢复定位」，等状态显示结束再重开一次；不要另开一个脚本同时回放。 |
| 步道乐跑没开始记录，或提示 GPS 信号弱 | 顺序错了：先在手机点「开始乐跑」，看到 App 自身在计时后，再在规划器点「开始模拟跑」。中途重开 App 会把定位会话丢掉，需重新点开始。 |
| 点「读取手机打卡点」后报「这台电脑没有可用的 OCR 语言包」 | 系统没装中文 OCR 组件。设置 → 时间和语言 → 语言 → 中文（简体）→ 选项 → 确认「光学字符识别」已安装，装完重启规划器。 |
| 读取打卡点后位置明显偏了（提示残差大于 150 米） | 屏幕上只认出 1–2 个打卡点，三点定位退化成圆交汇。把地图缩放到能看到全部打卡点再截，或者手动点一下起点。 |
| 计划里提示「图上位置离道路 N 米（多半在楼里）」 | 该标签在楼体中心，路网到不了 50 米内。路线已按楼门口的道路接入点走，出发前在手机上确认这个点确实变绿。 |
| 点「读取手机打卡点」后一直停在「正在读取手机…」 | 早期的版本在这里会卡死：名单里全是 App 自己的名字时，后台线程抛异常就没人把按钮恢复。现在任何异常都会写进 `planner-error.log` 并把按钮变回来，150 秒没结束也会强制报错。若仍然卡住，看 `planner-error.log` 首行。 |
| 打开规划器提示「规划器已经在运行」 | 同时开了两个窗口。两个窗口会抢同一台手机的定位隧道，读取一定卡住。关掉旧窗口，只留一个。 |
| 测距时提示「手机没有在 30 秒内接受模拟位置」 | 有别的脚本（`run_from_phone.py`、`locate_checkpoints.py`）正在占用隧道。等它退出，或按命令行过滤后结束它，再点读取。 |

诊断时记录报错首行、命令与退出码、Windows / iOS 版本以及是否已配对。分享日志或截图前遮盖设备名、UDID、序列号、配对记录、用户名、私有地址和实际位置。

## 5. 可选桌面工具 WanderPin

Windows 官方发布页提供 v1.0.0 安装包 `WanderPin-Setup.exe` 和免安装包 `WanderPin-Portable-Windows.zip`。可在发布页下载，运行安装器，或把 ZIP 全部解压后启动 `WanderPin.exe`。上游说明二进制未签名。如 Windows 阻止运行，可用下方源码流程或主线 CLI。发布包的运行和真机行为本次未实测。[官方发布页](https://github.com/udpluna/wanderpin/releases/tag/v1.0.0)

从源码运行时，在另一个可写目录执行。该标签的 GPX 导入使用了 `gpxpy`，安装列表未显式声明它。以下命令补齐该依赖，并固定与主线相同的 pymobiledevice3 版本。若本机只有带发行方标签的 Python，使用第 1 节的 `py -V:...` 写法创建 `venv)。[GPL-3.0 源码](https://github.com/udpluna/wanderpin/tree/v1.0.0) · [GPX 导入实现](https://github.com/udpluna/wanderpin/blob/v1.0.0/core/services.py#L138)

```powershell
git clone --depth 1 --branch v1.0.0 https://github.com/udpluna/wanderpin.git
Set-Location .\wanderpin
py -3.12 -m venv venv
.\venv\Scripts\python.exe -m pip install -r .\requirements.txt "pymobiledevice3==11.52.1" "gpxpy==1.6.2"
.\start.bat
```

连接后用 **Teleport** 验证固定点，用 **Import GPX file** 导入样例并播放。播放按钮支持暂停和继续，**Stop** 结束移动，**Real GPS** 尝试清除。WanderPin 会按界面速度走路线，它的 GPX 导入只保留坐标，因此按时间戳验收时使用主线 CLI。恢复时应在设备上检查蓝点。若卡在连接或恢复，关闭 WanderPin 后按第 2 节检查 USB，再用第 3 节的清除脚本。其日志在 `%APPDATA%\WanderPin\app.log`。[上游界面与连接说明](https://github.com/udpluna/wanderpin/tree/v1.0.0) · [待合入的清除修复](https://github.com/udpluna/wanderpin/pull/1)
