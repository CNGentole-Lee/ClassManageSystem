"""V4 测试夹具：一条临时事件链 + 一个可用的预设。

为什么需要它
    V4 起组名、分数、抽取次数**只存在于事件链的「预设」里**，
    ``config.ini`` 只是抄给老师看的一份副本（写坏了也不影响真数据）。
    因此凡是要读写积分的测试，都必须先有一条链、一个预设 ——
    否则 ``group_count`` 恒为 0，测的就不再生效。

这个模块把「建链 → 建预设 → 挂上 ConfigStore」这三步收在一处，
免得每个测试各写一遍、还各写错一处。
"""

from __future__ import annotations

import os

from namepicker.config_store import ConfigStore
from namepicker.ledger import Ledger
from namepicker.profiles import ProfileStore

#: 测试里默认的组数（与产品默认值一致）
DEFAULT_GROUPS = 6


def seed_chain(path: str, groups: int = DEFAULT_GROUPS,
               name: str = "测试预设") -> Ledger:
    """在 ``path`` 上准备一条链，并确保有一个 ``groups`` 组的当前预设。

    幂等：链已经能回放、已有预设时只把组数拉齐，不会重复建预设。
    """
    chain = Ledger(path)
    if chain.count() == 0:
        chain.migrate_from(0, [], [])
    store = ProfileStore(chain=chain)
    profiles = store.list()
    if not profiles:
        pid = store.create(name)
        store.set_rule(pid, int(groups), 0)
        store.use(pid)
        return chain
    profile = store.active() or profiles[0]
    if groups is not None and int(profile.get("group_count", 0)) != int(groups):
        store.set_rule(profile["id"], int(groups), len(profile.get("members", [])))
        if not store.active():
            store.use(profile["id"])
    return chain


def open_store(path: str, groups: int = DEFAULT_GROUPS) -> ConfigStore:
    """新建一个 ConfigStore 并挂上链（链/预设不存在就先建）。"""
    chain = seed_chain(path, groups)
    store = ConfigStore(path)
    store.attach_ledger(chain)
    store.apply_ledger_state(chain.state())
    return store


def reopen_store(path: str) -> ConfigStore:
    """重新打开一个已有目录（模拟「重启程序」），不新建任何预设。"""
    store = ConfigStore(path)
    chain = Ledger(path)
    store.attach_ledger(chain)
    store.apply_ledger_state(chain.state())
    return store


def wipe_dir_data(path: str) -> None:
    """删掉加密配置与其备份（测试「全部丢失」时用），保留链。"""
    for suffix in ("", ".bak"):
        target = path.replace("config.ini", "config.dat") + suffix
        if os.path.isfile(target):
            os.remove(target)


def sync_roster(path: str, count: int) -> bool:
    """把当前预设的成员表/次数表对齐到 ``count`` 人（模拟名单加载）。

    main.py 在名单加载后会做同一件事（见 apply_active_profile）。
    测试里要写抽取次数，就必须先走过这一步，否则新下标上的 draw
    会被 C++ 判为越界、静默丢弃。
    """
    return ProfileStore(chain=Ledger(path)).sync_roster(int(count))
