# 班级多用教学辅助终端：包内文件职责说明

> 程序入口为同级目录下的 `main.py`。`main.py` 负责组装下列组件、连接 Qt 信号，并进入事件循环。本文件仅包含说明，不含任何可执行代码。

## 零、先读这一节：两个闭源程序与七道检查

分数的权威来源是**事件链**（`Data/ledger.esc`），不是 `config.dat`。事件链由两个
闭源程序共同把关，职责刻意不对称：

| 程序 | 持有 | 能做什么 | 不能做什么 |
|---|---|---|---|
| `cmd_sign` | 密钥（加密钥 + 签名私钥） | 签名、加密、解密、v1→v2 迁移 | **不能**决定一条记录是否被接受 |
| `cmd_verify` | **只有公钥** | 验签、重放、规则判定 | **不能**伪造签名 |

写入是两段式的：`cmd_sign` 产生记录 → `cmd_verify` 复核整条链 → 通过才落盘。
换掉签名器，它签不出验证器认的记录；换掉验证器，会被哈希清单拦住。

### 七道独立检查 + 两程序互校

```text
1 签名        改记录            → BAD_SIG
2 哈希清单    换程序            → HASH_MISMATCH，可一键还原
3 锚点        链变短/头不符/状态不符/公钥被换
4 单调时间    时间回退          → TIME_WENT_BACK
5 ctime       拷回旧文件        → CTIME_AHEAD
6 NTP         整盘镜像/改系统时间 → 联网后暴露
7 归档        异常分级写入 tamper.log，不打断上课

互校：cmd_sign ↔ cmd_verify 共享同一构建令牌
      任意一方被替换 → 另一方拒绝工作（PEER_MISMATCH）
```

前五道离线可用，第六道需要网络，第七道只记录、不阻断。

**边界**：这些检查防的是“替换程序 / 篡改数据 / 恢复旧数据”，
**不防“修改源码”和“整盘镜像”**——任何本地程序都防不住这两件事。

---

## 数据流

数据流为单向，按以下顺序阅读：

```text
文件（Data/ledger.esc 事件链 / config.dat 加密缓存 / stats.ini 长期次数）
    ↓ 校验与重放（cmd_sign 解密 → cmd_verify 验签+重放）
逻辑层（NameEngine 决定抽取对象）
    ↓ Qt 信号
界面层（弹窗 / 悬浮球 / 面板展示结果）
```

`config.ini` 只是给人看的只写副本，程序永不读取；`points_log.dat` 仍是独立的
加密操作日志，不参与分数裁决。

---

## 一、数据持久化层

该层只负责文件读写，不依赖 Qt 控件。两个存储文件的分工如下。

### `config_store.py`

加密读写程序所在目录下的 `config.dat`（明文 `config.ini` 只是给人看的副本，
程序永不读取）。

**注意**：`config.dat` 里的分数是**缓存**，权威来源是 `Data/ledger.esc`。
启动时先验链、再重放，用链上的结果覆盖缓存；链不可信时不会采用链上数据。

- `[meta]`：应用名称、最后修改时间。
- `[points]`：小组数量、每个小组的名称与分数。

副本与回退顺序：

```text
config.dat → config.dat.bak → QSettings 隐蔽备份 → 旧版明文（一次性迁移）→ 默认值
```

任何一级读成功都会用成功的数据修复前面的副本。

行为：

- 加密：AES-256-GCM（见 `crypto_utils.py`），密钥在 `~/.classmanage_key`（权限 600）。
  任何一字节被改动都会解密失败，因此改分一定被发现。
