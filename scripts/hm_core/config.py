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
    min_detection_confidence: float = 0.6
    min_presence_confidence: float = 0.5
    min_tracking_confidence: float = 0.5

    # --- 操作エリア（カメラ画像の端は使わない。値は正規化座標の余白）---
    active_margin_x: float = 0.18
    active_margin_y: float = 0.14

    # --- カーソル平滑化（One Euro Filter）---
    filter_min_cutoff: float = 0.6
    filter_beta: float = 0.005
    filter_d_cutoff: float = 1.0
    # スタビライザー: この半径[px]以内の揺れは無視し、超えた分だけカーソルが引っ張られる
    stabilizer_radius: float = 10.0
    # オーバーレイの骨格の平滑化係数（0〜1。小さいほど滑らか、1で平滑化なし）
    skeleton_smoothing: float = 0.35

    # --- ピンチ判定（手の大きさで正規化した指先間距離。ヒステリシス付き）---
    pinch_on: float = 0.45
    pinch_off: float = 0.62
    # 親指が人差し指へこの距離まで「近づいてきたら」カーソルを固定し、クリック位置のズレを防ぐ
    # （0で無効。最初から近い姿勢では発火しない）
    pinch_arm: float = 0.7
    # 固定中に手がこれ以上[px]動いたら、クリックではないとみなして固定を解除
    arm_cancel_px: float = 30.0
    # 固定してからこの秒数ピンチが成立しなければ解除
    arm_timeout_sec: float = 1.0

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
    fist_toggle_sec: float = 0.8

    # --- 安全マージン（画面端に張り付かせない）[px] ---
    screen_margin_px: int = 2

    # --- 起動時からマウス操作を有効にするか（既定は安全のため無効）---
    enable_on_start: bool = False

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
