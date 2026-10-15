#!/bin/bash
# ============================================================
#  一键打包 macOS 应用（双击本文件即可运行）
#
#  产物：dist/ClassManageSystem.app
#
#  为什么不能顺便打个 Windows 的 .exe：
#  PyInstaller 不支持交叉编译，macOS 上只能产出 macOS 程序。
#  Windows EXE 请走 .github/workflows/build-windows.yml 或 Windows 上的 build.bat。
# ============================================================
set -euo pipefail

cd "$(dirname "$0")/../.."          # 切到项目根目录
ROOT="$(pwd)"
echo "项目目录: $ROOT"

# --- 1. 选 Python：优先项目自带虚拟环境 ---
PY=""
for cand in ".conda/bin/python" ".venv/bin/python" ".venv-build/bin/python"; do
  if [ -x "$cand" ]; then PY="$cand"; break; fi
done
if [ -z "$PY" ]; then
  for cand in python3 python; do
    if command -v "$cand" >/dev/null 2>&1; then PY="$cand"; break; fi
  done
fi
[ -n "$PY" ] || { echo "找不到 Python，请先安装 Python 3.10+"; exit 1; }

echo "[1/5] 使用 Python: $PY"
"$PY" --version

# --- 2. 依赖检查 ---
echo "[2/5] 检查依赖"
"$PY" - <<'CHECK' || exit 1
import importlib, sys
missing = []
for mod in ("PyQt5.QtCore", "PyQt5.QtWidgets", "cryptography"):
    try:
        importlib.import_module(mod)
    except ImportError:
        missing.append(mod.split(".")[0])
if missing:
    print("缺少依赖:", ", ".join(sorted(set(missing))))
    print("请先执行: python -m pip install -r requirements.txt")
    sys.exit(1)
try:
    import PyInstaller  # noqa: F401
except ImportError:
    print("缺少 PyInstaller，正在安装 ...")
    import subprocess
    sys.exit(subprocess.call([sys.executable, "-m", "pip", "install", "pyinstaller"]))
print("依赖齐全")
CHECK

# --- 3. 打包前自检（存储 / 日志 / 平台）---
echo "[3/5] 运行自检"
HOME_ISOLATED="$(mktemp -d)"
HOME="$HOME_ISOLATED" "$PY" tools/config_crypto_check.py | tail -1
HOME="$HOME_ISOLATED" "$PY" tools/log_crypto_check.py    | tail -1
rm -rf "$HOME_ISOLATED"
"$PY" tools/windows_check.py | tail -1

# --- 4. 生成图标（可选，缺 Pillow 也不影响，因为走 Qt）---
echo "[4/5] 生成图标"
if [ ! -f packaging/macos/app.icns ]; then
  "$PY" packaging/macos/make_icns.py || echo "  图标生成失败，将使用默认图标"
else
  echo "  已存在 app.icns，跳过"
fi

# --- 5. 打包 ---
echo "[5/5] PyInstaller 打包（首次约 1~3 分钟）"
rm -rf build "dist/ClassManageSystem.app" 2>/dev/null || true
# PyInstaller 的缓存/临时目录都放进项目内：
#   1) 不污染 ~/Library/Application Support；
#   2) 受限环境（沙箱、只读 HOME）下也能构建 —— 否则它清理 ~/Library 下的缓存
#      会直接 PermissionError 中断（本机首次就是这么挂的）。
export PYINSTALLER_CONFIG_DIR="$ROOT/.pyinstaller-cache"
mkdir -p "$PYINSTALLER_CONFIG_DIR"
"$PY" -m PyInstaller packaging/macos/ClassManageSystem.spec \
      --noconfirm --clean \
      --workpath "$ROOT/build" --distpath "$ROOT/dist"

APP="dist/ClassManageSystem.app"
if [ ! -d "$APP" ]; then
  echo "打包失败：没有生成 $APP"
  exit 1
fi

# 去掉隔离属性，避免本机首次运行被 Gatekeeper 拦
xattr -dr com.apple.quarantine "$APP" 2>/dev/null || true

SIZE="$(du -sh "$APP" | cut -f1)"
echo
echo "============================================================"
echo " 打包完成"
echo " 产物: $ROOT/$APP  ($SIZE)"
echo
echo " 运行:  open \"$APP\""
echo " 分发:  压缩后发给别人；对方首次需右键 → 打开"
echo "============================================================"
