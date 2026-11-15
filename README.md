# 校园跑路线规划器（步道乐跑 / iOS）

把「今天想在校园里跑哪一段」变成一条真人跑出来的轨迹，并直接推到 iPhone 上让 App 以为是真实定位。

- 读手机屏幕上的打卡点（Windows OCR + 三角定位），不需要手输
- 自动排一条**不绕圈**的路线：起点=当前位置，经过全部打卡点，总里程可设下限（默认 2.5 km）
- 轨迹带圆角转弯、横向漂移、配速波动，不是机器人直线拼的矩形
- 生成 GPX，用 pymobiledevice3 的 DVT 定位模拟在真机上按时间推进回放，随时可停

## 快速开始

双击项目根目录的 **`启动校园跑.bat`**，就这一个入口。

| 怎么开 | 打开什么 |
| --- | --- |
| 双击 | 实跑版：读打卡点 → 自动算起点 → 模拟跑（要连手机） |
| `启动校园跑.bat check` | 环境自检：Python / 依赖 / 手机连接 / 底图，逐项打勾 |
| `启动校园跑.bat debug` | 前台运行实跑版，报错直接留在控制台 |
| `启动校园跑.bat planner` | 旧版规划器（只画路线，不连手机）；也可以在界面里点「工具 → 打开旧版规划器」 |

第一次运行它会自己找 Python、建 `work\.venv`、装 `requirements.txt`（大约 1 分钟，只需一次），之后双击就是秒开。

跑一次的顺序：

1. 手机用 USB 连上、信任电脑、开开发者模式
2. 点「读取手机打卡点（自动规划）」——App 停在「乐跑」页的打卡点列表
3. 点「读取真实起点（自动）」——按屏幕上「距你 N 米」反推位置，不用手点
4. 填目标配速（5:00 左右最像真人），点右下角「模拟跑这条路线」
5. 窗口里 5 秒倒计时时，去手机上点「开始乐跑」；跑完自动停止并恢复真实定位

命令行等价物：

```bat
启动校园跑.bat check
work\.venv\Scripts\python.exe -B outputs\real-run-planner\real_run.py
work\.venv\Scripts\python.exe -B outputs\real-run-planner\real_position.py work\shot.png
work\.venv\Scripts\python.exe -B outputs\real-run-planner\real_run_sim.py
work\.venv\Scripts\python.exe -B outputs\run-planner\location_sim.py --play-gpx outputs\run-planner\generated\xxx.gpx --speed 60
```

## 目录

| 路径 | 作用 |
| --- | --- |
| `启动校园跑.bat` | 唯一的启动器：建 venv、查依赖、自检、开界面 |
| `tools/doctor.py` | 环境自检（Python / pymobiledevice3 / tkinter / 底图 / 手机连接） |
| `outputs/real-run-planner/real_run.py` | 主界面：避障地图 + 起点自动反解 + 一键模拟跑 |
| `outputs/real-run-planner/real_position.py` | 从「距你 N 米」反解手机位置（两圆相交 / 最小二乘 / 镜像解打分） |
| `outputs/real-run-planner/pedestrian_routes.py` | 步行路网：避障 Dijkstra、人行小径加权、里程补足 |
| `outputs/real-run-planner/read_checkpoints.py` | 截图 → OCR → 打卡点名 → 570 个名字里容错匹配 |
| `outputs/real-run-planner/real_run_sim.py` | 路线 → 时间戳轨迹 → 手机回放（+ 水域/建筑纠偏） |
| `outputs/real-run-planner/campus.json` | 底图：3015 节点 / 380 段路 / 427 个建筑水域 / 570 个打卡点名 |
| `outputs/run-planner/location_sim.py` | 轨迹生成内核（圆角/漂移/配速曲线）+ GPX + DVT 回放，两边共用 |
| `outputs/run-planner/run_planner.py` | 旧版规划器（菜单里可开，命令行 `... planner`） |
| `work/` | 一次性探针脚本、诊断图、建图脚本（`prepare_campus_map.py`） |
| `outputs/README.md` | 完整使用说明与排查表 |
| `outputs/TEST_REPORT.md` | 分阶段验收记录（含真机截图结论） |

## 为什么只留一个入口

