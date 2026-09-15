# -*- coding: utf-8 -*-
"""手のランドマークからジェスチャーを判定する。"""

import math
import time
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

# 右クリックに使える指（設定名 → (指先, 第二関節)）
RIGHT_CLICK_FINGERS = {
    "middle": (MIDDLE_TIP, MIDDLE_PIP),
    "ring": (RING_TIP, RING_PIP),
    "pinky": (PINKY_TIP, PINKY_PIP),
}

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

    def __init__(self, landmarks, handedness="", handedness_score=1.0):
        # 正規化座標（0.0〜1.0）のリストとして保持する
        self.points = [(lm.x, lm.y) for lm in landmarks]
        self.handedness = handedness
        self.handedness_score = float(handedness_score)
        # 手のひらの大きさ。指の開き具合に影響されない手首〜中指付け根を使う
        self.scale = max(_dist(self.points[WRIST], self.points[MIDDLE_MCP]), 1e-6)

    @classmethod
    def from_points(cls, points, handedness="", handedness_score=1.0):
        """(x, y) のリストから作る（平滑化済みの座標を渡すとき用）。"""
        hand = cls.__new__(cls)
        hand.points = list(points)
        hand.handedness = handedness
        hand.handedness_score = float(handedness_score)
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

    def pinch_to(self, tip):
        """親指と指定した指先の距離（手の大きさで正規化）。"""
        return _dist(self.points[THUMB_TIP], self.points[tip]) / self.scale

    def finger_reaching(self, tip, pip):
        """その指が前に出ているか（握り込んでいないか）。

        人差し指を立てた姿勢では親指が曲げた指に触れがちなので、
        右クリック判定はこれが真のときだけ有効にする。
        """
        return self._extended(tip, pip, ratio=0.95)

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

    def edge_distance(self):
        """手のひらの点のうち、フレーム端に最も近いものの端までの距離（正規化）。"""
        best = 1.0
        for i in (WRIST, INDEX_MCP, MIDDLE_MCP, RING_MCP, PINKY_MCP):
            x, y = self.points[i]
            best = min(best, x, 1.0 - x, y, 1.0 - y)
        return max(best, 0.0)

    def near_frame_edge(self, margin):
        """手のひらの点のどれかがフレーム端から margin 以内にあるか。"""
        return self.edge_distance() < margin

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
    pinch_right: float = None     # 右クリック用の指との距離（画面表示用）
    right_tip: int = RING_TIP     # 右クリックに使う指先の番号（描画用）
    arming: bool = False          # 親指が近づいていてカーソル固定中（クリック準備）
    lock_tip: int = None          # 固定ジェスチャーでつまんでいる指先（描画用。中指ピンチ固定のとき）
    lock_drag: bool = False       # 固定を続けてドラッグに移行した（本体側が描画用に立てる）
    lock_held_sec: float = 0.0    # 固定の継続時間（本体側が描画用に入れる）
    near_edge: bool = False       # 手のひらがカメラ映像の端に近い（検出が不安定になる）
    edge_factor: float = 0.0      # 端への近さ（0=十分内側, 1=端に接触）。安定化の強さに使う


