# -*- coding: utf-8 -*-
"""動作中の設定の読み直し・保存（HandMouseApp）のテスト。"""

import json

from hm_core.config import Config
from synthetic import make_app

# 読み直しは1秒ごと。テストでは十分に先の時刻を渡して毎回確認させる
LATER = iter(range(1000, 100000, 10))


def reload(app):
    app.reload_config_if_changed(float(next(LATER)))


def write(path, **values):
    data = json.loads(path.read_text(encoding="utf-8"))
    data.update(values)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def start(config_file, overrides=None, **settings):
    """設定ファイルを読んで起動した状態を作る（overrides は起動オプションの指定）。"""
    for key, value in settings.items():
        Config.update_file(config_file, **{key: value})
    cfg = Config.load(config_file)
    overrides = overrides or {}
    file_values = {name: getattr(cfg, name) for name in overrides}
    for name, value in overrides.items():
        setattr(cfg, name, value)
    app = make_app(cfg, config_path=config_file)
    app.cli_overrides = dict(overrides)
    app.override_file_values = file_values
    return app


# --- 設定画面での保存を反映する -------------------------------------------------

def test_saved_change_is_applied(config_file):
    app = start(config_file)
    Config.update_file(config_file, cursor_gain=0.6)
    reload(app)
    assert app.cfg.cursor_gain == 0.6
    assert any("読み直しました" in n for n in app.notes)


def test_restart_only_item_is_not_applied_but_announced(config_file):
    app = start(config_file)
    Config.update_file(config_file, camera_index=2)
    reload(app)
    assert app.cfg.camera_index == 0
    assert any("camera_index" in n and "再起動" in n for n in app.notes)


def test_unchanged_file_is_not_reapplied(config_file):
    app = start(config_file)
    reload(app)
    assert app.notes == []


# --- 壊れた設定ファイル ----------------------------------------------------

def test_broken_file_keeps_current_settings(config_file):
    app = start(config_file, swap_handedness=True, cursor_gain=0.3)
    config_file.write_text('{"swap_handedness": true, ', encoding="utf-8")
    reload(app)
    assert app.cfg.swap_handedness is True
    assert app.cfg.cursor_gain == 0.3
    assert any("読み込めません" in n for n in app.notes)
    # 直して保存すれば反映される
    Config().save(config_file)
    Config.update_file(config_file, swap_handedness=True, cursor_gain=0.5)
    reload(app)
    assert app.cfg.cursor_gain == 0.5


def test_non_utf8_file_does_not_crash(config_file):
    app = start(config_file)
    config_file.write_bytes('{"model_path": "モデル/x.task"}'.encode("cp932"))
    reload(app)                                   # 例外にならない


def test_unusable_value_keeps_current_value(config_file):
    app = start(config_file, use_hand="left")
    write(config_file, use_hand="みぎ", stabilizer_radius="20")
    reload(app)
    assert app.cfg.use_hand == "left"
    assert app.cfg.stabilizer_radius == 20.0
    assert any("use_hand" in n and "今の値" in n for n in app.notes)


# --- Ctrl+Alt+S（左右判定の入れ替え）----------------------------------------

def test_swap_saves_only_that_item(config_file):
    """起動オプションで一時的に変えた値（--enable / --display / --debug）をファイルに残さない。"""
    app = start(config_file, overrides={"enable_on_start": True, "display_mode": "preview",
                                        "debug_hud": True, "camera_index": 1})
    app.toggle_swap_handedness()
    saved = Config.load(config_file)
    assert saved.swap_handedness is True
    assert (saved.enable_on_start, saved.display_mode, saved.debug_hud, saved.camera_index) == \
           (False, "overlay", False, 0)


def test_swap_does_not_trigger_own_reload(config_file):
    app = start(config_file)
    app.toggle_swap_handedness()
    app.notes.clear()
    reload(app)
    assert app.notes == []


def test_swap_does_not_overwrite_broken_file(config_file):
    app = start(config_file)
    config_file.write_text("{broken", encoding="utf-8")
    app.toggle_swap_handedness()
    assert config_file.read_text(encoding="utf-8") == "{broken"
    assert app.cfg.swap_handedness is True           # 今回の起動中は有効
    assert any("今回の起動中のみ" in n for n in app.notes)


# --- 起動オプションは読み直しより優先する -------------------------------------

def test_cli_overrides_survive_saving_other_items(config_file):
    app = start(config_file, overrides={"use_hand": "both", "swap_handedness": True,
                                        "debug_hud": True})
    Config.update_file(config_file, cursor_gain=0.9)
    reload(app)
    assert (app.cfg.use_hand, app.cfg.swap_handedness, app.cfg.debug_hud) == ("both", True, True)
    assert app.cfg.cursor_gain == 0.9
    assert not any("起動オプション" in n for n in app.notes)   # 関係ない保存では黙っている


def test_changing_overridden_item_in_file_is_announced(config_file):
    app = start(config_file, overrides={"use_hand": "both"})
    Config.update_file(config_file, use_hand="left")
    reload(app)
    assert app.cfg.use_hand == "both"
    assert any("use_hand は起動オプション" in n for n in app.notes)


def test_enable_option_does_not_cause_restart_notice(config_file):
    app = start(config_file, overrides={"enable_on_start": True})
    Config.update_file(config_file, cursor_gain=0.8)
    reload(app)
    assert app.cfg.enable_on_start is True
    assert not any("enable_on_start" in n for n in app.notes)


def test_swap_hotkey_wins_over_swap_option(config_file):
    app = start(config_file, overrides={"swap_handedness": True})
    app.toggle_swap_handedness()                  # その場で切り替えた
    Config.update_file(config_file, cursor_gain=0.7)
    reload(app)
    assert app.cfg.swap_handedness is False
