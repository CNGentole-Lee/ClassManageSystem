"""ledger —— 事件链：积分变更的追加式记录。

设计：
    * 每条事件由原生模块加密、签名并算出链头（Python 不接触密钥）；
    * 文件是 base64 行文本，追加写，永不改写；
    * 启动时用原生模块校验整条链，再用 dump 取回明文做重放；
    * 校验失败时调用方应拒绝采用链上的分数，而不是静默忽略。

事件载荷（JSON，明文进 C++ 加密）：
    {"op":"init","count":6,"names":[...],"scores":[...]}
    {"op":"score","g":2,"v":5,"r":"+2"}
    {"op":"rename","g":2,"name":"雄鹰组"}
    {"op":"count","n":8}
    {"op":"reset","count":6,"names":[...],"scores":[...]}
    {"op":"wipe","parts":{"names":true,"scores":true,...}}
"""

from __future__ import annotations

import base64
import json
import os
from typing import NamedTuple

from . import native_bridge

#: 链头占位（创世）
GENESIS = b"\x00" * 32

#: 事件类型
OP_INIT = 1
OP_SCORE = 2
OP_RENAME = 3
OP_COUNT = 4
OP_RESET = 5
OP_WIPE = 6

#: 每多少条事件轮换一次签名代次（先固定为 0，格式已预留）
GEN_SIZE = 500


class ReplayState(NamedTuple):
    group_count: int
    names: dict[int, str]      # 1-based
    scores: dict[int, int]
    events: int                # 事件条数
    head: bytes


class LedgerError(Exception):
    pass


def _anchor_dirs(config_path: str) -> list[str]:
    """基准文件的位置：主目录一个，用户缓存目录一个（换个地方藏）。"""
    import hashlib
    import tempfile
    data_dir = data_dir_for(config_path)
    tag = hashlib.sha256(os.path.abspath(data_dir).encode("utf-8")).hexdigest()[:16]
    # 可用 CLASSMANAGE_STATE_DIR 覆盖（测试用；生产环境不设置）
    override = os.environ.get("CLASSMANAGE_STATE_DIR", "").strip()
    cache_root = override or os.environ.get("XDG_CACHE_HOME") or os.path.join(
        os.path.expanduser("~"), ".cache")
    if not cache_root or cache_root == os.path.join("~", ".cache"):
        cache_root = tempfile.gettempdir()
    return [data_dir, os.path.join(cache_root, "classmanage", tag)]


def data_dir_for(config_path: str) -> str:
    return os.path.join(os.path.dirname(os.path.abspath(config_path)), "Data")


def ledger_path_for(config_path: str) -> str:
    return os.path.join(data_dir_for(config_path), "ledger.esc")


