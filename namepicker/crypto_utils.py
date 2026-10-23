"""crypto_utils —— AES-256-GCM 认证加密，供 config.dat 防篡改存储使用。

设计要点：
    * 算法 AES-256-GCM（认证加密）：任何一字节被改动，解密时必然抛
      InvalidTag，所以「手改积分」在解密阶段就会暴露，而不是被当成合法配置。
    * 密钥首次运行自动生成 32 字节随机密钥，存放在用户主目录
      （~/.classmanage_key，靠 os.path.expanduser("~") 适配 macOS / Windows），
      权限 600，绝不硬编码进源码。
    * 落盘格式：nonce(12 字节) + 密文 + GCM tag(16 字节)，整体二进制读写，
      用记事本打开就是乱码。

本模块只用标准库 + cryptography，不含任何 Windows 专有模块，macOS 可直接运行。
"""

import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

try:
    from .i18n import tr
except ImportError:  # 允许把 namepicker 目录直接加进 sys.path 的用法
    from i18n import tr  # type: ignore

#: 密钥文件：~/.classmanage_key（macOS 与 Windows 下 expanduser("~") 都有效）
KEY_FILENAME = ".classmanage_key"
KEY_FILE = os.path.join(os.path.expanduser("~"), KEY_FILENAME)

KEY_SIZE = 32      # AES-256
NONCE_SIZE = 12    # GCM 推荐 96 bit nonce
TAG_SIZE = 16      # GCM 认证标签长度
MIN_BLOB_SIZE = NONCE_SIZE + 1  # 比这还短的文件一定是空的/被截断的

# 懒加载：避免 import 阶段就因为密钥文件读不出来而让整个程序起不来。
_aesgcm = None

# 密钥文件读写异常的原因（正常情况下为空串）。见 key_error()。
_key_error = ""


def key_error() -> str:
    """密钥文件无法读写时的原因；正常情况返回空串。

    主目录不可写（只读挂载、磁盘满、权限策略）时，本次运行会退化成「进程内
    临时密钥」：程序不会崩，但当次写入的数据下次启动读不回来。这种环境故障
    很难复现，所以留一个可查询的痕迹，而不是彻底静默。
    """
    return _key_error


def key_persisted() -> bool:
    """密钥是否真的落到了 ~/.classmanage_key。"""
    return not _key_error


def _get_key() -> bytes:
    """读取 ~/.classmanage_key；不存在或长度不对时重新生成并写入（chmod 600）。"""
    global _key_error

    try:
        with open(KEY_FILE, "rb") as f:
            key = f.read()
        if len(key) == KEY_SIZE:
            _key_error = ""
            return key
        reason = tr("密钥文件长度异常（{n} 字节）", "key file has bad length ({n} bytes)", n=len(key))
    except OSError as e:
        reason = str(e)

    key = AESGCM.generate_key(bit_length=256)
    try:
        directory = os.path.dirname(KEY_FILE)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(KEY_FILE, "wb") as f:
            f.write(key)
        try:
            os.chmod(KEY_FILE, 0o600)
        except OSError:
            # Windows 上 chmod 基本是空操作，失败无所谓；主目录本来就是私有的。
            pass
        _key_error = ""
    except OSError as e:
        # 主目录不可写（极少见）：退回内存里的临时密钥，程序照常运行，
        # 但本次写入的数据下次启动读不回来 —— 记录原因便于排查，不直接崩掉。
        _key_error = tr("无法写入密钥文件 {p}: {e}（{r}）",
                        "cannot write key file {p}: {e} ({r})",
                        p=KEY_FILE, e=e, r=reason)
    return key


def _cipher() -> AESGCM:
    global _aesgcm
    if _aesgcm is None:
        _aesgcm = AESGCM(_get_key())
    return _aesgcm


def reset_cipher_cache() -> None:
    """丢弃缓存的 cipher（密钥文件被替换后使用，主要给测试/排错用）。"""
    global _aesgcm
    _aesgcm = None


def encrypt(plaintext: bytes) -> bytes:
    """加密：返回 nonce(12B) + 密文 + GCM tag(16B)。"""
    nonce = os.urandom(NONCE_SIZE)
    return nonce + _cipher().encrypt(nonce, plaintext, None)


def decrypt(blob: bytes) -> bytes:
    """解密。文件被改过/被截断/为空时抛异常（ValueError 或 InvalidTag）。"""
    if not blob or len(blob) < MIN_BLOB_SIZE:
        raise ValueError(tr("文件为空或损坏", "file is empty or corrupt"))
    nonce, ciphertext = blob[:NONCE_SIZE], blob[NONCE_SIZE:]
    return _cipher().decrypt(nonce, ciphertext, None)
