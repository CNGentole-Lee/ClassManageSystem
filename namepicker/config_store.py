"""ConfigStore —— 小组积分的防篡改持久化（加密主文件 + 三级回档）。

存储布局（四个副本，读取时逐级回退）：

    config.dat          加密主数据源（AES-256-GCM）              读 + 写
    config.dat.bak      同目录加密备份                            读（回档）+ 写
    QSettings 隐蔽备份  注册表 / plist，学生难找难删（backup_store） 读（回档）+ 写
    config.ini          明文查看副本，程序**永不读取**             只写

读取顺序：

    config.dat → config.dat.bak → QSettings 隐蔽备份 → 旧版明文（一次性迁移）→ 默认值

任何一级成功，都会用成功的数据把前面的副本全部修复回一致状态。
config.ini 只是给人看的：老师/学生改它都不会影响分数（程序不读它），
每次保存都会被加密数据重新覆盖。

结构（加密前的明文，仅用于说明字段）：

    [meta]
    app = 班级多用教学辅助终端
    updated = 2026-09-27 10:30:00

    [points]
    group_count = 6
    group_1 = 第一组          ; 显示名，可自由编辑
    score_1 = 12              ; 可为负数
    ...

长期抽取次数刻意放在 stats.ini（见 stats_store.py），
这样「清空历史」不会把公平性记忆一起丢掉。
"""

import configparser
import io
import os
import sys
from datetime import datetime

try:  # 包内相对导入（正常运行时）
    from . import backup_store
    from . import crypto_utils
    from . import i18n
    from . import log_store
    from .i18n import tr
except ImportError:  # 允许把 namepicker 目录直接加进 sys.path 的用法
    import backup_store  # type: ignore
    import crypto_utils  # type: ignore
    import i18n  # type: ignore
    import log_store  # type: ignore
    from i18n import tr  # type: ignore

#: 产品名（写进 config 的 meta.app，保持稳定，不随界面语言变化）
APP_NAME = "班级多用教学辅助终端"


def app_name() -> str:
    """界面显示用产品名（双语）。"""
    return tr(APP_NAME, "Class Management Terminal")

CONFIG_FILENAME = "config.ini"   # 明文查看副本（只写不读）
DATA_FILENAME = "config.dat"     # 加密主数据源
DATA_SUFFIX = ".dat"
BAK_SUFFIX = ".bak"              # config.dat.bak

DEFAULT_GROUP_COUNT = 6
MIN_GROUP_COUNT = 1
MAX_GROUP_COUNT = 24

# 查看副本的标记行：用来区分「程序写的只读副本」和「旧版真正的明文数据」。
# 中英两行都会写进去：老文件用中文标记识别，新文件两种都认。
VIEW_MARKER = "# 仅供查看，修改无效"
VIEW_MARKER_EN = "# view-only copy - edits are ignored"
VIEW_HEADER = (
    VIEW_MARKER + " —— 分数保存在加密文件 config.dat 中，程序不会读取本文件。\n"
    + VIEW_MARKER_EN + "\n"
    + "# 手工修改这里不会影响程序里的分数，只作为人工查看/备份用。\n"
)

# 第一组 … 第六组（中文） / Group 1 … Group 6（英文）
DEFAULT_GROUP_NAMES = ["第{}组".format(n) for n in ("一", "二", "三", "四", "五", "六")]
DEFAULT_GROUP_NAMES_EN = [f"Group {i}" for i in range(1, len(DEFAULT_GROUP_NAMES) + 1)]

_last_io_error = ""


def default_names_for(index: int) -> tuple[str, str]:
    """小组 index 在中/英两种语言下的默认名（判定「这是不是默认名」用）。"""
    if 1 <= index <= len(DEFAULT_GROUP_NAMES):
        return DEFAULT_GROUP_NAMES[index - 1], DEFAULT_GROUP_NAMES_EN[index - 1]
    return f"第{index}组", f"Group {index}"


def is_default_group_name(name: str, index: int) -> bool:
    """这个名字是不是「程序给的默认名」（任一种语言都算）。

    默认名不该被当成用户数据固定下来：切到英文后「第一组」应显示为
    "Group 1"；只有老师自己改过的名字才保持原样。
    """
    zh, en = default_names_for(index)
    return name.strip() in (zh, en)


