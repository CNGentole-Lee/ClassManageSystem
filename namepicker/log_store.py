"""log_store —— 小组积分变动日志：加密存储、防篡改、可自动回档。

与 config_store 是**同一套思路、完全独立的一份文件**：

    points_log.dat          加密主日志（AES-256-GCM，二进制）
    points_log.dat.bak      同目录加密备份
    QSettings 隐蔽备份      注册表 / plist / conf（键前缀 sys_log，与积分分开）

故意**不生成明文副本**：日志只能从积分管理面板的「查看操作日志」入口查看，
磁盘上只有密文。

加密前的明文是 JSON：

    {"version": 1, "seq": 137, "entries": [["2026-10-16 00:12:03", "第2组（第一组）6 → 8｜+2"], ...]}

为什么多一个 seq（累计写入条数）：日志只增不减，所以「哪份副本的 seq 最大，
哪份就是最新的」。有人照搬积分那套攻击（用 .bak 覆盖主文件、把最近几条抹掉）
时，主文件的 seq 会小于隐蔽备份，程序随即用更新的那份自动修回来。

日志永不删除，包括「彻底重置」——只在末尾追加一条标记。审计记录可以被
清空的话，防篡改就没有意义了。
"""

import json
import os
from datetime import datetime
from typing import NamedTuple

try:  # 包内相对导入（正常运行时）
    from . import backup_store
    from . import crypto_utils
    from .atomic import replace_with_retry
except ImportError:  # 允许把 namepicker 目录直接加进 sys.path 的用法
    import backup_store  # type: ignore
    import crypto_utils  # type: ignore
    from atomic import replace_with_retry  # type: ignore

LOG_FILENAME = "points_log.dat"
BAK_SUFFIX = ".bak"
HIDDEN_PREFIX = "sys_log"     # QSettings 里的键前缀，与积分的 sys_cache 分开
FORMAT_VERSION = 1

#: 明文最多保留多少条（超出丢弃最旧的，seq 继续增长，回档判断不受影响）。
#: Windows 上隐蔽备份写在注册表里（单值上限约 1MB），这里刻意留足余量：
#: 400 条 × 单条最长 240 字符 ≈ 60KB 明文 → hex 约 120KB。
MAX_ENTRIES = 400

#: 单条日志正文长度上限（防止有人把小说填进组名，把注册表撑爆）
MAX_TEXT_LEN = 240


class LogView(NamedTuple):
    """一次读取的结果。

    entries 每条是 ``(时间, 中文, English)``。老日志只有一段文本，
    读出来时 English 为空串 —— 保证升级后旧记录照常显示。
    """
    entries: list          # [(时间, 中文, English)]，旧 → 新
    seq: int               # 累计写入条数（含已被裁剪掉的）
    source: str            # main / bak / hidden / empty —— 数据从哪份副本来的


def log_path_for(config_path: str) -> str:
    """日志与 config.dat 同目录（同样跟随只读目录回退规则）。"""
    return os.path.join(os.path.dirname(os.path.abspath(config_path)), LOG_FILENAME)


def log_backup_path_for(config_path: str) -> str:
    return log_path_for(config_path) + BAK_SUFFIX


def _tag(config_path: str) -> str:
    """隐蔽备份分桶：同一个配置目录共用一份日志备份。"""
    directory = os.path.dirname(os.path.abspath(config_path))
    return directory or os.path.abspath(os.sep)


# --- 读写底层 -----------------------------------------------------------


def _atomic_write_bytes(path: str, blob: bytes) -> bool:
    """二进制原子写入（与 config_store 里那份等价，保留 .tmp + os.replace）。"""
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
                pass
        replace_with_retry(tmp_path, path)
        return True
    except OSError:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        return False


def _parse(raw) -> tuple | None:
    """把解密出来的明文解析成 (seq, entries)；任何异常都当作「这份副本不可用」。"""
    try:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            return None
        entries = data.get("entries")
        if not isinstance(entries, list):
            return None
        clean = []
        for item in entries:
            if not isinstance(item, (list, tuple)):
                continue
            if len(item) == 3 and all(isinstance(x, str) for x in item):
                clean.append([item[0], item[1], item[2]])       # 双语格式
            elif len(item) == 2 and all(isinstance(x, str) for x in item):
                clean.append([item[0], item[1], ""])            # 老格式（纯文本）
        # seq 缺失或不合法时退回「条数」，老格式也能读
        try:
            seq = int(data.get("seq"))
            if seq < len(clean):
                seq = len(clean)
        except (TypeError, ValueError):
            seq = len(clean)
        return seq, clean
    except Exception:
        return None


