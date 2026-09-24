# -*- coding: utf-8 -*-
"""1フレーム分の処理（検出 → step → 描画）と、画面上部の案内文のテスト。

以前は run() のカメラのループの中にあってテストから呼べなかった部分。
"""

import numpy as np
import pytest

import hand_mouse as HM
from hm_core import gestures as G
from hm_core.config import Config
from synthetic import LM, make_app, make_hand


def state_of(mode=G.MODE_POINT, hands=None, **kw):
    return G.GestureState(mode=mode, hands=hands if hands is not None else [make_hand()], **kw)


# --- 画面上部の案内文（build_hint）------------------------------------------

def test_hint_when_disabled_and_no_hand_asks_to_show_open_hand():
    app = make_app()
    assert app.build_hint(state_of(G.MODE_IDLE, hands=[]), 0.0) == "手を開いてカメラに見せてください"


def test_hint_when_disabled_explains_how_to_start():
    app = make_app()
    app.hotkey_labels = {"toggle": "Ctrl+Alt+H"}
    hint = app.build_hint(state_of(), 0.0)
    assert hint == f"グーを{Config().fist_toggle_sec:g}秒保持 または Ctrl+Alt+H で開始"


def test_hint_uses_the_registered_key_or_omits_it():
    app = make_app()
    app.hotkey_labels = {"toggle": "Ctrl+Alt+Shift+H"}
    assert "Ctrl+Alt+Shift+H" in app.build_hint(state_of(), 0.0)
    app.hotkey_labels = {"toggle": None}                 # 登録できなかった
    assert "または" not in app.build_hint(state_of(), 0.0)


def test_hint_counts_fist_hold():
    app = make_app()
    app.fist_since = 10.0
    assert app.build_hint(state_of(G.MODE_FIST), 11.2).startswith("グー保持中 1.2 /")


def test_hint_for_ignored_hand_mentions_swap_key():
    app = make_app()
    app.hotkey_labels = {"swap": "Ctrl+Alt+S"}
    hint = app.build_hint(state_of(G.MODE_IDLE, hands=[]), 0.0, "左手と判定（信頼度 0.95）→ 無視中")
    assert hint.startswith("右手だけを使います（左手と判定")
    assert hint.endswith("Ctrl+Alt+S で左右入れ替え")


def test_temporary_notice_wins_until_it_expires():
    app = HM.HandMouseApp(Config())                     # 本物の notify（案内文に出る）を使う
    app.notify("設定を読み直しました（1項目）", 2.0)
    now = app.status_until - 1.0
    assert app.build_hint(state_of(fingers_out=True), now) == "設定を読み直しました（1項目）"
    assert app.build_hint(state_of(fingers_out=True), app.status_until + 0.1).startswith("指先がカメラの外")


def test_hint_priority_edge_warnings_before_status():
    app = make_app()
    app.enabled = True
    assert app.build_hint(state_of(fingers_out=True, near_edge=True), 0.0).startswith("指先がカメラの外")
    assert app.build_hint(state_of(near_edge=True), 0.0) == "手がカメラの端に近いです"
    assert app.build_hint(state_of(), 0.0) == ""         # 有効で問題なければ何も出さない


def test_hint_counts_down_to_idle_disable():
    app = make_app()
    app.enabled = True
    app.no_hand_since = 5.0
    hint = app.build_hint(state_of(G.MODE_IDLE, hands=[]), 6.0)
    assert hint == f"手が見えません 1.0 / {Config().idle_disable_sec:.1f} 秒で無効"


def test_debug_text_is_added_only_with_debug_option():
    app = make_app()
    app.enabled = True
    assert app.add_debug_text("", state_of(), 0.0) == ""
    app.cfg.debug_hud = True
    assert app.add_debug_text("", state_of(), 0.0).startswith("人差し指 ")


# --- 1フレーム分（step）--------------------------------------------------------

def test_step_moves_cursor_for_active_hand():
    cfg = Config()
    cfg.enable_on_start = True
    app = make_app(cfg)
    result = app.step([make_hand()], 0.033, 0.033)
    assert result.state.mode == G.MODE_POINT
    assert app.mouse.pos is not None
    assert result.ignored_hands == []