def default_group_name(index: int) -> str:
    """小组 index（1 起）的兜底显示名（跟随界面语言）。

    注意：组名是**数据**，只在「新建 / 补齐缺失小组」时取默认值；
    已有配置里的名字不会被语言切换改写。
    """
    names = DEFAULT_GROUP_NAMES if i18n.is_zh() else DEFAULT_GROUP_NAMES_EN
    if 1 <= index <= len(names):
        return names[index - 1]
    return tr(f"第{index}组", f"Group {index}")


def _shorten(text: str, limit: int = 16) -> str:
    """日志里用的短名：组名长度不受限，截断避免日志与注册表被撑大。"""
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit] + "…"


# --- 路径 ---------------------------------------------------------------
# 下面这些函数同时被 stats_store / crash_log 复用，保持原有签名不变。


def _app_dir() -> str:
    """程序运行目录：打包后是可执行文件所在目录，否则是项目根目录。

    macOS 的 .app 要特别处理：冻结后 sys.executable 指向
    `Xxx.app/Contents/MacOS/Xxx`，直接用它会把 config.dat 写进**应用包内部**——
    老师找不到、复制/更新 .app 时还可能连同数据一起被覆盖，而且包内目录在
    签名校验下本该只读。所以退回 .app 所在的那一级目录（老师能看到的地方）。
    """
    if getattr(sys, 'frozen', False):
        exe = os.path.dirname(os.path.abspath(sys.executable))
        # .../Xxx.app/Contents/MacOS → 上三级才是 .app 所在目录
        if (os.path.basename(exe) == "MacOS"
                and os.path.basename(os.path.dirname(exe)) == "Contents"
                and os.path.dirname(exe).endswith(".app/Contents")):
            return os.path.dirname(os.path.dirname(os.path.dirname(exe)))
        return exe
    # namepicker/config_store.py → 项目根目录
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _fallback_dir() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "ClassTerminal2411")


def _is_writable(directory: str) -> bool:
    probe = os.path.join(directory, ".~write_probe")
    try:
        with open(probe, "w", encoding="utf-8") as f:
            f.write("1")
        os.remove(probe)
        return True
    except OSError:
        return False


def data_path_for(config_path: str) -> str:
    """config.ini 的路径 → 同目录同基名的 config.dat 路径。"""
    base, _ext = os.path.splitext(config_path)
    return (base or config_path) + DATA_SUFFIX


def backup_path_for(config_path: str) -> str:
    """config.dat.bak 的路径。"""
    return data_path_for(config_path) + BAK_SUFFIX


def resolve_config_path() -> str:
    """优先用程序旁的 config.ini，只读目录则退到 %APPDATA%。

    防止装在只读位置（如 C:\\Program Files）时，老师点的分全部静默写不进去。
    加密主文件 config.dat 与它同目录同名，所以这里选中的目录同时也是
    config.dat / config.dat.bak 的目录。
    """
    primary = os.path.join(_app_dir(), CONFIG_FILENAME)
    if (os.path.isfile(primary)
            or os.path.isfile(data_path_for(primary))
            or _is_writable(_app_dir())):
        return primary

    fallback = _fallback_dir()
    try:
        os.makedirs(fallback, exist_ok=True)
    except OSError:
        pass
    return os.path.join(fallback, CONFIG_FILENAME)


def resolve_data_path() -> str:
    """加密主文件 config.dat 的路径（与 config.ini 同目录）。"""
    return data_path_for(resolve_config_path())


def _backup_tag(config_path: str) -> str:
    """隐蔽备份的分桶键：同一个目录的配置共用一个槽位。"""
    directory = os.path.dirname(os.path.abspath(config_path))
    return directory or os.path.abspath(os.sep)


# --- 原子写入 -----------------------------------------------------------
# 保留原有「先写 .tmp 再 os.replace()」的逻辑，只是内容从明文变成了加密二进制。
# 目录只有 .tmp 文件、主文件永远是完整的旧内容或完整的新内容，不会出现半截文件。


def _atomic_write_bytes(path: str, blob: bytes) -> bool:
    """二进制原子写入，跨平台（os.replace 在 Windows/macOS 都可用）。"""
    global _last_io_error
    tmp_path = path + ".tmp"
    try:
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(tmp_path, "wb") as f:
            f.write(blob)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass  # 某些文件系统不支持 fsync，不影响正确性
        os.replace(tmp_path, path)
        return True
    except OSError as e:
        _last_io_error = f"{path}: {e}"
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        return False


