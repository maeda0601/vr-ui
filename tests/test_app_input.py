# -*- coding: utf-8 -*-
"""判定結果からマウス操作への流れ（HandMouseApp.process）のテスト。"""

import math

import pytest

from hm_core import gestures as G
from hm_core import mouse as M
from hm_core.config import Config
from synthetic import FakeMouse, Player, make_app, make_hand, pinch_to


def approach(tip_index=G.INDEX_TIP, steps=10, hold=4, **kw):
    """親指を離れた位置から指先へ近づけてつまみ、そのまま保持する手の列。"""
    base = make_hand(**kw)
    tx, ty = base.point(tip_index)
    sx, sy = base.point(G.THUMB_TIP)
    seq = []
    for k in range(steps + 1):
        f = k / steps
        seq.append(make_hand(thumb_to=(sx + (tx + 0.005 - sx) * f,
                                       sy + (ty + 0.005 - sy) * f), **kw))
    return seq + [seq[-1]] * hold


def play(player, seq):
    for hand in seq:
        player.feed([hand])


def enabled_app(**settings):
    cfg = Config()
    cfg.enable_on_start = True
    for key, value in settings.items():
        setattr(cfg, key, value)
    return make_app(cfg)


# --- 有効／無効 ---------------------------------------------------------

def test_disabled_app_never_touches_mouse():
    app = make_app(Config())                      # 既定は無効で起動
    p = Player(app)
    p.feed([make_hand()], 5)
    play(p, approach())
    assert app.mouse.calls == [] and app.mouse.pos is None


def test_fist_held_for_configured_seconds_toggles_enabled():
    app = make_app(Config())
    p = Player(app)
    fist = make_hand(False, False, False, False)
    frames = math.ceil(Config().fist_toggle_sec / p.dt)
    p.feed([fist], frames - 2)
    assert not app.enabled                         # まだ保持時間に届かない
    p.feed([fist], 3)
    assert app.enabled


def test_hand_lost_for_idle_seconds_disables():
    app = enabled_app()
    p = Player(app)
    p.feed([make_hand()], 3)
    p.feed([], math.ceil(Config().idle_disable_sec / p.dt) + 2)
    assert not app.enabled


# --- クリック ----------------------------------------------------------------

def test_left_pinch_presses_and_release_lets_go():
    app = enabled_app()
    p = Player(app)
    p.feed([make_hand()], 3)
    play(p, approach())
    assert app.mouse.left_down
    p.feed([make_hand()], 2)                       # 親指を離す
    assert app.mouse.calls[-2:] == ["left_down", "left_up"]


def test_left_click_without_drag():
    app = enabled_app(left_drag_enabled=False)
    p = Player(app)
    p.feed([make_hand()], 3)
    play(p, approach())
    assert app.mouse.calls == ["left_click"]


def test_right_click_with_ring_finger():
    app = enabled_app()
    p = Player(app)
    p.feed([make_hand(index_ext=True, ring_ext=True)], 3)
    p.feed([pinch_to(G.RING_TIP, index_ext=True, ring_ext=True)], 4)
    assert app.mouse.calls.count("right_click") == 1


def test_scroll_up_when_scissors_move_up():
    app = enabled_app()
    p = Player(app)
    for k in range(12):
        p.feed([make_hand(index_ext=True, middle_ext=True, origin=(0.5, 0.8 - 0.01 * k))])
    scrolls = [c for c in app.mouse.calls if c[0] == "scroll"]
    assert scrolls and all(n > 0 for _, n in scrolls)


# --- クリック位置のズレ対策（カーソル固定）-------------------------------------

def test_cursor_freezes_while_thumb_approaches_and_clicks_there():
    app = enabled_app()
    p = Player(app)
    p.feed([make_hand()], 6)
    frozen_at = []
    for hand in approach():
        p.feed([hand])
        if app.frozen:
            frozen_at.append(app.last_screen_pos)
    assert frozen_at, "親指が近づいてきたらカーソルを止める"
    assert all(pos == frozen_at[0] for pos in frozen_at)
    assert app.mouse.left_down
    assert app.last_screen_pos == pytest.approx(frozen_at[0], abs=1.0)


