"""AboutDialog —— 关于窗口。

为什么必须有它：
    Apache-2.0 第 4(d) 条要求分发时随附许可证副本与 NOTICE；
    LGPL v3 也要求让用户知道 Qt 是可替换的、并能看到其许可证。
    所以这里总是显示：程序名、版本、版权、不担保声明，
    以及「查看许可证」与第三方声明。

许可证结构：
    * 主程序（Python）—— Apache License 2.0；
    * 原生模块（native/，二进制）—— 专有许可，随程序使用；
    * PySide6 / Qt 6 —— LGPL v3，动态链接、可替换。
"""

import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPushButton, QTabWidget, QTextBrowser,
    QVBoxLayout,
)

from . import dialogs, theme
from .config_store import APP_NAME
from .i18n import tr

#: 版本号 —— 全项目唯一来源。
#: 打包脚本（spec / version_info.txt）在构建时从这里读取，不必手工同步。
VERSION = "3.0.0"

#: 「关于」窗口里许可证入口的标识
LICENSE_ACTION = "license"

COPYRIGHT = "Copyright 2026 Gentole Lee"
LICENSE_NAME = "Apache License 2.0"
LICENSE_URL = "https://www.apache.org/licenses/LICENSE-2.0"
NOTICES_URL = "https://github.com/Gentole/ClassManageSystem/blob/main/THIRD-PARTY-NOTICES.md"