def _atomic_write_text(path: str, text: str) -> bool:
    return _atomic_write_bytes(path, text.encode("utf-8"))


# --- 序列化 / 解析 ------------------------------------------------------


def _new_parser() -> configparser.ConfigParser:
    """统一构造：关掉插值、保留键名大小写（人名/组名会当键用）。"""
    cp = configparser.ConfigParser(interpolation=None)
    cp.optionxform = str
    return cp


def _to_bytes(config: configparser.ConfigParser) -> bytes:
    buf = io.StringIO()
    config.write(buf)
    return buf.getvalue().encode("utf-8")


def _group_count_of(config: configparser.ConfigParser) -> int:
    raw = config.get("points", "group_count", fallback="")
    try:
        count = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_GROUP_COUNT
    return max(MIN_GROUP_COUNT, min(count, MAX_GROUP_COUNT))


def _ensure_sections(config: configparser.ConfigParser) -> None:
    """补齐缺失的段和键，调用方永远不会遇到 KeyError。"""
    if not config.has_section("meta"):
        config.add_section("meta")
    config.set("meta", "app", APP_NAME)

    if not config.has_section("points"):
        config.add_section("points")

    # 补齐缺失的小组名 / 分数槽位
    count = _group_count_of(config)
    for i in range(1, count + 1):
        if not config.has_option("points", f"group_{i}"):
            config.set("points", f"group_{i}", default_group_name(i))
        if not config.has_option("points", f"score_{i}"):
            config.set("points", f"score_{i}", "0")


def default_config() -> configparser.ConfigParser:
    """出厂默认配置（默认 6 组、0 分）。"""
    cp = _new_parser()
    cp.add_section("meta")
    cp.set("meta", "app", APP_NAME)
    cp.add_section("points")
    cp.set("points", "group_count", str(DEFAULT_GROUP_COUNT))
    for i in range(1, DEFAULT_GROUP_COUNT + 1):
        cp.set("points", f"group_{i}", default_group_name(i))
        cp.set("points", f"score_{i}", "0")
    return cp


def _parse_plaintext(plain: bytes):
    """把解密出来的明文解析成 ConfigParser；不像本程序的配置就返回 None。"""
    if not plain:
        return None
    try:
        text = plain.decode("utf-8")
    except UnicodeDecodeError:
        return None
    cp = _new_parser()
    try:
        cp.read_string(text)
    except (configparser.Error, ValueError):
        return None
    if not cp.sections():
        return None
    # 只认带 [meta]/[points] 的内容，避免拿别的 INI 当配置用。
    if not (cp.has_section("meta") or cp.has_section("points")):
        return None
    return cp


def _read_encrypted(path: str):
    """读一个加密文件 → (plaintext, blob)；不存在/被篡改/被清空都返回 (None, None)。"""
    try:
        with open(path, "rb") as f:
            blob = f.read()
    except OSError:
        return None, None
    if not blob:
        return None, None
    try:
        return crypto_utils.decrypt(blob), blob
    except Exception:
        # cryptography 的 InvalidTag、ValueError、TypeError…… 一律视为「这个副本不可用」
        return None, None


def _load_from_file(path: str):
    """从某个加密副本加载配置，失败返回 None。"""
    plain, _blob = _read_encrypted(path)
    return _parse_plaintext(plain)


def _load_from_backup_store(config_path: str):
    """从 QSettings 隐蔽备份加载配置，失败返回 None。"""
    blob = backup_store.load_backup(tag=_backup_tag(config_path))
    if not blob:
        return None
    try:
        plain = crypto_utils.decrypt(blob)
    except Exception:
        return None
    return _parse_plaintext(plain)


def _looks_like_view_copy(path: str) -> bool:
    """判断这个明文 config.ini 是不是程序自己写的「仅供查看」副本。"""
    try:
        with open(path, "rb") as f:
            head = f.read(512)
    except OSError:
        return False
    text = head.decode("utf-8", "ignore")
    return VIEW_MARKER in text or VIEW_MARKER_EN in text


