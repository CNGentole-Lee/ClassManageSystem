"""wipe_service —— 按「彻底重置」对话框的勾选项执行清空。

单独抽出来是为了可测试：main.py 只负责把对话框结果传进来，
tools/smoke_test.py 可以直接验证「只勾积分时组名不动」这类行为。
"""

from .i18n import tr

#: 勾选项 → (中文, English) 显示名
PART_LABELS = {
    "names": ("组名", "group names"),
    "scores": ("积分", "scores"),
    "fairness": ("长期公平记录", "fairness counts"),
    "history": ("抽取历史", "draw history"),
}


def selected_labels(parts: dict) -> list[str]:
    """被选中项的人话名字（跟随界面语言）。"""
    return [tr(zh, en) for key, (zh, en) in PART_LABELS.items() if parts.get(key)]


def perform_wipe(store, stats, engine, parts: dict) -> list[str]:
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

    store.save()
    return selected_labels(parts)
