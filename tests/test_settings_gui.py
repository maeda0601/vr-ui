# -*- coding: utf-8 -*-
"""設定画面（SettingsApp）のテスト。画面は作るが表示の操作はせず、値だけを検証する。"""

import json

import pytest

from hm_core.config import Config

tk = pytest.importorskip("tkinter")


@pytest.fixture
def open_gui():
    """設定画面を開く（テストの終わりに必ず閉じる）。"""
    from hm_core.settings_gui import SettingsApp

    opened = []

    def _open(path):
        try:
            app = SettingsApp(path)
        except tk.TclError as e:          # 画面を作れない環境
            pytest.skip(f"Tk を使えない環境: {e}")
        app.root.withdraw()
        opened.append(app)
        return app

    yield _open
    for app in opened:
        try:
            app.root.destroy()
        except tk.TclError:
            pass


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_save_writes_only_edited_items(config_file, open_gui):
    """開いている間に本体（Ctrl+Alt+S）が変えた値を、開いた時点の古い値で消さない。"""
    gui = open_gui(config_file)
    Config.update_file(config_file, swap_handedness=True)     # 本体の Ctrl+Alt+S
    gui.vars["cursor_gain"].set(0.6)                          # 画面で感度を変える
    assert gui.save()
    saved = read(config_file)
    assert saved["swap_handedness"] is True
    assert saved["cursor_gain"] == 0.6


def test_external_change_is_shown_for_untouched_items(config_file, open_gui):
    gui = open_gui(config_file)
    Config.update_file(config_file, swap_handedness=True)
    updated = gui._refresh_from_file()
    assert updated
    assert gui.vars["swap_handedness"].get() is True
    assert not gui.dirty                                      # 読み込んだだけでは未保存扱いにしない


def test_item_being_edited_wins_over_external_change(config_file, open_gui):
    gui = open_gui(config_file)
    gui.vars["cursor_gain"].set(0.4)                          # 画面で編集中
    Config.update_file(config_file, cursor_gain=0.9)          # 外でも変わった
    gui._refresh_from_file()
    assert gui.vars["cursor_gain"].get() == 0.4
    gui.save()
    assert read(config_file)["cursor_gain"] == 0.4


def test_save_without_changes_does_not_touch_file(config_file, open_gui):
    gui = open_gui(config_file)
    before = config_file.read_text(encoding="utf-8")
    assert gui.save()
    assert config_file.read_text(encoding="utf-8") == before
    assert "変更はありません" in gui.status.cget("text")


def test_reset_all_then_save(tmp_path, open_gui):
    path = tmp_path / "c.json"
    cfg = Config()
    cfg.cursor_gain = 0.3
    cfg.stabilizer_radius = 30.0
    cfg.save(path)
    gui = open_gui(path)
    for item in gui.items.values():
        gui._reset_one(item)
    gui.save()
    saved = read(path)
    assert saved["cursor_gain"] == Config().cursor_gain
    assert saved["stabilizer_radius"] == Config().stabilizer_radius


def test_broken_file_is_warned_and_can_be_replaced(tmp_path, open_gui):
    path = tmp_path / "broken.json"
    path.write_text("{broken", encoding="utf-8")
    gui = open_gui(path)
    assert gui.load_failed
    assert "壊れている" in gui.status.cget("text")
    gui.vars["cursor_gain"].set(0.5)
    assert gui.save()                                         # 警告のうえで置き換えられる
    assert Config.try_load(path).cursor_gain == 0.5


def test_healthy_file_has_no_warning(config_file, open_gui):
    assert not open_gui(config_file).load_failed
