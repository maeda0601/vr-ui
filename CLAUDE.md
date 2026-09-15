# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## プロジェクト概要

Webカメラの手の動き（MediaPipe HandLandmarker）でWindowsのマウスを操作するツール。
VRのハンドトラッキング風に、カメラ内の操作エリアを画面全体へ割り当てる絶対座標方式。
Python単体のデスクトップアプリで、Windows専用（ctypesでuser32を直接呼ぶ）。利用者向けの説明は [README.md](README.md)。

## コマンド

```bash
pip install -r requirements.txt          # mediapipe / opencv-python / numpy / Pillow
python scripts/download_model.py         # models/hand_landmarker.task を取得（初回のみ、約7.8MB）
python scripts/hand_mouse.py             # 起動（既定: 透過オーバーレイ表示、マウス操作は無効。Ctrl+Alt+Hで有効化）
python scripts/hand_mouse.py --display preview   # カメラ映像＋HUDのウィンドウ表示（感度調整・デバッグ用）
python scripts/hand_mouse.py --enable --camera 1 --display none   # 主なオプション
python -m compileall -q scripts          # 構文チェック
```

- 自動テストは無い。ジェスチャー判定は `hm_core.gestures.Hand` に `.x/.y` を持つダミーランドマーク21点を渡せば、カメラ無しで `GestureRecognizer.update()` を検証できる。
- 手を検出しないまま動作確認したいときは `enable_on_start=false`（既定）のまま起動すれば、マウスには一切触れない。
- 設定は初回起動時に `scripts/hand_mouse_config.json` が自動生成される。`Config` dataclass にフィールドを追加すればJSONにも自動で載る（未知キーは無視される）。

## アーキテクチャ

1フレームの流れ（`scripts/hand_mouse.py` の `HandMouseApp.run`）:

```
CameraStream(別スレッド, 最新フレームのみ保持)
  → cv2.flip で鏡像化  ※以降の正規化座標はすべて鏡像空間
  → HandLandmarker.detect_for_video(VIDEO mode, 単調増加のtimestamp_ms 必須)
  → Hand（特徴量: 指の伸展・ピンチ距離。手のサイズ dist(手首,中指付け根) で正規化しカメラ距離に依存させない）
  → GestureRecognizer.update()  … 状態を持つ（ピンチのヒステリシス）。モードを1つ返す
  → HandMouseApp.process()      … フレーム間状態（ドラッグ用オフセット、スクロール/ズーム累積、グー保持タイマー）
  → MouseController（SetCursorPos / SendInput）
  → 表示: display_mode により HandOverlay（透過オーバーレイ, 既定） / overlay.render_hud（カメラプレビュー） / なし
```

### 透過オーバーレイ（`hm_core/overlay_window.py`）

- ctypes直叩きの Win32 レイヤードウィンドウ（`WS_EX_LAYERED|TRANSPARENT|TOPMOST|TOOLWINDOW|NOACTIVATE`）に、ピクセル単位アルファのBGRA画像を `UpdateLayeredWindow` で流し込む。Tkinter の `-transparentcolor`（カラーキー）はDWM合成で太線が点線状に欠けて見えたため採用していない。
- ウィンドウは2枚: 手の外接矩形＋余白だけを覆って毎フレーム移動する `hand_win` と、上部中央の状態表示 `pill_win`（文言が変わったときだけ再描画）。全画面を毎フレーム描き直さないのが性能の要。
- 画像は **プリマルチプライドBGRA** で作る。図形は `cv2`（`LINE_AA`、色は `_bgra()` で事前にアルファを掛ける）、文字は PIL で描いて `_premultiply()` → `_blit()` で合成する。PILのストレートアルファをそのまま流すと縁が黒くなる。
- メッセージポンプ: `HotkeyManager.poll()` がスレッド宛の全メッセージを取り、`WM_HOTKEY` 以外は `DispatchMessageW` で配送する。`HandOverlay.update()` は自ウィンドウ宛だけを `PeekMessageW(hwnd)` で処理する（`hwnd=None` にするとホットキーを横取りしてしまう）。ウィンドウ生成・更新はメインスレッドから行う。
- 骨格の画面座標は `HandMouseApp.hands_to_screen()` が `map_to_screen(clamp=False)` で作る。カーソルと違ってクランプしないので、手が画面端から切れて見える。
- DIB はウィンドウサイズが変わったときだけ作り直す（サイズは `SIZE_STEP` 単位に丸める）。`overlay_alpha` は画像全体を `cv2.convertScaleAbs` で一律に薄める。