class Ledger:
    """一条事件链。线程不安全（GUI 单线程足够）。"""

    def __init__(self, config_path: str):
        self.config_path = config_path
        self.path = ledger_path_for(config_path)
        self._records: list[bytes] = []
        self._head: bytes = GENESIS
        self._loaded = False
        self._verify_error = ""
        self._verified = False

    # --- 读取 ---

    def load(self) -> list[bytes]:
        """读入所有记录（base64 行）。文件不存在返回空。"""
        if self._loaded:
            return self._records
        records: list[bytes] = []
        try:
            with open(self.path, "r", encoding="ascii") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        records.append(base64.b64decode(line, validate=True))
                    except Exception:
                        # 坏行保留占位，让 verify 去判定失败
                        records.append(b"")
        except FileNotFoundError:
            records = []
        except OSError as exc:
            raise LedgerError(str(exc)) from exc
        self._records = records
        self._loaded = True
        return records

    def count(self) -> int:
        return len(self.load())

    def head(self) -> bytes:
        return self._head

    def verified(self) -> bool:
        return self._verified

    def verify_error(self) -> str:
        return self._verify_error

    # --- 校验 ---

    def verify(self) -> bool:
        """用原生模块校验整条链。空链视为通过（尚未初始化）。"""
        records = self.load()
        if not records:
            self._verified = True
            self._verify_error = ""
            self._head = GENESIS
            return True
        ok, head, err = native_bridge.verify(records)
        self._verified = bool(ok)
        self._verify_error = "" if ok else (err or "UNKNOWN")
        if ok:
            self._head = head
        return ok

    # --- 基准（seq/head） ---
    #
    # 为什么需要它：事件链本身是“自洽”的 —— 把整个 Data 目录换成一份旧的、
    # 合法的副本，链依然能验签通过。只有记住“曾经到过第几条、链头是什么”，
    # 才能在启动时发现“变短了 / 换了一条”。

    def anchor_paths(self) -> list[str]:
        return [os.path.join(d, "anchor.json") for d in _anchor_dirs(self.config_path)]

    def read_anchor(self) -> tuple[int, bytes]:
        """取所有基准里 seq 最大的一份；没有返回 (0, b"")。"""
        best = (0, b"")
        for path in self.anchor_paths():
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                seq = int(data.get("seq", 0))
                head = base64.b64decode(data.get("head", ""))
            except (OSError, ValueError, TypeError):
                continue
            if seq > best[0]:
                best = (seq, head)
        return best

    def write_anchor(self, seq: int, head: bytes) -> None:
        """把 (seq, head) 写到所有基准位置；失败不影响追加。"""
        body = json.dumps({
            "seq": int(seq),
            "head": base64.b64encode(head).decode("ascii"),
        }, separators=(",", ":")).encode("utf-8")
        for path in self.anchor_paths():
            try:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                tmp = path + ".tmp"
                with open(tmp, "wb") as fh:
                    fh.write(body)
                    fh.flush()
                    os.fsync(fh.fileno())
                os.replace(tmp, path)
            except OSError:
                continue

    def shadow_path(self) -> str:
        """安全副本：放在用户缓存目录，与 Data 分开，删 Data 删不到它。"""
        return os.path.join(_anchor_dirs(self.config_path)[1], "ledger.esc")

    def _append_shadow(self, line: str) -> None:
        path = self.shadow_path()
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "a", encoding="ascii") as fh:
                fh.write(line + "\n")
                fh.flush()
                os.fsync(fh.fileno())
        except OSError:
            pass

    def restore_from_shadow(self) -> bool:
        """主链损坏/变短时，用安全副本恢复主链。成功返回 True。"""
        path = self.shadow_path()
        if not os.path.isfile(path):
            return False
        try:
            with open(path, "r", encoding="ascii") as fh:
                lines = [ln for ln in fh.read().splitlines() if ln.strip()]
            records = [base64.b64decode(ln, validate=True) for ln in lines]
            ok, head, _err = native_bridge.verify(records)
            if not ok:
                return False
            anchor_seq, anchor_head = self.read_anchor()
            if anchor_seq and len(records) < anchor_seq:
                return False                      # 副本也旧，不能用来恢复
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="ascii") as out:
                out.writelines(ln + "\n" for ln in lines)
                out.flush()
                os.fsync(out.fileno())
            os.replace(tmp, self.path)
        except (OSError, ValueError) as exc:
            self._verify_error = f"RESTORE_FAILED {exc}"
            return False
        self._loaded = False
        self.load()
        self._verified = True
        self._verify_error = ""
        self._head = head
        self.write_anchor(len(records), head)
        return True

    def rollback_reason(self) -> str:
        """返回空串表示正常；否则返回回滚/删除的原因。"""
        seq, head = self.read_anchor()
        count = self.count()
        if seq == 0:
            return ""                      # 从未写过基准：首次运行
        if count == 0:
            return "DELETED"
        if count < seq:
            return f"SHORTER {count}<{seq}"
        if count == seq and head and self.head() != head:
            return "HEAD_MISMATCH"
        return ""

    # --- 追加 ---

    def append(self, op: int, payload: dict) -> bytes:
        """追加一条事件，返回新链头；失败抛 LedgerError。"""
        records = self.load()
        seq = len(records) + 1
        gen = (seq - 1) // GEN_SIZE
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        try:
            record, head = native_bridge.append(self._head, seq, body, gen=gen)
        except native_bridge.NativeMissing as exc:
            raise LedgerError(f"native module missing: {exc}") from exc
        except native_bridge.NativeError as exc:
            raise LedgerError(str(exc)) from exc

        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        line = base64.b64encode(record).decode("ascii")
        try:
            with open(self.path, "a", encoding="ascii") as fh:
                fh.write(line + "\n")
                fh.flush()
                os.fsync(fh.fileno())
            self._append_shadow(line)
        except OSError as exc:
            raise LedgerError(str(exc)) from exc
        self._records.append(record)
        self._head = head
        self.write_anchor(seq, head)
        return head

    # --- 重放 ---

    def replay(self) -> ReplayState:
        """校验并解密所有事件，重放出组名 / 分数 / 组数。"""
        records = self.load()
        if not records:
            return ReplayState(0, {}, {}, 0, GENESIS)
        plains, head, err = native_bridge.dump(records)
        if not plains:
            raise LedgerError(err or "DUMP_FAILED")

        count = 0
        names: dict[int, str] = {}
        scores: dict[int, int] = {}
        n_events = 0
        for plain in plains:
            payload = _payload_of(plain)
            if payload is None:
                raise LedgerError("BAD_PAYLOAD")
            op = payload.get("op")
            n_events += 1
            if op == "init" or op == "reset":
                count = int(payload.get("count", 0))
                names = {i + 1: str(x) for i, x in enumerate(payload.get("names", []))}
                scores = {i + 1: int(x) for i, x in enumerate(payload.get("scores", []))}
            elif op == "score":
                scores[int(payload["g"])] = int(payload["v"])
            elif op == "rename":
                names[int(payload["g"])] = str(payload["name"])
            elif op == "count":
                new_count = int(payload["n"])
                names = {}
                scores = {}
                count = new_count
            elif op == "wipe":
                parts = payload.get("parts", {})
                if parts.get("names"):
                    names = {}
                if parts.get("scores"):
                    scores = {}
            else:
                raise LedgerError(f"UNKNOWN_OP {op!r}")
        return ReplayState(count, names, scores, n_events, head)

    # --- 迁移 ---

    def migrate_from(self, group_count: int, names: list[str], scores: list[int]) -> bool:
        """把现有配置写成一条 init 事件（仅当链为空时）。"""
        if self.count() > 0:
            return False
        self.append(OP_INIT, {
            "op": "init",
            "count": int(group_count),
            "names": [str(x) for x in names],
            "scores": [int(x) for x in scores],
        })
        return True


def _payload_of(plain: bytes) -> dict | None:
    """从明文里取出 payload：prev(32) seq(4) ts(8) op(1) len(4) payload。"""
    try:
        if len(plain) < 49:
            return None
        length = int.from_bytes(plain[45:49], "little")
        body = plain[49:49 + length]
        if len(body) != length:
            return None
        data = json.loads(body.decode("utf-8"))
        return data if isinstance(data, dict) else None
    except (ValueError, UnicodeDecodeError):
        return None
