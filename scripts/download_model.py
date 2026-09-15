# -*- coding: utf-8 -*-
"""MediaPipeの手のランドマーク検出モデルを取得する。

初回セットアップ時に一度だけ実行すればよい（約7.8MB）。
"""

import sys
import urllib.error
import urllib.request
from pathlib import Path

MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
             "hand_landmarker/float16/1/hand_landmarker.task")
ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "models" / "hand_landmarker.task"


def main():
    if DEST.exists():
        print(f"既に存在します: {DEST}（{DEST.stat().st_size:,} bytes）")
        return 0

    DEST.parent.mkdir(parents=True, exist_ok=True)
    print(f"ダウンロード中: {MODEL_URL}")
    try:
        urllib.request.urlretrieve(MODEL_URL, DEST)
    except (urllib.error.URLError, OSError) as e:
        print(f"ダウンロードに失敗しました: {e}")
        print("社内プロキシ環境の場合は、ブラウザで上記URLを開いて "
              f"{DEST} に保存してください。")
        return 1

    print(f"保存しました: {DEST}（{DEST.stat().st_size:,} bytes）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
