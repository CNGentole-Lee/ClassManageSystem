"""ledger —— 事件链的 Python 侧：只负责落盘与基准，业务在 C++ 里。

分工：
    C++（cmd_native）  状态机、规则校验、事件编码、加密、签名、链校验
    Python（本模块）   读文件、追加行、写基准、写安全副本、调用 C++
    Python（界面）     只显示 C++ 返回的状态，不解析事件

事件载荷是二进制（由 C++ 编码），Python 不解析、也不生成。
"""

from __future__ import annotations

import base64
import hashlib
import json
import os

from . import native_bridge

#: 链头占位（创世）
GENESIS = b"\x00" * 32


class LedgerError(Exception):
    pass


def data_dir_for(config_path: str) -> str:
    return os.path.join(os.path.dirname(os.path.abspath(config_path)), "Data")


def ledger_path_for(config_path: str) -> str:
    return os.path.join(data_dir_for(config_path), "ledger.esc")


def _anchor_dirs(config_path: str) -> list[str]:
    """基准/安全副本的位置：主目录一个，用户缓存目录一个（换个地方藏）。"""
    data_dir = data_dir_for(config_path)
    tag = hashlib.sha256(os.path.abspath(data_dir).encode("utf-8")).hexdigest()[:16]
    # 可用 CLASSMANAGE_STATE_DIR 覆盖（测试用；生产环境不设置）
    override = os.environ.get("CLASSMANAGE_STATE_DIR", "").strip()
    cache_root = override or os.environ.get("XDG_CACHE_HOME") or os.path.join(
        os.path.expanduser("~"), ".cache")
    return [data_dir, os.path.join(cache_root, "classmanage", tag)]


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
        self._state: dict | None = None
        self._pubkey_b64 = ""

    # --- 读取 ---

    def load(self) -> list[bytes]:
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
                        records.append(b"")     # 坏行留给 verify 判失败
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

    # --- 校验 / 状态 ---

    def verify(self) -> bool:
        """空链视为通过（尚未初始化）。"""
        records = self.load()
        if not records:
            self._verified = True
            self._verify_error = ""
            self._head = GENESIS
            self._state = {"count": 0, "names": [], "scores": [], "seq": 0, "ts": 0}
            return True
        data = self._call_state(records)
        self._verified = data is not None
        return self._verified

    def _call_state(self, records: list[bytes]) -> dict | None:
        try:
            data = native_bridge.state(records)
        except native_bridge.NativeError as exc:
            self._verify_error = str(exc)
            return None
        if not data.get("ok"):
            self._verify_error = str(data.get("error", "CHAIN_BROKEN"))
            return None
        self._head = base64.b64decode(data["head"])
        self._state = {
            "count": int(data.get("count", 0)),
            "names": list(data.get("names", [])),
            "scores": [int(x) for x in data.get("scores", [])],
            "seq": int(data.get("seq", 0)),
            "ts": int(data.get("ts", 0) or 0),
        }
        self._verify_error = ""
        return self._state

    def state(self) -> dict:
        """返回当前业务状态；必要时先校验。"""
        records = self.load()
        if not records:
            return {"count": 0, "names": [], "scores": [], "seq": 0, "ts": 0}
        if self._state is None:
            if self._call_state(records) is None:
                raise LedgerError(self._verify_error or "CHAIN_BROKEN")
        return self._state or {"count": 0, "names": [], "scores": [], "seq": 0, "ts": 0}

    # --- 基准（seq/head） ---

    def anchor_paths(self) -> list[str]:
        return [os.path.join(d, "anchor.json") for d in _anchor_dirs(self.config_path)]

    def read_anchor(self) -> tuple[int, bytes]:
        full = self.read_anchor_full()
        return int(full.get("seq", 0)), full.get("head_bytes", b"")

    def read_anchor_full(self) -> dict:
        """取所有锚点里 seq 最大的一份（含 ts/digest/pubkey）。"""
        best: dict = {"seq": 0, "head_bytes": b"", "ts": 0, "digest": "", "pubkey": ""}
        for path in self.anchor_paths():
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                seq = int(data.get("seq", 0))
                head = base64.b64decode(data.get("head", ""))
            except (OSError, ValueError, TypeError):
                continue
            if seq > int(best["seq"]):
                best = {
                    "seq": seq,
                    "head_bytes": head,
                    "ts": int(data.get("ts", 0) or 0),
                    "digest": str(data.get("digest", "") or ""),
                    "pubkey": str(data.get("pubkey", "") or ""),
                }
        return best

    def write_anchor(self, seq: int, head: bytes, ts: int = 0,
                     digest: str = "", pubkey: str = "") -> None:
        body = json.dumps({
            "seq": int(seq),
            "head": base64.b64encode(head).decode("ascii"),
            "ts": int(ts),
            "digest": digest,
            "pubkey": pubkey,
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
        """主链损坏/变短时，用安全副本恢复主链。"""
        path = self.shadow_path()
        if not os.path.isfile(path):
            return False
        try:
            with open(path, "r", encoding="ascii") as fh:
                lines = [ln.strip() for ln in fh if ln.strip()]
            records = [base64.b64decode(ln, validate=True) for ln in lines]
            ok, _head, _err = native_bridge.verify(records)
            if not ok:
                return False
            anchor_seq, _anchor_head = self.read_anchor()
            if anchor_seq and len(records) < anchor_seq:
                return False
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
        self._state = None
        self.load()
        self._verified = False
        if not self.verify():
            return False
        self.write_anchor(len(records), self._head)
        return True

    @staticmethod
    def state_digest(state: dict) -> str:
        """状态的规范化摘要（Python 直方，不需要密钥）。"""
        canonical = json.dumps({
            "count": int(state.get("count", 0)),
            "names": list(state.get("names", [])),
            "scores": [int(x) for x in state.get("scores", [])],
        }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.blake2b(canonical.encode("utf-8"), digest_size=32).hexdigest()

    def last_ts(self) -> int:
        """最后一条事件的单调时间戳（秒）。"""
        return int((self._state or {}).get("ts", 0) or 0)

    def anchor_problems(self, state: dict | None = None,
                        pubkey_b64: str = "") -> list[str]:
        """把本地链与锚点逐项对比，返回问题列表（空表示一致）。"""
        anchor = self.read_anchor_full()
        problems: list[str] = []
        if int(anchor["seq"]) == 0:
            return problems                        # 从未写过锚点：首次运行
        count = self.count()
        if count == 0:
            return ["DELETED"]
        if count < int(anchor["seq"]):
            problems.append(f"SHORTER {count}<{anchor['seq']}")
        if anchor["head_bytes"] and self._head and count == int(anchor["seq"]):
            if self._head != anchor["head_bytes"]:
                problems.append("HEAD_MISMATCH")
        ts = self.last_ts()
        if anchor["ts"] and ts and ts < int(anchor["ts"]):
            problems.append(f"TIME_ROLLBACK {ts}<{anchor['ts']}")
        if state is not None and anchor["digest"]:
            if self.state_digest(state) != anchor["digest"]:
                problems.append("STATE_MISMATCH")
        if pubkey_b64 and anchor["pubkey"] and pubkey_b64 != anchor["pubkey"]:
            problems.append("PUBKEY_MISMATCH")
        return problems

    def rollback_reason(self) -> str:
        seq, head = self.read_anchor()
        count = self.count()
        if seq == 0:
            return ""
        if count == 0:
            return "DELETED"
        if count < seq:
            return f"SHORTER {count}<{seq}"
        if count == seq and head and self.head() != head:
            return "HEAD_MISMATCH"
        return ""

    # --- 业务操作（交给 C++） ---

    def apply(self, op: str, **kwargs) -> dict:
        """执行一个业务操作，落盘并返回新状态。

        C++ 负责校验规则；规则不允许时抛 LedgerError，不写任何东西。
        """
        records = self.load()
        if records and not self._verified:
            if not self.verify():
                raise LedgerError("chain invalid: " + (self._verify_error or "UNKNOWN"))

        try:
            data = native_bridge.apply(records, op, **kwargs)
        except native_bridge.NativeError as exc:
            raise LedgerError(str(exc)) from exc
        if not data.get("ok"):
            raise LedgerError(str(data.get("error", "APPLY_FAILED")))

        record = base64.b64decode(data["record"])
        line = base64.b64encode(record).decode("ascii")
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        try:
            with open(self.path, "a", encoding="ascii") as fh:
                fh.write(line + "\n")
                fh.flush()
                os.fsync(fh.fileno())
            self._append_shadow(line)
        except OSError as exc:
            raise LedgerError(str(exc)) from exc

        self._records.append(record)
        self._head = base64.b64decode(data["head"])
        self._state = {
            "count": int(data.get("count", 0)),
            "names": list(data.get("names", [])),
            "scores": [int(x) for x in data.get("scores", [])],
            "seq": int(data.get("seq", len(self._records))),
            "ts": int(data.get("ts", 0) or 0),
        }
        self._verified = True
        self.write_anchor(len(self._records), self._head,
                          ts=self._state["ts"],
                          digest=self.state_digest(self._state),
                          pubkey=self._pubkey_b64)
        return self._state

    def migrate_from(self, group_count: int, names: list[str], scores: list[int]) -> bool:
        """把现有配置写成一条 init 事件（仅当链为空时）。"""
        if self.count() > 0:
            return False
        self.apply("init", count=int(group_count),
                   names=",".join(str(x) for x in names),
                   scores=",".join(str(int(x)) for x in scores))
        return True
