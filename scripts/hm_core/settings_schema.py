# -*- coding: utf-8 -*-
"""設定画面に出す項目の定義（ラベル・説明・入力の種類と範囲）。

Config のフィールドをどのタブにどう見せるかだけを持つ。値そのものは Config が持つ。
ここに書き忘れたフィールドは設定画面の「その他」タブに自動で並ぶので、
Config にフィールドを足しても編集できなくなることはない。
"""

from dataclasses import dataclass, fields


@dataclass
class Item:
    """設定1項目の見せ方。"""
    name: str                 # Config のフィールド名
    label: str                # 画面に出す名前
    desc: str = ""            # 画面に出す説明
    kind: str = "float"       # float / int / bool / choice / text
    lo: float = 0.0           # スライダーの下限
    hi: float = 1.0           # スライダーの上限
    step: float = 0.01        # 刻み
    choices: tuple = ()       # kind="choice" のときの選択肢
    restart: bool = False     # 再起動しないと反映されない項目


# 最初のタブ。他のタブにもある項目を再掲する（同じ項目なので値は連動する）
COMMON = (
    "cursor_gain", "stabilizer_radius", "filter_min_cutoff",
    "use_hand", "swap_handedness", "right_click_finger",
    "freeze_gesture", "pinch_on", "left_drag_enabled",
    "overlay_alpha", "overlay_hand_size",
    "fist_toggle_sec", "idle_disable_sec",
    "camera_index", "display_mode", "enable_on_start",
)

