# -*- coding: utf-8 -*-
"""デスクトップ上に手の骨格だけを描く透過オーバーレイ（Win32レイヤードウィンドウ）。

- ピクセル単位のアルファを持つ BGRA 画像を UpdateLayeredWindow で表示する
  （カラーキー透過はDWM合成で線が欠けて見えることがあるため使わない）
- 手の周りだけを覆う小さなウィンドウを毎フレーム動かすので全画面を描き直さない
- WS_EX_TRANSPARENT でクリックを素通し、WS_EX_NOACTIVATE でフォーカスを奪わない
- 図形は cv2（アンチエイリアス付き）、文字は PIL で描く
"""

import ctypes
import math
from ctypes import wintypes
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .gestures import (HAND_CONNECTIONS, INDEX_TIP, MIDDLE_TIP, MODE_LABELS,
                       MODE_LEFT, MODE_POINT, MODE_RIGHT, MODE_ZOOM, THUMB_TIP,
                       WRIST)

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

# --- Win32 定数 ---------------------------------------------------------
WS_POPUP = 0x80000000
WS_EX_TOPMOST = 0x00000008
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000
SW_HIDE = 0
SW_SHOWNOACTIVATE = 4
ULW_ALPHA = 0x02
AC_SRC_OVER = 0x00
AC_SRC_ALPHA = 0x01
BI_RGB = 0
DIB_RGB_COLORS = 0
HWND_TOPMOST = -1
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
PM_REMOVE = 0x0001

CLASS_NAME = "HandMouseOverlayWindow"

# --- 型定義 -------------------------------------------------------------
LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT,
                             wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wintypes.UINT),
                ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE),
                ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD),
                ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD),
                ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER),
                ("bmiColors", wintypes.DWORD * 3)]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", wintypes.BYTE),
                ("BlendFlags", wintypes.BYTE),
                ("SourceConstantAlpha", wintypes.BYTE),
                ("AlphaFormat", wintypes.BYTE)]


class SIZE(ctypes.Structure):
    _fields_ = [("cx", wintypes.LONG), ("cy", wintypes.LONG)]


# 64bit環境でハンドルが切り捨てられないよう戻り値・引数の型を明示する
user32.DefWindowProcW.restype = LRESULT
user32.DefWindowProcW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
user32.CreateWindowExW.restype = wintypes.HWND
user32.CreateWindowExW.argtypes = (wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                   wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, wintypes.HWND, wintypes.HMENU,
                                   wintypes.HINSTANCE, wintypes.LPVOID)
user32.GetDC.restype = wintypes.HDC
user32.GetDC.argtypes = (wintypes.HWND,)
user32.ReleaseDC.argtypes = (wintypes.HWND, wintypes.HDC)
user32.UpdateLayeredWindow.argtypes = (wintypes.HWND, wintypes.HDC, ctypes.POINTER(wintypes.POINT),
                                       ctypes.POINTER(SIZE), wintypes.HDC,
                                       ctypes.POINTER(wintypes.POINT), wintypes.COLORREF,
                                       ctypes.POINTER(BLENDFUNCTION), wintypes.DWORD)
user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
user32.DestroyWindow.argtypes = (wintypes.HWND,)
user32.SetWindowPos.argtypes = (wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, wintypes.UINT)
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateCompatibleDC.argtypes = (wintypes.HDC,)
gdi32.CreateDIBSection.restype = wintypes.HBITMAP
gdi32.CreateDIBSection.argtypes = (wintypes.HDC, ctypes.POINTER(BITMAPINFO), wintypes.UINT,
                                   ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD)
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.SelectObject.argtypes = (wintypes.HDC, wintypes.HGDIOBJ)
gdi32.DeleteObject.argtypes = (wintypes.HGDIOBJ,)
gdi32.DeleteDC.argtypes = (wintypes.HDC,)
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
kernel32.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)


def _wnd_proc(hwnd, msg, wparam, lparam):
    return user32.DefWindowProcW(hwnd, msg, wparam, lparam)


# GCで回収されないようモジュールに保持する
_WND_PROC = WNDPROC(_wnd_proc)
_class_registered = False


def _ensure_class():
    global _class_registered
    if _class_registered:
        return
    wc = WNDCLASSW()
    wc.lpfnWndProc = _WND_PROC
    wc.hInstance = kernel32.GetModuleHandleW(None)
    wc.lpszClassName = CLASS_NAME
    if not user32.RegisterClassW(ctypes.byref(wc)):
        raise ctypes.WinError(ctypes.get_last_error())
    _class_registered = True