def _load_legacy_plaintext(config_path: str):
    """读取旧版明文 config.ini（只用于一次性迁移）。

    只有在「所有加密副本都不可用」时才会走到这里；而且要满足：
      * 文件存在、非空、能解析、带 [meta]/[points]；
      * 文件里没有查看副本的标记行（否则读到的是程序自己写的只读副本）。
    """
    if not os.path.isfile(config_path):
        return None
    if _looks_like_view_copy(config_path):
        return None
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            text = f.read()
    except (OSError, UnicodeDecodeError):
        return None
    if not text.strip():
        return None
    cp = _new_parser()
    try:
        cp.read_string(text)
    except (configparser.Error, ValueError):
        return None
    if not (cp.has_section("meta") or cp.has_section("points")):
        return None
    return cp


# --- 读写主入口 ---------------------------------------------------------


def save_config(config: configparser.ConfigParser, path: str = "") -> bool:
    """加密写盘：主文件 + 同目录备份 + 隐蔽备份 + 明文查看副本。

    返回加密主文件是否写成功；备份/隐蔽副本/查看副本失败都不影响返回值，
    也绝不抛异常（隐蔽备份写入失败必须静默）。
    """
    global _last_io_error
    config_path = path or resolve_config_path()
    data_path = data_path_for(config_path)
    bak_path = data_path + BAK_SUFFIX

    try:
        plain = _to_bytes(config)
        blob = crypto_utils.encrypt(plain)
    except Exception as e:
        _last_io_error = tr("加密失败: {e}", "encryption failed: {e}", e=e)
        return False

    ok = _atomic_write_bytes(data_path, blob)
    if not ok:
        return False

    # 同目录备份：失败静默（下一次保存会再试）
    _atomic_write_bytes(bak_path, blob)

    # 系统级隐蔽备份：失败静默
    backup_store.save_backup(blob, tag=_backup_tag(config_path))

    # 明文查看副本：只写不读，仅供人工查看
    _write_view_copy(config_path, plain)
    return True


def _write_view_copy(config_path: str, plain: bytes) -> bool:
    try:
        text = plain.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return _atomic_write_text(config_path, VIEW_HEADER + text)


def load_config(path: str = "", repair: bool = True) -> configparser.ConfigParser:
    """按 config.dat → .bak → 隐蔽备份 → 旧版明文 → 默认值 逐级回退。

    任何一级读成功，都会（在 repair=True 时）用成功的数据把前面的副本
    重新写一遍，保证所有副本重新一致。永远不会返回 None，也不会抛异常。
    """
    config_path = path or resolve_config_path()

    # 1) 加密主文件
    config = _load_from_file(data_path_for(config_path))
    if config is not None:
        _ensure_sections(config)
        return config

    # 2) 同目录加密备份 → 回档并修复主文件
    config = _load_from_file(backup_path_for(config_path))
    if config is not None:
        _ensure_sections(config)
        if repair:
            save_config(config, config_path)
        return config

    # 3) 系统级隐蔽备份 → 回档并重建两个文件
    config = _load_from_backup_store(config_path)
    if config is not None:
        _ensure_sections(config)
        if repair:
            save_config(config, config_path)
        return config

    # 4) 旧版明文（一次性迁移）→ 加密落盘
    config = _load_legacy_plaintext(config_path)
    if config is not None:
        _ensure_sections(config)
        save_config(config, config_path)
        return config

    # 5) 全都没了：用默认值重建，绝不崩溃
    config = default_config()
    save_config(config, config_path)
    return config


def migrate_legacy_plaintext(path: str = "") -> bool:
    """把旧版明文 config.ini 迁移成加密存储（一次性，可重复调用）。

    只在「加密主文件与同目录备份都不存在、且隐蔽备份也不可用」时动手，
    因此不会覆盖加密数据，也不会把旧明文盖到隐蔽备份上。
    返回是否真的迁移了。
    """
    config_path = path or resolve_config_path()
    data_path = data_path_for(config_path)
    if os.path.exists(data_path) or os.path.exists(data_path + BAK_SUFFIX):
        return False
    if backup_store.load_backup(tag=_backup_tag(config_path)) is not None:
        return False
    config = _load_legacy_plaintext(config_path)
    if config is None:
        return False
    _ensure_sections(config)
    return save_config(config, config_path)


