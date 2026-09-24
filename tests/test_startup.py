# -*- coding: utf-8 -*-
"""起動と終了（ホットキーの登録、初期化の失敗、後始末）のテスト。"""

import io
import shutil

import pytest

import download_model as D
import hand_mouse as HM
from hm_core.config import Config
from hm_core.hotkeys import MOD_ALT, MOD_CONTROL, MOD_SHIFT
from synthetic import make_app

CA = MOD_CONTROL | MOD_ALT
CAS = CA | MOD_SHIFT
QUIT_KEYS = {(CA, HM.VK_Q), (CAS, HM.VK_Q), (CA, HM.VK_F12)}


@pytest.fixture
def dialogs(monkeypatch):
    """ダイアログを実際には出さず、出した内容を記録する。"""
    shown = []
    monkeypatch.setattr(HM, "show_message",
                        lambda message, warning=False: shown.append((warning, message)))
    return shown


# --- ホットキー ---------------------------------------------------------------

def test_hotkeys_registered_as_usual(fake_hotkeys, dialogs):
    app = make_app()
    assert app.register_hotkeys(use_preview=False)
    assert app.hotkey_labels == {"toggle": "Ctrl+Alt+H", "quit": "Ctrl+Alt+Q",
                                 "reset": "Ctrl+Alt+R", "swap": "Ctrl+Alt+S"}
    assert app.notes == [] and dialogs == []


def test_taken_hotkey_falls_back_and_is_announced(fake_hotkeys, dialogs):
    fake_hotkeys.add((CA, HM.VK_Q))               # 他のアプリが Ctrl+Alt+Q を使用中
    app = make_app()
    app.no_console = True
    assert app.register_hotkeys(use_preview=False)
    assert app.key("quit") == "Ctrl+Alt+Shift+Q"
    assert any("Ctrl+Alt+Shift+Q" in n for n in app.notes)
    assert len(dialogs) == 1


def test_hints_show_the_key_actually_registered(fake_hotkeys):
    fake_hotkeys.add((CA, HM.VK_H))
    app = make_app()
    app.register_hotkeys(use_preview=False)
    assert app.key("toggle") == "Ctrl+Alt+Shift+H"
    from hm_core.overlay import _help_text
    assert "Ctrl+Alt+Shift+H" in _help_text(app.hotkey_labels)
    assert "Ctrl+Alt+H " not in _help_text(app.hotkey_labels)


def test_no_quit_key_without_console_aborts_before_camera(fake_hotkeys, dialogs):
    """終了キーが無く、ほかに止める手段も無いなら起動しない（カメラも開かない）。"""
    fake_hotkeys.update(QUIT_KEYS)
    app = make_app()
    app.no_console = True
    opened = []
    app.open_camera = lambda: opened.append(1)
    app.run()
    assert opened == []
    assert dialogs and dialogs[0][0] is True        # 警告ダイアログ
    assert app.hotkeys._names == {}                 # 登録できた分も解除している


@pytest.mark.parametrize("use_preview, no_console", [(False, False), (True, True)])
def test_no_quit_key_but_other_way_to_stop_continues(fake_hotkeys, dialogs,
                                                     use_preview, no_console):
    """コンソールの Ctrl+C やプレビューの Esc で止められるなら起動を続ける。"""
    fake_hotkeys.update(QUIT_KEYS)
    app = make_app()
    app.no_console = no_console
    assert app.register_hotkeys(use_preview=use_preview)
    assert not any(warning for warning, _ in dialogs)


# --- 初期化の失敗と後始末 ------------------------------------------------------

class FakeCamera:
    def __init__(self):
        self.released = False

    def release(self):
        self.released = True


def test_failure_after_camera_opened_still_releases_everything(fake_hotkeys):
    app = make_app()
    camera = FakeCamera()
    app.open_camera = lambda: camera

    def fail():
        raise RuntimeError("モデルを読み込めませんでした（模擬）")

    app.create_landmarker = fail
    with pytest.raises(RuntimeError):
        app.run()
    assert camera.released
    assert app.hotkeys._names == {}


def test_shutdown_continues_after_a_step_fails(fake_hotkeys):
    app = make_app()
    app.register_hotkeys(use_preview=False)
    camera = FakeCamera()

    class BrokenLandmarker:
        def close(self):
            raise RuntimeError("閉じられません（模擬）")

    app.shutdown(camera, BrokenLandmarker(), None)
    assert camera.released                          # 検出器の失敗の後もカメラは解放
    assert app.hotkeys._names == {}


def test_startup_failure_without_console_shows_dialog(monkeypatch, dialogs, tmp_path):
    class Acquired:
        acquired = True

        def release(self):
            pass

    monkeypatch.setattr(HM, "SingleInstance", Acquired)
    monkeypatch.setattr(HM, "setup_logging_if_no_console", lambda: io.StringIO())

    def fail(self):
        raise RuntimeError("カメラを開けませんでした（模擬）")

    monkeypatch.setattr(HM.HandMouseApp, "run", fail)
    monkeypatch.setattr("sys.argv", ["hand_mouse.py", "--config", str(tmp_path / "c.json")])
    assert HM.main() == 1
    assert dialogs and dialogs[0][0] is True
    assert "カメラを開けませんでした" in dialogs[0][1]


# --- 壊れたモデルファイル ------------------------------------------------------

@pytest.fixture
def real_model():
    if D.check_model() is not None:
        pytest.skip("標準のモデルファイルが無い（uv run scripts/download_model.py で取得）")
    return D.DEST


def test_broken_default_model_is_set_aside(monkeypatch, tmp_path, real_model):
    broken = tmp_path / "hand_landmarker.task"
    broken.write_bytes(real_model.read_bytes()[:3_000_000])     # 途中で切れたファイル
    monkeypatch.setattr(HM, "MODEL_DEST", broken)
    cfg = Config()
    cfg.model_path = str(broken)
    app = make_app(cfg)
    with pytest.raises(RuntimeError, match="モデルファイルが壊れています"):
        app.create_landmarker()
    assert not broken.exists()                      # 次の起動で取り直されるよう退避
    assert broken.with_name("hand_landmarker.task.broken").exists()


def test_missing_model_is_clear_error(tmp_path):
    cfg = Config()
    cfg.model_path = str(tmp_path / "none.task")
    with pytest.raises(FileNotFoundError, match="モデルファイルがありません"):
        make_app(cfg).create_landmarker()