原来有四个启动文件：`启动规划器.bat`、`Start-Planner.bat`、`Start-Real-Run.bat`、`Open-Real-Run-Planner.cmd`，其中三个只是互相转发参数，改一处要动四个文件。现在合成一个 `启动校园跑.bat`，bootstrap 只写一份；旧版规划器降级成它的一种模式，不再是并列的第二个入口。

## 有效成绩与异常判定

轨迹本身解决了「位置不动」「穿楼穿河」「绕圈太机械」这几种最容易被判异常的特征：

- 配速在 5:30–6:30 之间波动，起跑 200 米更慢，每公里有快慢差
- 转弯是圆弧不是折角，横向有 2 米左右的行进漂移
- 路线走的是真实路网，不切建筑、不下水
- 每段路只走一次（开放式路线），不出现完美闭合的重复轨迹

仍然建议：不要在凌晨刷、每天换起点、配速别固定成同一个数字、单次里程别总是整 3.00 km。

## 依赖

Python 3.12 + `pymobiledevice3`（见 `work\.venv`），Windows 10/11（OCR 用系统 `Windows.Media.Ocr`）。

## 别人怎么用（分发）

别人不需要懂代码，按这三步走：

1. **装 Python**：https://www.python.org/downloads/ 装 3.12（安装时勾 `Add python.exe to PATH`）。已经有 Python 也行，3.10–3.13 都能跑。
2. **拿代码**：在 Releases 页下载 `campus-run-planner-vX.Y.zip` 解压（或者 `git clone https://github.com/cronaldo70/campus-run-planner.git`）。
3. **双击 `启动校园跑.bat`**。第一次它会自己找 Python、建 `work\.venv`、装 `pymobiledevice3`（约 1 分钟），之后双击秒开。

开不起来时先双击进 `启动校园跑.bat check`：它会逐项打印 Python 版本、pymobiledevice3 版本、tkinter、底图、手机有没有被识别，并在最后给一句结论和该动哪里。国内网络装依赖慢，可以先设镜像：

```bat
set CAMPUS_RUN_PIP_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple
启动校园跑.bat
```

手机侧要求：iOS 17 及以上、USB 连电脑、点「信任此电脑」、设置 → 隐私与安全性 → **开发者模式**打开并重启一次。iOS 16 及以下、安卓、Mac/Linux 都不在支持范围（DVT 定位隧道只有 Windows 这套脚本实现）。

界面四步：`读取手机打卡点（自动规划）` → `读取真实起点（自动）` → 填目标配速 → `模拟跑这条路线`。手机 App 里的「开始乐跑」要自己点，脚本无法点屏幕。

打包给别人的 zip：

```powershell
powershell -ExecutionPolicy Bypass -File tools\pack_release.ps1 -Version v0.13
# 产物 dist\campus-run-planner-v0.13.zip，只含源码/文档/启动脚本，不含 venv 与生成的 GPX
gh release create v0.13 dist\campus-run-planner-v0.13.zip --title "v0.13" --notes "一个启动器 + 环境自检"
```

打完 zip 用 `work\test_release_boot.py` 验一遍：它把 zip 解到一个空目录，按陌生人的方式跑启动器，等窗口出现，再跑一次 `check` 确认自检报告正常。

## 关于传感器（速度计 / 指南针 / 陀螺仪）

DVT 的 `LocationSimulation` 只写 **CoreLocation 的位置**，不碰 CoreMotion。所以：

- **速度、方向（course）没有问题**：它们不是独立传感器读数，而是 CoreLocation 从位置序列算出来的。点间隔 1 秒、位置连续、配速稳定，App 拿到的 speed/course 就自然正确。
- **加速度计 / 陀螺仪 / 指南针拿不到**：iOS 27 没有越狱，CoreMotion 的原始数据无法注入；`CMPedometer` 的步数、HealthKit 的锻炼记录也补不了。
- 步道乐跑自己的规则页写的是「根据运动行为特征、个人运动大数据、登录设备综合分析」——判据是**轨迹统计**（配速区间、直线段、重复轨迹、跑区内外），不是传感器。真要拿步数说话，只能靠人拿着手机走/跑一段。

所以本工具能做的是把「轨迹层」做到人类水平：真实路网、圆角转弯、横向漂移、配速波动、开放式不闭合、单次里程不取整。**传感器层的伪造不在能力范围内**，这也是为什么建议配速别低于 4:30、别在凌晨、别每天同一条路线。