class LayeredWindow:
    """BGRA（プリマルチプライド）画像をそのまま表示する最前面・クリック素通しウィンドウ。"""

    def __init__(self):
        _ensure_class()
        ex_style = (WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST
                    | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE)
        self.hwnd = user32.CreateWindowExW(
            ex_style, CLASS_NAME, "Hand Overlay", WS_POPUP, 0, 0, 1, 1,
            None, None, kernel32.GetModuleHandleW(None), None)
        if not self.hwnd:
            raise ctypes.WinError(ctypes.get_last_error())
        self.visible = False
        self._dib = None  # (w, h, hdc_mem, hbmp, old_obj, bits)

    def _dib_for(self, w, h):
        """サイズが変わったときだけDIBを作り直す。"""
        if self._dib and self._dib[0] == w and self._dib[1] == h:
            return self._dib
        self._free_dib()
        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = w
        bmi.bmiHeader.biHeight = -h  # 負にするとトップダウン（numpyの行順と一致）
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = BI_RGB
        hdc_screen = user32.GetDC(None)
        hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
        bits = ctypes.c_void_p()
        hbmp = gdi32.CreateDIBSection(hdc_screen, ctypes.byref(bmi), DIB_RGB_COLORS,
                                      ctypes.byref(bits), None, 0)
        user32.ReleaseDC(None, hdc_screen)
        if not hbmp:
            gdi32.DeleteDC(hdc_mem)
            raise ctypes.WinError(ctypes.get_last_error())
        old = gdi32.SelectObject(hdc_mem, hbmp)
        self._dib = (w, h, hdc_mem, hbmp, old, bits)
        return self._dib

    def _free_dib(self):
        if not self._dib:
            return
        _, _, hdc_mem, hbmp, old, _ = self._dib
        gdi32.SelectObject(hdc_mem, old)
        gdi32.DeleteObject(hbmp)
        gdi32.DeleteDC(hdc_mem)
        self._dib = None

    def update(self, bgra, x, y):
        """画像を表示し、ウィンドウを(x, y)へ移動する。"""
        bgra = np.ascontiguousarray(bgra, dtype=np.uint8)
        h, w = bgra.shape[:2]
        _, _, hdc_mem, _, _, bits = self._dib_for(w, h)
        ctypes.memmove(bits, bgra.ctypes.data, bgra.nbytes)

        hdc_screen = user32.GetDC(None)
        pt_dst = wintypes.POINT(int(x), int(y))
        size = SIZE(w, h)
        pt_src = wintypes.POINT(0, 0)
        blend = BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)
        ok = user32.UpdateLayeredWindow(self.hwnd, hdc_screen, ctypes.byref(pt_dst),
                                        ctypes.byref(size), hdc_mem, ctypes.byref(pt_src),
                                        0, ctypes.byref(blend), ULW_ALPHA)
        user32.ReleaseDC(None, hdc_screen)
        if not ok:
            raise ctypes.WinError(ctypes.get_last_error())
        if not self.visible:
            user32.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)
            self.visible = True

    def hide(self):
        if self.visible:
            user32.ShowWindow(self.hwnd, SW_HIDE)
            self.visible = False

    def raise_topmost(self):
        user32.SetWindowPos(self.hwnd, wintypes.HWND(HWND_TOPMOST), 0, 0, 0, 0,
                            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)

    def pump(self):
        """このウィンドウ宛のメッセージだけを処理する（ホットキーは奪わない）。"""
        msg = wintypes.MSG()
        while user32.PeekMessageW(ctypes.byref(msg), self.hwnd, 0, 0, PM_REMOVE):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def destroy(self):
        self._free_dib()
        if self.hwnd:
            user32.DestroyWindow(self.hwnd)
            self.hwnd = None


# --- 描画ユーティリティ -------------------------------------------------
_FONT_CANDIDATES = (
    "C:/Windows/Fonts/YuGothM.ttc",
    "C:/Windows/Fonts/meiryo.ttc",
    "C:/Windows/Fonts/msgothic.ttc",
)
_font_cache = {}


def _font(size):
    if size in _font_cache:
        return _font_cache[size]
    font = None
    for path in _FONT_CANDIDATES:
        if Path(path).exists():
            font = ImageFont.truetype(path, size)
            break
    if font is None:
        font = ImageFont.load_default()
    _font_cache[size] = font
    return font


