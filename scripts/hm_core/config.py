# -*- coding: utf-8 -*-
"""動作設定。JSONファイルで上書きできる。"""

import json
from dataclasses import dataclass, asdict, fields
from pathlib import Path


@dataclass
class Config:
    # --- カメラ ---
    camera_index: int = 0
    frame_width: int = 640
    frame_height: int = 480
    camera_fps: int = 30

    # --- 検出 ---
    model_path: str = "models/hand_landmarker.task"
    num_hands: int = 2
    # グーのような閉じた手は検出されにくいので、しきい値は控えめにする
    min_detection_confidence: float = 0.5
    min_presence_confidence: float = 0.4
    min_tracking_confidence: float = 0.5

    # --- 操作エリア（カメラ画像の端は使わない。値は正規化座標の余白）---
    # 上下は非対称にする。基準点（手のひら中心）より下に手首があるため、下の余白を
    # 大きく取らないと画面の一番下を狙うときに手がフレームから切れて検出が不安定になる
    # 上も同様に、基準点より上に指（手のひら長の約1.3倍）があるので、その分の余白が必要。
    # 詰めすぎると画面上端を狙うときに指先がフレーム外に出て、ピンチ判定が効かなくなる
    active_margin_x: float = 0.18
    active_margin_top: float = 0.26
    active_margin_bottom: float = 0.32
    # カーソル感度。1.0 で上の余白どおり。小さくすると操作エリアが広がり、同じ画面幅に
    # 対して手を大きく動かす必要がある（＝カーソルがゆっくりになる）。
    # 広げてもフレーム端に寄り過ぎないよう、余白は下の最小値で止める
    cursor_gain: float = 1.0
    min_margin_x: float = 0.05
    min_margin_top: float = 0.24
    min_margin_bottom: float = 0.25
    # 上の余白を「映っている手の大きさ」から自動で決める（手のひら長 × finger_reach_factor ＋ pad）。
    # 手が大きく映るほど指先が上にはみ出しやすいので、その分だけ上端を下げる
    adaptive_top_margin: bool = True
    finger_reach_factor: float = 1.6
    adaptive_margin_pad: float = 0.04
    # 手のひらの点がこの距離までフレーム端に近づいたら警告を表示する
    edge_warn_margin: float = 0.06
    # フレーム端からこの範囲に入ると、近いほど安定化を強める（0で無効）
    edge_zone: float = 0.15
    # 端に完全に寄ったときにスタビライザー半径を何倍増やすか（1.5 → 2.5倍）
    edge_stabilizer_boost: float = 1.5
    # 手のひら長（正規化座標）の基準。これより大きく映るほどブレが増えるので安定化を強める
    reference_palm_size: float = 0.15

    # --- カーソル平滑化（One Euro Filter）---
    filter_min_cutoff: float = 0.35
    filter_beta: float = 0.0015
    filter_d_cutoff: float = 1.0
    # スタビライザー: この半径[px]以内の揺れは無視し、超えた分だけカーソルが引っ張られる
    stabilizer_radius: float = 12.0
    # オーバーレイの骨格の平滑化係数（0〜1。小さいほど滑らか、1で平滑化なし）
    skeleton_smoothing: float = 0.25

    # --- ピンチ判定（手の大きさで正規化した指先間距離。ヒステリシス付き）---
    pinch_on: float = 0.40
    pinch_off: float = 0.62
    # ピンチが成立と判定されるまでに必要な連続フレーム数（1フレームのノイズを捨てる）
    pinch_confirm_frames: int = 2
    # 左クリックは「親指が一度 pinch_arm より離れてから近づいた」ときだけ受け付ける
    # （最初から指が近い姿勢での誤クリックを防ぐ。false で従来どおり距離のみで判定）
    pinch_require_approach: bool = True
    # カーソル固定（クリック準備）のやり方
    #   approach : 親指が人差し指へ近づいてきたら自動で固定（既定）
    #   middle   : 親指＋中指をつまんでいる間だけ固定。左クリックは固定中の親指＋人差し指のみ
    freeze_gesture: str = "approach"
    # 中指ピンチ固定の判定（つまむと中指が曲がるので、クリックより緩い条件にする）
    lock_pinch_on: float = 0.55      # 固定開始の距離（手の大きさで正規化）
    lock_pinch_off: float = 0.75     # 固定解除の距離（lock_hold_sec=0 のとき）／次の固定を許す距離
    # 固定をこの秒数で自動解除する（親指が離れても解除しない「固定窓」）。
    # 0 にすると従来どおり親指＋中指をつまんでいる間だけ固定
    lock_hold_sec: float = 1.5
    # 固定が切れた後、親指が中指からこの距離以上離れたら次の固定を始められる
    # （力を抜いた手でも届く値にしておく。lock_pinch_on より少し大きい程度）
    lock_rearm_distance: float = 0.60
    # 固定中の左クリックは「人差し指が一度 lock_click_release 以上離れてから
    # lock_click_on 未満まで親指に近づいた」ときだけ（固定時から触れている人差し指では発火しない）
    lock_click_on: float = 0.25
    lock_click_release: float = 0.30
    # 固定中の2回タップをダブルクリックとみなす間隔[秒]。OSのダブルクリック時間（既定0.5秒）より
    # 長い場合は、2回目のときにクリックを補ってOS側でも確実にダブルクリックにする
    double_click_sec: float = 0.8
    lock_finger_reach: float = 0.60  # 中指の曲がりの許容（指先が第二関節×この値より遠ければ可）
    lock_index_ratio: float = 1.50   # 固定開始は「中指距離 < 人差し指距離×この値」のときだけ（人差し指は中指の隣なので余裕を持たせる）
    # 固定をこの秒数続けると左ボタンを押した状態になり、そのまま動かすとドラッグ／範囲選択
    # （0 で無効。lock_hold_sec より短いときだけ意味がある）
    lock_drag_sec: float = 0.0
    # 親指＋人差し指をつまんだまま動かしたときにドラッグするか（false なら押して離すクリックのみ）
    left_drag_enabled: bool = True
    # 固定を離した後もこの秒数は固定位置を保ち、その間の
    # 親指＋薬指（右クリック）／親指＋人差し指（左クリック）を受け付ける
    lock_grace_sec: float = 1.5
    # 右クリックの指の曲がりの許容（指先が第二関節×この値より遠ければ可）
    right_finger_reach: float = 0.85
    # 親指が人差し指へこの距離まで「近づいてきたら」カーソルを固定し、クリック位置のズレを防ぐ
    # （0で無効。最初から近い姿勢では発火しない）
    pinch_arm: float = 0.7
    # 固定中に手がこれ以上[px]動いたら、クリックではないとみなして固定を解除
    arm_cancel_px: float = 30.0
    # 固定してからこの秒数ピンチが成立しなければ解除
    arm_timeout_sec: float = 1.0

    # --- 操作に使う手: right / left / both（both 以外では両手ズームは使えない）---
    use_hand: str = "right"
    # 左右の判定が逆になる環境（カメラが鏡像でない等）では true にする
    swap_handedness: bool = False
    # 左右判定の信頼度がこれ未満なら「不明」として無視しない（グーは判定が不安定）
    handedness_min_score: float = 0.8
    # 手が1つのとき、採用／無視を切り替えるまでに必要な連続フレーム数（判定のちらつき対策）
    handedness_switch_frames: int = 6

    # --- 右クリックに使う指（親指とつまむ指）: ring / middle / pinky ---
    right_click_finger: str = "ring"

    # --- カーソルの基準点 ---
    #   palm      : 手のひら中心（既定。5点平均でブレが最小、ピンチしても動かない）
    #   index_mcp : 人差し指の付け根（安定。手のひらより指先寄り）
    #   index_tip : 人差し指の先（狙いやすいがブレが大きく、ピンチ時に動く）
    cursor_landmark: str = "palm"

    # --- スクロール ---
    scroll_gain: float = 14.0
    scroll_dead_zone: float = 0.004

    # --- ズーム（両手ピンチ間の距離変化）---
    zoom_gain: float = 22.0
    zoom_dead_zone: float = 0.006

    # --- グー（握り拳）で有効/無効をトグルする保持時間[秒] ---
    fist_toggle_sec: float = 2.0
    # 手がカメラから消えてこの秒数経ったら操作を無効にする（0で無効化しない）
    idle_disable_sec: float = 3.0

    # --- 安全マージン（画面端に張り付かせない）[px] ---
    screen_margin_px: int = 2

    # --- 起動時からマウス操作を有効にするか（既定は安全のため無効）---
    enable_on_start: bool = False

    # --- 判定値の表示（しきい値調整用。--debug でも有効化できる）---
    debug_hud: bool = False

    # --- 表示方法 ---
    #   overlay : デスクトップ上に手の骨格だけを透過表示（既定）
    #   preview : カメラ映像のウィンドウを表示（調整・デバッグ用）
    #   none    : 何も表示しない（ホットキーのみで操作）
    display_mode: str = "overlay"
    # オーバーレイの不透明度（0.0〜1.0）
    overlay_alpha: float = 0.85
    # オーバーレイの手の大きさ（手のひら＝手首〜中指付け根の長さ[px]）。
    # カメラとの距離に関係なく一定サイズで描く。0にすると生の写像で描く
    overlay_hand_size: int = 70

    def active_area(self, palm_size=None):
        """cursor_gain を反映した操作エリア (x0, y0, x1, y1) を正規化座標で返す。

        余白で決まる範囲を中心はそのままに 1/cursor_gain 倍に広げ（縮め）、
        フレーム端に寄り過ぎないよう各余白の最小値で止める。
        palm_size（映っている手のひら長、正規化座標）を渡すと、指先がフレーム外に
        出ない高さまで上端を下げる（adaptive_top_margin）。
        """
        gain = max(0.3, float(self.cursor_gain))

        def expand(lo, hi, min_lo, min_hi):
            span = 1.0 - lo - hi
            center = lo + span / 2.0
            new_span = span / gain
            new_lo = max(center - new_span / 2.0, min_lo)
            new_hi = max(1.0 - (center + new_span / 2.0), min_hi)
            return new_lo, 1.0 - new_hi

        x0, x1 = expand(self.active_margin_x, self.active_margin_x,
                        self.min_margin_x, self.min_margin_x)
        y0, y1 = expand(self.active_margin_top, self.active_margin_bottom,
                        self.min_margin_top, self.min_margin_bottom)
        if self.adaptive_top_margin and palm_size:
            need = palm_size * self.finger_reach_factor + self.adaptive_margin_pad
            # 上端を下げすぎてエリアが潰れないよう、高さは最低 0.15 残す
            y0 = max(y0, min(need, y1 - 0.15))
        return x0, y0, x1, y1

    @classmethod
    def load(cls, path):
        """JSON設定を読み込む。存在しなければ既定値で新規作成する。"""
        path = Path(path)
        cfg = cls()
        if not path.exists():
            cfg.save(path)
            return cfg
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print(f"設定ファイルを読み込めないため既定値を使います: {path} ({e})")
            return cfg

        known = {f.name for f in fields(cls)}
        for key, value in data.items():
            if key in known:
                setattr(cfg, key, value)
            else:
                print(f"未知の設定項目は無視します: {key}")
        return cfg

    def save(self, path):
        """現在の設定をJSONに保存する。"""
        path = Path(path)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", encoding="utf-8") as f:
                json.dump(asdict(self), f, ensure_ascii=False, indent=2)
        except OSError as e:
            print(f"設定ファイルを保存できませんでした: {path} ({e})")
