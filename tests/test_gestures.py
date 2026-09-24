# -*- coding: utf-8 -*-
"""ジェスチャー判定（GestureRecognizer）のテスト。"""

import pytest

from hm_core import gestures as G
from hm_core.config import Config
from synthetic import make_hand, pinch_to


def recognize(hands, cfg=None, frames=3):
    """同じ手を数フレーム流したときの最終モード（ピンチは連続フレームで確定するため）。"""
    rec = G.GestureRecognizer(cfg or Config())
    state = None
    for i in range(frames):
        state = rec.update(hands, 0.033 * (i + 1))
    return state


def approach_and_pinch(tip_index, cfg=None, **kw):
    """親指を離れた位置から指先へ近づけてつまむ（左クリックは「近づいてきた」ことが条件）。"""
    rec = G.GestureRecognizer(cfg or Config())
    base = make_hand(**kw)
    tx, ty = base.point(tip_index)
    sx, sy = base.point(G.THUMB_TIP)
    states = []
    for k in range(14):
        f = min(1.0, k / 8.0)
        thumb = (sx + (tx + 0.005 - sx) * f, sy + (ty + 0.005 - sy) * f)
        states.append(rec.update([make_hand(thumb_to=thumb, **kw)], 0.033 * (k + 1)))
    return [s.mode for s in states]


def test_open_hand_moves_cursor():
    assert recognize([make_hand()]).mode == G.MODE_POINT


def test_no_hand_is_idle():
    assert recognize([]).mode == G.MODE_IDLE


def test_thumb_approaching_index_is_left_click():
    assert G.MODE_LEFT in approach_and_pinch(G.INDEX_TIP)


def test_thumb_already_on_index_does_not_click():
    """最初から指が付いている姿勢では左クリックにしない（近づいてきたときだけ）。"""
    assert recognize([pinch_to(G.INDEX_TIP)], frames=6).mode != G.MODE_LEFT


def test_thumb_on_ring_is_right_click():
    hand = pinch_to(G.RING_TIP, index_ext=True, ring_ext=True)
    assert recognize([hand]).mode == G.MODE_RIGHT


def test_thumb_on_middle_is_not_right_click_by_default():
    """右クリックの指は既定で薬指。中指ではクリックしない。"""
    hand = pinch_to(G.MIDDLE_TIP, index_ext=True, middle_ext=True)
    assert recognize([hand]).mode != G.MODE_RIGHT


def test_right_click_finger_can_be_middle():
    cfg = Config()
    cfg.right_click_finger = "middle"
    hand = pinch_to(G.MIDDLE_TIP, index_ext=True, middle_ext=True)
    assert recognize([hand], cfg).mode == G.MODE_RIGHT


def test_thumb_touching_curled_ring_is_not_right_click():
    """人差し指を立てて握った薬指に親指が触れているだけでは右クリックにしない。"""
    base = make_hand(index_ext=True)
    tx, ty = base.point(G.RING_TIP)
    hand = make_hand(index_ext=True, thumb_to=(tx + 0.005, ty + 0.005))
    assert recognize([hand]).mode != G.MODE_RIGHT


def test_scissors_is_scroll():
    assert recognize([make_hand(index_ext=True, middle_ext=True)]).mode == G.MODE_SCROLL


def test_fist():
    assert recognize([make_hand(False, False, False, False)]).mode == G.MODE_FIST


def test_thumb_on_index_inside_fist_is_not_click():
    base = make_hand(False, False, False, False)
    tx, ty = base.point(G.INDEX_TIP)
    hand = make_hand(False, False, False, False, thumb_to=(tx + 0.005, ty + 0.005))
    assert recognize([hand]).mode == G.MODE_FIST


def test_two_hands_pinching_is_zoom():
    hands = [pinch_to(G.INDEX_TIP, origin=(0.35, 0.8)),
             pinch_to(G.INDEX_TIP, origin=(0.65, 0.8))]
    state = recognize(hands)
    assert state.mode == G.MODE_ZOOM
    assert state.zoom_distance > 0


def test_pinch_is_held_with_hysteresis():
    """つまんだ後に少し緩めても、解除のしきい値までは左クリックのまま。"""
    rec = G.GestureRecognizer(Config())
    base = make_hand()
    tx, ty = base.point(G.INDEX_TIP)
    sx, sy = base.point(G.THUMB_TIP)
    t = 0.0
    for k in range(14):
        f = min(1.0, k / 8.0)
        t += 0.033
        state = rec.update([make_hand(thumb_to=(sx + (tx - sx) * f, sy + (ty - sy) * f))], t)
    assert state.mode == G.MODE_LEFT
    # つまみ始めのしきい値（pinch_on）と解除のしきい値（pinch_off）の真ん中まで緩める。
    # 距離は手の大きさ（手首〜中指付け根）で割った値なので、その分を掛けて置く
    cfg = Config()
    gap = (cfg.pinch_on + cfg.pinch_off) / 2 * base.scale
    loosened = make_hand(thumb_to=(tx, ty + gap))
    assert cfg.pinch_on < loosened.pinch_index < cfg.pinch_off
    assert rec.update([loosened], t + 0.033).mode == G.MODE_LEFT
    # 解除のしきい値より離せば、左クリックは終わる
    released = make_hand(thumb_to=(tx, ty + cfg.pinch_off * 1.2 * base.scale))
    assert rec.update([released], t + 0.066).mode != G.MODE_LEFT


@pytest.mark.parametrize("landmark", ["palm", "index_mcp", "index_tip"])
def test_cursor_landmark_choices(landmark):
    cfg = Config()
    cfg.cursor_landmark = landmark
    hand = make_hand()
    state = recognize([hand], cfg)
    expected = {"palm": hand.palm_center, "index_mcp": hand.point(G.INDEX_MCP),
                "index_tip": hand.point(G.INDEX_TIP)}[landmark]
    assert state.cursor == pytest.approx(expected)


def test_hand_near_frame_edge_is_flagged():
    assert recognize([make_hand(origin=(0.5, 0.99))]).near_edge
    assert not recognize([make_hand(origin=(0.5, 0.6))]).near_edge
