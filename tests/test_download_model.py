# -*- coding: utf-8 -*-
"""検出モデルの取得（download_model）のテスト。ネットワークには接続しない。"""

import shutil
from pathlib import Path

import pytest

import download_model as D

# 本物のモデルファイルの場所（テスト中は D.DEST を一時フォルダへ向けるので、先に控えておく）
REAL_MODEL = D.DEST


@pytest.fixture
def good_model(tmp_path):
    """正しいモデルファイルの写し（手元に標準のモデルがあるときだけ）。"""
    if D.check_model(REAL_MODEL) is not None:
        pytest.skip("標準のモデルファイルが無い（uv run scripts/download_model.py で取得）")
    path = tmp_path / "good.task"
    shutil.copy(REAL_MODEL, path)
    return path


@pytest.fixture
def dest(monkeypatch, tmp_path):
    """保存先を一時フォルダに向ける（本物のモデルファイルには触らない）。"""
    path = tmp_path / "models" / "hand_landmarker.task"
    monkeypatch.setattr(D, "DEST", path)
    return path


def fake_download(monkeypatch, action):
    monkeypatch.setattr(D.urllib.request, "urlretrieve", action)


def test_check_model_accepts_the_real_file(good_model):
    assert D.check_model(good_model) is None


def test_check_model_rejects_truncated_file(good_model, tmp_path):
    cut = tmp_path / "cut.task"
    cut.write_bytes(good_model.read_bytes()[:3_000_000])
    assert "大きさ" in D.check_model(cut)


def test_check_model_rejects_one_byte_difference(good_model, tmp_path):
    data = bytearray(good_model.read_bytes())
    data[100] ^= 0xFF
    other = tmp_path / "other.task"
    other.write_bytes(bytes(data))
    assert "一致しません" in D.check_model(other)


def test_interrupted_download_leaves_nothing(monkeypatch, dest):
    def interrupted(url, path):
        Path(path).write_bytes(b"x" * 1000)
        raise OSError("接続が切れました（模擬）")

    fake_download(monkeypatch, interrupted)
    assert D.main() == 1
    assert not dest.exists()
    assert list(dest.parent.glob("*")) == []        # 一時ファイルも残さない


def test_wrong_content_is_not_saved(monkeypatch, dest):
    """プロキシのログイン画面などを受け取っても、モデルとして保存しない。"""
    fake_download(monkeypatch, lambda url, path: Path(path).write_bytes(b"<html>login</html>"))
    assert D.main() == 1
    assert list(dest.parent.glob("*")) == []


def test_broken_existing_file_is_downloaded_again(monkeypatch, dest, good_model):
    dest.parent.mkdir(parents=True)
    dest.write_bytes(good_model.read_bytes()[:3_000_000])
    fake_download(monkeypatch, lambda url, path: shutil.copy(good_model, path))
    assert D.main() == 0
    assert D.check_model(dest) is None


def test_good_existing_file_is_not_downloaded(monkeypatch, dest, good_model):
    dest.parent.mkdir(parents=True)
    shutil.copy(good_model, dest)

    def must_not_download(url, path):
        raise AssertionError("正しいファイルがあるのにダウンロードした")

    fake_download(monkeypatch, must_not_download)
    assert D.main() == 0
