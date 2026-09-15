# -*- coding: utf-8 -*-
"""ハンドマウスの設定画面を開く。

    uv run scripts/hand_mouse_settings.py

本体（hand_mouse.py）を起動していなくても使える。保存すると設定JSONに書き込み、
本体が動作中ならそのまま反映される（カメラなど一部の項目は再起動が必要）。
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from hm_core.settings_gui import open_settings   # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "scripts" / "hand_mouse_config.json"


def main():
    parser = argparse.ArgumentParser(description="ハンドマウスの設定画面")
    parser.add_argument("--config", default=str(CONFIG_PATH), help="設定JSONのパス")
    args = parser.parse_args()

    try:
        open_settings(args.config)
    except Exception:
        import traceback
        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
