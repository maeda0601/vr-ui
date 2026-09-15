# -*- coding: utf-8 -*-
"""二重起動の防止。

同時に2つ動かすと、後から起動した方はカメラを開けず（先のプロセスが握っている）、
グローバルホットキーも登録できない。コンソール無し（pythonw）で起動していると
Ctrl+Alt+Q も効かないため終了する手段が無くなり、オーバーレイの表示だけが
画面に残り続ける。それを起動時に食い止める。
"""

import ctypes
from ctypes import wintypes

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32 = ctypes.WinDLL("user32", use_last_error=True)

ERROR_ALREADY_EXISTS = 183
MB_ICONINFORMATION = 0x00000040
MB_SETFOREGROUND = 0x00010000
MB_TOPMOST = 0x00040000

# ログオンセッション内で一意な名前。別ユーザーの起動は邪魔しない
MUTEX_NAME = "Local\vr-ui.hand_mouse.single_instance"

kernel32.CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
kernel32.CreateMutexW.restype = wintypes.HANDLE
kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
user32.MessageBoxW.argtypes = (wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.UINT)


class SingleInstance:
    """名前付きミューテックスで起動中のインスタンスを1つに保つ。

    既に起動していれば acquired が False になる。プロセスが異常終了しても
    OSがハンドルを回収するので、ミューテックスが残って起動できなくなることはない。
    """

    def __init__(self, name=MUTEX_NAME):
        self.handle = kernel32.CreateMutexW(None, False, name)
        err = ctypes.get_last_error()
        self.acquired = bool(self.handle) and err != ERROR_ALREADY_EXISTS
        if self.handle and not self.acquired:
            # 先に起動している側のミューテックスなので、こちらは持たずに閉じる
            kernel32.CloseHandle(self.handle)
            self.handle = None

    def release(self):
        if self.handle:
            kernel32.CloseHandle(self.handle)
            self.handle = None


def notify_already_running(show_dialog):
    """既に起動しているときの案内。コンソール無しでは見えないのでダイアログを出す。"""
    message = ("ハンドマウスは既に起動しています。\n\n"
               "二重に起動すると、カメラとホットキーを取り合って\n"
               "どちらも操作できなくなります。\n\n"
               "動いている方を終了するには Ctrl+Alt+Q を押してください。")
    print(message.replace("\n\n", "\n"))
    if show_dialog:
        user32.MessageBoxW(None, message, "ハンドマウス",
                           MB_ICONINFORMATION | MB_SETFOREGROUND | MB_TOPMOST)
