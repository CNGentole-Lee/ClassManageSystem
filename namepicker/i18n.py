"""i18n —— 中英双语。

用法::

    from .i18n import tr
    label.setText(tr("彻底重置", "Reset all"))
    status.setText(tr("已加载 {n} 个名字", "{n} names loaded", n=count))

需要同时保留两种语言（操作日志）时用 :func:`both`::

    zh, en = both("第{d}组", "Group {d}", d=index)

为什么不用 Qt 的 .ts/.qm：
    * 本程序的字符串几乎都带参数与业务语义，用 `tr(zh, en)` 就地维护更直观；
    * tools/ 下大量脚本不依赖 Qt，也能用同一套。
"""

from __future__ import annotations

import locale
import os
from typing import NamedTuple

#: 支持的语言代码 → 语言菜单里显示的名字
SUPPORTED = {"zh": "中文", "en": "English"}
DEFAULT = "zh"

_lang = DEFAULT


def normalize(lang: str | None) -> str:
    """把各种写法（zh/en/zh_CN/en_US/Chinese…）归一到 "zh" / "en"。"""
    code = (lang or "").strip().lower()
    if code.startswith("en"):
        return "en"
    return "zh"


def set_language(lang: str | None) -> str:
    """设置当前语言，返回归一后的代码。"""
    global _lang
    _lang = normalize(lang)
    return _lang


def language() -> str:
    return _lang


def is_zh() -> bool:
    return _lang == "zh"


def tr(zh: str, en: str | None = None, **kwargs) -> str:
    """按当前语言返回文案；`en` 缺省时回退中文。"""
    text = en if (_lang == "en" and en is not None) else zh
    return text.format(**kwargs) if kwargs else text


class Bi(NamedTuple):
    """一条双语文案（中文, English）。"""
    zh: str
    en: str


def both(zh: str, en: str, **kwargs) -> Bi:
    """同时生成两种语言（用于操作日志等需要长期留存的文本）。"""
    if kwargs:
        return Bi(zh.format(**kwargs), en.format(**kwargs))
    return Bi(zh, en)


def as_pair(value) -> tuple[str, str]:
    """把 Bi / (zh, en) / 纯字符串统一成 (zh, en)。"""
    if isinstance(value, Bi):
        return value.zh, value.en
    if isinstance(value, tuple) and len(value) == 2:
        return str(value[0]), str(value[1])
    text = "" if value is None else str(value)
    return text, text


def system_language() -> str:
    """按系统语言猜一个初始值（不依赖 Qt，tools 也能用）。"""
    name = ""
    try:
        name = locale.getdefaultlocale()[0] or ""
    except Exception:
        name = ""
    if not name:
        for key in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
            value = os.environ.get(key)
            if value:
                name = value
                break
    return normalize(name)


def translator_for_qt(app, lang: str) -> None:
    """按语言装载 / 卸载 Qt 自带控件的中文翻译。

    Qt 默认就是英文，所以 en 模式不需要额外翻译；zh 模式才装载 qtbase_zh_CN。
    语言在运行中切换时，先卸掉旧的翻译器再装新的。
    """
    try:
        from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator
    except Exception:
        return
    old = getattr(app, "_cmd_translator", None)
    if old is not None:
        app.removeTranslator(old)
        app._cmd_translator = None
    if normalize(lang) != "zh":
        return
    translator = QTranslator(app)
    path = QLibraryInfo.location(QLibraryInfo.TranslationsPath)
    if (translator.load(QLocale(QLocale.Chinese, QLocale.China), "qtbase", "_", path)
            or translator.load("qtbase_zh_CN", path)):
        app.installTranslator(translator)
        app._cmd_translator = translator
