# -*- coding: utf-8 -*-
"""手のランドマークからジェスチャーを判定する。"""

import math
from dataclasses import dataclass, field

# MediaPipeの手のランドマーク番号
WRIST = 0
THUMB_TIP = 4
INDEX_MCP = 5
INDEX_PIP = 6
INDEX_TIP = 8
MIDDLE_MCP = 9
MIDDLE_PIP = 10
MIDDLE_TIP = 12
RING_MCP = 13
RING_PIP = 14
RING_TIP = 16
PINKY_MCP = 17
PINKY_PIP = 18
PINKY_TIP = 20

# 骨格描画用の接続リスト
HAND_CONNECTIONS = (
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12),
    (9, 13), (13, 14), (14, 15), (15, 16),
    (13, 17), (17, 18), (18, 19), (19, 20),
    (0, 17),
)

# 動作モード
MODE_NONE = "NONE"        # 手はあるが操作しない
MODE_IDLE = "IDLE"        # 手が写っていない
MODE_POINT = "POINT"      # カーソル移動
MODE_LEFT = "LEFT"        # 左クリック / ドラッグ
MODE_RIGHT = "RIGHT"      # 右クリック
MODE_SCROLL = "SCROLL"    # スクロール
MODE_ZOOM = "ZOOM"        # ズーム
MODE_FIST = "FIST"        # グー（一時停止）

MODE_LABELS = {
    MODE_NONE: "待機",
    MODE_IDLE: "手を検出していません",
    MODE_POINT: "カーソル移動",
    MODE_LEFT: "左クリック / ドラッグ",
    MODE_RIGHT: "右クリック",
    MODE_SCROLL: "スクロール",
    MODE_ZOOM: "ズーム",
    MODE_FIST: "グー（一時停止）",
}


def _dist(a, b):
    """2点間のユークリッド距離。"""
    return math.hypot(a[0] - b[0], a[1] - b[1])


class Hand:
    """1つの手のランドマークと、そこから導かれる特徴量。"""

    def __init__(self, landmarks, handedness=""):
        # 正規化座標（0.0〜1.0）のリストとして保持する
        self.points = [(lm.x, lm.y) for lm in landmarks]
        self.handedness = handedness
        # 手のひらの大きさ。指の開き具合に影響されない手首〜中指付け根を使う
        self.scale = max(_dist(self.points[WRIST], self.points[MIDDLE_MCP]), 1e-6)

    @classmethod
    def from_points(cls, points, handedness=""):
        """(x, y) のリストから作る（平滑化済みの座標を渡すとき用）。"""
        hand = cls.__new__(cls)
        hand.points = list(points)
        hand.handedness = handedness
        hand.scale = max(_dist(hand.points[WRIST], hand.points[MIDDLE_MCP]), 1e-6)
        return hand

    def point(self, idx):
        return self.points[idx]

    def _extended(self, tip, pip, ratio=1.12):
        """指が伸びているか。手首からの距離で見るので手の向きに強い。"""
        wrist = self.points[WRIST]
        return _dist(wrist, self.points[tip]) > _dist(wrist, self.points[pip]) * ratio

    @property
    def index_extended(self):
        return self._extended(INDEX_TIP, INDEX_PIP)

    @property
    def middle_extended(self):
        return self._extended(MIDDLE_TIP, MIDDLE_PIP)

    @property
    def ring_extended(self):
        return self._extended(RING_TIP, RING_PIP)

    @property
    def pinky_extended(self):
        return self._extended(PINKY_TIP, PINKY_PIP)

    @property
    def pinch_index(self):
        """親指と人差し指の距離（手の大きさで正規化）。"""
        return _dist(self.points[THUMB_TIP], self.points[INDEX_TIP]) / self.scale

    @property
    def pinch_middle(self):
        """親指と中指の距離（手の大きさで正規化）。"""
        return _dist(self.points[THUMB_TIP], self.points[MIDDLE_TIP]) / self.scale

    @property
    def middle_reaching(self):
        """中指が前に出ているか（握り込んでいないか）。

        人差し指を立てた姿勢では親指が曲げた中指に触れがちなので、
        右クリック判定はこれが真のときだけ有効にする。
        """
        return self._extended(MIDDLE_TIP, MIDDLE_PIP, ratio=0.95)

    def _curled(self, tip, pip, ratio=0.95):
        """指を握り込んでいるか（指先が第二関節より手首側に来ている）。"""
        wrist = self.points[WRIST]
        return _dist(wrist, self.points[tip]) < _dist(wrist, self.points[pip]) * ratio

    @property
    def index_curled(self):
        return self._curled(INDEX_TIP, INDEX_PIP)

    @property
    def is_fist(self):
        """4本指をすべて握り込んでいればグーとみなす。

        「伸びていない」ではなく「握り込んでいる」で判定する。ピンチ中や
        クリック後に緩んだ手（半開き）をグーと誤判定しないため。
        """
        return (self._curled(INDEX_TIP, INDEX_PIP) and self._curled(MIDDLE_TIP, MIDDLE_PIP)
                and self._curled(RING_TIP, RING_PIP) and self._curled(PINKY_TIP, PINKY_PIP))

    @property
    def center(self):
        """手の基準位置（中指付け根）。スクロール量の計算に使う。"""
        return self.points[MIDDLE_MCP]

    @property
    def palm_center(self):
        """手のひら中心（手首と4本指の付け根の平均）。

        5点を平均するのでランドマークのブレが小さく、指を動かしても変わらないため
        カーソルの基準点として最も安定する。
        """
        idx = (WRIST, INDEX_MCP, MIDDLE_MCP, RING_MCP, PINKY_MCP)
        return (sum(self.points[i][0] for i in idx) / len(idx),
                sum(self.points[i][1] for i in idx) / len(idx))


