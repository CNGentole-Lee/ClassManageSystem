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

from . import dialogs, theme
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


#: 内置的 GPL-3.0 要点（与 LICENSE 文件同源）。
#: 目的：即使分发的 EXE / .app 旁边没有 LICENSE 文件，「关于」窗口也必须能显示许可证，
#: 这是 GPL-3.0 的分发要求 —— 不能因为漏带一个文本文件就不合规。
#: 完整条款仍以 LICENSE / gnu.org 为准；这里保证离线也能读到实质内容。
EMBEDDED_LICENSE = """GNU GENERAL PUBLIC LICENSE
Version 3, 29 June 2007

Copyright (C) 2007 Free Software Foundation, Inc. <https://fsf.org/>
Everyone is permitted to copy and distribute verbatim copies
of this license document, but changing it is not allowed.

班级多用教学辅助终端 (Class Management Terminal)
Copyright (C) 2026 Gentole Lee

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, version 3 of the License.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

-----------------------------------------------------------------------------
The complete text of GPL-3.0 is bundled as the `LICENSE` file and is also
available online at <https://www.gnu.org/licenses/gpl-3.0.txt>.
Full text online / 完整条款在线: <https://www.gnu.org/licenses/gpl-3.0.html>
-----------------------------------------------------------------------------

  0. Definitions.  "This License" refers to version 3 of the GNU General
Public License. "The Program" refers to any copyrightable work licensed under
this License.

  1. Source Code.  The "source code" for a work means the preferred form of
the work for making modifications to it.

  2. Basic Permissions.  All rights granted under this License are granted for
the term of copyright on the Program, and are irrevocable provided the stated
conditions are met. This License explicitly affirms your unlimited permission
to run the unmodified Program.

  3. Protecting Users' Legal Rights From Anti-Circumvention Law.  No covered
work shall be deemed part of an effective technological measure under any
applicable law fulfilling obligations under article 11 of the WIPO copyright
treaty.

  4. Conveying Verbatim Copies.  You may convey verbatim copies of the
Program's source code as you receive it, in any medium, provided that you
conspicuously and appropriately publish on each copy an appropriate copyright
notice and give all recipients a copy of this License along with the Program.

  5. Conveying Modified Source Versions.  You may convey a work based on the
Program in source form, provided that you carry prominent notices stating that
you modified it and that it is released under this License, and that you
license the entire work as a whole under this License.

  6. Conveying Non-Source Forms.  You may convey a covered work in object code
form provided that you also convey the machine-readable Corresponding Source
under the terms of this License.

  7. Additional Terms.  "Additional permissions" are terms that supplement the
terms of this License by making exceptions from one or more of its conditions.

  8. Termination.  You may not propagate or modify a covered work except as
expressly provided under this License. Any attempt otherwise to propagate or
modify it is void and terminates your rights under this License.

  9. Acceptance Not Required for Having Copies.  You are not required to
accept this License in order to receive or run a copy of the Program.

 10. Automatic Licensing of Downstream Recipients.  Each time you convey a
covered work, the recipient automatically receives a license from the original
licensors to run, modify and propagate that work under this License.

 11. Patents.  Each contributor grants you a non-exclusive, worldwide,
royalty-free patent license under the contributor's essential patent claims.

 12. No Surrender of Others' Freedom.  If conditions are imposed on you that
contradict the conditions of this License, they do not excuse you from its
conditions.

 13. Use with the GNU Affero General Public License.  You have permission to
link or combine any covered work with a work licensed under AGPL version 3.

 14. Revised Versions of this License.  The Free Software Foundation may
publish revised and/or new versions of the GNU General Public License.

 15. Disclaimer of Warranty.  THERE IS NO WARRANTY FOR THE PROGRAM, TO THE
EXTENT PERMITTED BY APPLICABLE LAW. EXCEPT WHEN OTHERWISE STATED IN WRITING
THE COPYRIGHT HOLDERS AND/OR OTHER PARTIES PROVIDE THE PROGRAM "AS IS" WITHOUT
WARRANTY OF ANY KIND, EITHER EXPRESSED OR IMPLIED.

 16. Limitation of Liability.  IN NO EVENT UNLESS REQUIRED BY APPLICABLE LAW
OR AGREED TO IN WRITING WILL ANY COPYRIGHT HOLDER BE LIABLE TO YOU FOR
DAMAGES, INCLUDING ANY GENERAL, SPECIAL, INCIDENTAL OR CONSEQUENTIAL DAMAGES
ARISING OUT OF THE USE OR INABILITY TO USE THE PROGRAM.

 17. Interpretation of Sections 15 and 16.  If the disclaimer of warranty and
limitation of liability provided above cannot be given local legal effect,
reviewing courts shall apply local law that most closely approximates an
absolute waiver of all civil liability.

                     END OF TERMS AND CONDITIONS
"""


