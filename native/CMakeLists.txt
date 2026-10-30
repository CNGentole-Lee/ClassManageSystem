# 原生模块构建（macOS / Windows 通用）
cmake_minimum_required(VERSION 3.16)
project(cmd_native CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# 源码目录（不进仓库）
file(GLOB SOURCES "${CMAKE_CURRENT_SOURCE_DIR}/src/*.cpp")

# libsodium：优先用 third_party 下的静态库，其次系统库
set(SODIUM_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/third_party/libsodium-macos")
if(EXISTS "${SODIUM_ROOT}/include/sodium.h")
  message(STATUS "using bundled libsodium: ${SODIUM_ROOT}")
  add_library(sodium STATIC IMPORTED)
  set_target_properties(sodium PROPERTIES
    IMPORTED_LOCATION "${SODIUM_ROOT}/lib/libsodium.a"
    INTERFACE_INCLUDE_DIRECTORIES "${SODIUM_ROOT}/include")
else()
  message(STATUS "using system libsodium")
  find_library(SODIUM_LIB sodium REQUIRED)
  find_path(SODIUM_INC sodium.h REQUIRED)
  add_library(sodium UNKNOWN IMPORTED)
  set_target_properties(sodium PROPERTIES
    IMPORTED_LOCATION "${SODIUM_LIB}"
    INTERFACE_INCLUDE_DIRECTORIES "${SODIUM_INC}")
endif()

add_executable(cmd_native ${SOURCES})
target_link_libraries(cmd_native PRIVATE sodium)

# 发布构建：去符号、优化
target_compile_options(cmd_native PRIVATE -O2 -Wall -Wextra)

if(APPLE)
  target_link_libraries(cmd_native PRIVATE "-framework Security")
endif()
