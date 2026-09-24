# -*- coding: utf-8 -*-
"""テスト用の合成データと、実機に触らないための代役。

カメラも MediaPipe も使わずに、ジェスチャー判定とマウス操作の流れを検証する。
"""

import hand_mouse as HM
from hm_core import gestures as G
from hm_core.config import Config


class LM:
    """MediaPipe の NormalizedLandmark の代わり（.x / .y だけ持つ）。"""

    def __init__(self, x, y):
        self.x = x
        self.y = y


def make_hand(index_ext=True, middle_ext=False, ring_ext=False, pinky_ext=False,
              thumb_to=None, origin=(0.5, 0.8), handedness="Right", score=1.0):
    """指の伸び方を指定した合成の手（21点）を作る。

    手首を原点に、各指を上方向（y が減る向き）へ伸ばした簡易モデル。
    thumb_to で親指先の位置を指定すると、ピンチ（つまむ動作）を作れる。
    """
    ox, oy = origin
    pts = [None] * 21
    pts[0] = (ox, oy)                                   # 手首
    mcp_x = {"index": ox - 0.06, "middle": ox - 0.02, "ring": ox + 0.02, "pinky": ox + 0.06}
    mcp_y = oy - 0.12
    spec = {
        "index": (5, 6, 7, 8, index_ext),
        "middle": (9, 10, 11, 12, middle_ext),
        "ring": (13, 14, 15, 16, ring_ext),
        "pinky": (17, 18, 19, 20, pinky_ext),
    }
    for name, (mcp, pip, dip, tip, extended) in spec.items():
        x = mcp_x[name]
        pts[mcp] = (x, mcp_y)
        pts[pip] = (x, mcp_y - 0.05)
        if extended:
            pts[dip] = (x, mcp_y - 0.09)
            pts[tip] = (x, mcp_y - 0.13)
        else:
            # 曲げた指は付け根側へ折り返す
            pts[dip] = (x, mcp_y - 0.02)
            pts[tip] = (x, mcp_y + 0.02)
    tx, ty = thumb_to if thumb_to else (ox - 0.13, oy - 0.08)
    pts[1] = (ox - 0.04, oy - 0.03)
    pts[2] = (ox - 0.07, oy - 0.05)
    pts[3] = ((pts[2][0] + tx) / 2, (pts[2][1] + ty) / 2)
    pts[4] = (tx, ty)
    return G.Hand([LM(*p) for p in pts], handedness, score)


def pinch_to(tip_index, **kw):
    """指定した指先に親指を付けた手を作る（その指は伸ばしておく）。"""
    base = make_hand(**kw)
    tx, ty = base.point(tip_index)
    return make_hand(thumb_to=(tx + 0.005, ty + 0.005), **kw)


class FakeMouse:
    """MouseController の代わり。実際のカーソルには触らず、呼ばれた操作を記録する。"""

    def __init__(self, screen_w=1920, screen_h=1080):
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.margin = 2
        self.left_down = False
        self.calls = []
        self.pos = None

    def move_to(self, x, y):
        self.pos = (x, y)

    def press_left(self):
        if not self.left_down:
            self.left_down = True
            self.calls.append("left_down")

    def release_left(self):
        if self.left_down:
            self.left_down = False
            self.calls.append("left_up")

    def click_left(self):
        self.left_down = False
        self.calls.append("left_click")

    def click_right(self):
        self.calls.append("right_click")

    def scroll(self, notches):
        self.calls.append(("scroll", notches))

    def zoom(self, notches):
        self.calls.append(("zoom", notches))

    def release_all(self):
        self.release_left()

    @staticmethod
    def double_click_time_sec():
        return 0.5


def make_app(cfg=None, mouse=None, config_path=None):
    """実機に触らない HandMouseApp を作る。通知は app.notes に溜まる。"""
    app = HM.HandMouseApp(cfg or Config())
    app.mouse = mouse if mouse is not None else FakeMouse()
    app.notes = []
    app.notify = lambda text, duration=2.0: app.notes.append(text)
    if config_path is not None:
        app.config_path = str(config_path)
        app.note_config_saved()
    return app


class Player:
    """手のシーケンスを recognizer → process に流す（時刻は 30fps 相当で進める）。"""

    def __init__(self, app, dt=0.033):
        self.app = app
        self.rec = app.recognizer
        self.dt = dt
        self.t = 0.0
        self.states = []

    def feed(self, hands, frames=1):
        for _ in range(frames):
            self.t += self.dt
            state = self.rec.update(hands, self.t)
            self.app.process(state, self.t, self.dt)
            self.states.append(state)
        return self.states[-1]

    @property
    def modes(self):
        return [s.mode for s in self.states]
