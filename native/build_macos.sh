#!/bin/bash
# 构建 macOS 原生模块：native/cmd_native
set -e
cd "$(dirname "$0")"

SODIUM=third_party/libsodium-macos
if [ ! -f "$SODIUM/lib/libsodium.a" ]; then
  echo "[i] libsodium 静态库缺失，先编译："
  echo "    cd native/third_party/libsodium-1.0.20"
  echo "    ./configure --prefix=\"\$(pwd)/../libsodium-macos\" --disable-shared --enable-static --with-pic"
  echo "    make -j8 && make install"
  exit 1
fi

SDK="$(xcrun --show-sdk-path)"
CXX="$(xcrun --find clang++)"

"$CXX" -std=c++17 -O2 -Wall -Wextra -isysroot "$SDK" \
  -I "$SODIUM/include" \
  src/main.cpp src/crypto.cpp src/envfp.cpp \
  "$SODIUM/lib/libsodium.a" \
  -o cmd_native

# 发布版：去掉符号表（调试时改用 -g，不要 strip）
strip -x cmd_native || true
# ad-hoc 签名：避免 Gatekeeper 直接拦下未签名的可执行文件
codesign --force --sign - cmd_native 2>/dev/null || true

echo "[i] built: $(pwd)/cmd_native  ($(stat -f%z cmd_native) bytes)"
./cmd_native selftest
