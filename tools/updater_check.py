"""更新检查的离线测试（不联网）。

覆盖：
    * 版本比较（含"同版本不同构建"）
    * 非法版本号 / 非法资产名被拒绝
    * 下载地址只由常量拼出，proxy 只能是前缀
    * 找不到 build-info 时返回空，上层据此跳过检查
"""

import os
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)
sys.path.insert(0, _HERE)

from _encoding import utf8_output

utf8_output()

from namepicker import updater

failures = []


def check(label, ok, detail=""):
    print(f"[{'OK  ' if ok else 'FAIL'}] {label}" + (f"  {detail}" if detail else ""))
    if not ok:
        failures.append(label)


def main() -> int:
    # ---- 版本比较 ----
    local = ("3.0.0", "2026-11-01T10:00:00+08:00")
    check("higher patch is newer", updater.is_newer({"version": "3.0.1"}, local))
    check("higher minor is newer", updater.is_newer({"version": "3.1.0"}, local))
    check("same version is not newer",
          not updater.is_newer({"version": "3.0.0", "build": local[1]}, local))
    check("same version is never newer, even if the build time differs",
          not updater.is_newer({"version": "3.0.0", "build": "2099-01-01T00:00:00+08:00"},
                               local))
    check("older is not newer", not updater.is_newer({"version": "2.9.9"}, local))
    check("garbage version is rejected", not updater.is_newer({"version": "v3.0.1"}, local))

    # ---- 非法响应 ----
    check("bad json is rejected", updater.parse_remote(b"not json") is None)
    check("missing version is rejected", updater.parse_remote(b'{"build":"x"}') is None)
    check("injected version is rejected",
          updater.parse_remote(b'{"version":"3.0.1; rm -rf /"}') is None)
    good = updater.parse_remote(
        b'{"version":"3.0.1","build":"b","assets":{"windows":"a.exe"},"sha256":{}}')
    check("valid payload parses", good is not None and good["version"] == "3.0.1")

    # ---- 下载地址来自常量 ----
    cfg = {"repo": updater.DEFAULT_REPO, "proxy": "", "check_url": updater.DEFAULT_CHECK_URL}
    remote_win = {"version": "3.0.1", "assets": {"windows": "Setup.exe", "macos": "App.dmg"}}
    url = updater.download_url(cfg, remote_win)
    expected_asset = updater.asset_name(remote_win)
    check("download url is built from constants",
          url.startswith("https://github.com/" + updater.DEFAULT_REPO)
          and url.endswith(expected_asset),
          url)
    check("unknown platform asset is rejected",
          updater.download_url(cfg, {"version": "3.0.1", "assets": {}}) == "")
    check("asset name with separators is rejected",
          updater.download_url(cfg, {"version": "3.0.1",
                                     "assets": {"windows": "../../evil.exe"}}) == "")
    cfg_proxy = dict(cfg, proxy="https://gh-proxy.com/")
    proxied = updater.download_url(cfg_proxy, remote_win)
    check("proxy is only a prefix", proxied.startswith("https://gh-proxy.com/https://github.com/"),
          proxied)

    # ---- 离线时静默 ----
    saved = updater.TIMEOUT
    updater.TIMEOUT = 0.05
    try:
        cfg_bad = dict(cfg, check_url="http://127.0.0.1:9/version.json")
        check("unreachable CDN returns None", updater.fetch(cfg_bad, timeout=0.05) is None)
    finally:
        updater.TIMEOUT = saved

    # ---- 发布工具必须能在没有 PySide6 的 runner 上跑 ----
    for name in ("make_version_json.py", "make_build_info.py", "_version.py"):
        content = open(os.path.join(_HERE, name), encoding="utf-8").read()
        check(f"{name} does not import PySide6",
              "from PySide6" not in content and "import PySide6" not in content)

    # ---- 默认检查地址跟随“最新发布”，同 Tag 覆盖也有效 ----
    check("default check url is the latest release asset",
          "releases/latest/download/version.json" in updater.DEFAULT_CHECK_URL,
          updater.DEFAULT_CHECK_URL)
    check("proxy is used as a fallback for checks",
          updater._with_proxy(updater.DEFAULT_CHECK_URL.format(repo="x"), {"proxy": "https://gh-proxy.com/"})[-1]
          == "https://gh-proxy.com/" + updater.DEFAULT_CHECK_URL.format(repo="x"))
    check("proxy page uses the default gh-proxy when unset",
          updater.release_page_via_proxy({"repo": "r", "proxy": ""})
          == "https://gh-proxy.com/https://github.com/r/releases/latest")
    check("no proxy means a single attempt",
          len(updater._with_proxy("https://github.com/x", {"proxy": ""})) == 1)

    # ---- 本地 build-info ----
    tmp = tempfile.mkdtemp(prefix="cm_upd_")
    path = os.path.join(tmp, "build-info.txt")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write('{"version": "9.9.9", "build": "test"}')
    old = updater._build_info_paths
    updater._build_info_paths = lambda: [path]
    try:
        check("local build info is read", updater.local() == ("9.9.9", "test"), str(updater.local()))
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("garbage")
        check("corrupt build info yields empty", updater.local() == ("", ""))
    finally:
        updater._build_info_paths = old

    print("\n" + "=" * 60)
    if failures:
        print(f"{len(failures)} FAILED: {failures}")
        return 1
    print("ALL PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