- 原子写入：先写 `.tmp`，再执行 `os.replace()`。断电或崩溃不会留下不完整文件。
- 程序位于只读目录（如 `C:\Program Files`）时，自动改用 `%APPDATA%\ClassTerminal2411`，避免因写入失败而丢失教师录入的分数。
- `resolve_config_path()` 被 `stats_store` 复用，确保两个文件始终位于同一目录。
- `set_group_count()` 是修改小组数量的入口：整段重建 `[points]`，组名恢复默认、分数清零。组数变化意味着分组方案变化，旧分数无法可靠映射到新分组。
- 历史兼容：早期版本将抽取次数写在 `[points]` 旁的 `[stats]` 段；现在 `reset_all()` 会删除该遗留段。
- 旧版兼容：首次运行时若只有旧的明文 `config.ini`，`migrate_legacy_plaintext()`
  会把它加密落盘一次，之后不再读取明文。
- 每次分数**真正变化**时自动追加一条操作日志（`set_score` / `reset_scores` /
  `_write_default_groups` 三个改分入口都覆盖），日志写失败静默，绝不影响积分。

### `crypto_utils.py`

AES-256-GCM 加解密与密钥管理：`encrypt()` / `decrypt()`，
密钥文件 `~/.classmanage_key`（32 字节，chmod 600），不硬编码密钥。
落盘格式为 `nonce(12B) + 密文 + GCM tag(16B)`。

### `backup_store.py`

用 Qt（PySide6）自带的 `QSettings` 存系统级隐蔽备份，一套代码三平台通用
（Windows 注册表 / macOS plist / Linux conf），因此**不需要** `import winreg`，
macOS 下不会 `ModuleNotFoundError`。所有失败静默处理。

积分的备份键前缀是 `sys_cache`，操作日志是 `sys_log`（见 `prefix` 参数），
两者按配置目录哈希分桶，互不覆盖。

### `log_store.py`

小组积分变动日志：`points_log.dat` + `points_log.dat.bak` + QSettings 隐蔽备份，
同样 AES-256-GCM 加密、三级回退、自动修复。**没有明文副本**。

行为：

- 写入由 `config_store` 在分数真正变化时自动触发，界面无需关心；
- 明文是 JSON：`{"version":1,"seq":137,"entries":[[时间, 文本], ...]}`；
- 日志只增不减（最多保留最近 `MAX_ENTRIES` 条，`seq` 持续增长），因此读取时
  取三份副本里 `seq` 最大的一份 —— 用旧密文覆盖主文件这种回滚式篡改也会被修回来；
- 「彻底重置」只追加一条标记，不清空日志；
- 唯一查看入口是积分面板的「操作日志」按钮（`points_window._LogViewerDialog`）。

### `stats_store.py`

读写 `stats.ini`：`[counts]` 段，每行对应一个学生，值为累计被抽中次数。

行为：

- 单独文件的原因：若长期次数与配置放在同一文件中，清空历史时可能一并清除长期次数，使跨课加权失效，退化为每节课独立随机；一学期内同一批学生可能反复被抽中。因此，长期次数需要独立存储。
- `save()` 是合并而非覆盖：更换花名册不会清除上一个班级或名单的累计记录。
- 次数为 0 时删除整行，而不是写入 `name = 0`，避免为 99 人名单留下 99 行冗余记录。
- `clear()` 执行完全清空，只在托盘菜单的“彻底重置”中调用。

---

### `ledger.py`

事件链：分数与组名的唯一权威来源。

- 记录格式：`seq | gen | nonce | ct_len | plain_hash | ct | sig`，
  其中 `plain_hash` 是被签名覆盖的明文 BLAKE2b-256，让验证器**不需要解密**也能
  确认签名方没有在明文上撒谎。
- 明文头含**单调时间戳**：每条 `max(现在, 上一条+1)`，系统时钟被调回也不会倒退。
- 写入是两段式：`cmd_sign.apply()` 出记录 → `cmd_verify.state()` 复核 →
  通过才追加到 `Data/ledger.esc`。任一步失败都不落盘。
- 锚点 `Data/anchor.json` 与隐藏副本记录 `seq/head/ts/digest/pubkey`；
  `anchor_problems()` 负责比对，返回 `SHORTER` / `HEAD_MISMATCH` /
  `TIME_ROLLBACK` / `STATE_MISMATCH` / `PUBKEY_MISMATCH`。