def last_save_error() -> str:
    """最近一次写盘失败的原因（成功时为空串）。"""
    return _last_io_error


# --- ConfigStore --------------------------------------------------------


class ConfigStore:
    """内存中的配置，加密原子写入。每个进程共享一个实例。

    path 仍然是 config.ini 的路径（兼容既有调用方与界面上的路径显示），
    加密主文件按同目录同基名推导：config.ini → config.dat / config.dat.bak。
    """

    def __init__(self, path: str = ""):
        self.path = path or resolve_config_path()
        self.data_path = data_path_for(self.path)
        self.backup_path = backup_path_for(self.path)
        self._cp = _new_parser()
        self._last_error = ""
        self.reload()

    # --- 加载 ---

    def reload(self) -> None:
        """重新加载配置：按照回退顺序读取，并丢弃内存中未保存的改动。

        注意：这里**不会**读明文 config.ini（除非它是待迁移的旧版明文，
        见 load_config 的第 4 级）。
        """
        try:
            loaded = load_config(self.path)
        except Exception as e:  # 兜底：任何意外都退回默认值，不让程序起不来
            loaded = default_config()
            self._last_error = str(e)
        else:
            self._last_error = ""

        # 原地替换内容，保持 self._cp 对象身份不变（外部可能持有引用）
        self._cp.clear()
        for section in loaded.sections():
            if not self._cp.has_section(section):
                self._cp.add_section(section)
            for key, value in loaded.items(section):
                self._cp.set(section, key, value)
        self._ensure_sections()

    def _ensure_sections(self) -> None:
        _ensure_sections(self._cp)

    # --- 小组 / 分数 ---

    @property
    def group_count(self) -> int:
        return _group_count_of(self._cp)

    def set_group_count(self, count: int) -> int:
        """改小组数量：整段重建 [points]，组名回默认、分数归零，返回实际生效值。

        换组数即换了一套分组，旧分数没有可挂靠的小组，所以一并清空。
        """
        try:
            count = int(count)
        except (TypeError, ValueError):
            return self.group_count
        count = max(MIN_GROUP_COUNT, min(count, MAX_GROUP_COUNT))
        if count == self.group_count:
            return count  # 数量没变，不做任何事，避免白清一次分数
        self._write_default_groups(count)
        return count

    def get_group_name(self, index: int) -> str:
        """小组 index（1 起）的显示名。

        存的是默认名（`第一组` / `Group 1`）时按当前界面语言返回 —— 这样切到
        英文后默认组名会变成 "Group 1"，而老师自定义的名字不受影响。
        """
        raw = self._cp.get("points", f"group_{index}", fallback="").strip()
        if not raw or is_default_group_name(raw, index):
            return default_group_name(index)
        return raw

    def set_group_name(self, index: int, name: str) -> None:
        name = name.strip()
        if not name:
            return
        self._cp.set("points", f"group_{index}", name)

    def get_score(self, index: int) -> int:
        raw = self._cp.get("points", f"score_{index}", fallback="0")
        try:
            return int(raw)
        except (TypeError, ValueError):
            return 0

    def set_score(self, index: int, value: int, reason=None) -> None:
        """改一个小组的分数；值真的变了才写一条操作日志。

        reason 可以是 i18n.Bi / (中文, English) / 纯字符串 —— 会原样附在日志里。
        日志写失败不影响积分（见 _log）。
        """
        try:
            value = int(value)
        except (TypeError, ValueError):
            return
        old = self.get_score(index)
        self._cp.set("points", f"score_{index}", str(value))
        if value != old:
            zh_reason, en_reason = i18n.as_pair(reason)
            name = _shorten(self.get_group_name(index))
            zh_suffix = f"｜{zh_reason}" if zh_reason else ""
            en_suffix = f" | {en_reason}" if en_reason else ""
            self._log(
                f"第{index}组（{name}）{old} → {value}{zh_suffix}",
                f"Group {index} ({name}) {old} → {value}{en_suffix}",
            )

    def all_scores(self) -> list[int]:
        return [self.get_score(i) for i in range(1, self.group_count + 1)]

    def reset_scores(self, reason=None) -> None:
        """所有小组归零，并把这次批量清零记成一条日志（而不是每组一条）。"""
        olds = self.all_scores()
        for i in range(1, self.group_count + 1):
            self._cp.set("points", f"score_{i}", "0")
        if any(olds):
            zh_reason, en_reason = i18n.as_pair(reason)
            zh_reason = zh_reason or "全部清零"
            en_reason = en_reason or "clear all"
            joined = "/".join(str(v) for v in olds)
            self._log(f"{zh_reason}：{joined} → 全 0", f"{en_reason}: {joined} -> all 0")

    # --- 可选清空（彻底重置对话框用） ---

    def wipe_group_names(self) -> None:
        """只把组名恢复默认，保留分数与小组数量。"""
        count = self.group_count
        for i in range(1, count + 1):
            self._cp.set("points", f"group_{i}", default_group_name(i))
        self._log("彻底重置：组名已恢复默认", "Full reset: group names restored")

    def wipe_scores(self) -> None:
        """只把积分归零，保留组名。"""
        olds = self.all_scores()
        for i in range(1, self.group_count + 1):
            self._cp.set("points", f"score_{i}", "0")
        if any(olds):
            joined = "/".join(str(v) for v in olds)
            self._log(f"彻底重置：积分已清零（原 {joined}）",
                      f"Full reset: scores cleared (was {joined})")

    def log_operation(self, zh: str, en: str = "") -> None:
        """写一条操作日志（供 main.py 记录公平记录/历史的清空）。"""
        self._log(zh, en)

    def _log(self, zh: str, en: str = "") -> None:
        """写一条双语操作日志；失败静默 —— 日志绝不能影响积分流程。"""
        try:
            log_store.append(zh, en, self.path)
        except Exception:
            pass

    def _write_default_groups(self, count: int, reason=None, force_log: bool = False) -> None:
        """把 [points] 整段换成 `count` 个全新小组（默认组名、0 分），并记一条日志。"""
        old_count = self.group_count
        olds = self.all_scores()
        zh_reason, en_reason = i18n.as_pair(reason)
        zh_reason = zh_reason or "修改小组数量"
        en_reason = en_reason or "change group count"
        if self._cp.has_section("points"):
            self._cp.remove_section("points")
        self._cp.add_section("points")
        self._cp.set("points", "group_count", str(count))
        for i in range(1, count + 1):
            self._cp.set("points", f"group_{i}", default_group_name(i))
            self._cp.set("points", f"score_{i}", "0")

        if old_count != count or any(olds) or force_log:
            joined = "/".join(str(v) for v in olds)
            zh_detail = f"（原积分 {joined}）" if any(olds) else ""
            en_detail = f" (was {joined})" if any(olds) else ""
            self._log(
                f"{zh_reason}：小组数量 {old_count} → {count}，组名与积分已重置{zh_detail}",
                f"{en_reason}: group count {old_count} -> {count}, names and scores reset{en_detail}",
            )

    def reset_all(self) -> bool:
        """回到出厂状态：组名、分数、组数全部重置（彻底重置用）。

        长期抽取次数不在这里，它存在 stats.ini（见 stats_store.py）。
        操作日志**不清空**：只追加一条标记，审计记录不能靠一个按钮抹掉。
        """
        self._write_default_groups(
            DEFAULT_GROUP_COUNT,
            reason=i18n.both("彻底重置", "full reset"),
            force_log=True,
        )
        # 早期版本把抽取次数写在 [stats] 段里，一并删除避免留下误导性残留。
        if self._cp.has_section("stats"):
            self._cp.remove_section("stats")
        return self.save()

    # --- 保存 ---

    def save(self) -> bool:
        """加密原子写入：config.dat + config.dat.bak + 隐蔽备份 + 明文副本。

        返回是否成功；失败原因见 last_error()。
        """
        global _last_io_error
        self._cp.set("meta", "updated", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        try:
            ok = save_config(self._cp, self.path)
        except Exception as e:  # 兜底：写盘失败不能让界面崩
            _last_io_error = str(e)
            ok = False
        if ok:
            # 保存成功；但如果密钥文件写不进去，留个可排查的痕迹（见 crypto_utils.key_error）
            self._last_error = crypto_utils.key_error()
        else:
            self._last_error = last_save_error() or tr("写入失败", "write failed")
        return ok

    def last_error(self) -> str:
        """最近一次保存的问题：失败原因，或「密钥未能落盘」的警告；正常为空串。"""
        return self._last_error
