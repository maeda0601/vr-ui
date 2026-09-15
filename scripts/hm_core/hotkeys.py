# -*- coding: utf-8 -*-
"""グローバルホットキー。

マウスを乗っ取っている最中はプレビューウィンドウにフォーカスが無く、
通常のキー入力を受け取れないことがある。どの状態からでも停止できるよう、
OSレベルのホットキーを登録しておく（安全装置）。
"""

import ctypes
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
PM_REMOVE = 0x0001


class HotkeyManager:
    """スレッド単位のホットキーを登録し、メインループからポーリングする。"""

    def __init__(self):
        self._names = {}
        self._next_id = 1

    def register(self, name, vk, modifiers=MOD_CONTROL | MOD_ALT):
        """ホットキーを登録する。成功したらTrue。"""
        hotkey_id = self._next_id
        ok = user32.RegisterHotKey(None, hotkey_id, modifiers | MOD_NOREPEAT, vk)
        if not ok:
            print(f"ホットキー登録に失敗しました（他のアプリと競合）: {name}")
            return False
        self._names[hotkey_id] = name
        self._next_id += 1
        return True

    def poll(self):
        """押されたホットキー名のリストを返す（非ブロッキング）。"""
        fired = []
        msg = wintypes.MSG()
        while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
            if msg.message == WM_HOTKEY:
                name = self._names.get(msg.wParam)
                if name:
                    fired.append(name)
            else:
                # 同じスレッドが持つウィンドウ（オーバーレイ等）宛のメッセージは配送する
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        return fired

    def unregister_all(self):
        for hotkey_id in list(self._names):
            user32.UnregisterHotKey(None, hotkey_id)
        self._names.clear()
