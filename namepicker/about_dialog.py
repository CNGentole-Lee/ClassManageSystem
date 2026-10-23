"""AboutDialog —— 关于窗口。

为什么必须有它：
    GPL-3.0 要求带交互界面的程序显示「Appropriate Legal Notices」
    （第 5(d) 条引用第 0 条的定义）：版权声明、不提供担保的说明、
    以及**如何查看许可证副本**。缺了它就属于分发不合规。

所以这里总是显示：
    * 程序名、版本、版权行；
    * "本程序不提供任何担保"；
    * 「查看许可证（GPL-3.0）」按钮 —— 直接打开完整的 LICENSE 全文。
"""

import os
import sys

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPushButton, QTextBrowser, QVBoxLayout,
)

from . import theme
from .config_store import APP_NAME
from .i18n import tr

#: 版本号 —— 全项目唯一来源。
#: 打包脚本（spec / version_info.txt）在构建时从这里读取，不必手工同步。
VERSION = "2.0.0"

#: 「关于」窗口里 GPL 要求的入口
LICENSE_ACTION = "license"

COPYRIGHT = "Copyright (C) 2026 Gentole Lee"
LICENSE_NAME = "GNU General Public License v3.0"
LICENSE_URL = "https://www.gnu.org/licenses/gpl-3.0.html"


def license_path() -> str:
    """找到随程序分发的 LICENSE 文件。

    源码运行：项目根目录；PyInstaller 打包后：`sys._MEIPASS`。
    找不到时返回空串（窗口里会提示去官网查看）。
    """
    candidates = []
    base = getattr(sys, "_MEIPASS", "")          # PyInstaller 解包目录
    if base:
        candidates.append(os.path.join(base, "LICENSE"))
    here = os.path.dirname(os.path.abspath(__file__))     # namepicker/
    root = os.path.dirname(here)
    candidates.append(os.path.join(root, "LICENSE"))      # 源码运行
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        candidates.append(os.path.join(exe_dir, "LICENSE"))
        # macOS .app：可执行文件在 Contents/MacOS 里
        candidates.append(os.path.join(exe_dir, "..", "Resources", "LICENSE"))
    for path in candidates:
        if path and os.path.isfile(path):
            return os.path.normpath(path)
    return ""


def license_text() -> str:
    """读取 LICENSE 全文；读不到时给出官网地址。"""
    path = license_path()
    if path:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return fh.read()
        except OSError:
            pass
    return tr("未找到随程序分发的 LICENSE 文件。\n\n请访问 {u} 查看完整条款。",
              "The LICENSE file bundled with this program was not found.\n\n"
              "See {u} for the full terms.", u=LICENSE_URL)


def _bold(text: str) -> str:
    """把 **xxx** 转成 <b>xxx</b>（QTextBrowser 不解析 Markdown）。"""
    import html
    import re
    escaped = html.escape(text)
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)


class AboutDialog(QDialog):
    """关于窗口：版权 + 不担保声明 + 许可证全文。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("关于", "About"))
        self.setMinimumSize(640, 520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(10)

        title = QLabel(tr(APP_NAME, "Class Management Terminal"))
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)
        layout.addWidget(QLabel(f"{tr('版本', 'Version')} {VERSION}"))
        layout.addWidget(QLabel(COPYRIGHT))

        # GPL-3.0 要求的「不担保」声明：必须显眼，不能藏起来
        notice = QLabel(tr(
            "本程序是自由软件，依据 GNU 通用公共许可证第 3 版授权，"
            "你可以转发和/或修改它。\n"
            "本程序分发时希望它有用，但**不提供任何担保**，"
            "甚至不提供适销性或特定用途适用性的默示担保。\n"
            "许可证全文见下方，也可访问 {u}。",
            "This program is free software, licensed under the GNU General Public "
            "License version 3; you may redistribute and/or modify it.\n"
            "It is distributed in the hope that it will be useful, but **WITHOUT ANY "
            "WARRANTY**, without even the implied warranty of merchantability or "
            "fitness for a particular purpose.\n"
            "The full license is shown below; see also {u}.",
            u=LICENSE_URL))
        notice.setWordWrap(True)
        notice.setTextFormat(Qt.RichText)
        notice.setText(_bold(notice.text()))
        notice.setStyleSheet(f"color: {theme.c('muted')};")
        layout.addWidget(notice)

        self._browser = QTextBrowser()
        self._browser.setPlainText(license_text())
        self._browser.setFont(theme.font(11))
        self._browser.setStyleSheet(
            f"background: {theme.c('log_bg')}; color: {theme.c('text')};"
            f" border: 1px solid {theme.c('view_border')};"
        )
        layout.addWidget(self._browser, 1)

        buttons = QHBoxLayout()
        path = license_path()
        if path:
            where = QLabel(tr("许可证文件：{p}", "License file: {p}", p=path))
            where.setStyleSheet(f"color: {theme.c('faint')}; font-size: 11px;")
            where.setWordWrap(True)
            buttons.addWidget(where, 1)
        buttons.addStretch()

        close_btn = QPushButton(tr("关闭", "Close"))
        close_btn.setDefault(True)
        close_btn.clicked.connect(self.accept)
        buttons.addWidget(close_btn)
        layout.addLayout(buttons)


def show_about(parent=None) -> None:
    """弹出关于窗口（模态）。"""
    AboutDialog(parent).exec_()