def _macos_app_root() -> str:
    """`.app` 包所在目录（可执行文件在 Contents/MacOS 里，往上三级）。"""
    try:
        exe = os.path.abspath(sys.executable)
        macos_dir = os.path.dirname(exe)
        contents = os.path.dirname(macos_dir)
        if os.path.basename(macos_dir) == "MacOS" and os.path.basename(contents) == "Contents":
            return os.path.dirname(contents)          # .../Xxx.app
    except Exception:
        pass
    return ""


def license_candidates() -> list[str]:
    """按优先级列出可能的 LICENSE 路径（自检里会逐条报告）。"""
    candidates = []
    base = getattr(sys, "_MEIPASS", "")               # 单文件 EXE / macOS .app 解包目录
    if base:
        candidates.append(os.path.join(base, "LICENSE"))
        candidates.append(os.path.join(base, "Resources", "LICENSE"))

    here = os.path.dirname(os.path.abspath(__file__))  # namepicker/
    candidates.append(os.path.join(os.path.dirname(here), "LICENSE"))   # 源码运行

    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        # .app 内部（bundle 里 Content*/Resources/LICENSE，随 BUNDLE.resources 打包）
        contents = os.path.dirname(exe_dir)
        candidates.append(os.path.join(contents, "Resources", "LICENSE"))
        # EXE / .app 同级（分发给用户时手工放一份也能读到）
        candidates.append(os.path.join(exe_dir, "LICENSE"))
        app_root = _macos_app_root()
        if app_root:
            candidates.append(os.path.join(app_root, "LICENSE"))
            candidates.append(os.path.join(os.path.dirname(app_root), "LICENSE"))
    return candidates


def license_path() -> str:
    """找到随程序分发的 LICENSE 文件；一个都找不到时返回空串。

    查找顺序覆盖：源码运行（项目根目录）、单文件 EXE（_MEIPASS）、
    macOS `.app`（Contents/Resources，或 .app 同级）。
    """
    for path in license_candidates():
        try:
            if path and os.path.isfile(path):
                return os.path.normpath(path)
        except OSError:
            continue
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
    # 找不到随程序分发的 LICENSE：显示内置全文，而不是只说一句“找不到”。
    # （分发的 EXE / .app 常常只拷贝了单文件，旁边没有 LICENSE。）
    header = tr(
        "[提示] 未找到随程序分发的 LICENSE 文件，以下为内置的许可证要点。\n"
        "完整条款请访问 {u}\n"
        "———————————————————————————————————————————\n\n",
        "[Note] The LICENSE file bundled with this program was not found; "
        "the embedded licence summary is shown below.\n"
        "Full terms: {u}\n"
        "———————————————————————————————————————————\n\n",
        u=LICENSE_URL)
    return header + EMBEDDED_LICENSE


def _bold(text: str) -> str:
    """把 **xxx** 转成 <b>xxx</b>（QTextBrowser 不解析 Markdown）。"""
    import html
    import re
    escaped = html.escape(text)
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)


class AboutDialog(QDialog):
    """关于窗口：版权 + 不担保声明 + 许可证全文。"""

    def showEvent(self, event) -> None:
        """显示时居中；macOS 上用 level 25 的浮层（低于抽选弹窗）。"""
        super().showEvent(event)
        dialogs.center_on_screen(self)
        if sys.platform == "darwin":
            from . import macos_window
            macos_window.make_overlay(self, macos_window.NS_STATUS_WINDOW_LEVEL)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("关于", "About"))
        self.setMinimumSize(640, 520)
        # 关于窗口不参与 macOS 的「对话框抬升到 26」：它要低于抽选弹窗(25)，
        # 这样用户一边看许可证、一边双击悬浮球抽人时，抽选结果仍在最上面。
        self.setProperty("cmd_skip_raise", True)

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


#: 当前打开的关于窗口（非模态，需要自己持有引用，否则会被 GC 掉）
_open_about = None


def _forget_about(*_args) -> None:
    global _open_about
    _open_about = None


def show_about(parent=None) -> None:
    """显示关于窗口。

    **非模态**：模态对话框会拦截整个程序的输入 —— 之前的版本用 exec_()，
    打开许可证之后悬浮球双击抽人完全失效。GPL 只要求能查看许可证，
    不要求模态，所以改成 show()。

    parent 固定为 None：这个窗口可能从托盘/悬浮球打开，那时主窗口是隐藏的，
    以它为父窗口在 Windows 上会把对话框定位到屏幕外。
    """
    global _open_about
    if _open_about is not None:
        try:
            if _open_about.isVisible():
                dialogs.reveal(_open_about)
                return
        except RuntimeError:          # C++ 侧已销毁
            _open_about = None

    dialog = AboutDialog(None)
    dialog.setAttribute(Qt.WA_DeleteOnClose, True)
    dialog.setWindowModality(Qt.NonModal)
    dialog.destroyed.connect(_forget_about)
    _open_about = dialog
    dialogs.reveal(dialog)