class GestureRecognizer:
    """フレームごとの手の情報からモードを決定する（ヒステリシス付き）。"""

    def __init__(self, cfg):
        self.cfg = cfg
        self._left_on = False
        self._right_on = False
        self._arm_on = False
        self._prev_d_index = None
        self._left_pending = 0    # ピンチ条件を満たした連続フレーム数（確定待ち）
        self._right_pending = 0
        self._lock_on = False     # 中指ピンチによる位置固定（freeze_gesture=middle）
        self._lock_released_at = None   # 固定を離した時刻（余韻の判定用）
        self._now = 0.0

    def reset(self):
        self._left_on = False
        self._right_on = False
        self._arm_on = False
        self._prev_d_index = None
        self._left_pending = 0
        self._right_pending = 0
        self._lock_on = False
        self._lock_released_at = None

    def _lock_active(self):
        """固定中、または固定を離した直後の余韻（lock_grace_sec）の中か。"""
        if self._lock_on:
            return True
        return (self._lock_released_at is not None
                and self._now - self._lock_released_at < self.cfg.lock_grace_sec)

    def _middle_lock_enabled(self):
        """中指ピンチ固定が有効か（右クリックの指と衝突する設定なら無効）。"""
        return (self.cfg.freeze_gesture == "middle"
                and self.cfg.right_click_finger != "middle")

    def _confirm(self, cond, currently_on, pending_attr):
        """ピンチ条件が連続フレーム数だけ続いたら成立とみなす（成立中は距離のみで維持）。"""
        if currently_on:
            setattr(self, pending_attr, 0)
            return cond
        if not cond:
            setattr(self, pending_attr, 0)
            return False
        n = getattr(self, pending_attr) + 1
        setattr(self, pending_attr, n)
        if n >= max(1, self.cfg.pinch_confirm_frames):
            setattr(self, pending_attr, 0)
            return True
        return False

    def _update_arming(self, d_index):
        """クリック準備（カーソル固定）の判定。

        しきい値を「外から内へ横切った」瞬間だけ立てる。最初から親指が近い姿勢
        （自然に指を寄せている状態）では発火しない。しきい値の外に出たら解除。
        """
        arm = self.cfg.pinch_arm
        if arm <= 0:
            # 固定機能が無効でも、接近の判定（左クリックの前提）は 0.7 相当で行う
            arm = 0.7
        if self._arm_on:
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

    def update(self, hands, now=None):
        """手のリスト（Hand）からGestureStateを返す。now は時刻[秒]（省略時は現在時刻）。"""
        self._now = time.monotonic() if now is None else now
        if not hands:
            self.reset()
            return GestureState(mode=MODE_IDLE)

        # カメラに近い（=大きく写っている）手を主操作の手とする
        hands = sorted(hands, key=lambda h: h.scale, reverse=True)
        primary = hands[0]

        right_tip, right_pip = RIGHT_CLICK_FINGERS.get(
            self.cfg.right_click_finger, RIGHT_CLICK_FINGERS["ring"])
        state = GestureState(
            hands=hands,
            pinch_index=primary.pinch_index,
            pinch_right=primary.pinch_to(right_tip),
            right_tip=right_tip,
            near_edge=primary.near_frame_edge(self.cfg.edge_warn_margin),
        )
        zone = self.cfg.edge_zone
        if zone > 0:
            state.edge_factor = max(0.0, min(1.0, 1.0 - primary.edge_distance() / zone))

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
        # 右クリックの指は「人差し指より明確に近い」ときだけ採用し、
        # 隣り合う指による左右クリックの取り違えを防ぐ
        d_index = primary.pinch_index
        d_right = state.pinch_right
        # 親指の接近（クリック準備）は毎フレーム追跡する。左クリックの前提条件にも使う
        self._update_arming(d_index)

        middle_lock = self._middle_lock_enabled()
        right_cond = (self._pinch_state(d_right, self._right_on)
                      and d_right < d_index * 0.8
                      and primary._extended(right_tip, right_pip,
                                            ratio=self.cfg.right_finger_reach))
        # 中指ピンチ固定のときは、右クリックも「固定してから」（固定中または余韻の中）だけ
        if middle_lock and not self._right_on and not self._lock_active():
            right_cond = False
        right_on = self._confirm(right_cond, self._right_on, "_right_pending")

        # 中指ピンチ固定: 親指＋中指をつまんでいる間だけ「固定」とみなす
        if middle_lock:
            d_middle = primary.pinch_to(MIDDLE_TIP)
            lock_was_on = self._lock_on
            thresh = self.cfg.lock_pinch_off if self._lock_on else self.cfg.lock_pinch_on
            lock = (d_middle < thresh
                    and primary._extended(MIDDLE_TIP, MIDDLE_PIP, ratio=self.cfg.lock_finger_reach)
                    and not right_on)
            # 固定の開始は「親指が人差し指より中指に近い」ときだけ
            # （親指を人差し指に付けただけで中指にも近づくため）。保持中は距離だけで維持
            if not self._lock_on and d_middle >= d_index * self.cfg.lock_index_ratio:
                lock = False
            self._lock_on = lock
            # 離した後も余韻の間は固定位置を保つ（その間の右／左クリックを受け付ける）
            if self._lock_on:
                self._lock_released_at = None
            elif lock_was_on:
                self._lock_released_at = self._now
            self._arm_on = self._lock_active()
            state.lock_tip = MIDDLE_TIP if self._lock_on else None
        else:
            self._lock_on = False
            self._lock_released_at = None

        # 人差し指を握り込んでいるとき（グー）は左ピンチとみなさない。
        # 未成立のうちは「親指が離れた状態から近づいてきた」（middle固定では固定中）ことも要求する
        left_cond = (self._pinch_state(d_index, self._left_on) and not right_on
                     and not primary.index_curled)
        if not self._left_on:
            if middle_lock:
                # 固定中に人差し指も親指に付いたときだけ。親指が中指に付いただけの姿勢では
                # 人差し指との距離が中指より明確に遠いので、その比で区別する
                if not self._lock_active() or d_index > d_middle * 1.3:
                    left_cond = False
            elif self.cfg.pinch_require_approach and not self._arm_on:
                left_cond = False
        left_on = self._confirm(left_cond, self._left_on, "_left_pending")

        if self._left_on and not left_on and not middle_lock:
            # 離した直後は、親指を一度離してからでないと再度クリックできない
            self._arm_on = False
        self._left_on = left_on
        self._right_on = right_on

        # ピンチはグーより優先する（つまむと他の指が閉じるため）
        if self._left_on:
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
        # （親指が中指をつまんでいる／固定中はチョキとみなさない）
        if (primary.index_extended and primary.middle_extended
                and not primary.ring_extended and not primary.pinky_extended
                and not self._lock_on
                and primary.pinch_to(MIDDLE_TIP) > self.cfg.lock_pinch_off):
            state.mode = MODE_SCROLL
            state.scroll_anchor = primary.center[1]
            return state

        # カーソル基準点が指先のときだけ人差し指を立てる必要がある。
        # 手のひら／付け根基準なら、グーでなければ手を開いた形でカーソル移動できる
        if self.cfg.cursor_landmark != "index_tip" or primary.index_extended:
            state.mode = MODE_POINT
            state.cursor = self._cursor_point(primary, MODE_POINT)
            # 親指が人差し指へ近づき始めたらクリック準備（本体側でカーソルを固定する）
            state.arming = self._arm_on
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
