# 班级多用教学辅助终端

> 面向课堂教学的 Windows 悬浮式抽选与小组积分工具。  
> 核心：**不遮挡课件、不抢焦点、无需退出 PPT 全屏课件，就能完成随机点名、连抽和小组加减分。**  
> 可运行版本见 **GitHub Releases**。系统要求：**Windows 10 及以上**。

---

## 简介：它有什么作用？

这是一个面向课堂教学的桌面辅助终端，尤其适合 **学习小组模式** 的课堂。

在小组合作学习、课堂竞赛、随机点名、任务分配等场景中，老师经常需要：

- 随机抽一个人回答问题；
- 随机抽一个小组或小组代表；
- 一次抽 2~10 人进行分组活动、任务分配；
- 给各学习小组加/减分，记录课堂表现；
- 在 PPT 全屏放映时完成以上操作，不退出课件、不切屏、不打断讲课。

这个程序就是为这些场景设计的。它默认以一个小悬浮球停在屏幕右侧，双击即可抽人，右键可以连抽、打开积分管理或管理面板。所有关键窗口置顶但不抢焦点，结果弹窗会自动关闭，积分面板用完关闭也不会退出程序。老师可以一直停留在 PPT 全屏放映中，像用遥控器一样完成课堂互动。

可运行版本已发布在 **GitHub Releases**，下载即用；系统要求 **Windows 10 及以上**。

### 核心卖点

- **不挡课件**：悬浮球只有 50×50，默认贴在屏幕右侧边缘，可拖动到不遮挡 PPT 的位置。
- **无需退出课件**：悬浮球通过 Qt.Tool + 置顶 + Win32 `SetWindowPos` 强制置顶，可覆盖在 PPT 全屏之上；双击抽人、右键连抽/积分，全程不用退出全屏课件。
- **不抢焦点**：悬浮球和结果弹窗使用 `Qt.WindowDoesNotAcceptFocus`，不打断键盘输入和 PPT 操作。
- **学习小组模式**：内置小组积分面板，默认 6 组，可调 1~24 组，支持 `-1 / +1 / +2 / +3`、撤销、重命名、清零、自动保存。
- **公平抽选**：不是纯随机，采用“加权少抽优先 + 每人冷却”，长期看每人被抽次数更均衡，避免“怎么又是他”。
- **常驻托盘**：关闭主窗口或积分面板不会退出程序，只有托盘菜单“退出”才会结束进程。

---

## 适用场景

- **学习小组课堂**：小组竞赛、合作学习、课堂表现积分。
- **随机点名**：公平抽人回答问题，避免总抽同一人。
- **分组活动**：连抽 2~10 人，快速组队或分配任务。
- **PPT 全屏授课**：不退出课件即可抽人和加分。
- **多班级 / 多名单**：支持 txt 名单、数字学号、`stats.ini` 长期公平记录。

---

## 功能特性

### 不挡课件、无需退出课件的课堂操作

- 悬浮球 50×50，默认在屏幕右侧，可拖动。
- 始终置顶，可覆盖在 PPT 全屏之上。
- 双击悬浮球：抽 1 个人。
- 右键悬浮球：连抽 2~10 人 / 积分管理 / 打开管理面板。
- 结果弹窗居中显示，带 `✕`，5 秒后自动关闭。
- 连抽只弹一个窗口，多个名字同时滚动、一起揭晓。
- 悬浮球和弹窗不抢焦点，不打断输入。
- 积分面板可独立打开，关闭后程序继续运行，PPT 不受影响。

### 学习小组积分模式

- 默认 6 个小组，可调 1~24 组。
- 每组一张卡片：
  - 单击展开操作按钮：`-1 / +1 / +2 / +3`；
  - 双击组名重命名；
  - 右键可清零本组；
  - 支持 `Ctrl+Z` 撤销；
  - 快捷键 `1/2/3/4` 对应 `-1/+1/+2/+3`。
- 分数自动保存到 `config.ini`，重启不丢。
- 小组数量变化会重置组名和分数，避免旧分数挂错组。
- 卡片网格可滚动，24 组也能正常使用。