def test_pinch_arm_zero_disables_freeze_but_keeps_click():
    """pinch_arm=0 は「近づいたときの自動固定をしない」。左クリックは従来どおり成立する。"""
    app = enabled_app(pinch_arm=0.0)
    p = Player(app)
    p.feed([make_hand()], 3)
    froze = False
    for hand in approach():
        p.feed([hand])
        froze |= app.frozen
    assert not froze
    assert app.mouse.left_down


# --- カーソルの安定化 ---------------------------------------------------------

def test_small_jitter_does_not_move_cursor():
    import random
    random.seed(1)
    app = enabled_app()
    p = Player(app)
    positions = []
    for _ in range(60):
        jitter = (random.uniform(-0.003, 0.003), random.uniform(-0.003, 0.003))
        p.feed([make_hand(origin=(0.5 + jitter[0], 0.6 + jitter[1]))])
        positions.append(app.last_screen_pos)
    settled = positions[20:]
    spread = max(math.dist(a, b) for a in settled for b in settled)
    assert spread < 2.0


def test_large_move_is_followed():
    app = enabled_app()
    p = Player(app)
    p.feed([make_hand(origin=(0.45, 0.6))], 20)
    start = app.last_screen_pos
    p.feed([make_hand(origin=(0.55, 0.6))], 40)
    assert app.last_screen_pos[0] - start[0] > 200


def test_overlay_hand_is_constant_size_and_on_cursor():
    """オーバーレイの手はカメラとの距離に関係なく同じ大きさで、基準点がカーソルに重なる。"""
    cfg = Config()
    cfg.cursor_landmark = "index_tip"
    app = make_app(cfg)
    app.last_screen_pos = (800.0, 500.0)
    for scale in (1.0, 0.5):                    # 0.5 = 遠くにある（小さく映る）手
        app.skeleton_prev = []
        hand = make_hand()
        cx, cy = hand.point(G.WRIST)
        hand = G.Hand.from_points([(cx + (x - cx) * scale, cy + (y - cy) * scale)
                                   for x, y in hand.points])
        state = G.GestureState(mode=G.MODE_POINT, cursor=hand.point(G.INDEX_TIP), hands=[hand])
        pts = app.hands_to_screen([hand], state)[0]
        assert math.dist(pts[G.WRIST], pts[G.MIDDLE_MCP]) == pytest.approx(cfg.overlay_hand_size)
        assert pts[G.INDEX_TIP] == pytest.approx((800.0, 500.0))


# --- マウス入力の送信失敗（ロック画面・UACなど）--------------------------------

class FlakyUser32:
    """SendInput だけ失敗させられる user32 の代わり。カーソルは実際には動かさない。"""

    def __init__(self, real):
        self.real = real
        self.fail = True

    def __getattr__(self, name):
        return getattr(self.real, name)

    def SendInput(self, n, inputs, size):
        return 0 if self.fail else n

    def SetCursorPos(self, x, y):
        return 1


def test_send_failure_does_not_stop_app_and_recovers(monkeypatch):
    flaky = FlakyUser32(M.user32)
    monkeypatch.setattr(M, "user32", flaky)
    cfg = Config()
    cfg.enable_on_start = True
    app = make_app(cfg, mouse=M.MouseController())   # 本物の MouseController を通す
    p = Player(app)
    p.feed([make_hand()], 3)
    play(p, approach())                               # 例外にならず処理が続く
    assert not app.mouse.left_down                    # 送れていないので押した扱いにしない
    flaky.fail = False                                # ロック解除で送れるようになる
    p.feed([p.states[-1].hands[0]], 2)
    assert app.mouse.left_down


# --- 長押しでダブルクリック（ドラッグを使わない設定）------------------------------

def hold_frames(player, sec):
    return math.ceil(sec / player.dt)


