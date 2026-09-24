# -*- coding: utf-8 -*-
"""pytest の共通設定。

実行: uv run pytest
カメラ・MediaPipe の推論・実際のマウス操作は使わない（合成データと代役で検証する）。
グローバルホットキーも実際には登録しない（他のアプリや動作中の本体と取り合わないため）。
"""

import sys

import pytest

from hm_core.config import Config


def pytest_collection_modifyitems(config, items):
    # Windows 専用（ctypes で user32 を直接呼ぶ）
    if sys.platform != "win32":
        skip = pytest.mark.skip(reason="Windows専用のため")
        for item in items:
            item.add_marker(skip)


@pytest.fixture
def config_file(tmp_path):
    """既定値で作った一時的な設定ファイル（本物の設定ファイルには触らない）。"""
    path = tmp_path / "hand_mouse_config.json"
    assert Config().save(path)
    return path


@pytest.fixture
def fake_hotkeys(monkeypatch):
    """ホットキーの登録を模擬する。taken に入れたキーは「他のアプリが使用中」になる。

    戻り値の taken（(修飾キー, 仮想キー) の集合）に追加して使う。
    """
    from hm_core.hotkeys import HotkeyManager

    taken = set()

    def register(self, name, vk, modifiers=0, quiet=False):
        if (modifiers, vk) in taken:
            return False
        hotkey_id = self._next_id
        self._names[hotkey_id] = name
        self._next_id += 1
        return True

    def unregister_all(self):
        self._names.clear()

    monkeypatch.setattr(HotkeyManager, "register", register)
    monkeypatch.setattr(HotkeyManager, "unregister_all", unregister_all)
    return taken