### 公平抽选

- 使用“加权少抽优先”算法，而不是 `random.choice`。
- 历史累计抽取次数越少，权重越高。
- 最近被抽中的人会被临时降权，避免连续抽中同一人。
- 长期抽取次数保存在 `stats.ini`，重启后仍然生效。
- 教师课前的“清空历史”只清历史与冷却，保留长期次数；只有“彻底重置”才会清零长期次数。

### 管理面板

- 名单来源：
  - 从 `.txt` 文件加载，一行一个名字，支持 `#` 注释；
  - 按数字范围生成名单，默认 1~99。
- 显示名单列表，冷却中的学生变灰并显示倒计时。
- 显示抽取历史表。
- 可配置每人冷却时间（1~60 分钟）。
- 支持开机自启动开关。
- 系统托盘菜单：
  - 显示主窗口；
  - 积分管理；
  - 抽取名字；
  - 彻底重置；
  - 退出。

### 稳定性

- 单实例保护：重复启动会唤醒已有实例并退出。
- 崩溃日志：`crash.log` 与 `config.ini` 同目录，记录 Python traceback 和原生故障。
- 原子写入：`config.ini` 与 `stats.ini` 都先写 `.tmp` 再 `os.replace()`。
- 只读目录回退：如果程序目录不可写，配置会落到 `%APPDATA%\ClassTerminal2411`。
- 关闭积分面板不会导致整个程序退出。

---

## 环境要求

- **Windows 10 及以上**；
- Python 3.10+（仅源码运行需要）；
- PyQt5（仅源码运行需要）。

安装依赖：

```bash
pip install PyQt5
```

> 本项目使用 `winreg`、`ctypes.windll`、Win32 `SetWindowPos` 等 Windows 特性，非 Windows 平台无法完整运行。

---

## 快速开始

### 下载可运行版本

前往 **GitHub Releases** 页面下载最新可运行版本。

- 系统要求：**Windows 10 及以上**；
- 下载后直接运行，无需安装 Python。

### 源码运行

```bash
python main.py
```

如果不想显示控制台，可使用：

```bash
pythonw main.py
```

首次启动且没有保存过名单文件时，程序会自动生成 1~99 的数字名单。

---

## 使用说明

### 悬浮球

| 操作 | 效果 |
|---|---|
| 左键双击 | 抽 1 个人 |
| 左键拖动 | 移动悬浮球 |
| 右键 | 打开菜单：连抽 / 积分管理 / 打开管理面板 |
| 抽取时 | 短暂闪金色 |

### 结果弹窗

- 单抽：显示 1 个名字。
- 连抽：一个弹窗中显示多个名字，同时滚动。
- 关闭方式：
  - 点击 `✕`；
  - 揭晓 5 秒后自动关闭。

### 积分面板

- 单击卡片：展开操作按钮。
- 双击组名：重命名。
- 右键卡片：清零本组。
- `Ctrl+Z`：撤销。
- `1/2/3/4`：`-1/+1/+2/+3`。
- “小组数量...”：修改组数，需二次确认，会清空所有组名与分数。
- “全部清零”：清空所有小组分数。

### 管理面板

- “名单来源”：
  - 浏览 `.txt` 文件；
  - 或按数字范围生成名单；
  - “重置为学号”恢复默认 1~99。
- “每人冷却”：设置冷却分钟数。
- “开机自启动”：写入当前用户注册表 Run 项。
- “积分管理”：打开小组积分面板。
- “隐藏悬浮球”：临时隐藏/显示悬浮球。
- “清空历史”：清空抽取历史与冷却状态，但保留长期公平计数。
- 托盘菜单“彻底重置...”：
  - 清空小组名称与积分；
  - 清空长期公平记录；
  - 清空抽取历史与冷却状态。

---

## 数据文件

### `config.ini`

与程序同目录，若目录不可写则放到 `%APPDATA%\ClassTerminal2411\config.ini`。

主要结构：

