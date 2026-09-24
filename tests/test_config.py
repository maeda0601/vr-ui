# -*- coding: utf-8 -*-
"""設定の読み書き（Config）のテスト。"""

import json
import threading

import pytest

from hm_core.config import Config


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


# --- 読み込み ---------------------------------------------------------------

def test_load_creates_file_with_defaults(tmp_path):
    path = tmp_path / "new.json"
    cfg = Config.load(path)
    assert path.exists()
    assert cfg == Config()


def test_broken_file_is_none_for_live_reload(tmp_path):
    """動作中の読み直し用（try_load / from_text）は、壊れていれば None を返す。"""
    path = tmp_path / "broken.json"
    path.write_text('{"swap_handedness": true, ', encoding="utf-8")
    assert Config.try_load(path) is None
    assert Config.from_text(path.read_text(encoding="utf-8")) is None


def test_broken_file_gives_defaults_at_startup(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{broken", encoding="utf-8")
    assert Config.load(path) == Config()


@pytest.mark.parametrize("text", ["[1, 2]", '"text"', "123"])
def test_non_object_json_is_rejected(text):
    assert Config.from_text(text) is None


def test_unknown_keys_are_ignored():
    cfg = Config.from_text(json.dumps({"future_key": 1, "cursor_gain": 0.5}))
    assert cfg.cursor_gain == 0.5
    assert not hasattr(cfg, "future_key")


# --- 値の型をそろえる --------------------------------------------------------

@pytest.mark.parametrize("key, raw, expected", [
    ("stabilizer_radius", "12", 12.0),       # 文字列の数値
    ("stabilizer_radius", 12, 12.0),         # 整数 → 小数の項目
    ("num_hands", 2.0, 2),                   # 整数値の小数 → 整数の項目
    ("num_hands", "1", 1),
    ("debug_hud", 1, True),                  # 0/1 → true/false
    ("debug_hud", "yes", True),
    ("swap_handedness", "false", False),
    ("use_hand", "both", "both"),
])
def test_values_are_coerced_to_field_type(key, raw, expected):
    value = getattr(Config.from_text(json.dumps({key: raw})), key)
    assert value == expected
    assert type(value) is type(expected)


@pytest.mark.parametrize("key, raw", [
    ("cursor_gain", "abc"),                  # 数値でない
    ("num_hands", 2.5),                      # 整数でない
    ("stabilizer_radius", True),             # true は数値として扱わない
    ("debug_hud", "maybe"),
    ("use_hand", "みぎ"),                     # 選択肢に無い（手を全部無視してしまう）
    ("display_mode", 3),                     # 文字列でない
    ("cursor_landmark", "thumb"),
])
def test_unusable_values_fall_back_to_default(key, raw):
    problems = []
    cfg = Config.from_text(json.dumps({key: raw}), problems=problems)
    assert getattr(cfg, key) == getattr(Config(), key)
    assert len(problems) == 1 and key in problems[0]


def test_non_finite_number_falls_back():
    cfg = Config.from_text('{"filter_beta": NaN}')
    assert cfg.filter_beta == Config().filter_beta


def test_unusable_values_keep_current_value_with_fallback():
    """動作中の読み直しでは、使えない値は既定値ではなく今の値を使う。"""
    current = Config()
    current.use_hand = "left"
    current.cursor_gain = 0.4
    text = json.dumps({"use_hand": "みぎ", "cursor_gain": "abc", "stabilizer_radius": "20"})
    cfg = Config.from_text(text, fallback=current)
    assert cfg.use_hand == "left"
    assert cfg.cursor_gain == 0.4
    assert cfg.stabilizer_radius == 20.0


# --- 保存 ---------------------------------------------------------------

def test_save_and_load_round_trip(tmp_path):
    cfg = Config()
    cfg.cursor_gain = 0.3
    cfg.use_hand = "both"
    path = tmp_path / "c.json"
    assert cfg.save(path)
    assert Config.load(path) == cfg
    assert not list(tmp_path.glob("*.tmp"))       # 一時ファイルは残らない


def test_update_file_changes_only_given_keys(config_file):
    data = read(config_file)
    data["future_key"] = 1                        # 今のバージョンが知らない項目も残す
    config_file.write_text(json.dumps(data), encoding="utf-8")
    assert Config.update_file(config_file, swap_handedness=True)
    after = read(config_file)
    assert after["swap_handedness"] is True
    assert after["future_key"] == 1
    assert {k: v for k, v in after.items() if k != "swap_handedness"} == \
           {k: v for k, v in data.items() if k != "swap_handedness"}


def test_update_file_does_not_overwrite_broken_file(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{broken", encoding="utf-8")
    assert not Config.update_file(path, swap_handedness=True)
    assert path.read_text(encoding="utf-8") == "{broken"


def test_update_file_creates_missing_file(tmp_path):
    path = tmp_path / "missing.json"
    assert Config.update_file(path, cursor_gain=0.5)
    assert Config.load(path).cursor_gain == 0.5


def test_update_file_rejects_unknown_key(config_file):
    with pytest.raises(KeyError):
        Config.update_file(config_file, no_such_key=1)


def test_readers_never_see_half_written_file(config_file):
    """保存は一時ファイルからの置き換えなので、並行して読んでも書きかけは見えない。

    置き換えの一瞬に開けない（OSError）ことはあるが、それは読む側が次の確認で読み直す。
    """
    stop = threading.Event()

    def writer():
        i = 0
        while not stop.is_set():
            c = Config()
            c.cursor_gain = 0.1 + (i % 9) / 10
            c.save(config_file)
            i += 1

    thread = threading.Thread(target=writer)
    thread.start()
    half_written = 0
    try:
        for _ in range(400):
            try:
                text = config_file.read_text(encoding="utf-8")
            except OSError:
                continue
            if Config.from_text(text) is None:
                half_written += 1
    finally:
        stop.set()
        thread.join()
    assert half_written == 0


# --- 操作エリア -----------------------------------------------------------

def test_active_area_shrinks_with_higher_gain():
    slow, fast = Config(), Config()
    slow.cursor_gain, fast.cursor_gain = 0.8, 1.5
    s, f = slow.active_area(), fast.active_area()
    assert (f[2] - f[0]) < (s[2] - s[0])


def test_active_area_stops_at_min_margin():
    """感度を下げてもエリアは min_margin_* より外へ広がらない（頭打ちになる）。"""
    cfg = Config()
    cfg.cursor_gain = 0.1
    x0, y0, x1, y1 = cfg.active_area()
    assert x0 == pytest.approx(cfg.min_margin_x)
    assert x1 == pytest.approx(1 - cfg.min_margin_x)
    assert y0 >= cfg.min_margin_top - 1e-9
    assert y1 <= 1 - cfg.min_margin_bottom + 1e-9
