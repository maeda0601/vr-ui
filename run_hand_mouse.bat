@echo off
chcp 932 > nul
cd /d "%~dp0"
title Hand Mouse

rem --- uv を探す（PATH に無ければ標準のインストール先を使う）---
set "UV=uv"
where uv > nul 2>&1
if errorlevel 1 (
    if exist "%USERPROFILE%\.local\bin\uv.exe" (
        set "UV=%USERPROFILE%\.local\bin\uv.exe"
    ) else if exist "%LOCALAPPDATA%\Programs\uv\uv.exe" (
        set "UV=%LOCALAPPDATA%\Programs\uv\uv.exe"
    ) else (
        echo uv が見つかりません。次のどちらかでインストールしてください。
        echo   pip install uv
        echo   powershell -c "irm https://astral.sh/uv/install.ps1 ^| iex"
        pause
        exit /b 1
    )
)

rem --- 初回: 仮想環境の作成 ---
if not exist ".venv\Scripts\python.exe" (
    echo 初回セットアップ: 依存パッケージを導入しています...
    "%UV%" sync
    if errorlevel 1 (
        echo 依存パッケージの導入に失敗しました。
        pause
        exit /b 1
    )
)

rem --- 初回: 検出モデルの取得 ---
if not exist "models\hand_landmarker.task" (
    echo 初回セットアップ: 検出モデルを取得しています...
    "%UV%" run scripts\download_model.py
    if errorlevel 1 (
        echo モデルの取得に失敗しました。
        pause
        exit /b 1
    )
)

rem --- 起動（引数はそのまま渡す。例: run_hand_mouse.bat --display preview）---
"%UV%" run scripts\hand_mouse.py %*
if errorlevel 1 (
    echo.
    echo 異常終了しました。上のメッセージを確認してください。
    pause
)
