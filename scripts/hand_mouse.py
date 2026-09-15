# -*- coding: utf-8 -*-
"""Webカメラの手の動きでWindowsのマウスを操作する（VRハンドトラッキング風UI）。

使い方:
    python scripts/hand_mouse.py

ジェスチャー:
    人差し指を立てる      : カーソル移動（絶対座標マッピング）
    親指＋人差し指ピンチ  : 左クリック／そのまま動かすとドラッグ
    親指＋中指ピンチ      : 右クリック
    チョキ（2本指）上下   : スクロール
    両手ピンチして広げる  : ズーム（Ctrl＋ホイール）
    グーを一定時間保持    : 操作の有効／無効を切り替え

表示:
    既定はデスクトップ上に手の骨格だけを透過表示するオーバーレイ（クリックは素通し）。
    --display preview でカメラ映像ウィンドウ、--display none で非表示。

安全装置:
    Ctrl+Alt+Q で終了、Ctrl+Alt+H で有効・無効を切り替え、Ctrl+Alt+R でリセット。
    いずれもフォーカスが無くても効くグローバルホットキー。
    preview表示中は Esc / Space / R も使える。
"""

import argparse
import math
import sys
import time
from pathlib import Path

import cv2
import mediapipe as mp
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python import vision

sys.path.insert(0, str(Path(__file__).resolve().parent))

from hm_core import gestures as G                      # noqa: E402
from hm_core.camera import CameraStream                # noqa: E402
from hm_core.config import Config                      # noqa: E402
from hm_core.filters import Point2DFilter              # noqa: E402
from hm_core.hotkeys import HotkeyManager              # noqa: E402
from hm_core.mouse import MouseController, enable_dpi_awareness  # noqa: E402
from hm_core.overlay import TextRenderer, render_hud   # noqa: E402
from hm_core.overlay_window import HandOverlay         # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "scripts" / "hand_mouse_config.json"
WINDOW_NAME = "Hand Mouse"

VK_H = 0x48
VK_Q = 0x51
VK_R = 0x52

DISPLAY_MODES = ("overlay", "preview", "none")

# ドラッグ開始時のカーソル飛びを吸収するオフセットの減衰時定数[秒]
OFFSET_DECAY_TAU = 0.12


def clamp01(v):
    return 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)