def test_step_ignores_left_hand_and_explains_once(capsys):
    app = make_app()
    app.hotkey_labels = {"swap": "Ctrl+Alt+S"}
    left = make_hand(handedness="Left", score=0.95)
    t = 0.0
    for _ in range(80):                                  # 約2.6秒映り続ける
        t += 0.033
        result = app.step([left], t, 0.033)
    assert result.state.mode == G.MODE_IDLE              # 操作には使わない
    assert result.ignored_hands == [left]                # 灰色で描く
    assert "左手と判定" in result.hint
    printed = capsys.readouterr().out
    assert printed.count("左右判定が逆です") == 1        # コンソールへの案内は一度だけ
    assert "Ctrl+Alt+S で判定を入れ替えられます" in printed


def test_step_swapped_handedness_uses_left_label_as_right():
    cfg = Config()
    cfg.swap_handedness = True
    app = make_app(cfg)
    result = app.step([make_hand(handedness="Left", score=0.95)], 0.033, 0.033)
    assert result.state.mode == G.MODE_POINT
    assert result.ignored_hands == []


# --- 手の検出（detect_hands）と時刻 ---------------------------------------------

class FakeCategory:
    def __init__(self, name, score):
        self.category_name = name
        self.score = score


class FakeResult:
    def __init__(self, hands):
        self.hand_landmarks = [[LM(x, y) for x, y in h.points] for h, _ in hands]
        self.handedness = [[FakeCategory(label, score)] if label else [] for _, (label, score) in hands]


class FakeLandmarker:
    """検出器の代わり。渡されたタイムスタンプを記録し、決まった手を返す。"""

    def __init__(self, hands):
        self.hands = hands
        self.timestamps = []

    def detect_for_video(self, image, timestamp_ms):
        self.timestamps.append(timestamp_ms)
        return FakeResult(self.hands)


def frame():
    return np.zeros((48, 64, 3), dtype=np.uint8)


def test_detect_hands_builds_hands_with_handedness():
    hand = make_hand()
    lm = FakeLandmarker([(hand, ("Left", 0.9)), (hand, ("", 0))])
    hands = make_app().detect_hands(lm, frame(), 1.0)
    assert [(h.handedness, h.handedness_score) for h in hands] == [("Left", 0.9), ("", 1.0)]
    assert hands[0].points == pytest.approx(hand.points)


def test_detect_hands_timestamps_always_increase():
    """VIDEO モードの検出器は同じ／戻ったタイムスタンプを受け付けないので、必ず増やす。"""
    app = make_app()
    lm = FakeLandmarker([])
    for now in (1.0, 1.0, 0.999, 1.0005, 2.0):
        app.detect_hands(lm, frame(), now)
    assert lm.timestamps == [1000, 1001, 1002, 1003, 2000]


def test_advance_clock_gives_dt_and_fps():
    app = make_app()
    app._last_frame_time = 10.0
    assert app.advance_clock(10.05) == pytest.approx(0.05)
    assert app.advance_clock(10.05) == pytest.approx(1e-3)   # 同じ時刻でも 0 にしない
    assert app.fps > 0


# --- 描画（show）-------------------------------------------------------------

class FakeOverlay:
    def __init__(self):
        self.closed = False
        self.rendered = []

    def render(self, hands_px, cursor_px, state, enabled, hint, ghost_px=()):
        self.rendered.append((len(hands_px), len(ghost_px), hint))

    def update(self):
        pass


def test_show_draws_active_and_ignored_hands_on_overlay():
    app = make_app()
    overlay = FakeOverlay()
    result = HM.FrameResult(state_of(), "案内", [make_hand(handedness="Left")])
    assert app.show(frame(), result, use_preview=False, overlay=overlay)
    assert overlay.rendered == [(1, 1, "案内")]


def test_show_stops_loop_when_overlay_closed():
    app = make_app()
    overlay = FakeOverlay()
    overlay.closed = True
    assert not app.show(frame(), HM.FrameResult(state_of()), use_preview=False, overlay=overlay)


def test_show_without_display_does_nothing():
    assert make_app().show(frame(), HM.FrameResult(state_of()), use_preview=False, overlay=None)
