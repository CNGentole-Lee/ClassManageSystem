# 班级多用教学辅助终端 / Classroom Multi-Purpose Teaching Assistant Terminal

[![English](https://img.shields.io/badge/English-Jump%20to%20English-blue)](#english)　[中文](#chinese) [English](#english)

> 本文档为中文 + 英文双语版：英文请点击 **English** 按钮
>   
>This document is available in both Chinese and English: for English, please click the **English** button.
>   
> **注意：** 由于作者时间紧张，全面英配工作量过大，目前程序还是纯中文，望理解
>   
> **Attention please:** Due to the author's tight schedule, full English localization would require too much work, so the program is currently still available in Chinese only. Thank you for your understanding.

---

<a id="chinese"></a>

# 班级多用教学辅助终端

> 面向课堂教学的悬浮式随机点名 + 小组积分工具。
> **不遮挡课件、不抢焦点、不退出 PPT 全屏放映**，就能完成抽人、连抽和小组加减分。

![platform](https://img.shields.io/badge/platform-Windows%2010%2B%20%7C%20macOS%2011%2B-blue)
![python](https://img.shields.io/badge/python-3.10%2B-3776AB)
![license](https://img.shields.io/badge/license-MIT-green)

![悬浮球](docs/images/floating-ball.png)

---

## 目录

- [截图](#截图)
- [它解决什么问题](#它解决什么问题)
- [功能特性](#功能特性)
- [快速开始](#快速开始)
- [使用说明](#使用说明)
- [数据与安全](#数据与安全)
- [核心设计：为什么不用纯随机](#核心设计为什么不用纯随机)
- [跨平台支持](#跨平台支持)
- [打包](#打包)
- [项目结构](#项目结构)
- [测试](#测试)
- [开发注意事项](#开发注意事项)
- [常见问题](#常见问题)
- [已知限制](#已知限制)

---

## 截图

> 下面的图由 `python tools/make_screenshots.py` 直接抓取真实控件生成，界面改动后重跑一次即可同步，不是手绘示意图。

### 小组积分面板

单击卡片展开操作按钮，双击组名重命名，支持撤销与快捷键。底栏「操作日志」是日志的唯一入口。

![积分面板](docs/images/points-panel.png)

### 操作日志

每次积分变动自动记录一条，加密存储、只增不减、可自动回档。只读，不可编辑。

![操作日志](docs/images/log-viewer.png)

### 抽选结果弹窗

连抽只弹一个窗口，多个名字同时滚动、一起揭晓，`✕` 关闭或 5 秒后自动消失。

![结果弹窗](docs/images/draw-popup.png)

### 管理面板

名单加载、冷却倒计时、抽取历史、开机自启动、托盘入口。

![管理面板](docs/images/main-window.png)

### 深色模式

界面跟随系统外观（仅macOS），不是把浅色主题硬套一遍：
卡片、按钮、表格、日志区都有各自的深色配色，文字与背景保持足够对比度。
也可用环境变量强制预览：`CLASSMANAGE_THEME=dark python main.py`。

| 积分面板 | 操作日志 |
|---|---|
| ![深色积分面板](docs/images/points-panel-dark.png) | ![深色操作日志](docs/images/log-viewer-dark.png) |

![深色管理面板](docs/images/main-window-dark.png)

---

## 它解决什么问题

在小组合作学习、课堂竞赛、随机点名、任务分配这类场景里，老师经常需要：

- 随机抽一个人回答问题；
- 一次抽 2~10 人做分组活动或任务分配；
- 给各学习小组加/减分，记录课堂表现；
- **在 PPT 全屏放映中完成以上操作，不退出课件、不切屏、不打断讲课**。

程序默认以一颗 50×50 的悬浮球停在屏幕右侧：双击抽人，右键连抽 / 开积分面板 / 开管理面板。所有关键窗口置顶但不抢焦点，弹窗自动关闭，关闭积分面板也不会退出程序 —— 老师可以一直留在 PPT 全屏里，像用遥控器一样完成课堂互动。

### 核心特点

| 特点 | 说明 |
|---|---|
| **不挡课件** | 悬浮球只有 50×50，默认贴屏幕右侧边缘，可拖到任意位置 |
| **无需退出课件** | 悬浮球强制置顶（Windows 用 `SetWindowPos(HWND_TOPMOST)`；macOS 设置 NSWindow 层级与 Space 行为），可覆盖在 PPT 之上 |
| **不抢焦点** | 悬浮球与弹窗使用 `Qt.WindowDoesNotAcceptFocus`，不打断键盘输入与 PPT 操作 |
| **公平抽选** | 不是 `random.choice`，而是「加权少抽优先 + 每人冷却」，长期看每人被抽次数更均衡 |
| **积分防篡改** | AES-256-GCM 加密 + 三级自动回档，学生改文件改不动分数 |
| **常驻托盘** | 关闭主窗口/积分面板都不退出，只有托盘菜单「退出」才结束进程 |

---

## 功能特性

### 课堂操作（不打断讲课）

- 双击悬浮球 → 抽 1 人；右键 → 连抽 2~10 人 / 积分管理 / 打开管理面板。
- 揭晓前有滚动动画（1.8 秒），结果弹窗居中、带 `✕`、5 秒后自动关闭。
- 连抽只弹一个窗口，多个名字同时滚动、一起揭晓。
- 悬浮球与弹窗都不抢焦点。

### 学习小组积分

- 默认 6 组，可调 1~24 组；每组一张卡片。
- 单击展开 `-1 / +1 / +2 / +3`；双击组名重命名；右键清零本组。
- 支持 `Ctrl+Z` 撤销；快捷键 `1/2/3/4` 对应 `-1/+1/+2/+3`。
- 分数加密保存在 `config.dat`，重启不丢；被改坏或删掉会自动回档。
- 每次积分变动自动写入加密操作日志，底栏「操作日志」按钮只读查看。
- 改组数会整段重置组名与分数（换组数就是换了一套分组，旧分数没有可挂靠的组）。

### 公平抽选

- 「加权少抽优先」：历史累计被抽次数越少，权重越高。
- 最近被抽中的人临时降权，避免连庄。
- 长期次数存在 `stats.ini`，重启仍生效。
- 课前「清空历史」只清历史与冷却，保留长期次数；只有「彻底重置」才清零长期次数。

### 管理面板

- 名单来源：`.txt` 文件（一行一个名字，支持 `#` 注释），或按数字范围生成（默认 1~99）。
- 名单列表显示冷却倒计时，冷却中的学生变灰。
- 抽取历史表、每人冷却时间（1~60 分钟，默认 10）。
- 开机自启动开关（Windows 写注册表 Run 项；macOS 写 LaunchAgent）。
- 托盘菜单：显示主窗口 / 积分管理 / 抽取名字 / 彻底重置 / 退出。

---

## 快速开始

### 环境要求

- Windows 10 及以上（主要目标平台）、macOS 11 及以上；Linux 未验证。
- Python 3.10+、PyQt5、cryptography（仅源码运行需要）。

```bash
pip install -r requirements.txt
```

### 源码运行

```bash
python main.py
```

不想留控制台窗口：

```bash
pythonw main.py          # Windows：pythonw 不弹控制台
```

macOS 直接 `python main.py` 即可；想做成双击启动的程序见 [打包](#打包)。

首次启动会在程序目录旁生成加密配置；没有历史名单时会自动生成 1~99 的数字名单。

### 下载可运行版本

在 **GitHub Releases** 下载（若尚未发布，见 [打包](#打包) 自行构建）。

---

## 使用说明

### 悬浮球

| 操作 | 效果 |
|---|---|
| 左键双击 | 抽 1 个人 |
| 左键拖动 | 移动悬浮球 |
| 右键 | 菜单：连抽 2~10 人 / 积分管理 / 打开管理面板 / 抽取名字 / 彻底重置 / 退出 |
| 抽中时 | 短暂闪金色 |

### 积分面板

| 操作 | 效果 |
|---|---|
| 单击卡片 | 展开操作按钮 |
| 双击组名 | 重命名 |
| 右键卡片 | 清零本组积分 |
| `Ctrl+Z` | 撤销最近一次加减分 |
| `1 / 2 / 3 / 4` | `-1 / +1 / +2 / +3` |
| 「小组数量...」 | 改组数（需二次确认，会清空组名与分数） |
| 「全部清零」 | 所有小组归零（不可撤销） |
| 「操作日志」 | 打开只读日志查看器（唯一入口） |

### 管理面板

- 「名单来源」：浏览 `.txt` 名单，或按数字范围生成；「重置为学号」恢复默认 1~99。
- 「每人冷却」：1~60 分钟。
- 「开机自启动」：写入当前用户的自启动项。
- 「隐藏悬浮球」：临时隐藏/显示悬浮球。
- 「清空历史」：清空抽取历史与冷却，**保留**长期公平计数。
- 托盘「彻底重置...」：组名、积分、长期公平记录、抽取历史全部回到出厂状态。

---

## 数据与安全

积分和操作日志都是**防篡改存储**：同一份数据有四个副本，读取时逐级回退。

| 文件 / 位置 | 角色 | 程序行为 |
|---|---|---|
| `config.dat` | 积分主数据源（AES-256-GCM） | 读 + 写 |
| `config.dat.bak` | 同目录加密备份 | 读（回档）+ 写 |
| `QSettings` 隐蔽备份 | Windows 注册表 / macOS plist / Linux conf | 读（回档）+ 写 |
| `config.ini` | 明文查看副本 | **只写，永不读** |

积分读取顺序：

```text
config.dat → config.dat.bak → QSettings 隐蔽备份 → 旧版明文（一次性迁移）→ 默认值
```

任何一级读成功，都会用成功的数据把前面的副本重新写一遍（自动修复）。

### `config.dat` / `config.dat.bak`

- 内容为 `nonce(12B) + 密文 + GCM tag(16B)`，用记事本打开是乱码；
- GCM 是认证加密：改任何一个字节，解密必然失败，程序随即回档到下一级副本。

### 密钥

- 首次运行自动生成 32 字节密钥到 `~/.classmanage_key`（macOS/Linux 权限 `600`）；
- 不硬编码在源码里，随用户账户隔离；
- 密钥文件写不进去时程序不会崩，会降级为「本次运行临时密钥」并把原因记在
  `crypto_utils.key_error()` 里（可用 `tools/config_crypto_check.py` 排查）。

### `config.ini`（查看副本）

每次保存重新生成，首行是 `# 仅供查看，修改无效`。**程序从不读取它**，手工改它不会影响分数，想改请用界面。

### `QSettings` 隐蔽备份

同一份密文再存一份到系统级位置，学生不易找到、也不好删：

```text
Windows : HKCU\Software\YourOrg\ClassManageSystem
macOS   : ~/Library/Preferences/com.yourorg.ClassManageSystem.plist
Linux   : ~/.config/YourOrg/ClassManageSystem.conf
```

用 `QSettings` 而非 `winreg`，一套代码三平台通用，macOS 下不会 `ModuleNotFoundError`。写入失败静默忽略，绝不影响主流程。

### `points_log.dat`（操作日志）

- 自动记录：加/减分、撤销、清零本组、全部清零、改组数、彻底重置；
- 分数没变化时不记录；组名重命名不记录（不是积分变动）；
- **只增不减**：最多保留最近 400 条（`seq` 是历史累计条数并持续增长），因此
  「哪份副本的 `seq` 最大就用哪份」—— 拿旧密文覆盖主文件这种**回滚式篡改**也会被自动修回；
- 「彻底重置」不清空日志，只追加一条标记：审计记录不能靠一个按钮抹掉；
- 磁盘上**没有明文副本**，唯一查看入口是积分面板的「操作日志」按钮。

### `stats.ini`

长期抽取次数，与配置同目录，明文存储（不含积分）。

```ini
[counts]
张三 = 5
李四 = 3
```

独立成文件的原因：若与积分放在一起，课前「清空历史」会连带清掉长期次数，加权就退化成"每节课各自独立随机"。

### `crash.log`

与配置同目录，记录 Python traceback 与原生崩溃，最多 200 条。**0 字节表示没有崩溃**。

### 数据放在哪

配置与日志写在**程序所在目录**旁（打包后是 EXE / `.app` 同级目录，不在 `.app` 包内部）；若该目录不可写，则整体回退到：

```text
Windows        : %APPDATA%\ClassTerminal2411\
macOS / Linux  : ~/ClassTerminal2411/
```

---

## 核心设计：为什么不用纯随机

`random.choice` 对「每一次」抽取是均匀的，但对「每个学生一学期」不是。40 人里出现有人被抽两次、有人一次没抽到是很常见的聚集现象，学生看到的就是「老师老抽他」。

因此 `NameEngine` 使用加权少抽优先模型：

```text
weight = (max_count - count + 1) ** FAIRNESS_STRENGTH
         * recency_penalty
```

参数位于 `namepicker/name_engine.py` 顶部：

| 参数 | 默认值 | 说明 |
|---|---:|---|
| `FAIRNESS_STRENGTH` | `4.0` | 向最少被抽者倾斜的强度。调到 9 会接近固定轮换。 |
| `RECENT_GAP` | `4` | 最近 N 次内被抽中过则降低权重。 |
| `RECENT_PENALTY` | `0.35` | 刚被抽中者的权重下限，避免连庄。 |
| `MIN_WEIGHT` | `0.01` | 保证每个有资格的人仍有可能被抽中。 |

两个语义不同的重置：

- `clear_history()`：清空抽取历史与冷却，**保留**长期累计次数 —— 对应教师课前的「清空历史」。
- `reset_fairness()`：连同长期累计次数一起清零 —— 用于新学期、换班级或「彻底重置」。

修改公平性参数后建议重跑基准：

```bash
python tools/fairness_benchmark.py
python tools/fairness_burnin.py
```

---

## 跨平台支持

| 能力 | Windows | macOS | Linux |
|---|---|---|---|
| 抽选 / 积分 / 日志 | ✅ | ✅ | 未验证 |
| 盖住全屏应用 | ✅ `SetWindowPos` | ✅ accessory 策略 + 浮层属性（已实测） | 未验证 |
| 托盘 / 菜单栏图标 | ✅ 彩色托盘图标 | ✅ 模板图；**菜单栏自动隐藏时不显示** | 未验证 |
| 浅色 / 深色模式 | ❌ 深色未生效 | ✅ 跟随系统 | 未验证 |
| 系统级隐蔽备份 | ✅ HKCU 注册表 | ✅ `~/Library/Preferences` plist | ✅ `~/.config` |
| 悬浮球置顶 | ✅ `SetWindowPos(HWND_TOPMOST)` | ✅ 层级 + `CanJoinAllSpaces`/`FullScreenAuxiliary`/`Stationary` | 未验证 |
| Dock 图标 | — | ❌ 无（accessory 策略的代价，见下） | — |
| 开机自启动 | ✅ 注册表 Run 项 | ✅ LaunchAgent | ❌（返回失败） |
| 冻结后数据位置 | ✅ EXE 同级目录 | ✅ `.app` **同级**目录（不在包内） | — |

设计约定：**不直接 `import winreg`**（改为 `try/except ImportError`），平台专有调用全部包在 `try/except` 里并静默降级；存储层统一走 PyQt5 自带的 `QSettings`；配色与字体统一由 `namepicker/theme.py` 提供。

---

## 打包

> **PyInstaller 不支持交叉编译**：在 macOS 上只能打出 macOS 程序，`.exe` 必须在 Windows 上打包（涉及到GUI相关，并且无法通过Somketest， CI无法测试故新Commit取消CI）

### Windows —— Windows 10及以上电脑+相关依赖

```bat
packaging\windows\build.bat
```

脚本会自动建 `.venv-build` 虚拟环境、装依赖、跑自检、打包，产物 `dist\ClassManageSystem.exe`。默认走清华 PyPI 镜像（国内下载 PyQt5 快得多），可换源：

```bat
packaging\windows\build.bat official                                 :: 官方 PyPI
packaging\windows\build.bat https://mirrors.aliyun.com/pypi/simple/  :: 阿里
```

镜像只作用于这条命令，**不写 `pip.ini`、不改系统全局 pip 配置**。

### macOS

```bash
packaging/macos/build.command        # 双击也可以
```

产物 `dist/ClassManageSystem.app`。打出来是**当前 CPU 架构**的原生程序（Apple Silicon 上是 arm64；要通用需 universal2 的 Python + PyQt5）。

### 产物说明

- 单文件窗口程序，目标机不需要装 Python；
- 配置与日志写在 EXE / `.app` 同级目录（只读目录则回退 `%APPDATA%\ClassTerminal2411`），密钥在用户主目录；
- **未做代码签名**：Windows 首次运行 SmartScreen 会提示「未知发布者」，点「更多信息 → 仍要运行」；macOS 拷给别人后首次需**右键 → 打开**。

---

## 项目结构

```text
.
├── main.py                          # 入口：组装组件、连接信号、进入事件循环
├── requirements.txt
├── names.txt                        # 示例名单
├── docs/images/                     # README 截图（由 tools/make_screenshots.py 生成）
│
├── namepicker/                      # 主程序包
│   ├── _init_.md                    # 包内文件职责说明
│   ├── config_store.py              # config.dat：加密配置 + 三级回档
│   ├── crypto_utils.py              # AES-256-GCM 与 ~/.classmanage_key 密钥管理
│   ├── log_store.py                 # points_log.dat：加密操作日志 + 防回滚
│   ├── backup_store.py              # QSettings 系统级隐蔽备份（跨平台）
│   ├── stats_store.py               # stats.ini：长期抽取次数
│   ├── name_engine.py               # 抽取逻辑：公平加权、冷却、历史
│   ├── floating_ball.py             # 悬浮球（含跨平台强制置顶）
│   ├── draw_popup.py                # 结果弹窗与滚动动画
│   ├── points_window.py             # 积分面板 + 操作日志查看器
│   ├── main_window.py               # 管理面板、托盘、开机自启动
│   ├── single_instance.py           # 单实例守护（QLocalServer 判活）
│   └── crash_log.py                 # 崩溃日志
│
├── packaging/
│   ├── windows/                     # PyInstaller spec、图标、版本信息、build.bat
│   ├── macos/                       # PyInstaller spec、icns、build.command
│   └── make_icon.py                 # 生成 Windows 图标（Qt 渲染，无需 Pillow）
│
├── tools/                           # 测试与开发脚本（不随程序分发）
│   ├── config_check.py              # 存储往返测试（不依赖 Qt）
│   ├── config_crypto_check.py       # 加密存储 / 篡改回档 / 迁移 自检
│   ├── log_crypto_check.py          # 操作日志：自动记录 / 篡改回档 / 防回滚
│   ├── windows_check.py             # Windows 平台自检（注册表 / 置顶 / 编码 / 占用）
│   ├── macos_check.py               # macOS 平台自检（菜单栏 / 浮层 / 深色 / 全屏覆盖）
│   ├── _fullscreen_helper.py         # 自检用：进入原生全屏的辅助进程
│   ├── smoke_test.py                # GUI 冒烟测试
│   ├── group_count_stress.py        # 小组数量功能 + 300 轮压力
│   ├── make_screenshots.py          # 生成 docs/images 下的 README 截图
│   ├── fairness_burnin.py           # 1 万次单抽烧机 + χ² 检验
│   ├── fairness_benchmark.py        # 公平性调参基准
│   ├── reset_fairness_benchmark.py  # 教师清空历史工作流模拟
│   ├── weighting_demo.py            # 新旧算法分布对比
│   ├── repro_quit.py                # 「关闭面板导致退出」最小复现
│   └── _settings_isolation.py       # 测试用的 QSettings 命名空间隔离
│
└── .github/workflows/build-windows.yml   # CI：x64 Windows 打包 --已弃用
```

---

## 测试

所有测试从项目根目录运行。

```bash
python tools/config_check.py           # 最快，不依赖 Qt：存储读写/合并/清零/重置
python tools/config_crypto_check.py    # 加密存储：乱码、手改无效、篡改/删除回档、迁移
python tools/log_crypto_check.py       # 操作日志：自动记录、无明文副本、防回滚、只增不减
python tools/windows_check.py          # 平台自检（在 Windows 上才跑真实分支）
python tools/macos_check.py            # 平台自检（菜单栏图标 / 浮层属性 / 深色 / 激活策略）
python tools/macos_check.py --fullscreen   # 额外跑一次「真·原生全屏」覆盖测试
python tools/smoke_test.py             # GUI 冒烟：信号连接、布局、落盘、撤销、连抽
python tools/group_count_stress.py     # 小组数量功能 + 300 轮压力
```

- `config_crypto_check` / `log_crypto_check` 会在临时 HOME 下运行，**不碰你的真实数据**；装了 PyQt5 时还会验证真实的 QSettings 隐蔽备份。
- 冒烟测试构造 `MainWindow` 会读写真实注册表（Windows），脚本会先备份开机自启动项、跑完还原；macOS/Linux 自动跳过。
- 测试统一使用隔离的 QSettings 命名空间，不会污染真实注册表 / plist。

公平性专项：

```bash
python tools/fairness_burnin.py        # 冷启动长跑、偏斜追赶、χ² 检验、连庄率…
python tools/fairness_benchmark.py     # 对比 FAIRNESS_STRENGTH = 2/4/6/9 与纯随机
python tools/reset_fairness_benchmark.py   # 模拟每节课前「清空历史」的工作流
python tools/weighting_demo.py         # 新旧算法分布对比
```

重新生成 README 截图：

```bash
python tools/make_screenshots.py                          # 浅色（默认）
CLASSMANAGE_THEME=dark python tools/make_screenshots.py   # 深色，输出 *-dark.png
```

截图脚本会把窗口移到屏幕外再 `grab()`，不会在你桌面上闪；数据用临时目录，
不碰真实配置。

---

## 开发注意事项

- 改 `name_engine.py` 顶部公平性参数后，请重跑公平性基准与烧机测试。
- `clear_history()` 与 `reset_fairness()` 语义不同，改之前务必确认。
- `points_window.py` 中旧卡片销毁前必须先 `hide()`，否则会闪成独立顶层窗口。
- 积分卡片样式按 `(选中态, 颜色)` 缓存，避免连续点击时高频重刷。
- 徽标定时器只创建一次并复用，不要在每次点击时重建 `QTimer`。
- 正式运行没有控制台时，排错先看 `crash.log`。
- 单实例守护**不能只看 `QSharedMemory`**：Unix 上共享内存段不随进程消失而释放，
  被 `kill -9` 后残留的孤儿段会让下次启动永远静默退出。现在以 `QLocalServer`
  能否连通作为存活判据，共享内存仅作兜底。
- 打包相关：`config_store._app_dir()` 对 `.app` 有专门处理，避免把数据写进应用包内部；
  Windows 的 `.bat` 必须是**纯 ASCII + CRLF**（`.gitattributes` 已强制 `eol=crlf`），
  且 `REM` 行里不能出现未配对的圆括号 —— cmd 的括号配对统计会因此从行中间截断命令。

---

## 常见问题

### 双击图标没反应，进程一闪就退？

旧版本的单实例实现会在共享内存残留后永久拒绝启动（见「开发注意事项」）。当前版本已改为
`QLocalServer` 判活，被强杀后能正常重启。若仍复现，先确认没有另一个实例在跑：

```bash
pgrep -fl ClassManageSystem        # macOS
tasklist | findstr ClassManage     # Windows
```

### 关闭积分面板后程序消失了？

已修复，`main.py` 中设置了 `app.setQuitOnLastWindowClosed(False)`。复现脚本：`python tools/repro_quit.py`。

### 分数没有保存？

检查程序所在目录（放 `config.dat` 的那个目录）是否可写；只读时会自动回退到
`%APPDATA%\ClassTerminal2411\`（macOS/Linux：`~/ClassTerminal2411/`）。
`python tools/config_crypto_check.py` 可以定位是密钥、密文还是目录权限的问题。

### 学生改了 `config.ini` 的分数，为什么没生效？

因为程序从不读取 `config.ini`，它每次保存都会被加密数据覆盖。真正生效的是 `config.dat`
（外加 `.bak` 与系统级隐蔽备份）。改 `config.dat` 也一样：GCM 认证加密会让解密失败，
程序自动从备份回档。想删数据也不行 —— 删掉主文件会从 `.bak` 恢复，两个都删会从
QSettings 隐蔽备份恢复。

### 操作日志能删吗？

不能，这是设计。日志只增不减，「彻底重置」也只追加一条标记。想留档可以截图或复制
查看器里的文本。

### 「清空历史」后公平性会失效吗？

不会。它只清历史与冷却，长期次数保留在 `stats.ini`；只有「彻底重置」才清零长期次数。

### 为什么连抽人数不足？

因为部分学生仍在冷却中。连抽只从当前可用名单里抽，返回实际抽到的人数并给出提示。

### 程序无提示退出怎么办？

看 `crash.log`。0 字节通常说明不是崩溃（可能被强杀或正常退出）。

### 打包时报 `'xxx' 不是内部或外部命令`？

`.bat` 被存成了 UTF-8/LF 或 `REM` 行里有未配对括号。本仓库的 `build.bat` 已修正并加了
`.gitattributes`；自行改动时请保持纯 ASCII + CRLF。

---

## 已知限制

- **未做代码签名/公证**：Windows 有 SmartScreen 提示，macOS 拷贝到别的机器需右键打开。
- **架构跟随构建机**：Apple Silicon 上打出 arm64 的 `.app`，Intel Mac 不能跑，没有写双架构冗余，Intel Mac需要自己运行打包的Shell程序；
- **macOS 全屏覆盖靠「应用激活策略」**：窗口层级再高也没用 —— regular 应用自己占着
  一个桌面 Space，别的 App 进全屏后它压根不在那个 Space 里。本程序启动时会切到
  **accessory** 策略（`LSUIElement`，与 Alfred / Raycast 相同），窗口才能加入
  全屏 Space。代价是**没有 Dock 图标**；入口改为悬浮球 + 菜单栏图标。
  已用 `CGWindowList onScreenOnly` 对真实原生全屏做过实测：
  `python tools/macos_check.py --fullscreen` 会显示「悬浮球可以盖在原生全屏应用之上 ✅」。
- **macOS 菜单栏图标**：图标本身是模板图、状态项也确实创建了（自检会验证
  `NSStatusBarWindow`）。如果系统开启了「自动隐藏菜单栏」（`_HIHideMenuBar=1`），
  菜单栏收起时状态项按系统设计就不显示 —— 这不是程序问题。此时可用悬浮球右键菜单，
  里面已包含托盘的全部动作（抽取名字 / 积分管理 / 打开面板 / 彻底重置 / 退出）。
  想要常驻可见，请在 系统设置 → 外观（或桌面与程序坞）关闭「自动隐藏菜单栏」。
- **密钥与账户同权限**：密钥在用户主目录，若教师与学生共用同一个系统登录账户，
  学生理论上可以读取密钥。这是「用户级密钥」方案的固有边界。
- **Linux 未验证**：代码有平台守卫不会崩，但托盘/置顶行为未测试。

> 许可证（MIT）见文末英文版 [License](#license)。

---
---

<a id="english"></a>

# Classroom Multi-Purpose Teaching Assistant Terminal

[![中文](https://img.shields.io/badge/中文-回到中文-red)](#chinese)

> A floating random name picker + group scoring tool for classroom teaching.
> Draw names, run multi-draws, and add or deduct group points **without covering your slides, without stealing focus, and without leaving PowerPoint's full-screen slideshow**.

![platform](https://img.shields.io/badge/platform-Windows%2010%2B%20%7C%20macOS%2011%2B-blue)
![python](https://img.shields.io/badge/python-3.10%2B-3776AB)
![license](https://img.shields.io/badge/license-MIT-green)

![Floating ball](docs/images/floating-ball.png)

---

## Table of Contents

- [Screenshots](#screenshots)
- [What Problem It Solves](#what-problem-it-solves)
- [Features](#features)
- [Quick Start](#quick-start)
- [Usage](#usage)
- [Data & Security](#data--security)
- [Core Design: Why Not Pure Randomness](#core-design-why-not-pure-randomness)
- [Cross-Platform Support](#cross-platform-support)
- [Packaging](#packaging)
- [Project Structure](#project-structure)
- [Testing](#testing)
- [Development Notes](#development-notes)
- [FAQ](#faq)
- [Known Limitations](#known-limitations)
- [License](#license)

---

## Screenshots

> The images below are generated by `python tools/make_screenshots.py`, which captures the real widgets. Re-run it after any UI change to keep them in sync — they are not hand-drawn mockups.

### Group Points Panel

Single-click a card to expand its action buttons, double-click a group name to rename it, undo and keyboard shortcuts are supported. The "Activity Log" button in the bottom bar is the only entry point to the log.

![Points panel](docs/images/points-panel.png)

### Activity Log

Every points change is recorded automatically: encrypted, append-only, and able to roll back by itself. Read-only, not editable.

![Activity log](docs/images/log-viewer.png)

### Draw Result Popup

A multi-draw opens only one window; several names scroll at the same time and are revealed together. Close it with `✕` or let it disappear automatically after 5 seconds.

![Result popup](docs/images/draw-popup.png)

### Management Panel

Roster loading, cooldown countdown, draw history, launch-at-startup, tray entry.

![Management panel](docs/images/main-window.png)

### Dark Mode

The UI follows the system appearance (macOS only) — it is not just the light theme inverted:
cards, buttons, tables and the log area each have their own dark palette, and text keeps sufficient contrast against the background.
You can also force a preview with an environment variable: `CLASSMANAGE_THEME=dark python main.py`.

| Points panel | Activity log |
|---|---|
| ![Dark points panel](docs/images/points-panel-dark.png) | ![Dark activity log](docs/images/log-viewer-dark.png) |

![Dark management panel](docs/images/main-window-dark.png)

---

## What Problem It Solves

In scenarios such as group collaborative learning, classroom competitions, random name picking, and task assignment, teachers frequently need to:

- randomly pick one student to answer a question;
- pick 2–10 students at once for group activities or task assignment;
- add or deduct points for each study group and record classroom performance;
- **do all of the above during a full-screen PowerPoint slideshow, without quitting the slides, switching screens, or interrupting the lesson**.

By default the program shows a 50×50 floating ball docked at the right edge of the screen: double-click to draw one name, right-click for multi-draw / points panel / management panel. All key windows stay on top but never steal focus, popups close themselves, and closing the points panel does not quit the program — the teacher can stay inside the full-screen presentation and run classroom interactions like using a remote control.

### Key Highlights

| Highlight | Description |
|---|---|
| **Never blocks the slides** | The floating ball is only 50×50, docked to the right screen edge by default, and can be dragged anywhere |
| **No need to leave the slides** | The floating ball is force-pinned on top (`SetWindowPos(HWND_TOPMOST)` on Windows; NSWindow level and Space behavior on macOS), so it can overlay PowerPoint |
| **Never steals focus** | The floating ball and popups use `Qt.WindowDoesNotAcceptFocus`, so keyboard input and PowerPoint operation are never interrupted |
| **Fair drawing** | Not `random.choice`, but "weighted least-drawn-first + per-person cooldown", so draw counts stay balanced over the long run |
| **Tamper-resistant points** | AES-256-GCM encryption + three-level automatic rollback — students cannot change scores by editing files |
| **Resident in tray** | Closing the main window or points panel does not quit; only "Quit" in the tray menu ends the process |

---

## Features

### Classroom Operations (Without Interrupting the Lesson)

- Double-click the floating ball → draw 1 name; right-click → multi-draw 2–10 names / points management / open management panel.
- A scrolling animation (1.8 s) plays before the reveal; the result popup is centered, has a `✕`, and closes automatically after 5 seconds.
- A multi-draw opens only one window; several names scroll at the same time and are revealed together.
- Neither the floating ball nor the popups steal focus.

### Study Group Points

- 6 groups by default, adjustable from 1 to 24; one card per group.
- Single-click to expand `-1 / +1 / +2 / +3`; double-click the group name to rename; right-click to reset the group to zero.
- `Ctrl+Z` undo supported; shortcuts `1/2/3/4` map to `-1/+1/+2/+3`.
- Scores are saved encrypted in `config.dat` and survive restarts; if corrupted or deleted, the data rolls back automatically.
- Every points change is appended to the encrypted activity log, viewable read-only via the "Activity Log" button in the bottom bar.
- Changing the group count resets group names and scores entirely (changing the group count means a whole new grouping, so old scores have no group to attach to).

### Fair Drawing

- "Weighted least-drawn-first": the fewer times a student has been drawn in total, the higher their weight.
- Recently drawn students are temporarily down-weighted to avoid back-to-back picks.
- Long-term counts live in `stats.ini` and remain effective across restarts.
- "Clear history" before class clears only history and cooldowns and keeps long-term counts; only "Full reset" zeroes the long-term counts.

### Management Panel

- Roster sources: a `.txt` file (one name per line, `#` comments supported), or generate by numeric range (1–99 by default).
- The roster list shows cooldown countdowns; students in cooldown are greyed out.
- Draw history table, per-person cooldown time (1–60 minutes, default 10).
- Launch-at-startup toggle (writes the registry Run key on Windows; a LaunchAgent on macOS).
- Tray menu: show main window / points management / draw a name / full reset / quit.

---

## Quick Start

### Requirements

- Windows 10 or later (primary target platform), macOS 11 or later; Linux unverified.
- Python 3.10+, PyQt5, cryptography (only needed when running from source).

```bash
pip install -r requirements.txt
```

### Run From Source

```bash
python main.py
```

If you don't want a console window:

```bash
pythonw main.py          # Windows: pythonw does not pop up a console
```

On macOS just run `python main.py`; to make it a double-clickable app, see [Packaging](#packaging).

The first launch creates the encrypted config next to the program directory; if there is no stored roster, a numeric roster 1–99 is generated automatically.

### Download a Runnable Build

Get it from **GitHub Releases** (if not published yet, build it yourself — see [Packaging](#packaging)).

---

## Usage

### Floating Ball

| Action | Effect |
|---|---|
| Left double-click | Draw 1 person |
| Left drag | Move the floating ball |
| Right-click | Menu: multi-draw 2–10 names / points management / open management panel / draw a name / full reset / quit |
| On draw | Briefly flashes gold |

### Points Panel

| Action | Effect |
|---|---|
| Single-click a card | Expand the action buttons |
| Double-click a group name | Rename |
| Right-click a card | Reset that group's points to zero |
| `Ctrl+Z` | Undo the most recent point change |
| `1 / 2 / 3 / 4` | `-1 / +1 / +2 / +3` |
| "Group count..." | Change the group count (requires confirmation; clears group names and scores) |
| "Reset all" | Zero every group (not undoable) |
| "Activity Log" | Open the read-only log viewer (the only entry point) |

### Management Panel

- "Roster source": browse for a `.txt` roster, or generate from a numeric range; "Reset to student numbers" restores the default 1–99.
- "Per-person cooldown": 1–60 minutes.
- "Launch at startup": writes the auto-start entry for the current user.
- "Hide floating ball": temporarily hide/show the floating ball.
- "Clear history": clears draw history and cooldowns, **keeping** the long-term fairness counters.
- Tray "Full reset...": group names, points, long-term fairness records and draw history all return to factory state.

---

## Data & Security

Both points and the activity log use **tamper-resistant storage**: each dataset has four copies and reads fall back level by level.

| File / location | Role | Program behavior |
|---|---|---|
| `config.dat` | Primary points data source (AES-256-GCM) | Read + write |
| `config.dat.bak` | Encrypted backup in the same directory | Read (rollback) + write |
| `QSettings` hidden backup | Windows registry / macOS plist / Linux conf | Read (rollback) + write |
| `config.ini` | Plaintext copy for viewing | **Write only, never read** |

Points read order:

```text
config.dat → config.dat.bak → QSettings hidden backup → legacy plaintext (one-time migration) → defaults
```

Whenever any level reads successfully, the successful data is written back to the earlier copies (automatic repair).

### `config.dat` / `config.dat.bak`

- Content is `nonce(12B) + ciphertext + GCM tag(16B)`, so it looks like garbage in Notepad;
- GCM is authenticated encryption: change any single byte and decryption must fail, after which the program rolls back to the next copy.

### Key

- On first run, a 32-byte key is generated automatically to `~/.classmanage_key` (permissions `600` on macOS/Linux);
- it is never hard-coded in the source, and is isolated per user account;
- if the key file cannot be written, the program does not crash — it degrades to a "temporary key for this run" and records the reason in
  `crypto_utils.key_error()` (you can diagnose it with `tools/config_crypto_check.py`).

### `config.ini` (Viewing Copy)

Regenerated on every save; its first line is `# 仅供查看，修改无效` ("for viewing only, edits have no effect"). **The program never reads it**, so editing it by hand will not change scores — use the UI instead.

### `QSettings` Hidden Backup

The same ciphertext is stored once more in a system-level location that students can hardly find or delete:

```text
Windows : HKCU\Software\YourOrg\ClassManageSystem
macOS   : ~/Library/Preferences/com.yourorg.ClassManageSystem.plist
Linux   : ~/.config/YourOrg/ClassManageSystem.conf
```

`QSettings` is used instead of `winreg` so one code path works on all three platforms and no `ModuleNotFoundError` occurs on macOS. Write failures are silently ignored and never affect the main flow.

### `points_log.dat` (Activity Log)

- Automatically records: point add/deduct, undo, reset one group, reset all, group count change, full reset;
- nothing is recorded when a score does not change; renaming a group is not recorded (it is not a points change);
- **append-only**: at most the latest 400 entries are kept (`seq` is a cumulative counter that keeps growing), so
  "whichever copy has the largest `seq` wins" — a **rollback-style tamper** (overwriting the main file with older ciphertext) is also repaired automatically;
- "Full reset" does not clear the log, it only appends a marker: audit records must not be wiped by a single button;
- there is **no plaintext copy on disk**; the only way to view it is the "Activity Log" button in the points panel.

### `stats.ini`

Long-term draw counts, stored in plaintext in the same directory as the config (contains no points).

```ini
[counts]
张三 = 5
李四 = 3
```

Reason for keeping it in a separate file: if it lived together with the points, "Clear history" before class would wipe the long-term counts too, and the weighting would degrade into "independent randomness for each lesson".

### `crash.log`

Stored in the same directory as the config; records Python tracebacks and native crashes, up to 200 entries. **0 bytes means no crash has occurred.**

### Where Data Lives

Config and logs are written next to the **program directory** (after packaging, alongside the EXE / `.app`, not inside the `.app` bundle); if that directory is not writable, everything falls back to:

```text
Windows        : %APPDATA%\ClassTerminal2411\
macOS / Linux  : ~/ClassTerminal2411/
```

---

## Core Design: Why Not Pure Randomness

`random.choice` is uniform for "each individual draw", but not for "each student over a semester". In a class of 40 it is very common to see clustering — someone drawn twice while someone else never gets drawn — and what students perceive is "the teacher always picks him".

So `NameEngine` uses a weighted least-drawn-first model:

```text
weight = (max_count - count + 1) ** FAIRNESS_STRENGTH
         * recency_penalty
```

Parameters live at the top of `namepicker/name_engine.py`:

| Parameter | Default | Description |
|---|---:|---|
| `FAIRNESS_STRENGTH` | `4.0` | Strength of the tilt toward the least-drawn students. Set it to 9 to approach fixed rotation. |
| `RECENT_GAP` | `4` | Lower the weight if drawn within the last N draws. |
| `RECENT_PENALTY` | `0.35` | Weight floor for the just-drawn student, to avoid back-to-back picks. |
| `MIN_WEIGHT` | `0.01` | Guarantees every eligible person can still be drawn. |

Two semantically different resets:

- `clear_history()`: clears draw history and cooldowns, **keeping** the long-term cumulative counts — this is the teacher's "Clear history" before class.
- `reset_fairness()`: also zeroes the long-term cumulative counts — for a new semester, a new class, or "Full reset".

After changing fairness parameters, re-run the benchmarks:

```bash
python tools/fairness_benchmark.py
python tools/fairness_burnin.py
```

---

## Cross-Platform Support

| Capability | Windows | macOS | Linux |
|---|---|---|---|
| Draw / points / log | ✅ | ✅ | Unverified |
| Cover full-screen apps | ✅ `SetWindowPos` | ✅ accessory policy + floating-window attributes (tested) | Unverified |
| Tray / menu bar icon | ✅ Color tray icon | ✅ Template image; **not shown when the menu bar auto-hides** | Unverified |
| Light / dark mode | ❌ Dark not working | ✅ Follows system | Unverified |
| System-level hidden backup | ✅ HKCU registry | ✅ `~/Library/Preferences` plist | ✅ `~/.config` |
| Floating ball pinned on top | ✅ `SetWindowPos(HWND_TOPMOST)` | ✅ Window level + `CanJoinAllSpaces`/`FullScreenAuxiliary`/`Stationary` | Unverified |
| Dock icon | — | ❌ None (the cost of the accessory policy, see below) | — |
| Launch at startup | ✅ Registry Run key | ✅ LaunchAgent | ❌ (returns failure) |
| Data location when frozen | ✅ Alongside the EXE | ✅ **Alongside** the `.app` (not inside the bundle) | — |

Design conventions: **never `import winreg` directly** (use `try/except ImportError`), wrap every platform-specific call in `try/except` with silent degradation; the storage layer always goes through PyQt5's built-in `QSettings`; colors and fonts are provided centrally by `namepicker/theme.py`.

---

## Packaging

> **PyInstaller does not support cross-compiling**: on macOS you can only produce a macOS app, and the `.exe` must be built on Windows (it involves GUI specifics and cannot pass a smoke test, so CI cannot test it — CI was removed in a newer commit)

### Windows — Windows 10 or later + required dependencies

```bat
packaging\windows\build.bat
```

The script automatically creates a `.venv-build` virtual environment, installs dependencies, runs self-checks, and packages; the output is `dist\ClassManageSystem.exe`. It uses the Tsinghua PyPI mirror by default (much faster for downloading PyQt5 in China); you can switch mirrors:

```bat
packaging\windows\build.bat official                                 :: official PyPI
packaging\windows\build.bat https://mirrors.aliyun.com/pypi/simple/  :: Aliyun
```

The mirror applies only to that command — it does **not** write `pip.ini` or change your global pip configuration.

### macOS

```bash
packaging/macos/build.command        # double-clicking works too
```

The output is `dist/ClassManageSystem.app`. It is a native binary for the **current CPU architecture** (arm64 on Apple Silicon; a universal build requires a universal2 Python + PyQt5).

### Build Notes

- Single-file windowed program; the target machine does not need Python installed;
- Config and logs are written alongside the EXE / `.app` (if read-only, it falls back to `%APPDATA%\ClassTerminal2411`), and the key lives in the user's home directory;
- **No code signing**: on Windows the first run triggers SmartScreen's "Unknown publisher" warning — click "More info → Run anyway"; on macOS, after copying to another machine the first launch requires **right-click → Open**.

---

## Project Structure

```text
.
├── main.py                          # Entry: assemble components, connect signals, start event loop
├── requirements.txt
├── names.txt                        # Sample roster
├── docs/images/                     # README screenshots (generated by tools/make_screenshots.py)
│
├── namepicker/                      # Main program package
│   ├── _init_.md                    # Description of responsibilities of files in the package
│   ├── config_store.py              # config.dat: encrypted config + three-level rollback
│   ├── crypto_utils.py              # AES-256-GCM and ~/.classmanage_key key management
│   ├── log_store.py                 # points_log.dat: encrypted activity log + rollback protection
│   ├── backup_store.py              # QSettings system-level hidden backup (cross-platform)
│   ├── stats_store.py               # stats.ini: long-term draw counts
│   ├── name_engine.py               # Draw logic: fair weighting, cooldown, history
│   ├── floating_ball.py             # Floating ball (incl. cross-platform force-on-top)
│   ├── draw_popup.py                # Result popup and scrolling animation
│   ├── points_window.py             # Points panel + activity log viewer
│   ├── main_window.py               # Management panel, tray, launch at startup
│   ├── single_instance.py           # Single-instance guard (QLocalServer liveness check)
│   └── crash_log.py                 # Crash log
│
├── packaging/
│   ├── windows/                     # PyInstaller spec, icons, version info, build.bat
│   ├── macos/                       # PyInstaller spec, icns, build.command
│   └── make_icon.py                 # Generates the Windows icon (Qt rendering, no Pillow needed)
│
├── tools/                           # Test and development scripts (not shipped with the program)
│   ├── config_check.py              # Storage round-trip test (no Qt dependency)
│   ├── config_crypto_check.py       # Encrypted storage / tamper rollback / migration self-check
│   ├── log_crypto_check.py          # Activity log: auto-recording / tamper rollback / rollback protection
│   ├── windows_check.py             # Windows platform self-check (registry / on-top / encoding / file locks)
│   ├── macos_check.py               # macOS platform self-check (menu bar / floating window / dark mode / full-screen overlay)
│   ├── _fullscreen_helper.py        # Self-check helper: subprocess that enters native full screen
│   ├── smoke_test.py                # GUI smoke test
│   ├── group_count_stress.py        # Group count feature + 300-round stress test
│   ├── make_screenshots.py          # Generates README screenshots under docs/images
│   ├── fairness_burnin.py           # 10,000 single-draw burn-in + χ² test
│   ├── fairness_benchmark.py        # Fairness parameter tuning benchmark
│   ├── reset_fairness_benchmark.py  # Simulates the teacher's "clear history" workflow
│   ├── weighting_demo.py            # Old vs. new algorithm distribution comparison
│   ├── repro_quit.py                # Minimal repro of "closing the panel quits the app"
│   └── _settings_isolation.py       # QSettings namespace isolation for tests
│
└── .github/workflows/build-windows.yml   # CI: x64 Windows packaging --deprecated
```

---

## Testing

Run all tests from the project root.

```bash
python tools/config_check.py           # Fastest, no Qt: storage read/write/merge/reset-all/full-reset
python tools/config_crypto_check.py    # Encrypted storage: garbage bytes, manual edits ineffective, tamper/delete rollback, migration
python tools/log_crypto_check.py       # Activity log: auto-recording, no plaintext copy, rollback protection, append-only
python tools/windows_check.py          # Platform self-check (real branches only run on Windows)
python tools/macos_check.py            # Platform self-check (menu bar icon / floating window attributes / dark mode / activation policy)
python tools/macos_check.py --fullscreen   # Additionally runs a "true native full screen" overlay test
python tools/smoke_test.py             # GUI smoke: signal wiring, layout, persistence, undo, multi-draw
python tools/group_count_stress.py     # Group count feature + 300-round stress test
```

- `config_crypto_check` / `log_crypto_check` run under a temporary HOME and **never touch your real data**; if PyQt5 is installed they also verify the real QSettings hidden backup.
- The smoke test constructs `MainWindow`, which reads and writes the real registry (Windows); the script backs up the launch-at-startup entry first and restores it afterwards, and skips this on macOS/Linux.
- Tests use an isolated QSettings namespace, so they never pollute the real registry / plist.

Fairness-specific:

```bash
python tools/fairness_burnin.py        # Cold-start long run, skew catch-up, χ² test, back-to-back rate…
python tools/fairness_benchmark.py     # Compares FAIRNESS_STRENGTH = 2/4/6/9 vs. pure randomness
python tools/reset_fairness_benchmark.py   # Simulates the "clear history before each lesson" workflow
python tools/weighting_demo.py         # Old vs. new algorithm distribution comparison
```

Regenerate README screenshots:

```bash
python tools/make_screenshots.py                          # Light (default)
CLASSMANAGE_THEME=dark python tools/make_screenshots.py   # Dark, outputs *-dark.png
```

The screenshot script moves windows off-screen before `grab()`, so nothing flashes on your desktop; it uses a temp directory for data and never touches the real config.

---

## Development Notes

- After changing the fairness parameters at the top of `name_engine.py`, re-run the fairness benchmark and burn-in test.
- `clear_history()` and `reset_fairness()` have different semantics — confirm which one you want before changing them.
- In `points_window.py`, old cards must be `hide()`-ed before being destroyed, otherwise they flash as independent top-level windows.
- Point card styles are cached by `(selected state, color)` to avoid high-frequency repaints on repeated clicks.
- Create the badge timer once and reuse it — do not rebuild a `QTimer` on every click.
- When running normally with no console, check `crash.log` first when troubleshooting.
- The single-instance guard **must not rely on `QSharedMemory` alone**: on Unix a shared memory segment is not released when a process disappears, so an orphaned segment after `kill -9` makes every later launch exit silently forever. Liveness is now determined by whether `QLocalServer` can connect, with shared memory only as a fallback.
- Packaging related: `config_store._app_dir()` handles `.app` specially to avoid writing data inside the app bundle;
  the Windows `.bat` must be **pure ASCII + CRLF** (`.gitattributes` already enforces `eol=crlf`),
  and `REM` lines must not contain unmatched parentheses — cmd's parenthesis counter would otherwise truncate the command mid-line.

---

## FAQ

### Nothing happens when I double-click the icon; the process flashes and exits?

The old single-instance implementation refused to start forever once shared memory was left behind (see "Development Notes"). The current version uses a `QLocalServer` liveness check and restarts normally after being force-killed. If it still happens, first confirm no other instance is running:

```bash
pgrep -fl ClassManageSystem        # macOS
tasklist | findstr ClassManage     # Windows
```

### The program disappears after I close the points panel?

Fixed — `main.py` now calls `app.setQuitOnLastWindowClosed(False)`. Repro script: `python tools/repro_quit.py`.

### Scores are not being saved?

Check whether the program directory (the one holding `config.dat`) is writable; if read-only, it falls back to
`%APPDATA%\ClassTerminal2411\` (macOS/Linux: `~/ClassTerminal2411/`).
`python tools/config_crypto_check.py` can pinpoint whether the problem is the key, the ciphertext, or directory permissions.

### A student edited the scores in `config.ini`; why did it not take effect?

Because the program never reads `config.ini`, and it is overwritten by the encrypted data on every save. What really takes effect is `config.dat`
(plus `.bak` and the system-level hidden backup). Editing `config.dat` fails too: GCM authenticated encryption makes decryption fail,
and the program rolls back from the backup automatically. Deleting the data does not work either — delete the main file and it is restored from `.bak`; delete both and it is restored from the QSettings hidden backup.

### Can the activity log be deleted?

No, by design. The log is append-only, and even "Full reset" only appends a marker. To keep an archive, take a screenshot or copy the text from the viewer.

### Does "Clear history" break fairness?

No. It clears only history and cooldowns; long-term counts stay in `stats.ini`. Only "Full reset" zeroes the long-term counts.

### Why were fewer names drawn than requested in a multi-draw?

Because some students are still in cooldown. A multi-draw picks only from the currently available roster, returns the number actually drawn, and shows a hint.

### The program exits without any message — what should I do?

Check `crash.log`. A size of 0 bytes usually means it was not a crash (it may have been force-killed or exited normally).

### Packaging fails with `'xxx' 不是内部或外部命令`?

The `.bat` was saved as UTF-8/LF, or a `REM` line contains unmatched parentheses. This repo's `build.bat` has been fixed and a `.gitattributes` was added;
when editing it yourself, keep it pure ASCII + CRLF.

---

## Known Limitations

- **No code signing / notarization**: Windows shows a SmartScreen warning, and on macOS you must right-click → Open after copying to another machine.
- **Architecture follows the build machine**: on Apple Silicon the `.app` is arm64 and cannot run on Intel Macs; there is no dual-architecture fallback, so Intel Mac users need to run the packaging shell script themselves;
- **macOS full-screen coverage relies on the "app activation policy"**: a higher window level alone is useless — a regular app occupies its own desktop Space, and once another app goes full screen it is simply not in that Space. This program switches to the
  **accessory** policy at startup (`LSUIElement`, same as Alfred / Raycast) so the window can join the full-screen Space. The cost is **no Dock icon**; entry points become the floating ball + the menu bar icon.
  This was verified against a real native full-screen window with `CGWindowList onScreenOnly`:
  `python tools/macos_check.py --fullscreen` reports "the floating ball can overlay native full-screen apps ✅".
- **macOS menu bar icon**: the icon itself is a template image and the status item is indeed created (the self-check verifies
  `NSStatusBarWindow`). If the system has "automatically hide and show the menu bar" enabled (`_HIHideMenuBar=1`), the status item is by design not shown while the menu bar is collapsed — that is not a program bug. In that case use the floating ball's right-click menu,
  which already contains every tray action (draw a name / points management / open panel / full reset / quit).
  If you want it permanently visible, turn off "Automatically hide and show the menu bar" in System Settings → Appearance (or Desktop & Dock).
- **Key shares the account's permissions**: the key lives in the user's home directory, so if a teacher and students share the same system login account, a student can theoretically read the key. This is an inherent boundary of the "user-level key" approach.
- **Linux unverified**: the code has platform guards so it won't crash, but tray and always-on-top behavior are untested.

---

## License

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
