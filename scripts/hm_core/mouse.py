# -*- coding: utf-8 -*-
"""Windows APIを直接叩いてマウス／キーボードを操作する。

PyAutoGUIより遅延が小さく、フェイルセーフの誤作動もないため
SendInput / SetCursorPos を使用する。
"""

import ctypes
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)

# SendInput用の定数
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_WHEEL = 0x0800
KEYEVENTF_KEYUP = 0x0002
VK_CONTROL = 0x11
WHEEL_DELTA = 120
SM_CXSCREEN = 0
SM_CYSCREEN = 1

ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG),
                ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD),
                ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ULONG_PTR)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


def _send(*inputs):
    """INPUT構造体をまとめて送信する。"""
    n = len(inputs)
    array = (INPUT * n)(*inputs)
    sent = user32.SendInput(n, array, ctypes.sizeof(INPUT))
    if sent != n:
        raise ctypes.WinError(ctypes.get_last_error())


def _mouse_input(flags, data=0):
    return INPUT(type=INPUT_MOUSE,
                 u=_INPUTUNION(mi=MOUSEINPUT(0, 0, data, flags, 0, 0)))


def _key_input(vk, up=False):
    flags = KEYEVENTF_KEYUP if up else 0
    return INPUT(type=INPUT_KEYBOARD,
                 u=_INPUTUNION(ki=KEYBDINPUT(vk, 0, flags, 0, 0)))


def enable_dpi_awareness():
    """画面スケーリング環境でも実ピクセル座標で扱えるようにする。"""
    try:
        ctypes.WinDLL("shcore").SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
        return
    except Exception:
        pass
    try:
        user32.SetProcessDPIAware()
    except Exception as e:
        print(f"DPI設定に失敗しました（座標がずれる可能性があります）: {e}")


class MouseController:
    """カーソル移動・クリック・スクロール・ズームをまとめて扱う。"""

    def __init__(self, margin_px=2):
        self.margin = int(margin_px)
        self.screen_w = user32.GetSystemMetrics(SM_CXSCREEN)
        self.screen_h = user32.GetSystemMetrics(SM_CYSCREEN)
        self.left_down = False

    def move_to(self, x, y):
        """画面座標へカーソルを移動する（画面端に張り付かせない）。"""
        x = int(min(max(x, self.margin), self.screen_w - 1 - self.margin))
        y = int(min(max(y, self.margin), self.screen_h - 1 - self.margin))
        user32.SetCursorPos(x, y)

    def get_position(self):
        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        return pt.x, pt.y

    def press_left(self):
        if not self.left_down:
            _send(_mouse_input(MOUSEEVENTF_LEFTDOWN))
            self.left_down = True

    def release_left(self):
        if self.left_down:
            _send(_mouse_input(MOUSEEVENTF_LEFTUP))
            self.left_down = False

    def click_right(self):
        _send(_mouse_input(MOUSEEVENTF_RIGHTDOWN),
              _mouse_input(MOUSEEVENTF_RIGHTUP))

    def scroll(self, notches):
        """ホイールを回す（正=上方向）。"""
        if notches:
            _send(_mouse_input(MOUSEEVENTF_WHEEL, int(notches * WHEEL_DELTA)))

    def zoom(self, notches):
        """Ctrl+ホイールでズームする（正=拡大）。"""
        if not notches:
            return
        _send(_key_input(VK_CONTROL),
              _mouse_input(MOUSEEVENTF_WHEEL, int(notches * WHEEL_DELTA)),
              _key_input(VK_CONTROL, up=True))

    def release_all(self):
        """押しっぱなしのボタンを確実に離す（終了時・無効化時に呼ぶ）。"""
        self.release_left()
