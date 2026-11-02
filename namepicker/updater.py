"""updater —— 通过一个公开的 version.json 检查是否有新版本。

设计约束（都是安全要求，不要放宽）：

* 响应**只用来比较版本号**；下载地址由代码里的常量拼出来，
  绝不从响应里读取 —— 否则 CDN 被污染就能把老师引到任意地址。
* **只下载，永不自动执行**。下载完提示路径，由老师自己双击安装。
* 版本号必须匹配 ``^\\d+\\.\\d+\\.\\d+$``，资产名必须匹配白名单字符，
  否则当作无效响应忽略。
* 任何失败都静默返回 None：断网、被墙、限流、CDN 挂掉都不该影响上课。
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.request

#: 仓库与地址都写死；换仓库需要重新发版，这是故意的
DEFAULT_REPO = "CNGentole-Lee/ClassManageSystem"
DEFAULT_CHECK_URL = "https://cdn.jsdelivr.net/gh/{repo}@main/version.json"
RELEASE_PAGE = "https://github.com/{repo}/releases/latest"
ASSET_URL = "https://github.com/{repo}/releases/latest/download/{asset}"

VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
ASSET_RE = re.compile(r"^[A-Za-z0-9._-]{1,120}$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")

TIMEOUT = 3.0


# ---------------------------------------------------------------- 本地信息

def app_dir() -> str:
    """程序所在目录（与 config_store._app_dir 的规则一致）。"""
    if getattr(sys, "frozen", False):
        exe = os.path.dirname(os.path.abspath(sys.executable))
        if (os.path.basename(exe) == "MacOS"
                and os.path.basename(os.path.dirname(exe)) == "Contents"
                and os.path.dirname(exe).endswith(".app/Contents")):
            return os.path.dirname(os.path.dirname(os.path.dirname(exe)))
        return exe
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _build_info_paths() -> list[str]:
    paths = []
    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        paths.append(os.path.join(meipass, "build-info.txt"))
    paths.append(os.path.join(app_dir(), "_internal", "build-info.txt"))
    paths.append(os.path.join(app_dir(), "build-info.txt"))
    return paths


def local() -> tuple[str, str]:
    """(version, build)；读不到就返回 ("", "")。

    源码运行或旧版打包没有这个文件 —— 此时上层直接跳过更新检查，
    免得给开发机和老用户弹莫名其妙的提示。
    """
    for path in _build_info_paths():
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            continue
        version = str(data.get("version", "")).strip()
        build = str(data.get("build", "")).strip()
        if VERSION_RE.match(version):
            return version, build
    return "", ""


# ---------------------------------------------------------------- 配置

def config_path() -> str:
    return os.path.join(app_dir(), "update.json")


def load_config() -> dict:
    """读 update.json；缺失或损坏时用默认值。"""
    cfg = {
        "enabled": True,
        "repo": DEFAULT_REPO,
        "proxy": "",
        "check_url": DEFAULT_CHECK_URL,
    }
    try:
        with open(config_path(), encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return cfg
    if isinstance(data, dict):
        for key in ("enabled", "repo", "proxy", "check_url"):
            if key in data and isinstance(data[key], type(cfg[key])):
                cfg[key] = data[key]
    if not VERSION_RE.match("0.0.0") or not cfg["repo"]:
        cfg["repo"] = DEFAULT_REPO
    return cfg


def check_url(cfg: dict) -> str:
    return str(cfg.get("check_url") or DEFAULT_CHECK_URL).format(repo=cfg["repo"])


# ---------------------------------------------------------------- 远端

def parse_remote(payload: bytes | str) -> dict | None:
    """解析 version.json；格式不对就返回 None（绝不抛异常）。"""
    try:
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")
        data = json.loads(payload)
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    version = str(data.get("version", "")).strip()
    if not VERSION_RE.match(version):
        return None
    assets = data.get("assets") or {}
    sha = data.get("sha256") or {}
    return {
        "version": version,
        "build": str(data.get("build", "")).strip(),
        "notes": str(data.get("notes", "")).strip(),
        "assets": {k: str(v) for k, v in assets.items()} if isinstance(assets, dict) else {},
        "sha256": {k: str(v) for k, v in sha.items()} if isinstance(sha, dict) else {},
    }


def fetch(cfg: dict, timeout: float = TIMEOUT) -> dict | None:
    """请求 version.json；失败返回 None。"""
    request = urllib.request.Request(
        check_url(cfg), headers={"User-Agent": "ClassManageSystem-updater"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return parse_remote(response.read(64 * 1024))
    except Exception:                                     # noqa: BLE001
        return None


def version_tuple(text: str) -> tuple[int, int, int] | None:
    match = VERSION_RE.match(text or "")
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def is_newer(remote: dict, local_pair: tuple[str, str]) -> bool:
    """远端是否比本地新。

    版本号相同但 build 不同 → 视为“同版本小更新”，也提示。
    这样发版不一定非要改版本号。
    """
    remote_version = version_tuple(remote.get("version", ""))
    local_version = version_tuple(local_pair[0])
    if remote_version is None or local_version is None:
        return False
    if remote_version != local_version:
        return remote_version > local_version
    remote_build = (remote.get("build") or "").strip()
    local_build = (local_pair[1] or "").strip()
    return bool(remote_build) and remote_build != local_build


# ---------------------------------------------------------------- 下载

def platform_key() -> str:
    return "windows" if sys.platform == "win32" else "macos"


def _proxy_prefix(cfg: dict) -> str:
    proxy = str(cfg.get("proxy") or "").strip()
    return proxy.rstrip("/") + "/" if proxy else ""


def asset_name(remote: dict) -> str:
    name = str((remote.get("assets") or {}).get(platform_key(), ""))
    return name if ASSET_RE.match(name) else ""


def download_url(cfg: dict, remote: dict) -> str:
    """由常量拼出下载地址；proxy 只作为前缀。"""
    name = asset_name(remote)
    if not name:
        return ""
    return _proxy_prefix(cfg) + ASSET_URL.format(repo=cfg["repo"], asset=name)


def release_page(cfg: dict) -> str:
    return RELEASE_PAGE.format(repo=cfg["repo"])


def download(cfg: dict, remote: dict, dest_dir: str = "", timeout: float = 120.0) -> str:
    """下载安装包到本地，返回路径。

    只下载、不执行。若 version.json 提供了 sha256 且格式合法，下载后核对。
    失败抛 OSError（调用方负责提示）。
    """
    url = download_url(cfg, remote)
    if not url:
        raise OSError("没有适用于本平台的安装包")
    target_dir = dest_dir or os.path.join(os.path.expanduser("~"), "Downloads")
    os.makedirs(target_dir, exist_ok=True)
    target = os.path.join(target_dir, asset_name(remote))

    request = urllib.request.Request(
        url, headers={"User-Agent": "ClassManageSystem-updater"})
    with urllib.request.urlopen(request, timeout=timeout) as response, \
            open(target + ".part", "wb") as fh:
        while True:
            chunk = response.read(256 * 1024)
            if not chunk:
                break
            fh.write(chunk)

    expected = str((remote.get("sha256") or {}).get(platform_key(), "")).lower()
    if SHA_RE.match(expected):
        import hashlib
        digest = hashlib.sha256()
        with open(target + ".part", "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                digest.update(chunk)
        if digest.hexdigest() != expected:
            os.remove(target + ".part")
            raise OSError("下载文件校验失败（SHA-256 不符）")

    os.replace(target + ".part", target)
    return target
