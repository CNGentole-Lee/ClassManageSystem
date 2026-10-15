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
- **无需退出课件**：悬浮球通过 Qt.Tool + 置顶强制压在其它窗口之上
  （Windows 走 `SetWindowPos(HWND_TOPMOST)`；macOS 走
  `WA_MacAlwaysShowToolWindow` + `CanJoinAllSpaces`/`FullScreenAuxiliary`），
  可覆盖在 PPT 全屏之上；双击抽人、右键连抽/积分，全程不用退出全屏课件。
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
- 分数自动加密保存到 `config.dat`，重启不丢；被改坏/删掉会自动回档。
- 每次积分变动（加减分 / 撤销 / 清零 / 改组数 / 彻底重置）自动写入加密操作日志；
  底栏「操作日志」按钮可只读查看，这是全程序唯一的查看入口。
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
- 崩溃日志：`crash.log` 与 `config.dat` 同目录，记录 Python traceback 和原生故障。
- 原子写入：`config.dat`、`config.dat.bak`、`config.ini` 与 `stats.ini` 都先写 `.tmp` 再 `os.replace()`。
- 防篡改 + 自动回档：积分用 AES-256-GCM 认证加密，读取顺序为
  `config.dat → config.dat.bak → QSettings 隐蔽备份 → 默认值`；
  任何一级被改坏、被清空或被删除，都会自动从下一级恢复，并顺手修复前面的副本。
- 操作日志同样加密 + 三级回档，并且**只增不减**（「彻底重置」也只追加一条标记）：
  日志多带一个累计条数 `seq`，哪份副本的 `seq` 最大就用哪份 —— 拿旧密文覆盖主
  文件这种「回滚式篡改」也会被自动修回来。磁盘上没有日志的明文副本。
- 只读目录回退：如果程序目录不可写，配置会落到 `%APPDATA%\ClassTerminal2411`。
- 关闭积分面板不会导致整个程序退出。

---

## 环境要求

- Windows 10 及以上 / macOS 11 及以上 / Linux；
- Python 3.10+（仅源码运行需要）；
- PyQt5、cryptography（仅源码运行需要）。

安装依赖：

```bash
pip install -r requirements.txt
```

或直接：

```bash
pip install PyQt5 cryptography
```

> 跨平台说明：存储层不 `import winreg`，系统级隐蔽备份统一走 PyQt5 自带的
> `QSettings`（Windows → 注册表，macOS → `~/Library/Preferences/*.plist`，
> Linux → `~/.config/*.conf`）；开机自启动在 Windows 用注册表、在 macOS 用
> LaunchAgent。所有平台专有调用都包在 `try/except` 里，因此 macOS 下能直接
> 启动运行，悬浮球也做了 mac 侧置顶（`WA_MacAlwaysShowToolWindow` +
> `NSWindowCollectionBehaviorCanJoinAllSpaces`），可盖在全屏课件之上。

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

积分为防篡改存储，同一份数据有四个副本，读取时逐级回退：

| 文件 / 位置 | 角色 | 程序行为 |
|---|---|---|
| `config.dat` | 加密主数据源（AES-256-GCM） | 读 + 写 |
| `config.dat.bak` | 同目录加密备份 | 读（回档）+ 写 |
| `QSettings` 隐蔽备份 | 注册表 / plist / conf | 读（回档）+ 写 |
| `config.ini` | 明文查看副本 | **只写，永不读** |

读取顺序：

```text
config.dat → config.dat.bak → QSettings 隐蔽备份 → 旧版明文（一次性迁移）→ 默认值
```

任何一级读成功，都会用成功的数据把前面的副本重新写一遍（自动修复）。
`config.dat` 与 `config.dat.bak` 与 `config.ini` 同目录，目录不可写时整体回退到
`%APPDATA%\ClassTerminal2411\`（macOS/Linux 下为 `~/ClassTerminal2411\`）。

### `config.dat` / `config.dat.bak`

- 内容为 `nonce(12B) + 密文 + GCM tag(16B)`，用记事本打开是乱码；
- 密钥首次运行自动生成到 `~/.classmanage_key`（32 字节，权限 `600`），不硬编码；
- GCM 是认证加密：改任何一个字节，解密都会失败，程序随即回档到下一级副本。

### `config.ini`（查看副本）

每次保存都会重新生成，内容与加密数据一致，开头带一行
`# 仅供查看，修改无效`。

- 程序**从不读取**它，手工改它不会影响分数；
- 想修改组名/分数请在界面里操作，或直接备份整个目录。

### `QSettings` 隐蔽备份

同一份密文再存一份到系统级位置，学生很难找到也不容易删：

```text
Windows : HKCU\Software\YourOrg\ClassManageSystem
macOS   : ~/Library/Preferences/com.YourOrg.ClassManageSystem.plist
Linux   : ~/.config/YourOrg/ClassManageSystem.conf
```

用 `QSettings` 而不是 `winreg`，一套代码三平台通用，且 macOS 下不会
`ModuleNotFoundError`。写入失败会被静默忽略，绝不影响正常使用。

加密前的明文结构（仅用于说明字段）：

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

### `points_log.dat` / `points_log.dat.bak`（操作日志）

与 `config.dat` 同目录，保存每次小组积分变动，同样是 AES-256-GCM 加密二进制，
再额外存一份到 QSettings（键前缀 `sys_log`，与积分的 `sys_cache` 分开）。

- **唯一查看入口**：积分面板底栏「小组数量...」旁边的「操作日志」按钮（只读）；
  磁盘上只有密文，**没有明文副本**，托盘菜单 / 管理面板都没有入口；