```ini
[meta]
app = 班级多用教学辅助终端
updated = 2026-09-27 10:30:00

[points]
group_count = 6
group_1 = 第一组
score_1 = 12
...
```

说明：

- `[points]` 保存小组数量、组名、分数；
- `set_group_count()` 会整段重建 `[points]`，组名恢复默认、分数清零；
- `reset_all()` 会删除早期版本遗留的 `[stats]` 段。

### `stats.ini`

与 `config.ini` 同目录，保存长期抽取次数。

```ini
[counts]
张三 = 5
李四 = 3
```

说明：

- 独立于 `config.ini`，因为“清空历史”不能清掉长期公平记忆；
- `save()` 是合并而非覆盖，换花名册不会清掉上一个班的记录；
- 次数为 0 时删除该行，而不是写 `name = 0`；
- 只有“彻底重置”会调用 `clear()`。

### `crash.log`

与 `config.ini` 同目录。

- 记录 Python 异常 traceback；
- 通过 `faulthandler` 记录原生崩溃；
- 最多 200 条，防止写满磁盘；
- 排错时首先查看该文件。0 字节通常表示没有崩溃。

---

## 核心设计：为什么不用纯随机？

`random.choice` 对“每一次”抽取是均匀的，但对“每个学生一学期”不是。40 人里出现有人被抽两次、有人一次没抽到是很常见的聚集现象，学生看到的就是“老师老抽他”。

因此 `NameEngine` 使用加权少抽优先模型：

```text
weight = (max_count - count + 1) ** FAIRNESS_STRENGTH
         * recency_penalty
```

参数位于 `namepicker/name_engine.py` 顶部：

| 参数 | 默认值 | 说明 |
|---|---:|---|
| `FAIRNESS_STRENGTH` | `4.0` | 向最少被抽者倾斜的强度。`P=9` 会退化为固定轮换。 |
| `RECENT_GAP` | `4` | 最近 N 次内被抽中过则降低权重。 |
| `RECENT_PENALTY` | `0.35` | 刚被抽中者的权重下限，避免连庄。 |
| `MIN_WEIGHT` | `0.01` | 保证每个有资格的人仍可被抽中。 |

两个关键语义：

- `clear_history()`：清空抽取历史与冷却状态，**保留**长期累计次数。对应教师课前的“清空历史”。
- `reset_fairness()`：连同长期累计次数一起清零。用于新学期、换班级或“彻底重置”。

修改公平性参数后，建议重新运行：

```bash
python tools/fairness_benchmark.py
python tools/fairness_burnin.py
```

---

## 项目结构

```text
.
├── main.py                     # 程序入口：组装组件、连接信号、进入事件循环
├── README.md
└── namepicker/
    ├── _init_.md               # 包内文件职责说明
    ├── config_store.py         # config.ini：小组积分与配置
    ├── stats_store.py          # stats.ini：长期抽取次数
    ├── name_engine.py          # 抽取逻辑：公平加权、冷却、历史
    ├── floating_ball.py        # 悬浮球
    ├── draw_popup.py           # 结果弹窗与滚动动画
    ├── points_window.py        # 小组积分面板
    ├── main_window.py          # 管理面板主窗口、托盘、自启动
    ├── crash_log.py            # 崩溃日志
    └── single_instance.py      # 单实例保护
└── tools/
    ├── smoke_test.py           # 冒烟测试
    ├── group_count_stress.py   # 小组数量功能 + 压力测试
    ├── config_check.py         # 存储往返测试（不依赖 Qt）
    ├── repro_quit.py           # “关闭面板导致退出”最小复现
    ├── fairness_burnin.py      # 1 万次单抽烧机测试 + χ² 检验
    ├── fairness_benchmark.py   # 公平性调参基准
    ├── reset_fairness_benchmark.py  # 教师清空历史工作流模拟
    └── weighting_demo.py       # 新旧算法分布对比
```

---

## 测试

所有测试建议从项目根目录运行。

### 快速检查

```bash
python tools/config_check.py
```