- 安全副本：追加时同步写 `~/.cache/classmanage/<哈希>/ledger.esc`，
  主链变短或损坏时用 `restore_from_shadow()` 自愈。
- v1→v2 迁移：首次启动检测到旧链时调用 `cmd_sign migrate` 重签，
  原文件备份为 `ledger.esc.v1.bak`，并写 `Data/format` 标记。

### `native_bridge.py`

两个闭源程序的唯一调用入口，按角色定位二进制（`sign` / `verify`）。

- `fingerprint()` / `identity()`：机器指纹与公钥，只有签名器能提供。
- `apply()`：签名器产生记录与明文。
- `dump()`：签名器解密整条链，返回明文（供验证器重放）。
- `migrate()`：v1 链重签为 v2。
- `state()` / `verify()`：验证器用公钥验签并重放，不需要密钥。
- Windows 下用 `CREATE_NO_WINDOW`，避免每次调用弹出控制台窗口。

### `integrity.py`

文件层面的完整性：

- `check_native(path, role)`：SHA-256 与 `native_manifest.py` 的钉死值比对，
  失败原因分 `MISSING` / `SIZE` / `HASH_MISMATCH`。
- `restore_native()`：从随包 `.gz` 副本解出原始二进制并复验。
- `check_ctime()`：文件 ctime 与最后事件时间差超过 10 分钟判为“被整体替换”；
  无法读取 ctime 的文件系统降级为“未知”，不误报。
- `append_tamper_log()`：异常分级写入 `tamper.log`（独立文件，不进链）。

### `guard.py`

启动判定，把上面各项组合成一个结论：

- `check_both()`：检查两个二进制，能还原就还原。
- `network_time()`：查 NTP，失败静默跳过，绝不阻断启动。
- `evaluate()`：综合锚点、ctime、NTP，返回 `info` / `warn` / `critical`。
- `describe()`：把内部错误码翻译成老师能看懂的一句话。

### `sntp.py`

极简 NTP 客户端（RFC 5905 子集）：

- UDP 123，一次查询约 50~120 ms，断网 0.6 s 超时。
- 多服务器取 RTT 最小的一份；`t1/t4` 用 `perf_counter` 计算间隔，
  避免查询期间系统时间被改动影响结果。
- 返回 `offset` / `rtt` / `samples` / `spread`，由 `guard` 决定如何判定。

### `native_manifest.py` / `native_backup/`

- `native_manifest.py`：四个二进制（两平台 × 两角色）的 SHA-256 与大小，
  由 `tools/make_native_manifest.py` 生成，**不要手改**。
- `native_backup/`：对应的 `.gz` 原始副本，是一键还原的来源。
  打包时会与二进制一起放进 `native/` 目录（macOS 在 `Resources/native/`）。

---

## 二、抽取逻辑层

该层为纯逻辑，不依赖界面控件，通过 Qt 信号发布结果。

### `name_engine.py`

核心算法：名单管理、公平加权抽取、每人冷却、历史记录。

不使用 `random.choice` 的原因：它保证单次抽取等概率，但不保证一个学期内每名学生被抽次数均衡。40 人中可能出现有人被抽两次、有人一次未抽，学生可能察觉教师反复抽取同一人。因此采用少抽优先加权：历史累计次数越少，权重越高。

权重公式：

```text
权重 = (max_count - count + 1) ** FAIRNESS_STRENGTH × 近期惩罚
```

参数位于类顶部。修改后需重新运行 `tools/fairness_benchmark.py`：

- `FAIRNESS_STRENGTH = 4.0`：向最少被抽者倾斜的强度。`P = 9` 会退化为固定轮换。
- `RECENT_GAP = 4`：最近 N 次内被抽中过则降低权重。
- `RECENT_PENALTY = 0.35`：刚被抽中者的权重下限，避免连续抽中同一人。

对外主要接口：