class HandMouseApp:
    """カメラ入力→ジェスチャー判定→マウス操作を1ループで回す。"""

    def __init__(self, cfg):
        self.cfg = cfg
        self.mouse = MouseController(cfg.screen_margin_px)
        self.recognizer = G.GestureRecognizer(cfg)
        self.filter = Point2DFilter(cfg.filter_min_cutoff, cfg.filter_beta,
                                    cfg.filter_d_cutoff)
        self.renderer = TextRenderer()
        self.hotkeys = HotkeyManager()

        self.enabled = bool(cfg.enable_on_start)
        self.running = True
        self.fps = 0.0

        # ジェスチャー間で引き継ぐ状態
        self.prev_mode = G.MODE_IDLE
        self.prev_scroll_anchor = None
        self.scroll_accum = 0.0
        self.prev_zoom_distance = None
        self.zoom_accum = 0.0
        self.fist_since = None
        self.fist_consumed = False
        self.offset = [0.0, 0.0]
        self.last_screen_pos = None
        self.frozen = False           # クリック準備中のカーソル固定
        self.freeze_since = None      # 固定開始時刻
        self.freeze_raw = None        # 固定開始時の生の写像位置（移動量の判定用）
        self.arm_suppressed = False   # 固定を自動解除した後、指が離れるまで再固定しない
        self.skeleton_prev = []       # オーバーレイ骨格の平滑化用（手ごとの前フレーム座標）
        self.noise_gain = 1.0         # 状況に応じた安定化の倍率（端・手の大きさで増える）
        self._single_allowed = True   # 手が1つのときの採用状態（左右判定のちらつき対策）
        self._allow_streak = 0
        self._ignored_since_first = 0.0   # 無視している手が見え始めた時刻（案内表示用）
        self._ignored_notice_shown = False
        self.status_text = ""
        self.status_until = 0.0

    # --- 部品の初期化 -------------------------------------------------
    def open_camera(self):
        cfg = self.cfg
        return CameraStream(cfg.camera_index, cfg.frame_width,
                            cfg.frame_height, cfg.camera_fps)

    def create_landmarker(self):
        cfg = self.cfg
        model_path = Path(cfg.model_path)
        if not model_path.is_absolute():
            model_path = ROOT / model_path
        if not model_path.exists():
            raise FileNotFoundError(
                f"モデルファイルがありません: {model_path}\n"
                "次のコマンドで取得してください:\n"
                "  python scripts/download_model.py"
            )
        options = vision.HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(model_path)),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=cfg.num_hands,
            min_hand_detection_confidence=cfg.min_detection_confidence,
            min_hand_presence_confidence=cfg.min_presence_confidence,
            min_tracking_confidence=cfg.min_tracking_confidence,
        )
        return vision.HandLandmarker.create_from_options(options)

    # --- 補助 ---------------------------------------------------------
    def notify(self, text, duration=2.0):
        """プレビュー下部に一時的なメッセージを出す。"""
        self.status_text = text
        self.status_until = time.monotonic() + duration
        print(text)

    def set_enabled(self, value):
        if value == self.enabled:
            return
        self.enabled = value
        if not value:
            self.mouse.release_all()
        self.filter.reset()
        self.offset = [0.0, 0.0]
        self.notify("マウス操作を有効にしました" if value else "マウス操作を無効にしました")

    def reset_state(self):
        self.recognizer.reset()
        self.filter.reset()
        self.mouse.release_all()
        self.offset = [0.0, 0.0]
        self.frozen = False
        self.prev_scroll_anchor = None
        self.prev_zoom_distance = None
        self.scroll_accum = 0.0
        self.zoom_accum = 0.0
        self.notify("トラッキング状態をリセットしました")

    def map_to_screen(self, nx, ny, clamp=True):
        """カメラ内の操作エリアを画面全体へ割り当てる（絶対座標）。

        clamp=False にすると画面外へはみ出した座標もそのまま返す
        （オーバーレイで手が画面端から切れて見えるようにするため）。
        """
        cfg = self.cfg
        span_x = max(1e-6, 1.0 - 2.0 * cfg.active_margin_x)
        span_y = max(1e-6, 1.0 - cfg.active_margin_top - cfg.active_margin_bottom)
        ax = (nx - cfg.active_margin_x) / span_x
        ay = (ny - cfg.active_margin_top) / span_y
        if clamp:
            ax, ay = clamp01(ax), clamp01(ay)
        return ax * (self.mouse.screen_w - 1), ay * (self.mouse.screen_h - 1)

    def hand_allowed(self, hand):
        """設定 use_hand に基づき、この手を操作に使うか（1フレームの判定）。

        MediaPipeの左右判定は鏡像入力を前提にしており、本アプリは検出前に
        フレームを鏡像化しているので、そのまま実際の左右に対応する。
        ラベルが無い手や信頼度の低い手（グーなど）は無視せず使う。
        """
        use = self.cfg.use_hand
        if use == "both" or not hand.handedness:
            return True
        if hand.handedness_score < self.cfg.handedness_min_score:
            return True
        label = hand.handedness.lower()
        if self.cfg.swap_handedness:
            label = "left" if label == "right" else "right"
        return label == use

    def select_hands(self, hands):
        """操作に使う手を選ぶ。手が1つのときは判定のちらつきを連続フレームで吸収する。"""
        if len(hands) != 1:
            self._allow_streak = 0
            return [h for h in hands if self.hand_allowed(h)]
        desired = self.hand_allowed(hands[0])
        if desired == self._single_allowed:
            self._allow_streak = 0
        else:
            self._allow_streak += 1
            if self._allow_streak >= self.cfg.handedness_switch_frames:
                self._single_allowed = desired
                self._allow_streak = 0
        return hands if self._single_allowed else []

    def hands_to_screen(self, hands, state):
        """オーバーレイ描画用に、各手の21点を画面座標へ変換する。

        既定では手を一定サイズ（overlay_hand_size）に正規化し、カーソル基準点が
        実際のカーソル位置に重なるように配置する。これでカメラとの距離に
        関係なく同じ大きさで描け、描かれた指先＝クリック位置になる。
        """
        cfg = self.cfg
        size = cfg.overlay_hand_size
        fw, fh = cfg.frame_width, cfg.frame_height
        points_list = self.smooth_skeleton(hands)
        result = []
        for i, hand in enumerate(hands):
            points = points_list[i]
            if size <= 0:
                result.append([self.map_to_screen(x, y, clamp=False) for (x, y) in points])
                continue
            # 主操作の手はカーソル基準点を実カーソル位置に合わせる。それ以外は生の写像位置。
            # 基準点は平滑化後の骨格から取り直す（生の座標を使うと骨格とリングがずれる）
            smoothed = G.Hand.from_points(points, hand.handedness)
            if i == 0 and state.cursor is not None and self.last_screen_pos is not None:
                anchor_norm = self.recognizer.cursor_point(smoothed, state.mode)
                anchor_px = self.last_screen_pos
            else:
                anchor_norm = smoothed.point(G.INDEX_TIP)
                anchor_px = self.map_to_screen(*anchor_norm, clamp=False)
            # 正規化座標はカメラの縦横で単位が違うので、いったんカメラ画素に戻して等方に拡縮する
            wx, wy = points[G.WRIST]
            mx, my = points[G.MIDDLE_MCP]
            palm_px = max(math.hypot((mx - wx) * fw, (my - wy) * fh), 1e-6)
            k = size / palm_px
            result.append([(anchor_px[0] + (x - anchor_norm[0]) * fw * k,
                            anchor_px[1] + (y - anchor_norm[1]) * fh * k)
                           for (x, y) in points])
        return result

    def smooth_skeleton(self, hands):
        """描画用に各手の21点を指数平滑化する（カーソルとは別系統）。

        生のランドマークは毎フレーム数px揺れるので、そのまま描くと手が震えて見える。
        操作には使わない表示専用の平滑化なので、遅延は気にせず強めにかける。
        """
        a = self.cfg.skeleton_smoothing
        if a >= 1.0:
            return [hand.points for hand in hands]
        if len(self.skeleton_prev) != len(hands):
            self.skeleton_prev = [list(hand.points) for hand in hands]
            return self.skeleton_prev
        out = []
        for prev, hand in zip(self.skeleton_prev, hands):
            cur = [(px + (x - px) * a, py + (y - py) * a)
                   for (px, py), (x, y) in zip(prev, hand.points)]
            out.append(cur)
        self.skeleton_prev = out
        return out

    # --- ジェスチャーの適用 -------------------------------------------
    def update_noise_gain(self, state):
        """状況に応じて安定化の強さを決める。

        - フレーム端に近いほど（edge_factor）: MediaPipeの切り出し領域がはみ出して
          ランドマークが荒れるので、不感帯を広げ平滑化を強める
        - 手が大きく映るほど（scale / reference_palm_size）: ブレの絶対量が増えるので同様
        """
        cfg = self.cfg
        gain = 1.0
        if state.hands:
            size_ratio = state.hands[0].scale / max(cfg.reference_palm_size, 1e-6)
            # 小さく映るときに弱めることはしない（基準より大きいときだけ強める）
            gain *= max(1.0, min(2.0, size_ratio))
        gain *= 1.0 + cfg.edge_stabilizer_boost * state.edge_factor
        self.noise_gain = gain
        self.filter.set_min_cutoff(cfg.filter_min_cutoff * (1.0 - 0.6 * state.edge_factor))

    def apply_cursor(self, cursor, now, dt):
        """カーソル基準点を画面座標へ変換し、平滑化・安定化して移動する。"""
        raw_x, raw_y = self.map_to_screen(*cursor)
        pos_x = raw_x + self.offset[0]
        pos_y = raw_y + self.offset[1]
        sx, sy = self.filter(pos_x, pos_y, now)
        sx, sy = self.stabilize(sx, sy)
        self.last_screen_pos = (sx, sy)
        if self.enabled:
            self.mouse.move_to(sx, sy)
        return raw_x, raw_y

    def stabilize(self, x, y):
        """不感帯つきの追従（糸で引っ張るモデル）。

        現在のカーソルから半径R以内の揺れは無視し、外に出た分だけカーソルを
        引き寄せる。静止時のブレを消しつつ、大きく動かすときの遅れは半径分だけで済む。
        半径は update_noise_gain() が状況に応じて増減させる。
        """
        r = self.cfg.stabilizer_radius * self.noise_gain
        if r <= 0 or self.last_screen_pos is None:
            return x, y
        cx, cy = self.last_screen_pos
        dx, dy = x - cx, y - cy
        d = math.hypot(dx, dy)
        if d <= r:
            return cx, cy
        k = (d - r) / d
        return cx + dx * k, cy + dy * k

    def decay_offset(self, dt):
        """ドラッグ終了後、ずらしたオフセットを滑らかに戻す。"""
        k = math.exp(-dt / OFFSET_DECAY_TAU)
        self.offset[0] *= k
        self.offset[1] *= k
        if abs(self.offset[0]) < 0.5:
            self.offset[0] = 0.0
        if abs(self.offset[1]) < 0.5:
            self.offset[1] = 0.0

    def reanchor(self, cursor_norm):
        """基準点が変わっても現在のカーソル位置から連続するようオフセットを取り直す。

        ピンチ成立（指先→指の中点）や、カーソル固定の解除のときに呼ぶ。
        """
        if self.last_screen_pos is None:
            return
        raw_x, raw_y = self.map_to_screen(*cursor_norm)
        self.offset[0] = self.last_screen_pos[0] - raw_x
        self.offset[1] = self.last_screen_pos[1] - raw_y
        self.filter.reset()

    def handle_scroll(self, anchor):
        """手の上下移動をホイール回転に変換する。"""
        if self.prev_scroll_anchor is None:
            self.prev_scroll_anchor = anchor
            return
        delta = self.prev_scroll_anchor - anchor  # 上に動かすと正
        self.prev_scroll_anchor = anchor
        if abs(delta) < self.cfg.scroll_dead_zone:
            return
        self.scroll_accum += delta * self.cfg.scroll_gain
        notches = int(self.scroll_accum)
        if notches and self.enabled:
            self.mouse.scroll(notches)
        self.scroll_accum -= notches

    def handle_zoom(self, distance):
        """両手の間隔の変化をCtrl+ホイールに変換する。"""
        if self.prev_zoom_distance is None:
            self.prev_zoom_distance = distance
            return
        delta = distance - self.prev_zoom_distance  # 広げると正（拡大）
        self.prev_zoom_distance = distance
        if abs(delta) < self.cfg.zoom_dead_zone:
            return
        self.zoom_accum += delta * self.cfg.zoom_gain
        notches = int(self.zoom_accum)
        if notches and self.enabled:
            self.mouse.zoom(notches)
        self.zoom_accum -= notches

    def handle_fist(self, mode, now):
        """グーを一定時間保持したら有効／無効をトグルする。"""
        if mode != G.MODE_FIST:
            self.fist_since = None
            self.fist_consumed = False
            return
        if self.fist_since is None:
            self.fist_since = now
            return
        if not self.fist_consumed and now - self.fist_since >= self.cfg.fist_toggle_sec:
            self.fist_consumed = True
            self.set_enabled(not self.enabled)

    def process(self, state, now, dt):
        """判定結果をマウス操作へ反映する。"""
        mode = state.mode
        entered = mode != self.prev_mode

        self.handle_fist(mode, now)
        self.update_noise_gain(state)

        # 手を見失って復帰したときは、直前のカーソル位置から滑らかにつなぐ
        # （フレーム端で検出が途切れるたびに生の位置へ飛ぶのを防ぐ）
        if (entered and self.prev_mode in (G.MODE_IDLE, G.MODE_NONE)
                and state.cursor is not None and self.last_screen_pos is not None):
            self.reanchor(state.cursor)

        if mode != G.MODE_LEFT:
            self.mouse.release_left()
        if mode != G.MODE_SCROLL:
            self.prev_scroll_anchor = None
            self.scroll_accum = 0.0
        if mode != G.MODE_ZOOM:
            self.prev_zoom_distance = None
            self.zoom_accum = 0.0

        if mode == G.MODE_POINT:
            self.decay_offset(dt)
            if not state.arming:
                self.arm_suppressed = False
            want_freeze = (state.arming and not self.arm_suppressed
                           and self.last_screen_pos is not None)
            if want_freeze and self.frozen:
                # 固定中に手が大きく動いた／時間切れなら、クリックではないとみなして解除
                raw = self.map_to_screen(*state.cursor)
                moved = math.hypot(raw[0] - self.freeze_raw[0], raw[1] - self.freeze_raw[1])
                if moved > self.cfg.arm_cancel_px or now - self.freeze_since > self.cfg.arm_timeout_sec:
                    want_freeze = False
                    self.arm_suppressed = True
            if want_freeze:
                if not self.frozen:
                    # 親指が近づいてきた瞬間にカーソルを固定し、ピンチ動作によるズレを防ぐ
                    self.frozen = True
                    self.freeze_since = now
                    self.freeze_raw = self.map_to_screen(*state.cursor)
            else:
                if self.frozen:
                    self.reanchor(state.cursor)
                    self.frozen = False
                self.apply_cursor(state.cursor, now, dt)

        elif mode == G.MODE_LEFT:
            if entered:
                # 固定位置／指先から「指の中点」へ基準点が変わるので、飛ばないように継ぎ直す
                self.reanchor(state.cursor)
            self.frozen = False
            self.apply_cursor(state.cursor, now, dt)
            if self.enabled:
                self.mouse.press_left()

        elif mode == G.MODE_RIGHT:
            if entered:
                self.reanchor(state.cursor)
            self.frozen = False
            self.decay_offset(dt)
            self.apply_cursor(state.cursor, now, dt)
            if entered and self.enabled:
                self.mouse.click_right()

        elif mode == G.MODE_SCROLL:
            self.handle_scroll(state.scroll_anchor)

        elif mode == G.MODE_ZOOM:
            self.handle_zoom(state.zoom_distance)

        else:
            # 手が無い／グー／待機のときはカーソルを動かさない
            self.frozen = False
            self.decay_offset(dt)
            if mode == G.MODE_IDLE:
                self.filter.reset()

        self.prev_mode = mode

    # --- 入力処理 -----------------------------------------------------
    def handle_keys(self):
        key = cv2.waitKey(1) & 0xFF
        if key in (27, ord("q")):
            self.running = False
        elif key == 32:
            self.set_enabled(not self.enabled)
        elif key in (ord("r"), ord("R")):
            self.reset_state()

    def handle_hotkeys(self):
        for name in self.hotkeys.poll():
            if name == "quit":
                self.running = False
            elif name == "toggle":
                self.set_enabled(not self.enabled)
            elif name == "reset":
                self.reset_state()

    # --- メインループ -------------------------------------------------
    def run(self):
        cap = self.open_camera()
        landmarker = self.create_landmarker()
        self.hotkeys.register("toggle", VK_H)
        self.hotkeys.register("quit", VK_Q)
        self.hotkeys.register("reset", VK_R)

        display = self.cfg.display_mode if self.cfg.display_mode in DISPLAY_MODES else "overlay"
        use_preview = display == "preview"
        overlay = None
        if use_preview:
            cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_AUTOSIZE)
            try:
                cv2.setWindowProperty(WINDOW_NAME, cv2.WND_PROP_TOPMOST, 1)
            except cv2.error:
                pass
        elif display == "overlay":
            overlay = HandOverlay(self.mouse.screen_w, self.mouse.screen_h,
                                  self.cfg.overlay_alpha)

        print(f"画面解像度: {self.mouse.screen_w}x{self.mouse.screen_h} / 表示: {display}")
        print("Ctrl+Alt+H:有効切替 / Ctrl+Alt+R:リセット / Ctrl+Alt+Q:終了（どこからでも有効）")
        if use_preview:
            print("プレビュー表示中は Space / R / Esc も使えます。")
        if not self.enabled:
            print("※ 安全のため操作は無効状態で起動しました。Ctrl+Alt+H で開始します。")

        last_time = time.monotonic()
        last_timestamp_ms = -1
        frame_id = 0
        timeouts = 0

        try:
            while self.running:
                frame_id, frame = cap.read(frame_id)
                if frame is None:
                    timeouts += 1
                    print(f"カメラのフレーム取得に失敗しました（{timeouts}回目）")
                    if timeouts >= 5:
                        print("カメラから読み取れないため終了します。")
                        break
                    self.handle_hotkeys()
                    continue
                timeouts = 0

                # 鏡像にして、手の動きと画面の動きを一致させる
                frame = cv2.flip(frame, 1)
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

                now = time.monotonic()
                dt = max(now - last_time, 1e-3)
                last_time = now
                self.fps = self.fps * 0.9 + (1.0 / dt) * 0.1

                # 単調増加するタイムスタンプが必要
                timestamp_ms = max(int(now * 1000), last_timestamp_ms + 1)
                last_timestamp_ms = timestamp_ms

                result = landmarker.detect_for_video(mp_image, timestamp_ms)
                hands = []
                for i, landmarks in enumerate(result.hand_landmarks):
                    label, score = "", 1.0
                    if i < len(result.handedness) and result.handedness[i]:
                        label = result.handedness[i][0].category_name
                        score = result.handedness[i][0].score
                    hands.append(G.Hand(landmarks, label, score))

                # 設定で使わない手（既定では左手）は操作にも描画にも使わない
                active_hands = self.select_hands(hands)
                ignored_only = bool(hands) and not active_hands
                ignored_label = ""
                if ignored_only:
                    h = hands[0]
                    side = {"left": "左手", "right": "右手"}.get(h.handedness.lower(), "不明")
                    ignored_label = f"{side}と判定（信頼度 {h.handedness_score:.2f}）→ 無視中"
                    if self._ignored_since_first == 0.0:
                        self._ignored_since_first = now
                    # 1.5秒以上無視し続けたら、コンソールにも対処法を一度だけ出す
                    if (not self._ignored_notice_shown
                            and now - self._ignored_since_first > 1.5):
                        self._ignored_notice_shown = True
                        print(f"検出した手を「{side}」と判定して無視しています（設定 use_hand={self.cfg.use_hand}）。"
                              "これが実際の右手なら左右判定が逆です。"
                              "--swap-hands を付けて起動するか、設定 swap_handedness を true にしてください。")
                else:
                    self._ignored_since_first = 0.0

                state = self.recognizer.update(active_hands)
                self.process(state, now, dt)

                status = self.status_text if now < self.status_until else ""
                if use_preview:
                    view = render_hud(frame, self.renderer, self.cfg, state,
                                      self.enabled, self.fps, status)
                    cv2.imshow(WINDOW_NAME, view)
                    if cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
                        break
                    self.handle_keys()
                elif overlay is not None:
                    if status:
                        hint = status
                    elif self.fist_since is not None and not self.fist_consumed:
                        # 保持時間が長いので、あと何秒かを見せる
                        held = now - self.fist_since
                        hint = f"グー保持中 {held:.1f} / {self.cfg.fist_toggle_sec:.1f} 秒"
                    elif ignored_only:
                        hint = (f"{'右' if self.cfg.use_hand == 'right' else '左'}手だけを使います"
                                f"（{ignored_label}）")
                    elif state.near_edge:
                        hint = "手がカメラの端に近いです"
                    elif self.enabled:
                        hint = ""
                    elif not state.hands:
                        # 閉じた手は検出されにくいので、まず開いた手を見せてもらう
                        hint = "手を開いてカメラに見せてください"
                    else:
                        hint = "グーを3秒保持 または Ctrl+Alt+H で開始"
                    overlay.render(self.hands_to_screen(state.hands, state),
                                   self.last_screen_pos, state, self.enabled, hint)
                    overlay.update()
                    if overlay.closed:
                        break

                self.handle_hotkeys()
        except KeyboardInterrupt:
            print("中断しました。")
        finally:
            self.mouse.release_all()
            self.hotkeys.unregister_all()
            if overlay is not None:
                overlay.close()
            landmarker.close()
            cap.release()
            cv2.destroyAllWindows()
            print("終了しました。")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Webカメラのハンドトラッキングでマウスを操作する")
    parser.add_argument("--camera", type=int, help="カメラ番号（既定は設定ファイルの値）")
    parser.add_argument("--config", default=str(CONFIG_PATH), help="設定JSONのパス")
    parser.add_argument("--enable", action="store_true",
                        help="起動直後からマウス操作を有効にする")
    parser.add_argument("--display", choices=DISPLAY_MODES,
                        help="表示方法: overlay=手の骨格だけを透過表示（既定） / "
                             "preview=カメラ映像ウィンドウ / none=非表示")
    parser.add_argument("--no-preview", action="store_true",
                        help="--display none と同じ（互換用）")
    parser.add_argument("--hand", choices=("right", "left", "both"),
                        help="操作に使う手（既定は設定ファイルの値。初期値は right）")
    parser.add_argument("--swap-hands", action="store_true",
                        help="左右の判定が逆になる環境で、判定を入れ替える")
    return parser.parse_args()


def main():
    args = parse_args()
    cfg = Config.load(args.config)
    if args.camera is not None:
        cfg.camera_index = args.camera
    if args.enable:
        cfg.enable_on_start = True
    if args.display:
        cfg.display_mode = args.display
    if args.no_preview:
        cfg.display_mode = "none"
    if args.hand:
        cfg.use_hand = args.hand
    if args.swap_hands:
        cfg.swap_handedness = True

    enable_dpi_awareness()

    try:
        app = HandMouseApp(cfg)
        app.run()
    except (RuntimeError, FileNotFoundError) as e:
        print(f"起動できませんでした: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