#: 内置的许可证摘要（读不到 LICENSE 文件时显示）。
#: 目的：即使分发的安装包漏带了 LICENSE，关于窗口也能说明授权与担保状况。
#: 完整条款以随包的 LICENSE（Apache-2.0 全文）为准。
EMBEDDED_LICENSE = """                                 Apache License
                           Version 2.0, January 2004
                        http://www.apache.org/licenses/

班级多用教学辅助终端 (Class Management Terminal)
Copyright 2026 Gentole Lee

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

-----------------------------------------------------------------------------
The full text of the Apache License 2.0 is bundled as the `LICENSE` file.
完整条款见随包的 `LICENSE` 文件，或在线查看：
<https://www.apache.org/licenses/LICENSE-2.0>
-----------------------------------------------------------------------------

主要条款摘要（非正式文本，以英文原文为准）：

  1. 定义 —— "License" 指 Apache License 2.0 的条款与条件；
     "Licensor" 指授予许可的版权所有者或实体；
     "Work" 指本许可下提供的作品（含源码与目标码形式）。
  2. 版权许可 —— 每位贡献者授予你永久的、全球的、免费的、
     非独占的、不可撤销的版权许可，允许复制、创作衍生作品、
     公开展示、公开表演、再许可和分发本作品及其衍生作品。
  3. 专利许可 —— 每位贡献者授予你永久的、全球的、免费的、
     非独占的、不可撤销的专利许可，允许制造、使用、销售、
     许诺销售、进口本作品。
  4. 再分发 —— 你可以在任何媒介中复制和分发本作品或其衍生作品，
     前提是：向接收者提供本许可证副本；修改过的文件须显著标注；
     保留所有版权、专利、商标与归属声明；若作品含 NOTICE 文件，
     衍生产品须在分发中包含该 NOTICE 的可读副本。
  5. 提交贡献 —— 除非明确声明，你有意向本作品提交的贡献
     均按本许可条款授权，不附加额外条件。
  6. 商标 —— 本许可不授予使用许可方的商号、商标、服务标记
     或产品名称的权利，除非为合理描述作品来源所必需。
  7. 无担保 —— 本作品按"现状"提供，不附带任何明示或默示的担保，
     包括但不限于适销性、特定用途适用性和不侵权的担保。
  8. 责任限制 —— 在任何情况下，无论依据何种法律理论，
     贡献者均不对因使用本作品产生的任何损害承担责任。
  9. 接受担保或附加责任 —— 在再分发时，你可以提供担保、
     支持服务或其他责任承担，但须自行承担相应责任。
 10. 许可证版本 —— 版权所有者可授权使用本许可的任一版本。

-----------------------------------------------------------------------------
原生模块（native/）不适用 Apache-2.0，而是专有许可：
仅可随本程序使用，禁止单独分发、反向工程或提取算法。
详见随包的 native/LICENSE。

第三方组件（PySide6 / Qt 6 为 LGPL v3 等）见随包的 THIRD-PARTY-NOTICES.md。
-----------------------------------------------------------------------------
                     END OF TERMS SUMMARY
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


def _doc_candidates(rel: str) -> list[str]:
    """在源码目录与打包目录里找随包文档（rel 形如 'LICENSE'、'native/LICENSE'）。"""
    candidates = []
    base = getattr(sys, "_MEIPASS", "")
    if base:
        candidates.append(os.path.join(base, rel))
        candidates.append(os.path.join(base, "Resources", rel))
    here = os.path.dirname(os.path.abspath(__file__))
    candidates.append(os.path.join(os.path.dirname(here), rel))
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        contents = os.path.dirname(exe_dir)
        candidates.append(os.path.join(contents, "Resources", rel))
        candidates.append(os.path.join(exe_dir, rel))
        app_root = _macos_app_root()
        if app_root:
            candidates.append(os.path.join(app_root, rel))
            candidates.append(os.path.join(os.path.dirname(app_root), rel))
    return candidates


def doc_path(rel: str) -> str:
    """找到随程序分发的某个文档；找不到返回空串。"""
    for path in _doc_candidates(rel):
        try:
            if path and os.path.isfile(path):
                return os.path.normpath(path)
        except OSError:
            continue
    return ""


def doc_text(rel: str) -> str:
    """读取随包文档；读不到返回空串。"""
    path = doc_path(rel)
    if not path:
        return ""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def native_license_text() -> str:
    """原生模块的专有许可；缺失时给出内置摘要。"""
    text = doc_text(os.path.join("native", "LICENSE"))
    if text:
        return text
    return tr(
        "[\u63d0\u793a] \u672a\u627e\u5230 native/LICENSE\uff0c\u4ee5\u4e0b\u4e3a\u5185\u7f6e\u6458\u8981\uff1a\n\n"
        "\u539f\u751f\u6a21\u5757\uff08cmd_native / cmd_native.exe\uff09\u4e3a\u4e13\u6709\u8f6f\u4ef6\uff0c"
        "\u53ea\u80fd\u968f\u672c\u7a0b\u5e8f\u4f7f\u7528\uff1b\u7981\u6b62\u5355\u72ec\u5206\u53d1\u3001"
        "\u53cd\u5411\u5de5\u7a0b\u3001\u4fee\u6539\u6216\u63d0\u53d6\u5176\u4e2d\u7684\u7b97\u6cd5\u4e0e\u5bc6\u94a5\u3002"
        "\u6309\u201c\u73b0\u72b6\u201d\u63d0\u4f9b\uff0c\u4e0d\u9644\u5e26\u4efb\u4f55\u62c5\u4fdd\u3002\n",
        "[Note] native/LICENSE was not found; embedded summary:\n\n"
        "The native module (cmd_native / cmd_native.exe) is proprietary software and "
        "may only be used together with this application; standalone distribution, "
        "reverse engineering, modification or extraction of its algorithms and keys "
        "are prohibited. Provided AS IS, without warranty.\n",
    )


#: 依赖清单：(名称, 版本, 许可证, 备注)
DEPENDENCIES = [
    ("PySide6", "6.12.x", "LGPL-3.0", "dynamic"),
    ("Qt 6", "6.12.x", "LGPL-3.0", "dynamic"),
    ("shiboken6", "6.12.x", "LGPL-3.0", ""),
    ("cryptography", "50.x", "Apache-2.0 OR BSD-3-Clause", ""),
    ("cffi", "2.x", "MIT-0", ""),
    ("pycparser", "3.x", "BSD-3-Clause", ""),
    ("libsodium", "static", "ISC", "native-only"),
    ("Python", "3.14.x", "PSF-2.0", "bundled"),
]

#: 备注列按语言翻译
DEPENDENCY_NOTES = {
    "dynamic": ("动态链接、可替换", "dynamically linked, replaceable"),
    "native-only": ("仅存在于原生模块内部", "only inside the native module"),
    "bundled": ("打包时随附解释器", "interpreter bundled"),
}


def dependencies_html() -> str:
    """把依赖表渲染成 HTML 表格（比纯文本对齐好看得多）。"""
    zh = _is_zh()
    header = ("组件", "版本", "许可证", "说明") if zh else ("Component", "Version", "License", "Notes")
    parts = ['<table cellspacing="0" cellpadding="5" width="100%">',
             '<tr style="color:#888888; font-size:12px;">'
             + "".join(f'<td width="{w}">{h}</td>' for h, w
                       in zip(header, ("24%", "12%", "36%", "")))
             + '</tr>']
    for name, version, license_, note in DEPENDENCIES:
        note_zh, note_en = DEPENDENCY_NOTES.get(note, ("", ""))
        note_text = (note_zh if zh else note_en)
        parts.append(
            '<tr>'
            f'<td width="22%"><b>{name}</b></td>'
            f'<td width="14%" style="color:#888888;">{version}</td>'
            f'<td width="34%">{license_}</td>'
            f'<td style="color:#888888;">{note_text}</td>'
            '</tr>'
        )
    parts.append("</table>")
    if zh:
        tail = (
            "<p style='margin:12px 0 4px 0; font-size:12px; color:#888888;'>"
            "LGPL v3 要求用户能够替换 Qt 库：安装目录下的 Qt 动态库"
            "（_internal/Qt*.dll、Contents/Frameworks/Qt*.framework）是独立文件，"
            "安装后可直接替换，无需重新编译本程序。</p>"
            "<p style='margin:8px 0; font-size:12px; color:#888888;'>"
            "完整声明（版权行、主页、许可证链接）见「第三方组件」分页与随包的 "
            "THIRD-PARTY-NOTICES.md。</p>"
        )
    else:
        tail = (
            "<p style='margin:12px 0 4px 0; font-size:12px; color:#888888;'>"
            "LGPL v3 requires that users can replace the Qt libraries: the Qt shared "
            "libraries in the install directory (_internal/Qt*.dll, "
            "Contents/Frameworks/Qt*.framework) are separate files and can be replaced "
            "after installation without rebuilding this program.</p>"
            "<p style='margin:8px 0; font-size:12px; color:#888888;'>"
            "Full notices (copyright, homepages, license links) are on the "
            "&quot;Third-party&quot; tab and in the bundled THIRD-PARTY-NOTICES.md.</p>"
        )
    return "".join(parts) + tail


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


def _is_zh() -> bool:
    try:
        from . import i18n
        return i18n.is_zh()
    except Exception:                                  # noqa: BLE001
        return True


def markdown_to_html(text: str) -> str:
    """把随包文档里的少量 Markdown 转成 HTML。

    只支持这些文档实际用到的语法，不做通用实现：
    标题 #~####、加粗 **x**、行内代码 `x`、链接 [t](url)、裸 URL、
    分隔线 ---、无序/有序列表、``` 代码块。
    其余内容先做 HTML 转义再原样输出，因此许可证里的缩进与符号不会被破坏。
    """
    import html
    import re

    def inline(chunk: str) -> str:
        out = html.escape(chunk, quote=False)
        out = re.sub(r"`([^`]+)`",
                     lambda m: '<code>' + m.group(1) + '</code>', out)
        out = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", out)
        out = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', out)
        out = re.sub(r"&lt;(https?://[^&]+)&gt;", r'<a href="\1">\1</a>', out)
        out = re.sub(r"(?<![\"=>])(https?://[^\s<]+)", r'<a href="\1">\1</a>', out)
        return out

    out: list[str] = []
    in_code = False
    list_open = None
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            out.append('<p style="margin:4px 0;">' + inline(" ".join(paragraph)) + '</p>')
            paragraph = []

    def close_list() -> None:
        nonlocal list_open
        if list_open:
            out.append("</" + list_open + ">")
            list_open = None

    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if stripped.startswith("```"):
            flush_paragraph()
            close_list()
            out.append("</pre>" if in_code
                       else '<pre style="margin:6px 0;">')
            in_code = not in_code
            continue
        if in_code:
            out.append(html.escape(raw, quote=False))
            continue
        if not stripped:
            flush_paragraph()
            close_list()
            continue
        if set(stripped) <= {"-"} and len(stripped) >= 3:
            flush_paragraph()
            close_list()
            out.append('<hr style="border:none; border-top:1px solid #88888855; margin:10px 0;">')
            continue
        heading = re.match(r"^(#{1,4})\s+(.*)$", stripped)
        if heading:
            flush_paragraph()
            close_list()
            level = len(heading.group(1))
            size = {1: "15px", 2: "14px", 3: "13px", 4: "12px"}.get(level, "12px")
            out.append('<p style="font-size:' + size + '; font-weight:bold; margin:10px 0 4px 0;">'
                       + inline(heading.group(2)) + '</p>')
            continue
        bullet = re.match(r"^[-*]\s+(.*)$", stripped)
        ordered = re.match(r"^(\d+)\.\s+(.*)$", stripped)
        if bullet or ordered:
            flush_paragraph()
            want = "ul" if bullet else "ol"
            if list_open != want:
                close_list()
                indent = "18px" if want == "ul" else "22px"
                out.append('<' + want + ' style="margin:4px 0 4px ' + indent + ';">')
                list_open = want
            body = bullet.group(1) if bullet else ordered.group(2)
            out.append("<li>" + inline(body) + "</li>")
            continue
        close_list()
        paragraph.append(stripped)

    flush_paragraph()
    close_list()
    if in_code:
        out.append("</pre>")
    return "\n".join(out)


class AboutDialog(QDialog):
    """关于窗口：版权 + 不担保声明 + 许可证全文。"""

    def _make_text_view(self, text: str, already_html: bool = False) -> QTextBrowser:
        """生成一个与许可证页同样式的只读视图。"""
        view = QTextBrowser()
        view.setOpenExternalLinks(True)
        if not already_html:
            view.setHtml(markdown_to_html(text))
        view.setFont(theme.font(11))
        view.setStyleSheet(
            f"background: {theme.c('log_bg')}; color: {theme.c('text')};"
            f" border: 1px solid {theme.c('view_border')};"
        )
        return view

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

        # 「不担保」声明：必须显眼，不能藏起来（Apache-2.0 第 7、8 条）
        notice = QLabel(tr(
            "本程序以 Apache License 2.0 授权；你可以自由使用、修改与再分发，"
            "但须保留版权与许可声明。\n"
            "本程序按**“现状”**提供，**不提供任何担保**，"
            "也不承担因使用产生的任何责任。\n"
            "原生模块（native/）为专有许可，仅可随本程序使用；"
            "PySide6 / Qt 6 为 LGPL v3，可替换。\n"
            "许可证全文见下方（{u}），第三方声明见 THIRD-PARTY-NOTICES.md。",
            "This program is licensed under the Apache License 2.0; you may use, "
            "modify and redistribute it, provided the copyright and license notices "
            "are kept.\n"
            "It is provided **\"AS IS\"**, **WITHOUT WARRANTIES OR CONDITIONS OF ANY "
            "KIND**, and without liability for any damages.\n"
            "The native module (native/) is proprietary and may only be used together "
            "with this program; PySide6 / Qt 6 are LGPL v3 and replaceable.\n"
            "The license is shown below ({u}); see THIRD-PARTY-NOTICES.md for "
            "third-party notices.",
            u=LICENSE_URL))
        notice.setWordWrap(True)
        notice.setTextFormat(Qt.RichText)
        notice.setText(_bold(notice.text()))
        notice.setStyleSheet(f"color: {theme.c('muted')};")
        layout.addWidget(notice)

        # 四个分页：许可证 / 原生模块 / 第三方组件 / 依赖
        self._browser = QTextBrowser()
        self._browser.setFont(theme.font(11))
        self._browser.setStyleSheet(
            f"background: {theme.c('log_bg')}; color: {theme.c('text')};"
            f" border: 1px solid {theme.c('view_border')};"
        )

        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(
            f"QTabBar::tab {{ padding: 5px 12px; color: {theme.c('muted')}; }}"
            f"QTabBar::tab:selected {{ color: {theme.c('text')}; font-weight: bold; }}"
        )
        self._tabs.addTab(self._browser, tr("许可证", "License"))

        self._native_view = self._make_text_view(native_license_text())
        self._tabs.addTab(self._native_view, tr("原生模块", "Native module"))

        notices = doc_text("THIRD-PARTY-NOTICES.md") or tr(
            "未找到 THIRD-PARTY-NOTICES.md。\n\n" + DEPENDENCIES_ZH,
            "THIRD-PARTY-NOTICES.md was not found.\n\n" + DEPENDENCIES_EN)
        self._notices_view = self._make_text_view(notices)
        self._tabs.addTab(self._notices_view, tr("第三方组件", "Third-party"))

        self._deps_view = self._make_text_view("", already_html=True)
        self._deps_view.setHtml(dependencies_html())
        self._tabs.addTab(self._deps_view, tr("依赖", "Dependencies"))

        self._browser.setOpenExternalLinks(True)
        self._browser.setHtml(markdown_to_html(license_text()))
        layout.addWidget(self._tabs, 1)

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
    打开许可证之后悬浮球双击抽人完全失效。查看许可证不需要模态，
    所以改成 show()。

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