### 使う手の選別（`HandMouseApp.hand_allowed`）

`use_hand`（既定 `right`）に合わない手は recognizer に渡す前に落とす（描画もされない）。MediaPipe の handedness は鏡像入力前提で、本アプリは検出前に `cv2.flip` しているのでラベル＝実際の左右。環境で逆になるなら `swap_handedness`。ラベル無し・信頼度 `handedness_min_score` 未満の手は落とさない（グーは左右判定が不安定で、落とすと起動時の有効化ができなくなる）。手が1つのときは `select_hands()` が `handedness_switch_frames` 連続で同じ判定になるまで採用／無視を切り替えない。
無視した手は `ignored_hands` として灰色で描く（プレビュー `draw_ghost_hand`、オーバーレイ `ghost_px`）。描かないと「検出していない」と区別がつかない。左右が逆の環境（ドライバが既に鏡像化しているカメラ等）向けに `Ctrl+Alt+S`（`toggle_swap_handedness`）で入れ替えて `config_path` に保存する。
MediaPipe の手のひら検出は開いた手が前提で、閉じた手（グー）は追跡中でないと検出されにくい。無効中で手が無いときの案内は「手を開いてカメラに見せてください」にしている。

### モード判定の優先順位（`hm_core/gestures.py`）

ZOOM（両手ともピンチ）→ LEFT（親指+人差し指）→ RIGHT（親指+`right_click_finger`、既定は薬指）→ FIST → SCROLL（チョキ）→ POINT → NONE。
ピンチの成立には `_confirm()` で `pinch_confirm_frames` 連続を要求し（成立後は距離のヒステリシスのみで維持）、左ピンチはさらに `pinch_require_approach` により `_arm_on`（親指が `pinch_arm` の外から近づいた）を前提にする。離した瞬間に `_arm_on` を落とすので、連続クリックには一度親指を離す必要がある。`_update_arming` は毎フレーム先頭で呼ぶ（POINT以外でも追跡する）。
ピンチはFISTより先に見る（つまむと他の指が閉じてグーに見えるため）。FISTは「4本指を握り込んでいる」（指先が第二関節より手首側、`_curled`）で判定し、「伸びていない」では判定しない。左ピンチは `index_curled` でないことも要求する（グーの中で親指が人差し指先に触れてもクリックしない）。POINTは `cursor_landmark` が `index_tip` のときだけ人差し指の伸展を要求し、それ以外は開いた手なら何でもよい（クリック後に緩んだ手で操作が途切れないため）。
右クリックは「その指の距離 < 人差し指距離×0.8」かつ `finger_reaching`（その指を握り込んでいない）のときだけ採用する。人差し指を立てた姿勢では親指が曲げた指に触れがちで、これが無いと誤発火する。描画側は `state.right_tip` で線を引く指を知る。
新しいジェスチャーを足すときはこの順序のどこに入れるか（既存ジェスチャーとの排他）を先に決めること。

### 変更時に壊しやすい設計上の約束