def _read_copy(path: str) -> tuple | None:
    """读一份加密副本 → (seq, entries)；不存在/为空/被篡改/格式坏都返回 None。"""
    try:
        with open(path, "rb") as f:
            blob = f.read()
    except OSError:
        return None
    if not blob:
        return None
    try:
        plain = crypto_utils.decrypt(blob)
    except Exception:
        return None
    return _parse(plain)


def _read_hidden(config_path: str) -> tuple | None:
    blob = backup_store.load_backup(tag=_tag(config_path), prefix=HIDDEN_PREFIX)
    if not blob:
        return None
    try:
        plain = crypto_utils.decrypt(blob)
    except Exception:
        return None
    return _parse(plain)


def _dump(seq: int, entries: list) -> bytes:
    payload = {
        "version": FORMAT_VERSION,
        "seq": int(seq),
        "entries": entries[-MAX_ENTRIES:],
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _save(seq: int, entries: list, config_path: str) -> bool:
    """写主文件（成功后再刷 .bak 与隐蔽备份）；返回主文件是否写成功。"""
    try:
        blob = crypto_utils.encrypt(_dump(seq, entries))
    except Exception:
        return False

    ok = _atomic_write_bytes(log_path_for(config_path), blob)
    if not ok:
        return False
    _atomic_write_bytes(log_backup_path_for(config_path), blob)
    backup_store.save_backup(blob, tag=_tag(config_path), prefix=HIDDEN_PREFIX)
    return True


# --- 对外接口 -----------------------------------------------------------


def load(config_path: str = "", repair: bool = True) -> LogView:
    """读取日志：main → .bak → 隐蔽备份，取 seq 最大的那份，并修复其它副本。

    日志是只增不减的，所以 seq 最大 = 最新。这样即使有人用旧的 .bak 覆盖主
    文件（GCM 解不出来才算篡改；用旧密文覆盖是能被看出来的），也会被修回来。
    永远不抛异常；一份副本都没有时返回空日志。
    """
    if not config_path:
        from .config_store import resolve_config_path
        config_path = resolve_config_path()

    candidates = []           # (seq, 优先级, source, entries)
    main = _read_copy(log_path_for(config_path))
    if main is not None:
        candidates.append((main[0], 2, "main", main[1]))
    bak = _read_copy(log_backup_path_for(config_path))
    if bak is not None:
        candidates.append((bak[0], 1, "bak", bak[1]))
    hidden = _read_hidden(config_path)
    if hidden is not None:
        candidates.append((hidden[0], 0, "hidden", hidden[1]))

    if not candidates:
        return LogView([], 0, "empty")

    seq, _prio, source, entries = max(candidates, key=lambda c: (c[0], c[1]))
    if repair and source != "main":
        _save(seq, entries, config_path)   # 顺手把主文件/备份修回一致
    return LogView(entries, seq, source)


def _pair(value) -> tuple[str, str]:
    """把 ("中文","English") / 纯字符串 统一成两条文本。"""
    if isinstance(value, (tuple, list)) and len(value) == 2:
        return str(value[0])[:MAX_TEXT_LEN], str(value[1])[:MAX_TEXT_LEN]
    text = ("" if value is None else str(value))[:MAX_TEXT_LEN]
    return text, ""


def append_many(texts, config_path: str = "") -> bool:
    """追加若干条日志（旧 → 新），写满三个副本。失败静默返回 False。

    texts 里的元素可以是纯字符串，也可以是 (中文, English) 二元组。
    """
    pairs = [_pair(t) for t in texts]
    pairs = [p for p in pairs if p[0] or p[1]]
    if not pairs:
        return False
    try:
        view = load(config_path)
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entries = list(view.entries) + [[stamp, zh, en] for zh, en in pairs]
        return _save(view.seq + len(pairs), entries, config_path)
    except Exception:
        return False


def append(zh: str, en: str = "", config_path: str = "") -> bool:
    """追加一条双语日志。"""
    return append_many([(zh, en)], config_path)


def clear(config_path: str = "") -> bool:
    """清空日志（仅供测试/排障；应用本身从不调用，日志永不删除）。"""
    if not config_path:
        from .config_store import resolve_config_path
        config_path = resolve_config_path()
    return _save(0, [], config_path)
