# -*- coding: utf-8 -*-
"""MediaPipeの手のランドマーク検出モデルを取得する。

初回セットアップ時に一度だけ実行すればよい（約7.8MB）。

- 一時ファイルに落としてから置き換えるので、途中で失敗しても壊れたファイルは残らない
- 中身をハッシュ値で確かめる（途中で切れたファイル・別物のファイルを使わないため）
- 既にあるファイルも確かめ、壊れていれば取り直す（以前の失敗で残ったものの修復）
"""

import hashlib
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
             "hand_landmarker/float16/1/hand_landmarker.task")
# 上のURL（版 "1" 固定）で配布されているファイルの SHA-256 と大きさ
MODEL_SHA256 = "fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1"
MODEL_SIZE = 7819105
ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "models" / "hand_landmarker.task"


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check_model(path=None):
    """モデルファイルが正しいか確かめる。問題なければ None、あれば理由を返す。"""
    path = Path(path) if path is not None else DEST
    if not path.exists():
        return "ファイルがありません"
    size = path.stat().st_size
    if size != MODEL_SIZE:
        return f"大きさが違います（{size:,} bytes、正しくは {MODEL_SIZE:,} bytes。途中で切れた可能性）"
    if sha256_of(path) != MODEL_SHA256:
        return "中身が配布物と一致しません（壊れているか、別のファイルです）"
    return None


def main():
    problem = check_model()
    if problem is None:
        print(f"既に存在します（確認済み）: {DEST}（{MODEL_SIZE:,} bytes）")
        return 0
    if DEST.exists():
        print(f"既存のモデルファイルを取り直します: {problem}")

    DEST.parent.mkdir(parents=True, exist_ok=True)
    tmp = DEST.with_name(DEST.name + ".download")
    print(f"ダウンロード中: {MODEL_URL}")
    try:
        urllib.request.urlretrieve(MODEL_URL, tmp)
        problem = check_model(tmp)
        if problem is not None:
            raise ValueError(f"ダウンロードしたファイルが正しくありません: {problem}")
        os.replace(tmp, DEST)
    except (urllib.error.URLError, OSError, ValueError) as e:
        print(f"ダウンロードに失敗しました: {e}")
        print("社内プロキシ環境の場合は、ブラウザで上記URLを開いて "
              f"{DEST} に保存してから、もう一度このスクリプトを実行して確認してください。")
        try:
            tmp.unlink()
        except OSError:
            pass
        return 1

    print(f"保存しました（確認済み）: {DEST}（{MODEL_SIZE:,} bytes）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
