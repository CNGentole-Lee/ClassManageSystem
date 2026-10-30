#!/bin/bash
# 在 macOS 上交叉编译 Windows 原生模块（native/cmd_native.exe）
#
# 不需要管理员权限，也不依赖 MSVC：
#   * 用 zig 提供 x86_64-windows-gnu 的 C/C++ 工具链与 libc++；
#   * libsodium 用同一套工具链静态编译。
#
# 前置（一次性）：
#   .tools/zig-macos-aarch64-0.13.0/          解压好的 zig
#   native/third_party/libsodium-1.0.20/      libsodium 源码
#   native/third_party/libsodium-windows/     交叉编译产物（本脚本可生成）
#
# 注意：
#   * zig 默认把缓存写到 ~/.cache/zig，受限环境不可写，这里改到 .tools 下；
#   * libsodium 的 libtool 在 mingw 目标下会调用 MSVC 的 lib.exe，
#     .tools/bin/lib 是转发到 `zig ar` 的兼容脚本，需要加入 PATH。
set -e
cd "$(dirname "$0")"
ROOT="$(cd .. && pwd)"
TP="$ROOT/native/third_party"
TOOLS="$ROOT/.tools"
ZIG="$TOOLS/zig-macos-aarch64-0.13.0/zig"

export ZIG_GLOBAL_CACHE_DIR="$TOOLS/zig-global"
export ZIG_LOCAL_CACHE_DIR="$TOOLS/zig-local"

if [ ! -x "$ZIG" ]; then
  echo "[x] 缺少 zig：$ZIG"
  echo "    下载 zig-macos-aarch64-0.13.0.tar.xz 并解压到 $TOOLS"
  exit 1
fi

if [ ! -f "$TP/libsodium-windows/lib/libsodium.lib" ]; then
  echo "[1/2] 交叉编译 libsodium"
  if [ ! -d "$TP/libsodium-1.0.20" ]; then
    echo "[x] 缺少 libsodium 源码：$TP/libsodium-1.0.20"
    exit 1
  fi
  cd "$TP/libsodium-1.0.20"
  make distclean >/dev/null 2>&1 || true
  CC="$ZIG cc -target x86_64-windows-gnu" \
  AR="$ZIG ar" RANLIB="$ZIG ranlib" \
  ./configure --host=x86_64-w64-mingw32 \
    --prefix="$TP/libsodium-windows" \
    --disable-shared --enable-static --with-pic \
    >/tmp/sodium_win_conf.log 2>&1
  PATH="$TOOLS/bin:$PATH" make -j8 >/tmp/sodium_win_make.log 2>&1
  PATH="$TOOLS/bin:$PATH" make install >>/tmp/sodium_win_make.log 2>&1
fi

echo "[2/2] 编译 cmd_native.exe"
cd "$ROOT/native"
"$ZIG" c++ -target x86_64-windows-gnu -std=c++17 -O2 -static \
  -I "$TP/libsodium-windows/include" \
  src/main.cpp src/crypto.cpp src/envfp.cpp src/state.cpp \
  "$TP/libsodium-windows/lib/libsodium.lib" \
  -o cmd_native.exe -lbcrypt

file cmd_native.exe
ls -lh cmd_native.exe