ITEMS = (
    # --- カメラ・検出 ---
    Item("camera_index", "カメラ番号", "使うWebカメラ。内蔵カメラが0。外付けを使うなら1や2を試す。",
         "int", 0, 8, 1, restart=True),
    Item("frame_width", "映像の幅[px]", "カメラから取り込む解像度。上げると検出は安定するが重くなる。",
         "int", 320, 1920, 160, restart=True),
    Item("frame_height", "映像の高さ[px]", "カメラから取り込む解像度。幅と縦横比を合わせる。",
         "int", 240, 1080, 120, restart=True),
    Item("camera_fps", "カメラのFPS", "要求するフレームレート。暗い場所では実際には出ない（露光が延びるため）。",
         "int", 5, 60, 5, restart=True),
    Item("model_path", "モデルのパス", "MediaPipeの検出モデル。通常は変更しない。",
         "text", restart=True),
    Item("num_hands", "検出する手の数", "1にすると少し軽くなる（両手ズームは使えなくなる）。",
         "int", 1, 4, 1, restart=True),
    Item("min_detection_confidence", "検出の信頼度", "手を新しく見つけるときのしきい値。下げると見つけやすいが誤検出が増える。",
         "float", 0.1, 0.9, 0.05, restart=True),
    Item("min_presence_confidence", "存在の信頼度", "手がそこにあると見なすしきい値。グーは判定が不安定なので低めにしてある。",
         "float", 0.1, 0.9, 0.05, restart=True),
    Item("min_tracking_confidence", "追跡の信頼度", "見つけた手を追い続けるしきい値。",
         "float", 0.1, 0.9, 0.05, restart=True),

    # --- 操作エリア・感度 ---
    Item("cursor_gain", "カーソル感度",
         "小さくするとカーソルがゆっくりになる（操作エリアが広がり、手を大きく動かす必要がある）。"
         "下の余白の下限まで広がると、それ以上下げても変わらない。",
         "float", 0.1, 2.0, 0.05),
    Item("active_margin_x", "操作エリアの左右余白",
         "カメラ映像の左右で使わない範囲。小さくすると手の移動量が減るが、画面の端が使いにくくなる。",
         "float", 0.0, 0.4, 0.01),
    Item("active_margin_top", "操作エリアの上余白",
         "基準点（手のひら中心）より上に指があるぶんの余白。詰めると画面上端を狙うときに指先がフレームから切れ、ピンチが効かなくなる。",
         "float", 0.0, 0.45, 0.01),
    Item("active_margin_bottom", "操作エリアの下余白",
         "基準点より下に手首があるぶんの余白。詰めると画面下端を狙うときに手首が切れて検出が不安定になる。",
         "float", 0.0, 0.45, 0.01),
    Item("min_margin_x", "左右余白の下限",
         "感度を下げてエリアを広げるときに、これ以上フレーム端へ寄せない下限。"
         "感度を下げても変わらないときはここを下げる（下げすぎると端で検出が荒れる）。",
         "float", 0.0, 0.3, 0.01),
    Item("min_margin_top", "上余白の下限",
         "同上（上端）。ただし「上余白を自動調整」が入っていると、そちらが優先されることが多い。",
         "float", 0.0, 0.4, 0.01),
    Item("min_margin_bottom", "下余白の下限",
         "同上（下端）。下げすぎると画面下端を狙うときに手首がフレームから切れる。",
         "float", 0.0, 0.4, 0.01),
    Item("adaptive_top_margin", "上余白を自動調整",
         "映っている手の大きさから上の余白を決める。手が大きく映る環境でも指先が映像内に収まる。",
         "bool"),
    Item("finger_reach_factor", "指の長さの見積り",
         "手のひら長の何倍を指の高さとみなすか（上余白の自動調整に使う）。",
         "float", 1.0, 2.5, 0.05),
    Item("adaptive_margin_pad", "自動調整の追加余白", "上余白の自動調整にさらに足す余白。",
         "float", 0.0, 0.2, 0.01),
    Item("edge_warn_margin", "端の警告距離",
         "手がフレーム端にこれだけ近づくと「端に寄っています」と警告する。",
         "float", 0.0, 0.2, 0.01),
    Item("edge_zone", "端で安定化する範囲",
         "フレーム端からこの範囲に入ると、近いほど手ブレ対策を強める。0で無効。",
         "float", 0.0, 0.4, 0.01),
    Item("edge_stabilizer_boost", "端での安定化の強さ",
         "端に寄り切ったときに不感帯を何倍増やすか（1.5なら最大2.5倍）。",
         "float", 0.0, 3.0, 0.1),
    Item("reference_palm_size", "手の大きさの基準",
         "手のひら長がこれより大きく映るほど（＝カメラに近いほど）安定化を強める。",
         "float", 0.05, 0.4, 0.01),

    # --- カーソルの安定化 ---
    Item("cursor_landmark", "カーソルの基準点",
         "palm=手のひら中心（最も安定）/ index_mcp=人差し指の付け根 / index_tip=指先（狙いやすいがブレる）。",
         "choice", choices=("palm", "index_mcp", "index_tip")),
    Item("stabilizer_radius", "不感帯の半径[px]",
         "この範囲内の揺れは無視する。震えが残るなら18前後に、反応が鈍いなら6前後に。",
         "float", 0.0, 40.0, 1.0),
    Item("filter_min_cutoff", "平滑化の強さ",
         "小さいほど滑らかになるが、遅れが増える。",
         "float", 0.05, 2.0, 0.05),
    Item("filter_beta", "速い動きへの追従",
         "大きくするほど、速く動かしたときの遅れが減る（そのぶん細かい揺れは残る）。",
         "float", 0.0, 0.02, 0.0005),
    Item("filter_d_cutoff", "速度の平滑化", "速度推定の平滑化。通常は変更しない。",
         "float", 0.1, 5.0, 0.1),
    Item("skeleton_smoothing", "骨格表示の滑らかさ",
         "画面に描く手の平滑化（小さいほど滑らか）。表示だけで、操作には影響しない。",
         "float", 0.05, 1.0, 0.05),

    # --- クリック・ピンチ ---
    Item("pinch_on", "クリック成立の距離",
         "親指と人差し指がこの距離まで近づいたらクリック（手の大きさで正規化）。誤クリックが多ければ下げる。",
         "float", 0.1, 1.0, 0.01),
    Item("pinch_off", "クリック解除の距離",
         "この距離まで離れたらクリックを離す。成立の距離より大きくする（チャタリング防止）。",
         "float", 0.1, 1.2, 0.01),
    Item("pinch_confirm_frames", "クリック確定のフレーム数",
         "この連続フレーム数だけ閉じていたらクリックを確定する（1フレームのノイズを捨てる）。",
         "int", 1, 10, 1),
    Item("pinch_require_approach", "近づいたときだけクリック",
         "親指が一度離れてから近づいたときだけ左クリックする。最初から指が近い姿勢での誤クリックを防ぐ。",
         "bool"),
    Item("left_drag_enabled", "ドラッグを使う",
         "つまんだまま動かしたときにドラッグする。オフなら「押して離す」クリックのみ。",
         "bool"),
    Item("right_click_finger", "右クリックの指",
         "親指とつまむ指。ring=薬指 / middle=中指 / pinky=小指。",
         "choice", choices=("ring", "middle", "pinky")),
    Item("right_finger_reach", "右クリックの指の伸び",
         "その指を握り込んでいないと見なす条件。厳しくすると誤発火が減る。",
         "float", 0.3, 1.2, 0.05),
    Item("pinch_arm", "カーソル固定を始める距離",
         "親指が人差し指へこの距離まで近づいたらカーソルを止め、クリック位置のズレを防ぐ。0で無効。",
         "float", 0.0, 1.2, 0.05),
    Item("arm_cancel_px", "固定を解除する移動量[px]",
         "カーソルを止めている間に手がこれ以上動いたら、クリックではないとみなして解除する。",
         "float", 5.0, 150.0, 5.0),
    Item("arm_timeout_sec", "固定を解除する時間[秒]",
         "止めてからこの秒数つまむ動作が来なければ解除する。",
         "float", 0.2, 5.0, 0.1),

    # --- 固定（中指ピンチ）---
    Item("freeze_gesture", "カーソル固定のやり方",
         "approach=親指が近づいたら自動で固定 / middle=親指＋中指をつまんでいる間だけ固定（誤クリックが最も少ない）。",
         "choice", choices=("approach", "middle")),
    Item("lock_pinch_on", "固定を始める距離", "親指と中指がこの距離まで近づいたら固定する。",
         "float", 0.1, 1.2, 0.05),
    Item("lock_pinch_off", "固定を解く距離", "この距離まで離れたら固定を解く（固定を続ける時間が0のとき）。",
         "float", 0.1, 1.5, 0.05),
    Item("lock_hold_sec", "固定を続ける時間[秒]",
         "つまんだ瞬間からこの秒数は親指が離れても固定が続き、自動で解除される。0で「つまんでいる間だけ」。",
         "float", 0.0, 5.0, 0.1),
    Item("lock_rearm_distance", "次に固定できる距離",
         "固定が切れた後、親指が中指からこれだけ離れたら次の固定を始められる。",
         "float", 0.1, 1.5, 0.05),
    Item("lock_click_on", "固定中のクリック距離",
         "固定中に人差し指がこの距離まで近づいたら左クリック。",
         "float", 0.05, 0.8, 0.01),
    Item("lock_click_release", "固定中のクリック解除距離",
         "固定中の左クリックは、人差し指が一度これだけ離れてから近づいたときに成立する。",
         "float", 0.05, 0.9, 0.01),
    Item("double_click_sec", "ダブルクリックの間隔[秒]",
         "固定中の2回タップをダブルクリックとみなす間隔。",
         "float", 0.2, 2.0, 0.1),
    Item("lock_finger_reach", "固定時の中指の曲がり",
         "中指をどこまで曲げても固定と認めるか（大きいほど厳しい）。つまむと中指は曲がるので緩めにしてある。",
         "float", 0.3, 1.2, 0.05),
    Item("lock_index_ratio", "隣の指との距離比",
         "中指の距離が人差し指・薬指の距離×この値より近いときだけ固定する。親指を人差し指や薬指に付けただけで固定しないようにする。",
         "float", 1.0, 3.0, 0.1),
    Item("lock_drag_sec", "固定からドラッグへ[秒]",
         "固定をこの秒数続けると左ボタンを押した状態になり、そのまま動かすと範囲選択になる。0で無効。",
         "float", 0.0, 5.0, 0.1),
    Item("lock_grace_sec", "固定を離した後の余韻[秒]",
         "固定を離した後もこの秒数は位置を保ち、その間のクリックを受け付ける。",
         "float", 0.0, 5.0, 0.1),

    # --- スクロール・ズーム ---
    Item("scroll_gain", "スクロールの量", "チョキを上下に動かしたときのスクロール量の倍率。",
         "float", 1.0, 40.0, 1.0),
    Item("scroll_dead_zone", "スクロールの不感帯", "この範囲の手の動きは無視する（静止時の誤スクロール防止）。",
         "float", 0.0, 0.05, 0.001),
    Item("zoom_gain", "ズームの量", "両手ピンチの間隔を変えたときのズーム量の倍率。",
         "float", 1.0, 60.0, 1.0),
    Item("zoom_dead_zone", "ズームの不感帯", "この範囲の間隔変化は無視する。",
         "float", 0.0, 0.05, 0.001),

    # --- 手の選択 ---
    Item("use_hand", "操作に使う手",
         "right=右手 / left=左手 / both=両手（両手ズームはbothのときだけ使える）。",
         "choice", choices=("right", "left", "both")),
    Item("swap_handedness", "左右の判定を入れ替える",
         "右手なのに反応しない（左手が反応する）ときにオンにする。Ctrl+Alt+Sでも切り替えられる。",
         "bool"),
    Item("handedness_min_score", "左右判定の信頼度",
         "これ未満の信頼度の手は「不明」として無視しない（グーは左右判定が不安定なため）。",
         "float", 0.0, 1.0, 0.05),
    Item("handedness_switch_frames", "左右判定の切替フレーム数",
         "手が1つのとき、採用／無視を切り替えるまでに必要な連続フレーム数（判定のちらつき対策）。",
         "int", 1, 30, 1),

    # --- 表示・安全装置 ---
    Item("display_mode", "表示のしかた",
         "overlay=手の骨格だけ透過表示 / preview=カメラ映像を表示（調整用）/ none=表示なし。",
         "choice", choices=("overlay", "preview", "none"), restart=True),
    Item("overlay_alpha", "オーバーレイの濃さ", "手の骨格表示の不透明度。",
         "float", 0.1, 1.0, 0.05),
    Item("overlay_hand_size", "表示する手の大きさ[px]",
         "画面に描く手のひらの長さ。カメラとの距離によらず一定サイズで描く。0で生のサイズ。",
         "int", 0, 200, 5),
    Item("fist_toggle_sec", "グーで切り替える時間[秒]",
         "グー（握り拳）をこの秒数保つと、操作の有効／無効が切り替わる。",
         "float", 0.5, 5.0, 0.1),
    Item("idle_disable_sec", "手が消えたら無効化[秒]",
         "手がカメラから見えなくなってこの秒数で操作を自動的に無効にする。0で無効化しない。",
         "float", 0.0, 30.0, 0.5),
    Item("screen_margin_px", "画面端の余白[px]",
         "カーソルを画面の端に張り付かせないための余白。",
         "int", 0, 20, 1),
    Item("enable_on_start", "起動直後から有効にする",
         "オンにすると起動と同時にマウス操作が始まる。安全のため既定はオフ（Ctrl+Alt+Hで開始）。",
         "bool", restart=True),
    Item("debug_hud", "判定値を表示する",
         "指の距離や伸び比を画面に出す。しきい値を調整するときに使う。",
         "bool"),
)