@dataclass
class GestureState:
    """1フレーム分の判定結果。"""
    mode: str = MODE_IDLE
    cursor: tuple = None          # カーソル基準点（正規化座標）
    hands: list = field(default_factory=list)
    scroll_anchor: float = None   # スクロール判定用のy座標
    zoom_distance: float = None   # 両手の人差し指先の距離
    pinch_index: float = None     # 画面表示用
    pinch_middle: float = None
    arming: bool = False          # 親指が近づいていてカーソル固定中（クリック準備）


class GestureRecognizer:
    """フレームごとの手の情報からモードを決定する（ヒステリシス付き）。"""

    def __init__(self, cfg):
        self.cfg = cfg
        self._left_on = False
        self._right_on = False
        self._arm_on = False
        self._prev_d_index = None

    def reset(self):
        self._left_on = False
        self._right_on = False
        self._arm_on = False
        self._prev_d_index = None

    def _update_arming(self, d_index):
        """クリック準備（カーソル固定）の判定。

        しきい値を「外から内へ横切った」瞬間だけ立てる。最初から親指が近い姿勢
        （自然に指を寄せている状態）では発火しない。しきい値の外に出たら解除。
        """
        arm = self.cfg.pinch_arm
        if arm <= 0:
            self._arm_on = False
        elif self._arm_on:
            self._arm_on = d_index < arm
        else:
            self._arm_on = (self._prev_d_index is not None
                            and self._prev_d_index >= arm and d_index < arm)
        self._prev_d_index = d_index
        return self._arm_on

    def _pinch_state(self, value, current):
        """しきい値を2段にして、境界付近でのチャタリングを防ぐ。"""
        if current:
            return value < self.cfg.pinch_off
        return value < self.cfg.pinch_on

    def update(self, hands):
        """手のリスト（Hand）からGestureStateを返す。"""
        if not hands:
            self.reset()
            return GestureState(mode=MODE_IDLE)

        # カメラに近い（=大きく写っている）手を主操作の手とする
        hands = sorted(hands, key=lambda h: h.scale, reverse=True)
        primary = hands[0]

        state = GestureState(
            hands=hands,
            pinch_index=primary.pinch_index,
            pinch_middle=primary.pinch_middle,
        )

        # 両手ともピンチしていれば、手の間隔でズーム
        if len(hands) >= 2:
            both_pinch = all(h.pinch_index < self.cfg.pinch_on for h in hands[:2])
            if both_pinch:
                self._left_on = False
                self._right_on = False
                state.mode = MODE_ZOOM
                state.zoom_distance = _dist(hands[0].point(INDEX_TIP),
                                            hands[1].point(INDEX_TIP))
                return state

        # ピンチ状態を更新（ヒステリシス）
        # 中指ピンチは「人差し指より明確に近い」ときだけ採用し、
        # 隣り合う指による左右クリックの取り違えを防ぐ
        d_index = primary.pinch_index
        d_middle = primary.pinch_middle
        right_on = (self._pinch_state(d_middle, self._right_on)
                    and d_middle < d_index * 0.8
                    and primary.middle_reaching)
        # 人差し指を握り込んでいるとき（グー）は左ピンチとみなさない
        left_on = (self._pinch_state(d_index, self._left_on) and not right_on
                   and not primary.index_curled)
        self._left_on = left_on
        self._right_on = right_on

        # ピンチはグーより優先する（つまむと他の指が閉じるため）
        if self._left_on:
            self._arm_on = False
            state.mode = MODE_LEFT
            state.cursor = self._cursor_point(primary, MODE_LEFT)
            return state

        if self._right_on:
            self._arm_on = False
            state.mode = MODE_RIGHT
            state.cursor = self._cursor_point(primary, MODE_RIGHT)
            return state

        if primary.is_fist:
            self._arm_on = False
            state.mode = MODE_FIST
            return state

        # 人差し指と中指だけを立てた「チョキ」でスクロール
        if (primary.index_extended and primary.middle_extended
                and not primary.ring_extended and not primary.pinky_extended):
            state.mode = MODE_SCROLL
            state.scroll_anchor = primary.center[1]
            return state

        # カーソル基準点が指先のときだけ人差し指を立てる必要がある。
        # 手のひら／付け根基準なら、グーでなければ手を開いた形でカーソル移動できる
        if self.cfg.cursor_landmark != "index_tip" or primary.index_extended:
            state.mode = MODE_POINT
            state.cursor = self._cursor_point(primary, MODE_POINT)
            # 親指が人差し指へ近づき始めたらクリック準備（本体側でカーソルを固定する）
            state.arming = self._update_arming(d_index)
            return state

        self._arm_on = False
        state.mode = MODE_NONE
        return state

    def cursor_point(self, hand, mode):
        """カーソルの基準点を返す（設定とモードで切り替える）。表示側からも使う。"""
        return self._cursor_point(hand, mode)

    def _cursor_point(self, hand, mode):
        landmark = self.cfg.cursor_landmark
        if landmark == "palm":
            return hand.palm_center
        if landmark == "index_mcp":
            return hand.point(INDEX_MCP)
        if mode == MODE_LEFT:
            # ドラッグ中は親指と人差し指の中点を基準にするとブレにくい
            tp, ip = hand.point(THUMB_TIP), hand.point(INDEX_TIP)
            return ((tp[0] + ip[0]) * 0.5, (tp[1] + ip[1]) * 0.5)
        return hand.point(INDEX_TIP)