- **`enabled` はマウス出力だけをゲートする。** ジェスチャー判定と `handle_fist` は無効中も動く（グー保持で再有効化するため）。`process()` 内で `self.enabled` を見ずに `mouse.*` を呼ばないこと。
- **安全装置は残す**: 無効化・終了時の `mouse.release_all()`、`enable_on_start=False` 既定、手が `idle_disable_sec`（3秒）見えなければ自動無効化（`handle_idle`）、`Ctrl+Alt+Q/H/R` のグローバルホットキー、画面端の `screen_margin_px` クランプ。ホットキーはスレッド束縛のメッセージキューに届くため、`HotkeyManager.register/poll` はメインスレッドから呼ぶ。オーバーレイはフォーカスを取らないので、`Space/R/Esc` のキー操作は `display_mode=preview`（cv2ウィンドウ）のときしか効かない。ユーザー向けの操作案内はホットキーを基準に書く。
- **固定ジェスチャーは2方式**（`freeze_gesture`）: `approach`（既定）は下記の自動固定。`middle` は親指＋中指ピンチ（`_lock_on`）を固定とみなし `_arm_on` に流し込む。固定の判定は専用のしきい値（`lock_pinch_on/off`、`lock_finger_reach`、`lock_index_ratio`）で、クリックより緩い（つまむと中指が曲がるため `finger_reaching` の0.95では取れない）。開始は「中指距離 < 人差し指距離×`lock_index_ratio`」のときだけ（親指を人差し指に付けると中指にも近づくため）。継続は `lock_hold_sec` > 0 なら**固定窓**（開始から一定秒数、距離に関係なく固定し時間で解除。再固定は `_lock_rearmed`＝親指が `lock_pinch_off` 以上離れてから）、0 なら距離のヒステリシス。`left_drag_enabled=false` のとき LEFT は `click_left()`（押して離す）のみで、固定中（`frozen`）は LEFT/RIGHT でもカーソルを動かさない。固定が `lock_drag_sec` 続くと `process()` が `lock_drag=True` にして左ボタンを押し、固定を解いて追従（ドラッグ／範囲選択）。固定が外れたら離す。`release_left` の通常経路は `lock_drag` 中は抑止する。固定を離した後は `_lock_released_at`（`lock_grace_sec`、時刻ベース。`update(hands, now)` で時刻を受け取る）の余韻があり、`_lock_active()`（固定中 or 余韻）の間は `_arm_on` を維持して位置を保ち、左右クリックを受け付ける（`middle` モードでは右クリックも固定してからしか成立しない）。余韻は `state.lock_tip` が None なので `arm_cancel_px`/`arm_timeout_sec` で自然に解ける。その解除で立つ `arm_suppressed` は、明示的な固定（`lock_tip` 非None）では無視して即クリアする（余韻中に再度つまんだとき固定できなくなるバグの原因だった）。`--debug`（`debug_hud`）で指の距離・伸び比を画面とコンソールに出せる。固定中の左クリックは「人差し指距離 ≤ 中指距離×1.3」（3本指でつまんだ形）で判定。チョキ（SCROLL）は固定中・中指ピンチ中は除外。このとき左クリックは `_lock_on` 中のみ、`arm_cancel_px`/`arm_timeout_sec` の自動解除は行わない（`state.lock_tip` が非None で判別）。`right_click_finger` が `middle` のときは衝突するので `approach` にフォールバック。
- **クリック位置ズレ対策は2段構え**: (1) 親指–人差し指の距離が `pinch_arm` を外から内へ横切った瞬間に `state.arming` がラッチし（`_update_arming`。最初から近い姿勢では立たない。中指は見ない）、`process()` は `self.frozen=True` でカーソルを止める。固定中に `arm_cancel_px` 以上動くか `arm_timeout_sec` を過ぎたら解除し、指が離れるまで `arm_suppressed` で再固定しない。(2) 基準点が変わる瞬間（固定解除、LEFT/RIGHT突入で指先→指の中点）は `reanchor()` で `self.offset` を取り直し、フィルタをリセットして飛びを防ぐ。オフセットは `decay_offset` で滑らかに戻す。カーソル基準点（`cursor_landmark`）を変える変更をするなら、この仕組みも合わせて見直す。
- **カーソルの安定化は3層**: 基準点（`cursor_landmark`、既定 `palm`＝手首＋4指付け根の平均。指先は最もブレる）→ One Euro Filter（`filters.py`）→ `stabilize()` の不感帯（`stabilizer_radius` px 以内は不動、超えた分だけ引き寄せる）。`apply_cursor()` はこの順で通す。不感帯半径とフィルタのカットオフは `update_noise_gain()` が毎フレーム調整する（フレーム端に近いほど・手が大きく映るほど強める。`state.edge_factor`、`reference_palm_size`）。層を足す・外すときは `reanchor()`（`last_screen_pos` からの連続性）が壊れないか確認する。
- **操作エリアは `Config.active_area()` が唯一の出所**: 余白（`active_margin_*`）を `cursor_gain` で中心そのままに拡縮し、`min_margin_*` で下限を止めた (x0, y0, x1, y1)。`map_to_screen` もプレビューの枠描画もこれを使う。感度を変える要望は `cursor_gain` で受ける（絶対座標なので、遅くする＝手を大きく動かす、のトレードオフを説明する）。
- **操作エリアは上下非対称**（`active_margin_top` < `active_margin_bottom`）: 基準点の手のひら中心より下に手首があるので、下の余白を大きく取らないと画面下端を狙うときに手がフレームから切れて検出が荒れる。`near_frame_edge` → `state.near_edge` で警告を出す。手を見失って復帰した瞬間は `reanchor()` で直前位置からつなぐ。
- **骨格の表示は別系統で平滑化する**: `smooth_skeleton()`（EMA、`skeleton_smoothing`）は表示専用で、操作系のフィルタとは独立。表示だけ滑らかにしたいときはこちら、操作の遅延を変えるなら One Euro / stabilizer を触る。
- **オーバーレイの手は生の写像で描かない**: 操作エリア→画面の写像は約4.7倍・縦横比も非等方なので、`hands_to_screen()` は手のひら長を `overlay_hand_size` px に正規化し、カーソル基準点が `last_screen_pos`（実カーソル）に重なるよう配置する。描かれた指先＝クリック位置、が守るべき不変条件。
- **MediaPipe 1.0 では `mp.solutions.hands` が存在しない。** Tasks API（`mediapipe.tasks.python.vision.HandLandmarker`）＋ `models/hand_landmarker.task` を使う。
- **日本語表示は `overlay.TextRenderer`（PIL）経由。** `cv2.putText` は日本語を描けない。1フレームにつきPIL変換は1回にまとめる（`render_hud` の `items` に集約）。
- **`print` する日本語は cp932 で表せる文字にする**（コンソールがcp932のため）。絵文字や `➡` などは化ける。
- `CameraStream.read(last_id)` は新しいフレームが無ければ `(last_id, None)` を返す。同じフレームを二度処理しない前提でスクロール/ズームの差分を計算している。

