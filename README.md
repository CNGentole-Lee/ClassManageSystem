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
- [许可证](#许可证)

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

界面跟随系统外观（macOS / Windows 均可），不是把浅色主题硬套一遍：
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
| 浅色 / 深色模式 | ✅ 跟随系统 | ✅ 跟随系统 | ✅ 跟随系统 |
| 系统级隐蔽备份 | ✅ HKCU 注册表 | ✅ `~/Library/Preferences` plist | ✅ `~/.config` |
| 悬浮球置顶 | ✅ `SetWindowPos(HWND_TOPMOST)` | ✅ 层级 + `CanJoinAllSpaces`/`FullScreenAuxiliary`/`Stationary` | 未验证 |
| Dock 图标 | — | ❌ 无（accessory 策略的代价，见下） | — |
| 开机自启动 | ✅ 注册表 Run 项 | ✅ LaunchAgent | ❌（返回失败） |
| 冻结后数据位置 | ✅ EXE 同级目录 | ✅ `.app` **同级**目录（不在包内） | — |

设计约定：**不直接 `import winreg`**（改为 `try/except ImportError`），平台专有调用全部包在 `try/except` 里并静默降级；存储层统一走 PyQt5 自带的 `QSettings`；配色与字体统一由 `namepicker/theme.py` 提供。

---

## 打包

> **PyInstaller 不支持交叉编译**：在 macOS 上只能打出 macOS 程序，`.exe` 必须在 Windows 上打包（本地 Windows 或 CI）。

### Windows —— 方式一：GitHub Actions（推荐）

推送即自动打包，产物在 Actions 页面下载：

```bash
git push origin main                    # 触发 .github/workflows/build-windows.yml
git tag v1.0.0 && git push origin v1.0.0   # 打 tag 会自动建 Release 并附上 EXE
```

CI 会依次跑：`tools/windows_check.py`（平台自检，同时验证注册表隐蔽备份与 Win32 置顶是否真的可用）→ 存储/日志验收 → PyInstaller 打包 → 上传 `ClassManageSystem-windows-x64` 产物。**自检失败会中断出包**，所以能下到 EXE 就意味着这些功能在真 Windows 上实测过。

### Windows —— 方式二：任意一台 Windows

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
└── .github/workflows/build-windows.yml   # CI：x64 Windows 打包
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
- **架构跟随构建机**：Apple Silicon 上打出 arm64 的 `.app`，Intel Mac 不能跑；
  Windows CI 产出 x64。
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
