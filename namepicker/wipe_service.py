"""wipe_service —— 按「彻底重置」对话框的勾选项执行清空。

单独抽出来是为了可测试：main.py 只负责把对话框结果传进来，
tools/smoke_test.py 可以直接验证「只勾积分时组名不动」这类行为。
"""

from typing import NamedTuple

from .config_store import ConfigStore, is_default_group_name
from .i18n import tr

#: 勾选项 → (中文, English) 显示名
PART_LABELS = {
    "names": ("组名", "group names"),
    "scores": ("积分", "scores"),
    "fairness": ("长期公平记录", "fairness counts"),
    "history": ("抽取历史", "draw history"),
}


class WipeReport(NamedTuple):
    """一次重置的结果。saved/verified 都是 False 时界面必须报错，不能装作成功。"""
    labels: list[str]        # 被清空项的名字（当前语言）
    saved: bool              # store.save() 是否成功
    verified: bool           # 是否已从磁盘读回并确认已生效
    error: str = ""          # 失败原因（保存失败时来自 ConfigStore.last_error）

    def ok(self) -> bool:
        return self.saved and self.verified


def selected_labels(parts: dict) -> list[str]:
    """被选中项的人话名字（跟随界面语言）。"""
    return [tr(zh, en) for key, (zh, en) in PART_LABELS.items() if parts.get(key)]


def _verify(store, stats, engine, parts: dict) -> bool:
    """从磁盘重新读一遍，确认选中的项真的被清掉了。"""
    try:
        disk = ConfigStore(store.path)
        if parts.get("scores") and any(disk.all_scores()):
            return False
        if parts.get("names"):
            for index in range(1, disk.group_count + 1):
                if not is_default_group_name(disk.get_group_name(index), index):
                    return False
        if parts.get("fairness"):
            if stats.load():
                return False
            if any(engine.get_draw_counts().values()):
                return False
        if parts.get("history") and engine.get_history():
            return False
        return True
    except Exception:
        return False


def perform_wipe(store, stats, engine, parts: dict) -> WipeReport:
    """按 parts 清空，返回被清空项的名字（用于状态栏提示）。

    parts = {"names": bool, "scores": bool, "fairness": bool, "history": bool}

    语义：
      * names   —— 只恢复默认组名，保留分数与组数
      * scores  —— 只把分数归零，保留组名
      * fairness—— 清长期抽取次数（stats.ini + 内存），保留抽取历史
      * history —— 清抽取历史与冷却，保留长期次数
    操作日志永不清空，由各步骤自行追加记录。
    """
    parts = {k: bool(v) for k, v in (parts or {}).items()}
    try:
        return _wipe(store, stats, engine, parts)
    except Exception as exc:          # 任何一步炸了都要让上层看见
        return WipeReport(selected_labels(parts), False, False, repr(exc))


def _wipe(store, stats, engine, parts: dict) -> WipeReport:
    if parts.get("names"):
        store.wipe_group_names()
    if parts.get("scores"):
        store.wipe_scores()
    if parts.get("fairness"):
        stats.clear()
        engine.clear_draw_counts()
        store.log_operation("彻底重置：长期公平记录已清零",
                            "Full reset: lifetime fairness counts cleared")
    if parts.get("history"):
        engine.clear_history()
        store.log_operation("彻底重置：抽取历史与冷却已清空",
                            "Full reset: draw history and cooldowns cleared")

    saved = bool(store.save())
    error = "" if saved else (store.last_error() or "save failed")
    verified = _verify(store, stats, engine, parts) if saved else False
    return WipeReport(selected_labels(parts), saved, verified, error)
