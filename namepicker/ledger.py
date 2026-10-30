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
        except OSError as exc:
            raise LedgerError(str(exc)) from exc
        self._records.append(record)
        self._head = head
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
