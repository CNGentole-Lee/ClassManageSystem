#!/bin/bash
# 在 macOS 上交叉编译 Windows 原生模块（需要 mingw-w64 + 交叉编译的 libsodium）
#   brew install mingw-w64
set -e
cd "$(dirname "$0")"

CXX=x86_64-w64-mingw32-g++
SODIUM=third_party/libsodium-windows
if ! command -v "$CXX" >/dev/null; then
  echo "[x] 未安装 mingw-w64：brew install mingw-w64"
  exit 1
fi
if [ ! -f "$SODIUM/lib/libsodium.a" ]; then
  echo "[x] 缺少交叉编译的 libsodium（$SODIUM/lib/libsodium.a）"
  echo "    先按 README 用 --host=x86_64-w64-mingw32 编译 libsodium"
  exit 1
fi

"$CXX" -std=c++17 -O2 -static -Wall -Wextra \
  -I "$SODIUM/include" \
  src/main.cpp src/crypto.cpp src/envfp.cpp \
  "$SODIUM/lib/libsodium.a" \
  -o cmd_native.exe -lbcrypt

echo "[i] built: $(pwd)/cmd_native.exe"