- 自动记录的动作：加分、减分、撤销、清零此组、全部清零、修改小组数量、彻底重置；
- 分数没变化时不记录，避免噪音；
- 记录格式（加密前的明文，JSON）：

```json
{"version": 1, "seq": 137,
 "entries": [["2026-10-16 00:12:03", "第2组（雄鹰组）6 → 8｜+2"]]}
```

- 日志**只增不减**：最多保留最近 400 条（超长组名会截断，避免 Windows 注册表单值超限），
  `seq` 是历史累计条数并持续增长；
  读取时取三份副本里 `seq` 最大的那份 —— 用旧密文覆盖主文件（回滚式篡改）
  也会被自动修回来；
- 「彻底重置」不清空日志，只在末尾追加一条标记：审计记录不能靠一个按钮抹掉。

### `stats.ini`

与 `config.dat` 同目录，保存长期抽取次数（明文，不含积分）。

```ini
[counts]
张三 = 5
李四 = 3
```

说明：

- 独立于配置，因为“清空历史”不能清掉长期公平记忆；
- `save()` 是合并而非覆盖，换花名册不会清掉上一个班的记录；
- 次数为 0 时删除该行，而不是写 `name = 0`；
- 只有“彻底重置”会调用 `clear()`。

### `crash.log`

与 `config.dat` 同目录。

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
    ├── config_store.py         # config.dat：加密配置 + 三级回档（config.ini 只写不读）
    ├── crypto_utils.py         # AES-256-GCM 加解密与 ~/.classmanage_key 密钥管理
    ├── log_store.py            # points_log.dat：加密操作日志 + 防回滚
    ├── backup_store.py         # QSettings 系统级隐蔽备份（跨平台，不 import winreg）
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
    ├── config_crypto_check.py  # 加密存储 / 篡改回档 / 迁移 自检
    ├── log_crypto_check.py     # 操作日志：自动记录 / 篡改回档 / 防回滚 自检
    ├── windows_check.py        # Windows 兼容性自检（在 Windows 上一条命令跑）
    └── _settings_isolation.py  # 测试用的 QSettings 命名空间隔离
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

```bash
python tools/config_crypto_check.py
python tools/log_crypto_check.py
python tools/windows_check.py
```

前两个验证加密存储与操作日志的验收标准：`config.dat` 是乱码、`config.ini` 手改无效、
篡改/清空/删除后自动回档、全部删除后回默认值、旧版明文一次性迁移、
密钥文件权限 600、不留 `.tmp` 残留。在临时 HOME 下运行，不碰真实数据。

### 冒烟测试

```bash
python tools/smoke_test.py
```

不启动完整程序，直接构造各窗口并模拟操作。覆盖信号连接、布局、`config.dat` 落盘、撤销、连抽、小组数量、崩溃日志等。

> 构造 `MainWindow` 在 Windows 上会读写真实注册表，测试会先备份开机自启动项，跑完后还原；macOS/Linux 下自动跳过。

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

## 打包 Windows EXE

> **PyInstaller 不支持交叉编译**：在 macOS 上执行只会得到 mac 程序，`.exe` 必须在
> Windows 上打包。别用 Apple Silicon 的 Parallels（打出来是 ARM64，学校 x64 电脑跑不了）。

### 方式一：GitHub Actions（推荐）

推送代码即自动打包，产物在 Actions 页面下载，无需本机 Windows：

```bash
git push origin main          # 触发 .github/workflows/build-windows.yml
git tag v1.0 && git push origin v1.0   # 打 tag 会额外自动建 Release 并附上 EXE
```

工作流会依次执行：`tools/windows_check.py`（平台自检，同时验证注册表隐蔽备份与
Win32 置顶是否真的可用）→ 三个存储/日志验收 → PyInstaller 打包 → 上传
`ClassManageSystem-windows-x64` 产物。自检失败会中断出包，因此"能下到 EXE"
本身就意味着 Windows 上这些功能是实测过的。

### 方式二：任意一台 Windows

```bat
packaging\windows\build.bat
```

脚本会自动建 `.venv-build` 虚拟环境、装依赖、跑自检、打包，产物为
`dist\ClassManageSystem.exe`。

### 产物说明

- 单文件窗口程序，双击即用，不需要目标机装 Python；
- 配置与操作日志写在 EXE 同目录（只读目录则回退 `%APPDATA%\ClassTerminal2411`），
  密钥在 `%USERPROFILE%\.classmanage_key`；
- 未做代码签名，首次运行 SmartScreen 会提示"未知发布者"，点"更多信息 → 仍要运行"即可。

---

## 常见问题

### 关闭积分面板后程序消失了？

已修复。`main.py` 中设置了：

```python
app.setQuitOnLastWindowClosed(False)
```

如果问题复现，运行 `python tools/repro_quit.py` 检查。

### 分数没有保存？

检查配置目录（放 `config.dat` 的那个目录）是否可写。程序目录只读时会自动回退到：

```text
%APPDATA%\ClassTerminal2411\config.ini（macOS/Linux：~/ClassTerminal2411/）
```

积分本身存加密的 `config.dat`，`config.ini` 只是给人看的副本。运行
`python tools/config_crypto_check.py` 可以定位是密钥、密文还是目录权限的问题。

### 学生改了 config.ini 的分数，为什么没生效？

因为程序从不读取 `config.ini`。它每次保存都会被加密数据重新覆盖，
真正生效的是 `config.dat`（外加 `.bak` 与系统级隐蔽备份）。
改了 `config.dat` 也一样没用：GCM 认证加密会让解密失败，程序自动回档。

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