- `draw_name()`：单抽，由悬浮球双击触发。
- `draw_names(n)`：连续抽 n 人；逐个抽取，因此不重复。
- `clear_history()`：清空抽取历史与冷却状态，保留长期累计次数；对应教师课前的清空历史操作。
- `reset_fairness()`：连同长期累计次数一起清零；用于新学期或彻底重置。

`clear_history()` 与 `reset_fairness()` 的区别决定公平性设计。修改前需确认二者语义。

---

## 三、界面层

每个文件对应一个窗口或控件。界面组件之间不直接调用，统一由 `main.py` 连接信号。

### `floating_ball.py`

屏幕上的 50×50 像素圆形“抽”按钮，可拖动，始终置顶。

行为：

- 强制置顶是分平台的（见模块顶部注释）：
  - Windows：`SetWindowPos(HWND_TOPMOST)` 把窗口钉进 topmost 层；传 HWND 用
    `ctypes.c_void_p`，不依赖 `ctypes.wintypes`（`import ctypes` 不会带出该子模块，
    早期写法因此静默失效）。
  - macOS：`Qt.Tool` 即 NSPanel，默认 `hidesOnDeactivate=YES`，失焦会被系统隐藏，
    故设置 `Qt.WA_MacAlwaysShowToolWindow`；再用 `ctypes` 调 libobjc 设
    `NSWindowCollectionBehaviorCanJoinAllSpaces | FullScreenAuxiliary` 并抬到
    `NSStatusWindowLevel`，才能盖在全屏课件之上。
- 双击：抽一个人。
- 右键：菜单，包括连抽 2~10 人、积分管理、打开管理面板。
- 使用 `Qt.Tool`，使其不获取焦点，避免输入时被打断。
- 注意：由于是 `Qt.Tool`，Qt 不将其视为主窗口。因此 `main.py` 必须设置 `setQuitOnLastWindowClosed(False)`；否则关闭积分面板时，Qt 会认为“最后一个窗口已关闭”并退出整个程序。

### `draw_popup.py`

屏幕中央的结果弹窗：先快速滚动名字约 1.8 秒，再揭晓结果，5 秒后自动关闭。

行为：

- 单抽调用 `show_result()`。
- 连抽调用 `show_results()`。
- 连抽是在一个大弹窗中让 N 个格子同时滚动，而不是弹出 N 个窗口。
- 格子宽度按名单中最长名字实测（`QFontMetrics`），否则长名字会被左右裁切。
- 字体和列数随人数自适应。

### `points_window.py`

小组积分管理面板：每组一张卡片。

交互：

- 单击展开 `-1` / `+1` / `+2` / `+3`。
- 双击改名。
- 右键清零本组。
- 支持撤销（`Ctrl+Z`）和“全部清零”。
- 每次改动防抖 400 ms 后写盘；关闭窗口前再强制保存一次。
- 底栏“小组数量...”可修改组数：弹框输入数字并二次确认，两步操作降低误操作风险。修改后整段重置：组名恢复默认、分数清零。
- 底栏“小组数量...”旁边的“操作日志”按钮打开只读查看器（`_LogViewerDialog`），
  显示最近 400 条积分变动（最新在最上面），并提示本次读取是否用到了备份回档。
  这是全程序读取操作日志的唯一入口。
- 卡片网格置于滚动区域中。24 组为 8 行 × 200 px，普通窗口无法容纳。

为避免崩溃采用的写法（代码中有注释）：

- 徽标定时器只创建一次，不重建。
- 样式表按 `(选中态, 颜色)` 缓存，避免重复样式刷新。
- 关闭过程中不访问界面控件。

### `main_window.py`

管理面板主窗口，包含：

- 名单来源：文件 / 数字范围。
- 名单列表：冷却中的学生变灰并显示倒计时。
- 抽取历史表。
- 每人冷却时间。
- 开机自启动开关。

其他行为：