def _bgra(r, g, b, a=255):
    """RGBA → cv2用のプリマルチプライドBGRA。"""
    return (b * a // 255, g * a // 255, r * a // 255, a)


def _premultiply(rgba):
    """PILのRGBA（ストレートアルファ）をプリマルチプライドBGRAへ変換する。"""
    a = rgba[..., 3:4].astype(np.uint16)
    rgb = (rgba[..., :3].astype(np.uint16) * a + 127) // 255
    return np.dstack([rgb[..., 2], rgb[..., 1], rgb[..., 0], rgba[..., 3]]).astype(np.uint8)


def _blit(dst, src, x, y):
    """プリマルチプライド同士のover合成（画面外は切り捨て）。"""
    h, w = src.shape[:2]
    H, W = dst.shape[:2]
    x0, y0 = max(x, 0), max(y, 0)
    x1, y1 = min(x + w, W), min(y + h, H)
    if x1 <= x0 or y1 <= y0:
        return
    s = src[y0 - y:y1 - y, x0 - x:x1 - x].astype(np.uint16)
    d = dst[y0:y1, x0:x1].astype(np.uint16)
    inv = 255 - s[..., 3:4]
    out = s + (d * inv + 127) // 255
    dst[y0:y1, x0:x1] = np.clip(out, 0, 255).astype(np.uint8)


def _text_box(text, font, fg, bg, pad=(10, 6), radius=8):
    """角丸の背景付きテキストをプリマルチプライドBGRAで返す。"""
    left, top, right, bottom = font.getbbox(text)
    tw, th = right - left, bottom - top
    w, h = tw + pad[0] * 2, th + pad[1] * 2
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=radius, fill=bg)
    d.text((pad[0] - left, pad[1] - top), text, font=font, fill=fg)
    return _premultiply(np.array(im))


# --- 配色（RGBA） -------------------------------------------------------
RGB_BONE = (120, 215, 255)
RGB_BONE_OFF = (150, 150, 150)
RGB_JOINT = (230, 246, 255)
RGB_TIP = (255, 255, 255)
RGB_LEFT = (125, 230, 125)
RGB_RIGHT = (255, 138, 122)
RGB_ACCENT = (255, 209, 102)
RGB_TEXT_DIM = (180, 180, 180)
RGBA_PILL = (28, 24, 22, 215)

_TIPS = (4, 8, 12, 16, 20)
BONE_WIDTH = 5
MARGIN = 80          # 手のまわりに確保する余白[px]（リング・ラベルが収まる分）
SIZE_STEP = 64       # ウィンドウサイズをこの単位に丸めてDIBの作り直しを減らす