### 環境の注意

- `mediapipe` は `opencv-contrib-python` を依存で入れるため、`opencv-python` / `opencv-python-headless` と同居する。`cv2` は最後にインストールされた方に解決され、headless だと `imshow` が無い。プレビューが出なくなったら `pip install --force-reinstall opencv-python`。
- 実効フレームレートはカメラ側で決まることが多い（暗いと露光延長で半減）。検出自体は約18〜19ms/フレーム。

## 自動コミット

`.claude/settings.json` の Stop フックが各ターン終了時に `.claude/hooks/auto-commit.sh` を実行し、作業ツリーに変更があれば `git add -A` → コミットする（メッセージは「自動コミット: 日時（Nファイル）」）。ユーザーの希望による運用なので、途中状態でもコミットされる前提でよい。意味のある単位でまとめたいときは、ターンの終わりに自分で説明的なメッセージでコミットすれば、フックは何もしない。

## ドキュメント整理のルール

- 調査メモや手順書などのMarkdownドキュメントを新規作成・保存する際は、[okf_summary.md](okf_summary.md) にまとめた Open Knowledge Format（OKF）v0.2 に従う。要点: 1ファイル＝1コンセプト、先頭にYAMLフロントマター（`type` 必須。`title` / `description` / `tags` / `generated`(`by`,`at`) / `status` / `stale_after` を推奨）、コンセプト間はMarkdownリンクで関連付け。未知の `type` や欠落フィールドがあっても読み込みを拒否しない。
- プランモードでプランを作成したら `plan.md` として保存する。
- [CLAUDE.template.md](CLAUDE.template.md) は新規プロジェクト用の雛形であり、このリポジトリの指示ではない。