- 系统托盘图标与菜单：显示主窗口 / 积分管理 / 抽取名字 / 彻底重置... / 退出。
- 点击 X 不退出程序，而是隐藏到托盘（`closeEvent` 中执行 `hide()` + `ignore()`）。
- “彻底重置”只负责弹出确认框；真正的清理由 `main.py` 注入的回调执行，因为数据文件不归窗口管理。

---

## 四、基础设施

### `crash_log.py`

将崩溃信息写入与 `config.dat` 同目录的 `crash.log`。

行为：

- 存在原因：正式运行时没有控制台（`pythonw` 或窗口版 EXE）。异常 traceback 会写入 stderr，用户不可见，程序表现为无提示退出。
- 安装两个钩子：
  - `sys.excepthook`：捕获 Python 异常。
  - `faulthandler`：捕获原生崩溃（访问违例、栈溢出）并打印堆栈。
- 上限 200 条，防止同一错误反复触发写满磁盘。
- 排错时首先检查该文件：0 字节表示没有崩溃，说明是正常退出或其他原因，而非异常。

### `single_instance.py`

单实例保护：使用 `QSharedMemory` + `QLocalServer` 确保同一时间只运行一份程序。

行为：

- 第二个实例启动时，会将第一个实例唤到前台，然后自行退出。
- 存在原因：两个实例会同时写入 `config.dat`，后写入者覆盖先写入者。

---

## 五、`tools/` 下的测试程序

这些程序不属于主程序，仅用于验证。修改核心逻辑后，应运行相关测试。

### 一键入口

#### `run_all_tests.py`

一次跑完全部测试（默认 13~15 秒）：自动寻找解释器、隔离设置、逐项限时，
任一失败即汇总报告。CI 与本地都用它。

### 安全 / 篡改专项

#### `tamper_check.py`（24 项）

篡改专项。覆盖：翻转/截断二进制、从备份还原、改记录、删记录、重排、
回滚旧链、锚点时间倒退、digest 不符、公钥不符、ctime 异常、NTP 离线、
NTP 时间戳往返精度、单调时间戳递增、**二进制不得泄漏协议字符串**、
**换掉 peer 后另一方拒绝工作**。

#### `ledger_check.py`（22 项）

事件链：迁移、由 C++ 改分、回档检测、安全副本恢复、v1→v2 重签。

#### `native_check.py`（20 项）

两个原生程序的协议层：签名器出记录、验证器重放、单字节篡改被拒、
跨机器指纹无法通过。

#### `lint_check.py`

pyflakes 静态检查，把“未定义名字”设为失败。它抓到过一次真实崩溃：
`about_dialog` 引用了已删除的常量，只有在第三方声明缺失时才触发。

#### `packaging_check.py`

打包一致性：spec / 安装脚本 / CI / 清单哈希 / 备份文件 / README 的约定，
包括“release 不许执行 macOS 二进制”这类回归。

### 工具

#### `make_native_manifest.py`

重编原生程序后重新生成 `native_manifest.py` 与 `native_backup/*.gz`。
**忘了这一步，启动会报 `HASH_MISMATCH`**（这是设计如此：宁可报错也不静默）。

#### `obfuscate_source.py`

构建期把字符串字面量包成 `OBF("...")`，并自动补 `#include "obf.hpp"`。
只在构建目录里生成，不改动仓库源码。

### 功能回归

#### `smoke_test.py`（67 处断言）

冒烟测试。修改代码后应首先运行。

- 不启动完整程序，而是分别构造每个窗口并模拟操作。
- 用于捕获“编译能过但一运行就错”的问题：信号连接、布局、`config.dat` 落盘、撤销、连抽、小组数量、崩溃日志。
- 构造 `MainWindow` 会读写真实注册表，因此它会先备份开机自启动项，跑完后还原。

#### `config_crypto_check.py` / `log_crypto_check.py`

加密存储的验收自检，不依赖 Qt 也能跑（装了 PyQt5 时会额外验证真实的隐蔽备份）。