class HandOverlay:
    """手の骨格・カーソルリング・状態表示を画面上に重ねる。"""

    def __init__(self, screen_w, screen_h, alpha=0.9):
        self.screen_w = int(screen_w)
        self.screen_h = int(screen_h)
        self.alpha = max(0.1, min(1.0, float(alpha)))
        self.closed = False
        self._frame_count = 0

        self.hand_win = LayeredWindow()
        self.pill_win = LayeredWindow()
        self.font = _font(15)
        self.font_small = _font(14)
        self._pill_key = None

    # --- 描画 -----------------------------------------------------------
    def render(self, hands_px, cursor_px, state, enabled, hint=""):
        """1フレーム分を描いて表示する。

        hands_px : 手ごとの21点の画面座標リスト
        cursor_px: 平滑化後のカーソル座標（無ければNone）
        state    : GestureState
        """
        if self.closed:
            return
        if hands_px:
            self._render_hands(hands_px, cursor_px, state, enabled)
        else:
            self.hand_win.hide()
        self._render_pill(state, enabled, hint)

        self._frame_count += 1
        if self._frame_count % 60 == 0:
            self.hand_win.raise_topmost()
            self.pill_win.raise_topmost()

    def _render_hands(self, hands_px, cursor_px, state, enabled):
        pts = [p for hand in hands_px for p in hand]
        if cursor_px is not None:
            pts = pts + [cursor_px]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        # ウィンドウ領域: 手の外接矩形＋余白。画面から大きくはみ出す分は切る
        x0 = max(int(min(xs)) - MARGIN, -MARGIN)
        y0 = max(int(min(ys)) - MARGIN, -MARGIN)
        x1 = min(int(max(xs)) + MARGIN, self.screen_w + MARGIN)
        y1 = min(int(max(ys)) + MARGIN, self.screen_h + MARGIN)
        w = max(int(math.ceil((x1 - x0) / SIZE_STEP)) * SIZE_STEP, SIZE_STEP)
        h = max(int(math.ceil((y1 - y0) / SIZE_STEP)) * SIZE_STEP, SIZE_STEP)
        if w <= 0 or h <= 0:
            self.hand_win.hide()
            return

        img = np.zeros((h, w, 4), dtype=np.uint8)

        def local(p):
            return (int(round(p[0] - x0)), int(round(p[1] - y0)))

        bone_rgb = RGB_BONE if enabled else RGB_BONE_OFF
        bone = _bgra(*bone_rgb)
        joint = _bgra(*RGB_JOINT)
        tip = _bgra(*RGB_TIP)

        for hand in hands_px:
            lp = [local(p) for p in hand]
            for a, b in HAND_CONNECTIONS:
                cv2.line(img, lp[a], lp[b], bone, BONE_WIDTH, cv2.LINE_AA)
            for i, p in enumerate(lp):
                is_tip = i in _TIPS
                cv2.circle(img, p, 7 if is_tip else 4, tip if is_tip else joint, -1, cv2.LINE_AA)
            if enabled and state.mode == MODE_LEFT:
                cv2.line(img, lp[THUMB_TIP], lp[INDEX_TIP], _bgra(*RGB_LEFT), 7, cv2.LINE_AA)
            elif enabled and state.mode == MODE_RIGHT:
                cv2.line(img, lp[THUMB_TIP], lp[MIDDLE_TIP], _bgra(*RGB_RIGHT), 7, cv2.LINE_AA)

        if state.mode == MODE_ZOOM and len(hands_px) >= 2:
            a = local(hands_px[0][INDEX_TIP])
            b = local(hands_px[1][INDEX_TIP])
            cv2.line(img, a, b, _bgra(*RGB_ACCENT), 3, cv2.LINE_AA)

        if cursor_px is not None and state.mode in (MODE_POINT, MODE_LEFT, MODE_RIGHT):
            self._draw_ring(img, local(cursor_px), state, enabled)

        # 手元のモード名（VRのツールチップ風）
        label = MODE_LABELS.get(state.mode, "")
        if label:
            color = {MODE_LEFT: RGB_LEFT, MODE_RIGHT: RGB_RIGHT}.get(state.mode, RGB_ACCENT)
            if not enabled:
                color = RGB_TEXT_DIM
            box = _text_box(label, self.font_small, color + (255,), RGBA_PILL)
            wx, wy = local(hands_px[0][WRIST])
            _blit(img, box, wx - box.shape[1] // 2, wy + 22)

        if self.alpha < 1.0:
            img = cv2.convertScaleAbs(img, alpha=self.alpha)
        self.hand_win.update(img, x0, y0)

    def _draw_ring(self, img, center, state, enabled):
        """ピンチが閉じるほど縮むリング。クリック中は半透明に塗る。"""
        pinch = state.pinch_index if state.pinch_index is not None else 1.0
        r = int(14 + max(0.0, min(pinch, 1.2)) * 22)
        if not enabled:
            cv2.circle(img, center, r, _bgra(*RGB_BONE_OFF), 3, cv2.LINE_AA)
        elif state.mode == MODE_POINT and state.arming:
            # クリック準備（カーソル固定中）は黄色の太いリングで知らせる
            cv2.circle(img, center, r, _bgra(*RGB_ACCENT, 90), -1, cv2.LINE_AA)
            cv2.circle(img, center, r, _bgra(*RGB_ACCENT), 4, cv2.LINE_AA)
        elif state.mode == MODE_LEFT:
            cv2.circle(img, center, r, _bgra(*RGB_LEFT, 120), -1, cv2.LINE_AA)
            cv2.circle(img, center, r, _bgra(*RGB_LEFT), 3, cv2.LINE_AA)
        elif state.mode == MODE_RIGHT:
            cv2.circle(img, center, r, _bgra(*RGB_RIGHT, 120), -1, cv2.LINE_AA)
            cv2.circle(img, center, r, _bgra(*RGB_RIGHT), 3, cv2.LINE_AA)
        else:
            cv2.circle(img, center, r, _bgra(*RGB_BONE), 3, cv2.LINE_AA)

    def _render_pill(self, state, enabled, hint):
        """画面上部中央の状態表示。文言が変わったときだけ描き直す。"""
        label = ("● 操作: 有効" if enabled else "○ 操作: 無効") + "   " \
            + MODE_LABELS.get(state.mode, state.mode)
        if hint:
            label += "   " + hint
        key = (label, enabled)
        if key == self._pill_key and self.pill_win.visible:
            return
        self._pill_key = key
        fg = (RGB_LEFT if enabled else RGB_TEXT_DIM) + (255,)
        box = _text_box(label, self.font, fg, RGBA_PILL, pad=(16, 8), radius=12)
        if self.alpha < 1.0:
            box = cv2.convertScaleAbs(box, alpha=self.alpha)
        self.pill_win.update(box, (self.screen_w - box.shape[1]) // 2, 10)

    # --- ループ連携 -----------------------------------------------------
    def update(self):
        """メインループから毎フレーム呼ぶ。自前ウィンドウ宛のメッセージを処理する。"""
        if self.closed:
            return
        self.hand_win.pump()
        self.pill_win.pump()

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.hand_win.destroy()
        self.pill_win.destroy()
