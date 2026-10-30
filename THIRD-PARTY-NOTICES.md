# Third-Party Notices / 第三方软件声明

本程序（班级多用教学辅助终端 / Class Management Terminal）以 Apache License 2.0
发布。运行时依赖下列第三方组件，它们各自保留原有许可证与版权。

This project is licensed under the Apache License 2.0. It depends on the
following third-party components, each retaining its own license and copyright.

---

## 运行时依赖 / Runtime dependencies

### PySide6

- 版本 / Version: 6.12.x
- 许可证 / License: **LGPL-3.0**（GNU Lesser General Public License v3）
- 版权 / Copyright: The Qt Company Ltd. and contributors
- 主页 / Homepage: https://www.qt.io/qt-for-python
- 说明：本程序以**动态链接**方式使用 PySide6 与 Qt，安装目录下的 Qt 库
  （`_internal/Qt*.dll`、`Contents/Frameworks/Qt*.framework`）是独立文件，
  **用户可以替换**，符合 LGPL v3 第 4(d) 条。
  This application links PySide6/Qt **dynamically**; the Qt libraries are
  separate files under `_internal/` (Windows) or `Contents/Frameworks` (macOS)
  and can be replaced by the user, as required by LGPL v3 section 4(d).

### Qt 6

- 版本 / Version: 6.12.x
- 许可证 / License: **LGPL-3.0**
- 版权 / Copyright: The Qt Company Ltd. and contributors
- 主页 / Homepage: https://www.qt.io/

### shiboken6

- 版本 / Version: 6.12.x
- 许可证 / License: **LGPL-3.0**
- 版权 / Copyright: The Qt Company Ltd. and contributors
- 主页 / Homepage: https://www.qt.io/qt-for-python

### cryptography

- 版本 / Version: 50.x
- 许可证 / License: **Apache-2.0 OR BSD-3-Clause**
- 版权 / Copyright: The Python Cryptographic Authority and individual contributors
- 主页 / Homepage: https://github.com/pyca/cryptography

### cffi

- 版本 / Version: 2.x
- 许可证 / License: **MIT-0**
- 版权 / Copyright: Armin Rigo, Maciej Fijalkowski and contributors
- 主页 / Homepage: https://github.com/python-cffi/cffi

### pycparser

- 版本 / Version: 3.x
- 许可证 / License: **BSD-3-Clause**
- 版权 / Copyright: Eli Bendersky and contributors
- 主页 / Homepage: https://github.com/eliben/pycparser

### libsodium

- 版本 / Version: 由 native 模块静态链接 / statically linked into the native module
- 许可证 / License: **ISC**
- 版权 / Copyright: Frank Denis and contributors
- 主页 / Homepage: https://libsodium.org/
- 说明：仅存在于私有 native 模块中；该模块随程序分发，但源码不公开。
  Only present inside the proprietary native module, which is shipped in binary
  form only.

### Python

- 版本 / Version: 3.14.x（打包时随附解释器 / bundled by PyInstaller）
- 许可证 / License: **PSF-2.0**（Python Software Foundation License）
- 版权 / Copyright: Python Software Foundation
- 主页 / Homepage: https://www.python.org/

---

## 构建期工具 / Build-time tools（不随程序分发 / not distributed）

### PyInstaller

- 许可证 / License: GPL-2.0 **with a special exception** that permits building and
  distributing proprietary/commercial applications
- 主页 / Homepage: https://pyinstaller.org/
- 说明：仅用于打包，其代码不进入最终产物（bootloader 例外条款允许分发）。
  Used only to package; its code is not part of the application, and the
  bootloader exception explicitly permits redistribution of bundled apps.

---

## 商标 / Trademarks

"Qt" and the Qt logo are trademarks of The Qt Company Ltd.
"Python" is a trademark of the Python Software Foundation.
本程序与上述公司无隶属关系，也未获其背书。
This project is not affiliated with, or endorsed by, those companies.

---

## 许可证全文 / Full license texts

- Apache License 2.0: https://www.apache.org/licenses/LICENSE-2.0
- LGPL v3: https://www.gnu.org/licenses/lgpl-3.0.html
- MIT-0: https://opensource.org/license/mit-0
- BSD-3-Clause: https://opensource.org/license/bsd-3-clause
- ISC: https://opensource.org/license/isc-license-txt
- PSF-2.0: https://docs.python.org/3/license.html

随程序分发的 `LICENSE` 是 Apache License 2.0 全文；
其余许可证文本可从上述链接获取。
The bundled `LICENSE` file is the full text of the Apache License 2.0;
the other license texts are available at the links above.