不依赖 Qt，运行最快，验证 `ConfigStore` 与 `StatsStore` 的读写、合并、清零、重置。

### 冒烟测试

```bash
python tools/smoke_test.py
```

不启动完整程序，直接构造各窗口并模拟操作。覆盖信号连接、布局、`config.ini` 落盘、撤销、连抽、小组数量、崩溃日志等。

> 构造 `MainWindow` 会读写真实注册表，测试会先备份开机自启动项，跑完后还原。

### 小组数量压力测试

```bash
python tools/group_count_stress.py
```

覆盖：

- 改小组数量后组名恢复默认、分数清零；
- 边界夹取 1~24；
- 数量未变化时不得修改分数；
- 彻底重置后恢复默认 6 组；
- 300 轮“改组数 × 加减分 × 重建卡片 × 存盘”压力；
- 旧卡片不会闪成独立窗口；
- 24 组时滚动条生效。

### 公平性测试

```bash
python tools/fairness_burnin.py
```

1 万次单抽烧机测试，包含：

1. 冷启动长跑分布；
2. 纯随机对照；
3. 偏斜起点追赶；
4. χ² 拟合检验；
5. 真实课间节奏；
6. 连续抽中率；
7. 领先者冷落时长。

```bash
python tools/fairness_benchmark.py
```

调参基准，对比 `FAIRNESS_STRENGTH = 2 / 4 / 6 / 9` 与纯随机，观察长期分布和单节课重复情况。

```bash
python tools/reset_fairness_benchmark.py
```

模拟教师每节课前“清空历史”的工作流，量化保留长期次数带来的改善。

```bash
python tools/weighting_demo.py
```

简化版对比，输出新旧算法分布表和每轮重复人数。

### 退出缺陷复现

```bash
python tools/repro_quit.py
```

用于确认 `main.py` 中的修复没有被改回：

- `QApplication` 默认 `quitOnLastWindowClosed = True`；
- 悬浮球是 `Qt.Tool`，不算主窗口；
- 主窗口缩到托盘后，关闭积分面板会导致整个程序退出；
- 修复方式：`app.setQuitOnLastWindowClosed(False)`。

---

## 开发注意事项

- 修改 `name_engine.py` 顶部公平性参数后，请重新运行公平性基准和烧机测试。
- `clear_history()` 与 `reset_fairness()` 语义不同，修改前务必确认。
- `points_window.py` 中旧卡片销毁前必须先 `hide()`，否则会闪成独立顶层窗口。
- 积分卡片样式按 `(选中态, 颜色)` 缓存，避免连续点击时高频重刷。
- 徽标定时器只创建一次并复用，不要在每次点击时重建 `QTimer`。
- 正式运行没有控制台时，排错首先看 `crash.log`。
- 两个实例会同时写 `config.ini`，因此有单实例保护，不要移除。
- 打包为 PyInstaller 窗口程序时，注意 `namepicker` 包和资源路径；打包后 `sys.executable` 是 EXE 路径。

---

## 常见问题

### 关闭积分面板后程序消失了？

已修复。`main.py` 中设置了：

```python
app.setQuitOnLastWindowClosed(False)
```

如果问题复现，运行 `python tools/repro_quit.py` 检查。

### 分数没有保存？

检查 `config.ini` 是否可写。程序目录只读时会自动回退到：

```text
%APPDATA%\ClassTerminal2411\config.ini
```

### 清空历史后公平性会失效吗？

不会。清空历史只清历史和冷却，长期抽取次数保留在 `stats.ini`。只有“彻底重置”才会清零长期次数。

### 为什么连抽人数不足？

因为部分学生仍在冷却中。连抽只从当前可用名单中抽取，返回实际抽到的人数并给出提示。

### 程序无提示退出怎么办？

查看 `crash.log`。如果文件为 0 字节，通常说明不是崩溃，而是正常退出或其他原因。

### 可运行版本在哪里下载？

在 **GitHub Releases** 页面下载。系统要求 **Windows 10 及以上**。

---

## 许可证

MIT License

Copyright (c) 2026 Gentole Lee

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
