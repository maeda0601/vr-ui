# -*- coding: utf-8 -*-
"""プレビューウィンドウの描画（日本語表示対応）。"""

from pathlib import Path

import cv2
import numpy as np

from .gestures import (HAND_CONNECTIONS, INDEX_TIP, MODE_LABELS, MODE_LEFT,
                       MODE_POINT, MODE_RIGHT, MODE_ZOOM, RING_TIP, THUMB_TIP)

# 日本語フォントの候補（Windows標準）
_FONT_CANDIDATES = (
    "C:/Windows/Fonts/YuGothM.ttc",
    "C:/Windows/Fonts/meiryo.ttc",
    "C:/Windows/Fonts/msgothic.ttc",
)

# 配色（BGR）
COL_BG = (28, 24, 22)
COL_TEXT = (240, 240, 240)
COL_ON = (120, 230, 120)
COL_OFF = (110, 110, 235)
COL_AREA = (180, 160, 60)
COL_BONE = (200, 180, 120)
COL_JOINT = (255, 220, 160)
COL_TIP = (120, 200, 255)


class TextRenderer:
    """PILを使って日本語を描画する（cv2.putTextは日本語非対応のため）。"""

    def __init__(self):
        self._font_path = None
        self._fonts = {}
        self._pil = None
        for path in _FONT_CANDIDATES:
            if Path(path).exists():
                self._font_path = path
                break
        try:
            from PIL import Image, ImageDraw, ImageFont  # noqa: F401
            self._pil = (Image, ImageDraw, ImageFont)
        except ImportError:
            print("Pillowが無いため日本語表示は英数字にフォールバックします。")

    @property
    def available(self):
        return self._pil is not None and self._font_path is not None

    def _font(self, size):
        if size not in self._fonts:
            _, _, ImageFont = self._pil
            self._fonts[size] = ImageFont.truetype(self._font_path, size)
        return self._fonts[size]

    def draw(self, frame, items):
        """items = [(テキスト, (x, y), サイズ, 色BGR), ...] を一括描画する。"""
        if not items:
            return frame
        if not self.available:
            for text, (x, y), size, color in items:
                cv2.putText(frame, text, (x, y + size), cv2.FONT_HERSHEY_SIMPLEX,
                            size / 30.0, color, 1, cv2.LINE_AA)
            return frame

        Image, ImageDraw, _ = self._pil
        img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(img)
        for text, (x, y), size, color in items:
            draw.text((x, y), text, font=self._font(size),
                      fill=(color[2], color[1], color[0]))
        return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)


def draw_active_area(frame, cfg, area=None):
    """操作エリア（この矩形が画面全体に対応する）を描く。"""
    h, w = frame.shape[:2]
    ax0, ay0, ax1, ay1 = area if area is not None else cfg.active_area()
    x0, y0, x1, y1 = int(ax0 * w), int(ay0 * h), int(ax1 * w), int(ay1 * h)
    cv2.rectangle(frame, (x0, y0), (x1, y1), COL_AREA, 1, cv2.LINE_AA)
    # 四隅だけ太くしてVRのプレイエリアらしく見せる
    for cx, cy, dx, dy in ((x0, y0, 1, 1), (x1, y0, -1, 1),
                           (x0, y1, 1, -1), (x1, y1, -1, -1)):
        cv2.line(frame, (cx, cy), (cx + 22 * dx, cy), COL_AREA, 3, cv2.LINE_AA)
        cv2.line(frame, (cx, cy), (cx, cy + 22 * dy), COL_AREA, 3, cv2.LINE_AA)
    return (x0, y0, x1, y1)


def draw_hand(frame, hand, highlight_mode=None, right_tip=RING_TIP, lock_tip=None):
    """手の骨格を描く。"""
    h, w = frame.shape[:2]
    pts = [(int(p[0] * w), int(p[1] * h)) for p in hand.points]

    for a, b in HAND_CONNECTIONS:
        cv2.line(frame, pts[a], pts[b], COL_BONE, 2, cv2.LINE_AA)
    for i, p in enumerate(pts):
        is_tip = i in (4, 8, 12, 16, 20)
        cv2.circle(frame, p, 5 if is_tip else 3,
                   COL_TIP if is_tip else COL_JOINT, -1, cv2.LINE_AA)

    # 中指ピンチによる位置固定中は黄色で結ぶ
    if lock_tip is not None:
        cv2.line(frame, pts[THUMB_TIP], pts[lock_tip], COL_AREA, 3, cv2.LINE_AA)
    # ピンチしている指同士を結んで、判定状況を分かりやすくする
    if highlight_mode == MODE_LEFT:
        cv2.line(frame, pts[THUMB_TIP], pts[INDEX_TIP], COL_ON, 3, cv2.LINE_AA)
    elif highlight_mode == MODE_RIGHT:
        cv2.line(frame, pts[THUMB_TIP], pts[right_tip], COL_OFF, 3, cv2.LINE_AA)

    # カーソル位置になる人差し指先を強調
    cv2.circle(frame, pts[INDEX_TIP], 12, COL_TIP, 2, cv2.LINE_AA)