def test_long_press_turns_into_double_click():
    """触れた瞬間に1回、長押しが成立したらダブルクリックになるようクリックを足す。"""
    app = enabled_app(left_drag_enabled=False)          # 長押し 0.6秒 > OS のダブルクリック時間 0.5秒
    p = Player(app)
    p.feed([make_hand()], 3)
    play(p, approach(hold=0))
    assert app.mouse.calls == ["left_click"]            # 触れた瞬間のクリックは遅らせない
    touching = approach()[-1]
    p.feed([touching], hold_frames(p, 0.7))
    assert app.mouse.calls == ["left_click"] * 3        # 足した2回が OS でダブルクリックになる
    assert any("ダブルクリック（長押し）" in n for n in app.notes)
    p.feed([touching], 30)                              # 押し続けても繰り返さない
    assert app.mouse.calls.count("left_click") == 3


def test_long_press_within_os_double_click_time_adds_one_click():
    """長押しの秒数が OS のダブルクリック時間より短ければ、1回目と合わせて2回にする（3連続にしない）。"""
    app = enabled_app(left_drag_enabled=False, long_press_double_click_sec=0.4)
    p = Player(app)
    p.feed([make_hand()], 3)
    play(p, approach(hold=0))
    p.feed([approach()[-1]], hold_frames(p, 0.5))
    assert app.mouse.calls == ["left_click"] * 2


def test_short_tap_is_single_click():
    app = enabled_app(left_drag_enabled=False)
    p = Player(app)
    p.feed([make_hand()], 3)
    play(p, approach(hold=3))                           # 0.1秒ほどで離す
    p.feed([make_hand()], 10)
    assert app.mouse.calls == ["left_click"]


def test_long_press_is_drag_when_drag_enabled():
    app = enabled_app(left_drag_enabled=True)
    p = Player(app)
    p.feed([make_hand()], 3)
    play(p, approach(hold=0))
    p.feed([approach()[-1]], hold_frames(p, 1.0))
    assert app.mouse.left_down
    assert "left_click" not in app.mouse.calls


def test_long_press_double_click_can_be_turned_off():
    app = enabled_app(left_drag_enabled=False, long_press_double_click_sec=0.0)
    p = Player(app)
    p.feed([make_hand()], 3)
    play(p, approach(hold=0))
    p.feed([approach()[-1]], hold_frames(p, 1.0))
    assert app.mouse.calls == ["left_click"]


def test_long_press_shows_countdown():
    app = enabled_app(left_drag_enabled=False)
    p = Player(app)
    p.feed([make_hand()], 3)
    play(p, approach(hold=0))
    state = p.feed([approach()[-1]], hold_frames(p, 0.3))
    assert app.build_hint(state, p.t).startswith("長押しでダブルクリック 0.")


def test_long_press_while_locked_with_middle_finger():
    """中指で固定してから人差し指を付けたまま長押し（今の使い方）でもダブルクリックになる。"""
    app = enabled_app(left_drag_enabled=False, freeze_gesture="middle")
    p = Player(app)
    kw = dict(index_ext=True, middle_ext=True)
    base = make_hand(**kw)
    mx, my = base.point(G.MIDDLE_TIP)
    sx, sy = base.point(G.THUMB_TIP)
    p.feed([base], 3)
    for k in range(8):                                   # 親指を中指先へ近づけて固定
        f = k / 7
        p.feed([make_hand(thumb_to=(sx + (mx - sx) * f, sy + (my - sy) * f), **kw)])
    locked = make_hand(thumb_to=(mx, my), **kw)
    state = p.feed([locked], 3)
    assert state.lock_tip is not None and app.frozen
    frozen_at = app.last_screen_pos
    points = list(locked.points)
    points[G.INDEX_TIP] = (mx - 0.003, my + 0.003)       # 人差し指の先を親指に付ける
    touching = G.Hand.from_points(points, "Right")
    p.feed([touching], hold_frames(p, 0.8))
    assert app.mouse.calls == ["left_click"] * 3
    assert app.last_screen_pos == frozen_at              # 固定した位置のまま