- `config_crypto_check.py`：积分加密、篡改/删除/清空回档、旧明文迁移、原子写入。
- `log_crypto_check.py`：操作日志自动记录、无明文副本、篡改回档、**防回滚**、只增不减。
- `windows_check.py`：**在 Windows 上运行**，实测注册表隐蔽备份、Win32 `SetWindowPos` 是否拿到真函数、
  中文/空格路径、`os.replace`、文件被占用等平台专有行为。
- `_settings_isolation.py`：测试辅助，把 QSettings 切到测试命名空间并在退出时清空，
  避免测试数据写进用户真实的注册表 / plist（Windows 上 `$HOME` 隔离对注册表无效）。

#### `group_count_stress.py`（43 处断言）

“小组数量”功能的功能测试与压力测试。

功能测试：

- 修改数量后组名恢复默认 / 分数清零。
- 边界夹取（1~24）。
- 落盘。
- 数量未变化时不得修改分数。
- 彻底重置后恢复默认 6 组。

压力测试：

- 300 轮反复执行“改组数 × 加减分 × 重建卡片 × 存盘”。
- 结束后检查面板仍可用、文件仍可解析、界面显示分数与文件内容一致。

回归测试，两个已修复问题：

1. 改组数时旧卡片不能短暂显示为独立顶层窗口。对可见控件使用 `setParent(None)` 会使其成为顶层窗口。
2. 24 组时滚动条必须生效，且窗口仍可缩小到所需尺寸。

#### `repro_quit.py`

“关闭积分面板导致整个程序退出”缺陷的最小复现。

- `QApplication` 默认 `quitOnLastWindowClosed = True`。
- 悬浮球是 `Qt.Tool`，不被视为主窗口。
- 因此主窗口缩到托盘后，关闭积分面板即退出程序。
- 保留此脚本用于确认 `main.py` 中的修复没有被改回。

#### `config_check.py`（纯 `assert`，不依赖 Qt）

两个存储的往返测试：

- `ConfigStore`：分数 / 组名 / `reset_all`。
- `StatsStore`：合并保存、次数为 0 时删行、`clear`。

运行最快，不需要启动界面。

### 公平性压力测试 / 基准

#### `fairness_burnin.py`（16 处断言）

1 万次单抽的压力测试，检验概率分布和加权是否生效。

七个部分：

1. 冷启动长跑分布
2. 纯随机对照
3. 偏斜起点追赶
4. χ² 拟合检验
5. 真实课间节奏
6. 连续抽中率
7. 领先者冷落时长

χ² 拟合检验：先取引擎声明的概率，再用 5 万次实测采样拟合。该检验用于证明 `_pick` 按 `_weight` 抽签，而非仅表现为分布均匀。

#### `reset_fairness_benchmark.py`

重现教师工作流，量化加权失效缺陷：

- 5 轮 × 20 节课 × 每课 10 抽。
- 对比两种清空语义：
  - 旧行为：清空历史时同时清除长期次数。
  - 新行为：保留长期次数。
- 结论：每人总次数极差 15 → 4，σ 3.89 → 0.95。
- 该结果用于决定将次数迁移到 `stats.ini`。

#### `fairness_benchmark.py`

调参基准。对比 `FAIRNESS_STRENGTH = 2 / 4 / 6 / 9` 与纯随机：

1. 40 人抽 400 次时的长期分布是否均匀。
2. 单节课只抽 10~40 次时，“同一人被抽第二次”的次数，即学生较易察觉的重复抽取。

当前采用 `P = 4`，即由此基准选出。`P = 9` 分布最均匀，但会退化为固定轮换。

修改 `name_engine.py` 顶部参数后，重新运行此基准。

#### `weighting_demo.py`

上述基准的简化版：

- 40 人 × 400 次。
- 新旧算法并排输出分布表。
- 统计每 40 次一轮中的重复人数。

指标不如 `fairness_benchmark.py` 全面，但输出直观，适合快速对比。