TABS = (
    ("よく使う", COMMON),
    ("カメラ・検出", ("camera_index", "frame_width", "frame_height", "camera_fps",
                     "model_path", "num_hands", "min_detection_confidence",
                     "min_presence_confidence", "min_tracking_confidence")),
    ("操作エリア・感度", ("cursor_gain", "active_margin_x", "active_margin_top",
                         "active_margin_bottom", "min_margin_x", "min_margin_top",
                         "min_margin_bottom", "adaptive_top_margin", "finger_reach_factor",
                         "adaptive_margin_pad", "edge_warn_margin", "edge_zone",
                         "edge_stabilizer_boost", "reference_palm_size")),
    ("カーソルの安定化", ("cursor_landmark", "stabilizer_radius", "filter_min_cutoff",
                         "filter_beta", "filter_d_cutoff", "skeleton_smoothing")),
    ("クリック・ピンチ", ("pinch_on", "pinch_off", "pinch_confirm_frames",
                         "pinch_require_approach", "left_drag_enabled",
                         "right_click_finger", "right_finger_reach", "pinch_arm",
                         "arm_cancel_px", "arm_timeout_sec")),
    ("固定（中指ピンチ）", ("freeze_gesture", "lock_pinch_on", "lock_pinch_off",
                           "lock_hold_sec", "lock_rearm_distance", "lock_click_on",
                           "lock_click_release", "double_click_sec", "lock_finger_reach",
                           "lock_index_ratio", "lock_drag_sec", "lock_grace_sec")),
    ("スクロール・ズーム", ("scroll_gain", "scroll_dead_zone", "zoom_gain", "zoom_dead_zone")),
    ("手の選択", ("use_hand", "swap_handedness", "handedness_min_score",
                 "handedness_switch_frames")),
    ("表示・安全装置", ("display_mode", "overlay_alpha", "overlay_hand_size",
                       "fist_toggle_sec", "idle_disable_sec", "screen_margin_px",
                       "enable_on_start", "debug_hud")),
)

