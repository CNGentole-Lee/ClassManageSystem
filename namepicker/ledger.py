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
import shutil
import time

from . import native_bridge

#: 链头占位（创世）
GENESIS = b"\x00" * 32

#: 记录格式版本文件（v1 无此文件；迁移后写 2）
FORMAT_FILE = "format"
FORMAT_V2 = "2"


class LedgerError(Exception):
    pass


def data_dir_for(config_path: str) -> str:
    return os.path.join(os.path.dirname(os.path.abspath(config_path)), "Data")


def ledger_path_for(config_path: str) -> str:
    return os.path.join(data_dir_for(config_path), "ledger.esc")


#: 这些错误码表示"文件是老版本写的"，而不是"文件坏了"。
#: 区别很重要：坏数据要报警/恢复，旧数据只要提示重录 —— 绝不能去"修"它。
_LEGACY_ERRORS = ("BAD_FORMAT", "UNKNOWN_OP", "BAD_COUNT", "BAD_EVENT")


def _is_format_mismatch(exc: Exception) -> bool:
    """判断 native 报的错是不是"格式不兼容"（≡ 旧版本数据）。"""
    message = str(exc)
    return any(code in message for code in _LEGACY_ERRORS)


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
        self._plains: list[bytes] | None = None
        self._resigned = False
        self._last_repair_error = ""
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
        self._legacy = False
        if records and self._has_format_marker():
            # 链存在但重放不了：可能是旧版签名密钥问题，尝试原地重签一次
            # （必须能解密且明文哈希匹配，否则放弃，不掩盖真正的篡改）
            try:
                native_bridge.dump(records)
            except native_bridge.NativeError as exc:
                if _is_format_mismatch(exc):
                    # 版本/格式不对：这是"旧数据"，不是"坏数据"。
                    # 绝不能让 repair 去重签 —— 那会把用户的原始记录改写成
                    # 新格式，等于悄悄替他做了迁移，而且迁移出来还是错的。
                    self._legacy = True
                else:
                    self._repair_chain()
        if records and not self._has_format_marker():
            # 先判断是不是已经是 v2（新版本创建的链）：能 dump 就是 v2
            try:
                native_bridge.dump(records)
            except native_bridge.NativeError as exc:
                if _is_format_mismatch(exc):
                    self._legacy = True
                else:
                    # 也可能是「本机指纹变了，解不开」——迁移同样会失败，
                    # 此时不要静默吞掉，直接报错，否则后面所有操作都会莫名其妙地失败。
                    self._migrate_v1()
            else:
                self._write_format_marker()
        return self._records

    def is_legacy(self) -> bool:
        """这条链是不是旧版本（格式不兼容）写的。

        注意与"被篡改"区分：格式不兼容是**已知的旧版本**，
        应当提示老师手动重录；而字节被改是安全问题，走另一条提示。
        """
        self.load()                     # 确保已判定过
        return bool(getattr(self, "_legacy", False))

    def _repair_chain(self) -> None:
        """重新签名整条链；失败则保持原样（让上层报错）。"""
        try:
            data = native_bridge.repair(self._records)
        except native_bridge.NativeError:
            return
        new_records = [base64.b64decode(x) for x in data.get("records", [])]
        if len(new_records) != len(self._records):
            return
        # 备份必须成功，否则宁可不重写：这是唯一能回退的副本
        backup = self.path + ".repair.bak"
        try:
            shutil.copy2(self.path, backup)
        except OSError:
            self._last_repair_error = "backup failed"
            return
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="ascii") as fh:
            for rec in new_records:
                fh.write(base64.b64encode(rec).decode("ascii") + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self.path)

        # 写完后立即复核；不通过就回滚到备份，绝不留下坏链。
        #
        # 用 dump 而不是 state：dump 会完整走一遍「解密 → 验签 → 解析事件 →
        # 应用状态」，验证强度和 state 一样；而 state() 要求把 plains 按顺序
        # 喂进去，repair 重编号之后那份 plains 与记录不再一一对应，V4 的
        # 有状态事件（profile-rule 依赖 profile-new）会因此被误判为失败。
        plains = [base64.b64decode(x) for x in data.get("plains", [])]
        try:
            check = native_bridge.dump(new_records)
            verified = check.get("ok") is True
        except native_bridge.NativeError:
            verified = False
        if not verified:
            try:
                shutil.copy2(backup, self.path)
            except OSError:
                pass
            self._last_repair_error = "repair did not verify; rolled back"
            return

        self._records = new_records
        self._plains = plains
        self._resigned = True

        # 重签后链头变了，锚点必须同步更新，否则下次启动会误报 HEAD_MISMATCH。
        # digest 留空：重签后的状态还没重放，等正常流程再写。
        try:
            head = hashlib.blake2b(new_records[-1], digest_size=32).digest()
            self.write_anchor(len(new_records), head, ts=0, digest="",
                              pubkey=self._pubkey_b64,
                              repaired_at=int(time.time()))
        except Exception:                            # noqa: BLE001
            pass

    def _has_format_marker(self) -> bool:
        return os.path.isfile(os.path.join(os.path.dirname(self.path), FORMAT_FILE))

    def _write_format_marker(self) -> None:
        try:
            with open(os.path.join(os.path.dirname(self.path), FORMAT_FILE),
                      "w", encoding="ascii") as fh:
                fh.write(FORMAT_V2 + "\n")
        except OSError:
            pass

    def _migrate_v1(self) -> None:
        """v1 → v2：用签名器重签整条链，原文件备份为 ledger.esc.v1.bak。"""
        try:
            data = native_bridge.migrate(self._records)
        except native_bridge.NativeError as exc:
            raise LedgerError(f"migrate failed: {exc}") from exc
        new_records = [base64.b64decode(x) for x in data.get("records", [])]
        if len(new_records) != len(self._records):
            raise LedgerError("migrate returned a different record count")
        try:
            shutil.copy2(self.path, self.path + ".v1.bak")
        except OSError:
            pass
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="ascii") as fh:
            for rec in new_records:
                fh.write(base64.b64encode(rec).decode("ascii") + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self.path)
        self._records = new_records
        self._plains = [base64.b64decode(x) for x in data.get("plains", [])]
        self._write_format_marker()

    def count(self) -> int:
        return len(self.load())

    def head(self) -> bytes:
        return self._head

    def verified(self) -> bool:
        return self._verified

    def verify_error(self) -> str:
        return self._verify_error

    # --- 校验 / 状态 ---

    def plains(self) -> list[bytes]:
        """拿到每条记录的明文（签名器解密），用于验证器重放。"""
        records = self.load()
        if self._plains is not None and len(self._plains) == len(records):
            return self._plains
        if not records:
            self._plains = []
            return self._plains
        try:
            data = native_bridge.dump(records)
        except native_bridge.NativeError as exc:
            raise LedgerError(str(exc)) from exc
        self._plains = [base64.b64decode(x) for x in data.get("plains", [])]
        if len(self._plains) != len(records):
            raise LedgerError("dump returned a different record count")
        return self._plains

    def verify(self) -> bool:
        """空链视为通过；有记录则交给【验证器】验签 + 重放。"""
        records = self.load()
        if not records:
            self._verified = True
            self._verify_error = ""
            self._head = GENESIS
            self._state = {"count": 0, "names": [], "scores": [], "seq": 0, "ts": 0}
            return True
        try:
            plains = self.plains()
        except LedgerError as exc:
            self._verify_error = str(exc)
            self._verified = False
            return False
        return self._verify_with(records, plains)

    def _verify_with(self, records: list[bytes], plains: list[bytes]) -> bool:
        try:
            data = native_bridge.state(records, plains)
        except native_bridge.NativeError as exc:
            self._verify_error = str(exc)
            self._verified = False
            return False
        if data.get("ok") is not True:
            self._verify_error = str(data.get("error", "CHAIN_BROKEN"))
            self._verified = False
            return False
        self._head = base64.b64decode(data["head"])
        # V4：所有业务数据都在 profiles 里。count/names/scores/draws 保留空值，
        # 只为让旧的调用方不至于 KeyError —— 它们是 3.x 的遗留字段。
        self._state = {
            "count": 0,
            "names": [],
            "scores": [],
            "draws": {},
            "seq": int(data.get("seq", 0)),
            "ts": int(data.get("ts", 0) or 0),
            "profiles": [
                {
                    "id": int(p.get("id", 0)),
                    "name": str(p.get("name", "")),
                    "group_count": int(p.get("group_count", 0)),
                    "members": [int(g) for g in p.get("members", [])],
                    "group_names": [str(n) for n in p.get("group_names", [])],
                    "scores": [int(v) for v in p.get("scores", [])],
                    "draw_counts": [int(v) for v in p.get("draw_counts", [])],
                }
                for p in data.get("profiles", [])
            ],
            "active_profile": int(data.get("active_profile", 0) or 0),
        }
        self._verify_error = ""
        self._verified = True
        return True

    def state(self) -> dict:
        """返回当前业务状态；必要时先校验。"""
        empty = {"count": 0, "names": [], "scores": [], "seq": 0, "ts": 0,
                 "draws": {}, "profiles": [], "active_profile": 0}
        records = self.load()
        if not records:
            return empty
        if self._state is None:
            if not self.verify():
                raise LedgerError(self._verify_error or "CHAIN_BROKEN")
        return self._state or empty

    # --- 基准（seq/head） ---

    def anchor_paths(self) -> list[str]:
        return [os.path.join(d, "anchor.json") for d in _anchor_dirs(self.config_path)]

    def read_anchor(self) -> tuple[int, bytes]:
        full = self.read_anchor_full()
        return int(full.get("seq", 0)), full.get("head_bytes", b"")

    def read_anchor_full(self) -> dict:
        """取所有锚点里 seq 最大的一份（含 ts/digest/pubkey）。"""
        best: dict = {"seq": 0, "head_bytes": b"", "ts": 0, "digest": "",
                      "pubkey": "", "repaired_at": 0}
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
                    "repaired_at": int(data.get("repaired_at", 0) or 0),
                    # 旧版锚点没有 pubkey 字段：这是"还没有"，不是"不一致"
                    "has_pubkey": "pubkey" in data,
                }
        return best

    def write_anchor(self, seq: int, head: bytes, ts: int = 0,
                     digest: str = "", pubkey: str = "",
                     repaired_at: int = 0) -> None:
        """更新锚点。

        **公钥只写一次**：锚点里已有公钥就沿用旧值，绝不覆盖。
        否则每次启动 / 每次改分都会把“当前公钥”写进去，随后的比对
        永远一致 —— 那等于把 PUBKEY_MISMATCH 废掉。
        """
        existing = self.read_anchor_full()
        # 全零链头只在 seq=0（创世）时合法；seq>0 传进来说明调用方还没重放，
        # 此时保留旧链头，避免把锚点写成一片 0 造成 HEAD_MISMATCH。
        if seq > 0 and head and not any(head):
            head = existing.get("head_bytes", b"") or head
        if existing.get("has_pubkey") and existing.get("pubkey"):
            pubkey = existing["pubkey"]
        # 重签时间同样只保留，不被后续启动覆盖
        if not repaired_at:
            repaired_at = int(existing.get("repaired_at", 0) or 0)
        body = json.dumps({
            "seq": int(seq),
            "head": base64.b64encode(head).decode("ascii"),
            "ts": int(ts),
            "digest": digest,
            "pubkey": pubkey,
            "repaired_at": int(repaired_at),
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
            dumped = native_bridge.dump(records)
            plains = [base64.b64decode(x) for x in dumped.get("plains", [])]
            ok, _head, _err = native_bridge.verify(records, plains)
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

    def repaired_at(self) -> int:
        """最近一次重签的时间（0 = 从未重签）。"""
        return int(self.read_anchor_full().get("repaired_at", 0) or 0)

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
        # digest 只在“链长度与锚点相同”时比；链正常增长时 digest 必然变，
        # 那不是篡改，比较它只会每天误报。
        if state is not None and anchor["digest"] and count == int(anchor["seq"]):
            if self.state_digest(state) != anchor["digest"]:
                problems.append("STATE_MISMATCH")
        # 旧锚点没有 pubkey 字段：视为“还没有”，不报错（升级兼容）
        if (pubkey_b64 and anchor.get("has_pubkey", bool(anchor["pubkey"]))
                and anchor["pubkey"] and pubkey_b64 != anchor["pubkey"]):
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
        """执行一个业务操作：签名器出记录，验证器复核，通过才落盘。"""
        records = self.load()
        plains = self.plains() if records else []
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
        plain = base64.b64decode(data.get("plain", ""))

        # 关键：新记录必须被【验证器】接受才写盘。
        # 换掉签名器时，它签出的记录在这里被拒。
        trial_records = records + [record]
        trial_plains = plains + [plain]
        if not self._verify_with(trial_records, trial_plains):
            raise LedgerError("verifier rejected the new record: " + self._verify_error)

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
        self._plains = trial_plains
        state = self._state or {}
        self.write_anchor(len(self._records), self._head,
                          ts=int(state.get("ts", 0)),
                          digest=self.state_digest(state),
                          pubkey=self._pubkey_b64)
        return state

    def import_snapshot(self, state: dict) -> bool:
        """用一份外部数据（用户已确认信任）作为本机链的新起点。

        V4：整条链被重建成「一条新的 init + 若干 profile-* 事件」——
        预设名字、组数、组员、组名、分数、抽取次数全部照搬，
        换电脑后不用重录任何东西。

        调用方必须先让用户明确确认"我信任这份数据"：数据来自别的密钥体系，
        签名证明不了来源，只能靠人。
        """
        profiles = list(state.get("profiles") or [])
        # 关键：把【已有记录】传下去，签名器才会算出正确的 seq。
        # 传空列表会让它从 seq=1 重新开始，与现有记录撞号，整条链报废。
        existing = self.load()
        plains = self.plains() if existing else []
        try:
            data = native_bridge.apply(existing, "init", count=0)
        except native_bridge.NativeError as exc:
            raise LedgerError(str(exc)) from exc
        record = base64.b64decode(data["record"])
        plain = base64.b64decode(data.get("plain", ""))
        # 验证器要复核**整条链**：只喂新记录会被判成"第一条记录的 prev 对不上"。
        if not self._verify_with(existing + [record], plains + [plain]):
            raise LedgerError("verifier rejected the imported snapshot: "
                              + self._verify_error)
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "a", encoding="ascii") as fh:
            fh.write(base64.b64encode(record).decode("ascii") + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        self._records.append(record)
        self._plains = plains + [plain]
        self._state = None                     # 强制下次重放，别拿旧状态

        # 预设（分组制）跟着这份数据一起搬过来：换电脑后分组不用重录。
        # 没有 profiles 的旧快照（3.x 那种只有组名/分数的）也在这里被
        # 装成一个预设，否则导入完就是「0 组」。
        if not profiles:
            profiles = [self._profile_from_legacy(state)]
        # 失败不影响导入本身 —— init 已经落地，分数没了可以再录一次；
        # 但这里不该吞掉编程错误，所以只忽略链层面的拒绝。
        self._import_profiles(profiles, int(state.get("active_profile", 0) or 0))
        return True

    @staticmethod
    def _profile_from_legacy(state: dict) -> dict:
        """把 3.x 快照的「组名 + 分数」装成一个预设。"""
        count = int(state.get("count", len(state.get("scores") or [])) or 0)
        names = [str(x) for x in (state.get("names") or [])][:count]
        scores = [int(x) for x in (state.get("scores") or [])][:count]
        return {
            "id": 1,
            "name": "导入的预设",
            "group_count": count,
            "members": [],
            "group_names": names,
            "scores": scores,
            "draw_counts": [],
        }

    def _load_incremental(self) -> list[bytes]:
        """把磁盘上新追加的行接进内存（绕过 load() 的一次性读取缓存）。

        `load()` 只在第一次读盘，之后一直返回缓存的列表；需要"看一眼最新
        落盘内容"的场合（如导入外部快照）用这个方法。
        """
        self._loaded = False
        self._records = []
        return self.load()

    def _import_profiles(self, profiles: list, active: int) -> None:
        """把外部快照里的预设写成 profile-* 事件（连同组名、分数、次数）。

        快照里的 id 会被保留：导入前写的那条 init 已经把预设表清空，
        所以 id 是自由的，不需要重新编号，界面上的勾选/引用也不会错位。
        """
        current = {p["id"]: p for p in self.state().get("profiles", [])}
        existing_max = max(current, default=0)
        id_map: dict[int, int] = {}
        pending: list[tuple[dict, dict]] = []
        for offset, raw in enumerate(profiles):
            if not isinstance(raw, dict):
                continue
            try:
                old_id = int(raw.get("id", 0))
                groups = int(raw.get("group_count", 0))
            except (TypeError, ValueError):
                continue
            name = str(raw.get("name", "")).strip()
            if old_id <= 0 or not name or not (0 <= groups <= 24):
                continue
            if old_id in current:
                # 同 id 已在链上：这份快照的预设跳过，绝不覆盖本机的
                id_map[old_id] = old_id
                continue
            pid = old_id if old_id > existing_max else existing_max + 1 + offset
            id_map[old_id] = pid
            pending.append((raw, {"id": pid, "name": name, "group_count": groups}))

        # 全部走 chain.apply：它负责签名、验证器复核、追加到磁盘并维护内存列表，
        # 每一步都能看到上一条的结果（profile-new 之后才允许 profile-rule）。
        for raw, profile in pending:
            pid = profile["id"]
            groups = profile["group_count"]
            members = [int(g) for g in (raw.get("members") or [])]
            draw_counts = [int(v) for v in (raw.get("draw_counts") or [])]
            member_count = max(len(members), len(draw_counts))
            self.apply("profile-new", id=pid, name=profile["name"])
            self.apply("profile-rule", id=pid, count=groups,
                       members=member_count)
            for index, group in enumerate(members):
                if 1 <= group <= groups:
                    self.apply("profile-member", id=pid, index=index, group=group)
            # 组名：空表示用默认名，不必写事件
            for index, name in enumerate(list(raw.get("group_names") or [])[:groups]):
                name = str(name)
                if name:
                    self.apply("profile-groupname", id=pid, group=index + 1,
                               name=name)
            # 分数：链上只记增量，从 0 加到目标值
            for index, value in enumerate(list(raw.get("scores") or [])[:groups]):
                value = max(-1000000, min(1000000, int(value)))
                if value:
                    self.apply("profile-score", id=pid, group=index + 1,
                               delta=value)
            # 抽取次数：按下标还原，0 不需要事件
            for index, total in enumerate(draw_counts):
                if int(total) > 0:
                    self.apply("draw", id=pid, index=index, total=int(total))

        mapped = id_map.get(active, 0)
        if not mapped and pending:
            # 没指定当前预设（或指向的预设被跳过了）：默认用第一个，
            # 否则导入完是"有预设但没启用"，界面还是 0 组。
            mapped = min(id_map.values()) if id_map else 0
        if mapped:
            self.apply("profile-use", id=mapped)
        self._state = None

    def migrate_from(self, group_count: int, names: list[str], scores: list[int]) -> bool:
        """把链写成一条 init 事件（仅当链为空时）。

        V4 起 init 只记「预设列表」：首次运行时没有任何预设，因此写 count=0。
        三个参数保留是为了不改调用方；它们描述的是 3.x 的全局组名/分数，
        在 V4 里已经没有对应概念了。
        """
        if self.count() > 0:
            return False
        self.apply("init", count=0)
        self._write_format_marker()
        return True
