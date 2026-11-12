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