BY_NAME = {item.name: item for item in ITEMS}

# 起動時にしか読まれない項目（動作中に設定を読み直しても反映できない）。
# 本体（hand_mouse.py）もこの集合を見て、再読込の対象から外す
RESTART_REQUIRED = frozenset(item.name for item in ITEMS if item.restart)


def build_tabs(config_cls):
    """(タブ名, [Item, ...]) の並びを返す。定義漏れのフィールドは「その他」タブへ。"""
    known = {f.name for f in fields(config_cls)}
    tabs = []
    listed = set()
    for title, names in TABS:
        items = [BY_NAME[n] for n in names if n in BY_NAME and n in known]
        listed.update(item.name for item in items)
        if items:
            tabs.append((title, items))

    # どのタブにも載っていないフィールドを拾う（Config に足したのに書き忘れた分）
    rest = []
    for f in fields(config_cls):
        if f.name in listed:
            continue
        rest.append(BY_NAME.get(f.name) or _guess_item(f))
    if rest:
        tabs.append(("その他", rest))
    return tabs


def _guess_item(field):
    """定義していないフィールドを、既定値の型から推測して編集できるようにする。"""
    default = field.default
    if isinstance(default, bool):
        return Item(field.name, field.name, "（説明が未設定の項目）", "bool")
    if isinstance(default, int):
        return Item(field.name, field.name, "（説明が未設定の項目）",
                    "int", 0, max(10, default * 4), 1)
    if isinstance(default, float):
        hi = max(1.0, abs(default) * 4)
        return Item(field.name, field.name, "（説明が未設定の項目）",
                    "float", 0.0, hi, hi / 100.0)
    return Item(field.name, field.name, "（説明が未設定の項目）", "text")
