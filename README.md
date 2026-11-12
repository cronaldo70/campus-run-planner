# 校园跑路线规划器（步道乐跑 / iOS）

把「今天想在校园里跑哪一段」变成一条真人跑出来的轨迹，并直接推到 iPhone 上让 App 以为是真实定位。

- 读手机屏幕上的打卡点（Windows OCR + 三角定位），不需要手输
- 自动排一条**不绕圈**的路线：起点=当前位置，经过全部打卡点，总里程可设下限（默认 2.5 km）
- 轨迹带圆角转弯、横向漂移、配速波动，不是机器人直线拼的矩形
- 生成 GPX，用 pymobiledevice3 的 DVT 定位模拟在真机上按时间推进回放，随时可停

## 快速开始

双击项目根目录的 `启动规划器.bat`（内部走 `work\.venv\Scripts\python.exe -B outputs\run-planner\run_planner.py`）。

1. 手机用 USB 连上、信任电脑、开开发者模式
2. 点「读取手机打卡点（自动识别）」——App 停在乐跑地图页
3. 确认「不绕圈」勾选，填目标配速（6:00 左右最像真人）
4. 点「开始模拟跑」，回放到终点后自动停；中途可按「停止模拟并恢复定位」

命令行等价物：

```bat
work\.venv\Scripts\python.exe -B outputs\run-planner\run_planner.py
work\.venv\Scripts\python.exe -B outputs\run-planner\checkpoint_reader.py shot.png
work\.venv\Scripts\python.exe -B outputs\run-planner\location_sim.py --play-gpx outputs\run-planner\generated\xxx.gpx --speed 60
```

## 目录

| 路径 | 作用 |
| --- | --- |
| `outputs/run-planner/run_planner.py` | Tkinter 主界面：标点、读手机、规划、模拟跑 |
| `outputs/run-planner/checkpoint_reader.py` | 截图 → OCR → 打卡点名字/距离 → 定位 |
| `outputs/run-planner/auto_route.py` | 开放式路线：Held-Karp 排序 + 里程补足 |
| `outputs/run-planner/road_network.py` | 校园路网（3015 节点 / 3247 段）、避障 Dijkstra |
| `outputs/run-planner/location_sim.py` | 轨迹生成（圆角/漂移/变速）+ GPX + DVT 回放 |
| `work/` | 一次性探针脚本、诊断图、建图脚本（`prepare_campus_map.py`） |
| `outputs/README.md` | 完整使用说明与排查表 |
| `outputs/TEST_REPORT.md` | 分阶段验收记录（含真机截图结论） |

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

1. **装 Python**：https://www.python.org/downloads/ 装 3.12（安装时勾 `Add python.exe to PATH`）。
2. **拿代码**：`git clone https://github.com/cronaldo70/campus-run-planner.git`，或在 Releases 页下载 `campus-run-planner-vX.Y.zip` 解压。
3. **装依赖并启动**（cmd 里执行）：
   ```bat
   cd campus-run-planner
   python -m pip install -r requirements.txt
   启动规划器.bat
   ```
   第一次会自己建 venv（`work\.venv`）并装 `pymobiledevice3`，之后双击 bat 就能开。

手机侧要求：iOS 17 及以上、USB 连电脑、点「信任此电脑」、设置 → 隐私与安全性 → **开发者模式**打开并重启一次。iOS 16 及以下、安卓、Mac/Linux 都不在支持范围（DVT 定位隧道只有 Windows 这套脚本实现）。

界面三步：`读取手机打卡点（自动识别）` → 确认勾选「不绕圈」和最短距离 → `开始模拟跑`。手机 App 里的「开始乐跑」要自己点，脚本无法点屏幕。

打包给别人的 zip：

```powershell
powershell -ExecutionPolicy Bypass -File tools\pack_release.ps1
# 产物 dist\campus-run-planner-v0.6.zip，只含源码/文档/启动脚本，不含 venv 与生成的 GPX
gh release create v0.6 dist\campus-run-planner-v0.6.zip --title "v0.6" --notes "读取打卡点 + 开放式路线"
```

## 关于传感器（速度计 / 指南针 / 陀螺仪）

DVT 的 `LocationSimulation` 只写 **CoreLocation 的位置**，不碰 CoreMotion。所以：

- **速度、方向（course）没有问题**：它们不是独立传感器读数，而是 CoreLocation 从位置序列算出来的。点间隔 1 秒、位置连续、配速稳定，App 拿到的 speed/course 就自然正确。
- **加速度计 / 陀螺仪 / 指南针拿不到**：iOS 27 没有越狱，CoreMotion 的原始数据无法注入；`CMPedometer` 的步数、HealthKit 的锻炼记录也补不了。
- 步道乐跑自己的规则页写的是「根据运动行为特征、个人运动大数据、登录设备综合分析」——判据是**轨迹统计**（配速区间、直线段、重复轨迹、跑区内外），不是传感器。真要拿步数说话，只能靠人拿着手机走/跑一段。

所以本工具能做的是把「轨迹层」做到人类水平：真实路网、圆角转弯、横向漂移、配速波动、开放式不闭合、单次里程不取整。**传感器层的伪造不在能力范围内**，这也是为什么建议配速别低于 4:30、别在凌晨、别每天同一条路线。