def draw_zoom_link(frame, hands):
    """ズーム中は両手の人差し指先を線で結ぶ。"""
    h, w = frame.shape[:2]
    a = hands[0].point(INDEX_TIP)
    b = hands[1].point(INDEX_TIP)
    pa = (int(a[0] * w), int(a[1] * h))
    pb = (int(b[0] * w), int(b[1] * h))
    cv2.line(frame, pa, pb, COL_ON, 2, cv2.LINE_AA)


def _panel(frame, x, y, w, h, alpha=0.55):
    """半透明の黒パネルを敷く。"""
    x2, y2 = min(x + w, frame.shape[1]), min(y + h, frame.shape[0])
    roi = frame[max(y, 0):y2, max(x, 0):x2]
    if roi.size:
        overlay = np.full(roi.shape, COL_BG, dtype=np.uint8)
        cv2.addWeighted(overlay, alpha, roi, 1 - alpha, 0, roi)


def _gauge(frame, x, y, w, value, on_threshold, label_color):
    """ピンチ距離のゲージ（左に行くほど閉じている）。"""
    cv2.rectangle(frame, (x, y), (x + w, y + 6), (70, 70, 70), -1)
    ratio = max(0.0, min(1.0, 1.0 - min(value, 1.2) / 1.2))
    cv2.rectangle(frame, (x, y), (x + int(w * ratio), y + 6), label_color, -1)
    tx = x + int(w * (1.0 - on_threshold / 1.2))
    cv2.line(frame, (tx, y - 3), (tx, y + 9), (240, 240, 240), 1)


def draw_ghost_hand(frame, hand):
    """設定で無視している手を灰色の骨格で描く（検出はしていると分かるように）。"""
    h, w = frame.shape[:2]
    pts = [(int(p[0] * w), int(p[1] * h)) for p in hand.points]
    for a, b in HAND_CONNECTIONS:
        cv2.line(frame, pts[a], pts[b], (110, 110, 110), 2, cv2.LINE_AA)
    for p in pts:
        cv2.circle(frame, p, 3, (160, 160, 160), -1, cv2.LINE_AA)


def render_hud(frame, renderer, cfg, state, enabled, fps, status_text="", ignored_hands=(),
               area=None):
    """プレビュー画面にHUDを重ねて返す。"""
    h, w = frame.shape[:2]

    if getattr(cfg, "mapping_mode", "absolute") == "absolute":
        draw_active_area(frame, cfg, area)   # 相対モードでは操作エリアの枠は意味を持たない
    for hand in ignored_hands:
        draw_ghost_hand(frame, hand)
    for hand in state.hands:
        draw_hand(frame, hand, state.mode, state.right_tip, state.lock_tip)
    if state.mode == MODE_ZOOM and len(state.hands) >= 2:
        draw_zoom_link(frame, state.hands)

    # 上部パネル
    _panel(frame, 0, 0, w, 66)
    # 下部パネル
    _panel(frame, 0, h - 54, w, 54)

    lamp_color = COL_ON if enabled else COL_OFF
    cv2.circle(frame, (22, 22), 9, lamp_color, -1, cv2.LINE_AA)

    mode_text = MODE_LABELS.get(state.mode, state.mode)
    if state.mode == MODE_POINT and state.lock_drag:
        mode_text = "ドラッグ中（固定から）"
    elif state.mode == MODE_POINT and state.arming:
        mode_text = "位置固定中"
    items = [
        ("操作: 有効" if enabled else "操作: 無効", (40, 10), 20, lamp_color),
        (mode_text, (40, 36), 18, COL_TEXT),
        (f"{fps:5.1f} fps", (w - 100, 12), 18, COL_TEXT),
        ("Space:有効切替  R:リセット  Esc:終了   /   Ctrl+Alt+H 切替  Ctrl+Alt+S 左右入替  Ctrl+Alt+Q 終了",
         (12, h - 48), 15, COL_TEXT),
    ]
    if status_text:
        items.append((status_text, (12, h - 26), 15, COL_ON))

    # ピンチゲージ（左＝左クリック、右＝右クリック）
    if state.pinch_index is not None:
        _gauge(frame, 12, 62, 110, state.pinch_index, cfg.pinch_on, COL_ON)
        _gauge(frame, 140, 62, 110, state.pinch_right, cfg.pinch_on, COL_OFF)
        items.append(("左", (126, 54), 14, COL_ON))
        items.append(("右", (254, 54), 14, COL_OFF))

    return renderer.draw(frame, items)
